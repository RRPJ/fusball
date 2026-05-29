"""Phone API and mobile leaderboard page.

This module provides a small Flask app that reads the existing shelve-backed
player database and exposes:
- JSON API for leaderboard data
- Mobile-friendly HTML leaderboard view
- Minimal authenticated finished-match submission
"""

from __future__ import annotations

import argparse
import os
import random
import re
import time
from pathlib import Path
from string import capwords

from flask import Flask, jsonify, redirect, request
from werkzeug.security import check_password_hash

from odds import playerLevel
import trueskill as _trueskill
from services.match_service import best_balanced_lineup, odds_ratio_for_teams
from services.phone_write_store import BaseWriteStore, WriteStoreConfig, create_write_store
from services.player_store import rank_labels_by_name, ranked_players


ROOT_DIR = Path(__file__).resolve().parent
WRITE_LOCK_NAME = "phone_api_write.lock"
OPERATOR_TOKEN_HEADER = "X-Operator-Token"
READ_PIN_HEADER = "X-Read-Pin"
WRITE_PIN_HEADER = "X-Write-Pin"
MATCH_DUPLICATE_WINDOW_SECONDS = 60.0
_RECENT_MATCH_SIGNATURES: dict[str, float] = {}


def _load_leaderboard(store: BaseWriteStore, limit: int = 50, scope: str = "all") -> list[dict[str, object]]:
  ratings = store.leaderboard_ratings(scope)
  if not ratings:
    return []

  ranked = ranked_players(ratings.items())
  labels = rank_labels_by_name(ranked)

  rows = []
  for index, (name, rating) in enumerate(ranked[:limit], start=1):
    rows.append(
      {
        "position": index,
        "name": capwords(name),
        "rank": labels[name],
        "level": round(playerLevel(rating), 2),
        "offense_level": round(_trueskill.expose(rating[0]), 2),
        "defense_level": round(_trueskill.expose(rating[1]), 2),
        "offense_mu": round(rating[0].mu, 2),
        "offense_sigma": round(rating[0].sigma, 2),
        "defense_mu": round(rating[1].mu, 2),
        "defense_sigma": round(rating[1].sigma, 2),
      }
    )
  return rows


def _match_signature(team1: list[str], team2: list[str], score1: int, score2: int) -> str:
    return f"{','.join(team1)}|{','.join(team2)}|{score1}|{score2}"


def _is_recent_duplicate(signature: str, now_monotonic: float) -> bool:
    expiry = now_monotonic - MATCH_DUPLICATE_WINDOW_SECONDS
    stale = [sig for sig, ts in _RECENT_MATCH_SIGNATURES.items() if ts < expiry]
    for sig in stale:
        del _RECENT_MATCH_SIGNATURES[sig]
    return signature in _RECENT_MATCH_SIGNATURES


def _remember_match_signature(signature: str, now_monotonic: float) -> None:
    _RECENT_MATCH_SIGNATURES[signature] = now_monotonic


def _default_selected_slots() -> dict[str, str | None]:
    return {
        "red_offense": None,
        "red_defense": None,
        "blue_offense": None,
        "blue_defense": None,
    }


def _required_slots_for_mode(mode: str) -> list[str]:
    if mode == "doubles":
        return ["red_defense", "red_offense", "blue_defense", "blue_offense"]
    if mode == "singles":
        return ["red_offense", "blue_offense"]
    raise ValueError("mode must be 'singles' or 'doubles'")


def _lineup_from_active_players(active_players: set[str], mode: str) -> dict[str, str | None]:
    required_slots = _required_slots_for_mode(mode)
    if len(active_players) < len(required_slots):
        raise ValueError(f"need at least {len(required_slots)} active players for {mode}")

    picked = random.sample(sorted(active_players), len(required_slots))
    selected = _default_selected_slots()
    for index, slot in enumerate(required_slots):
        selected[slot] = picked[index]
    return selected


def _validate_auto_payload(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")

    mode = payload.get("mode")
    if mode != "doubles":
        raise ValueError("auto lineup is only available for doubles")

    selected_raw = payload.get("selected")
    if not isinstance(selected_raw, dict):
        raise ValueError("selected must be an object")

    slots = ["red_defense", "red_offense", "blue_defense", "blue_offense"]
    selected: dict[str, str] = {}
    for slot in slots:
        value = selected_raw.get(slot)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("auto lineup requires all four selected players")
        selected[slot] = _normalize_player_name(value)

    if len(set(selected.values())) != 4:
        raise ValueError("auto lineup requires four unique players")

    return selected


def _normalize_player_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("player names must be strings")
    name = value.strip().lower()
    if not name:
        raise ValueError("player names must be non-empty")
    return name


def _validate_finished_score(score1: object, score2: object) -> tuple[int, int]:
    if not isinstance(score1, int) or not isinstance(score2, int):
        raise ValueError("scores must be integers")
    if score1 < 0 or score2 < 0:
        raise ValueError("scores must be non-negative")
    if max(score1, score2) != 5 or min(score1, score2) == 5:
        raise ValueError("only finished foosball results are accepted")
    return score1, score2


def _validate_match_payload(store: BaseWriteStore, payload: object) -> tuple[list[str], list[str], int, int]:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")

    team1_raw = payload.get("team1")
    team2_raw = payload.get("team2")
    if not isinstance(team1_raw, list) or not isinstance(team2_raw, list):
        raise ValueError("team1 and team2 must be arrays")

    team1 = [_normalize_player_name(name) for name in team1_raw]
    team2 = [_normalize_player_name(name) for name in team2_raw]

    if len(team1) == 0 or len(team1) > 2 or len(team1) != len(team2):
        raise ValueError("only balanced singles or doubles matches are accepted")

    all_players = team1 + team2
    if len(set(all_players)) != len(all_players):
        raise ValueError("a player may only appear once in a submitted match")

    score1, score2 = _validate_finished_score(payload.get("score1"), payload.get("score2"))

    missing = store.missing_players(all_players)
    if missing:
        raise ValueError("all submitted players must already exist")

    return team1, team2, score1, score2


def _validate_new_player_name(payload: object) -> str:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")

    name = _normalize_player_name(payload.get("name"))
    if len(name) < 2 or len(name) > 30:
        raise ValueError("player name must be 2-30 characters")
    if not re.fullmatch(r"[a-z][a-z\- ]+[a-z]", name):
        raise ValueError("player name may contain only letters, spaces, and hyphens")
    return name


def _write_lock_path(db_dir: Path) -> Path:
    return db_dir / WRITE_LOCK_NAME


def _acquire_write_lock(db_dir: Path, owner: str) -> bool:
    lock_path = _write_lock_path(db_dir)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False

    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(owner)
    return True


def _release_write_lock(db_dir: Path) -> None:
    _write_lock_path(db_dir).unlink(missing_ok=True)


def _verify_secret(secret_hash: str | None, provided_secret: str | None) -> bool:
  if not secret_hash or not provided_secret:
    return False
  try:
    return check_password_hash(secret_hash, provided_secret)
  except Exception:
    return False


def _render_phone_html(rows: list[dict[str, object]]) -> str:
    table_rows = "\n".join(
        (
            "<tr>"
            f"<td>{row['position']}</td>"
            f"<td><div>{row['name']}</div><div class='sub'>Off&nbsp;{row['offense_level']} &middot; Def&nbsp;{row['defense_level']}</div></td>"
            f"<td>{row['level']}</td>"
            "</tr>"
        )
        for row in rows
    )

    if not table_rows:
        table_rows = "<tr><td colspan='3'>No players found.</td></tr>"

    html = """<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8' />
  <meta name='viewport' content='width=device-width, initial-scale=1' />
  <title>Fusball Phone API</title>
  <style>
    :root {
      --bg: #0b1721;
      --bg-2: #122535;
      --accent: #ef8a17;
      --text: #e7eef4;
      --muted: #9fb3c4;
      --panel: rgba(14, 34, 49, 0.95);
      --line: rgba(159, 179, 196, 0.28);
      --ok: #2aa675;
      --bad: #b45151;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Trebuchet MS", sans-serif;
      background:
        radial-gradient(1200px 480px at 10% -10%, #1f4c6c 0%, transparent 70%),
        radial-gradient(800px 500px at 100% 0%, #253f59 0%, transparent 65%),
        linear-gradient(165deg, var(--bg), var(--bg-2));
      color: var(--text);
      min-height: 100vh;
      padding: 12px;
      padding-bottom: 106px;
    }
    .panel {
      width: min(760px, 100%);
      margin: 0 auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 12px 36px rgba(0, 0, 0, 0.35);
    }
    header {
      padding: 14px 14px 8px;
      border-bottom: 1px solid var(--line);
    }
    h1 {
      margin: 0;
      font-size: 1.03rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--accent);
    }
    .muted { color: var(--muted); font-size: 0.82rem; }
    .progress {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
      margin-top: 8px;
    }
    .progress button {
      border: 1px solid var(--line);
      background: rgba(15, 38, 56, 0.9);
      color: var(--muted);
      border-radius: 8px;
      font-size: 0.74rem;
      padding: 7px 6px;
    }
    .progress button.active {
      border-color: var(--accent);
      color: var(--accent);
    }
    .section { display: none; padding: 14px; border-bottom: 1px solid var(--line); }
    .section.active { display: block; }
    .section h2 {
      margin: 0 0 10px;
      font-size: 0.88rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .row { display: flex; gap: 8px; flex-wrap: wrap; }
    .btn {
      border: 1px solid var(--line);
      background: rgba(15, 38, 56, 0.95);
      color: var(--text);
      border-radius: 10px;
      padding: 11px 12px;
      font-size: 0.9rem;
      cursor: pointer;
      min-height: 44px;
    }
    .btn.small { padding: 8px 10px; font-size: 0.82rem; }
    .btn.active { border-color: var(--accent); color: var(--accent); }
    .btn.score { padding: 10px 14px; font-size: 1rem; min-height: 48px; }
    .btn.score.red-team { border-color: rgba(180, 60, 60, 0.55); }
    .btn.score.blue-team { border-color: rgba(60, 100, 180, 0.55); }
    .btn.score.red-team.active { background: #b43c3c; border-color: #b43c3c; color: #fff; font-weight: 700; }
    .btn.score.blue-team.active { background: #3c64b4; border-color: #3c64b4; color: #fff; font-weight: 700; }
    .btn.primary { background: #ef8a17; border-color: #ef8a17; color: #0b1721; font-weight: 700; }
    .btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .slot { min-width: 144px; text-align: left; }
    .slot .label { display: block; color: var(--muted); font-size: 0.7rem; text-transform: uppercase; }
    .slot .value { display: block; margin-top: 4px; font-weight: 600; }
    .token {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: rgba(15, 38, 56, 0.95);
      color: var(--text);
      padding: 11px 12px;
      font-size: 0.9rem;
    }
    .players {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      max-height: 260px;
      overflow: auto;
      padding-right: 4px;
      align-content: start;
    }
    @media (min-width: 560px) {
      .players {
        grid-template-columns: repeat(auto-fit, minmax(156px, 1fr));
      }
    }
    .players .muted { grid-column: 1 / -1; }
    .presence-list { width: 100%; margin-top: 8px; }
    .presence-list + .presence-list { margin-top: 12px; }
    .presence-list h3 {
      margin: 0 0 6px;
      font-size: 0.73rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }
    .player-item { min-width: 0; display: grid; gap: 6px; }
    .player-item.present-row { grid-template-columns: minmax(0, 1fr) 38px; align-items: stretch; }
    .player-item .btn {
      width: 100%;
      min-width: 0;
      text-align: left;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .player-item .btn.present-player { border-color: rgba(42, 166, 117, 0.45); }
    .player-item .btn.away-player { opacity: 0.72; }
    .player-item .btn.demote {
      width: 38px;
      text-align: center;
      padding: 8px 0;
      border-color: rgba(180, 81, 81, 0.45);
      color: #ffd4d4;
      font-weight: 700;
    }
    .btn.present { border-color: var(--ok); color: var(--ok); }
    .btn.assign-off { opacity: 0.55; }
    .score-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 10px; align-items: center; }
    .status { margin-top: 8px; font-size: 0.84rem; min-height: 18px; color: var(--muted); }
    .status.ok { color: var(--ok); }
    .status.bad { color: var(--bad); }
    .live-status {
      margin-top: 10px;
      display: grid;
      gap: 6px;
    }
    .live-status-row {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
    }
    .status-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 8px;
      border-radius: 999px;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      border: 1px solid var(--line);
      color: var(--muted);
      background: rgba(159, 179, 196, 0.08);
    }
    .status-chip::before {
      content: '';
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: currentColor;
      box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.06);
    }
    .status-chip.ok {
      color: var(--ok);
      border-color: rgba(42, 166, 117, 0.45);
      background: rgba(42, 166, 117, 0.12);
    }
    .status-chip.bad {
      color: #ffd4d4;
      border-color: rgba(180, 81, 81, 0.75);
      background: rgba(180, 81, 81, 0.2);
    }
    .status-chip.fetching {
      color: var(--accent);
      border-color: rgba(239, 138, 23, 0.55);
      background: rgba(239, 138, 23, 0.14);
    }
    .review-card {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px;
      background: rgba(15, 38, 56, 0.85);
    }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 10px 8px; text-align: left; border-bottom: 1px solid var(--line); }
    th { font-size: 0.73rem; text-transform: uppercase; color: var(--muted); }
    td { font-size: 0.9rem; }
    td:first-child { width: 48px; color: var(--accent); font-weight: 700; }
    .sub { font-size: 0.72rem; color: var(--muted); margin-top: 3px; }
    .sticky {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(8, 20, 30, 0.97);
      border-top: 1px solid var(--line);
      padding: 10px 12px;
      z-index: 5;
    }
    .sticky-wrap { width: min(760px, 100%); margin: 0 auto; }
    .summary { font-size: 0.8rem; color: var(--muted); margin-bottom: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .sort-row { margin: 8px 0 10px; }
    .btn.sort { padding: 6px 10px; font-size: 0.78rem; min-height: 34px; }
    .add-player { margin: 10px 0 0; }
    .add-player .token { margin-top: 0; }
    .badge { display:inline-block; font-size:0.7rem; padding:2px 6px; border-radius:5px; font-weight:700; margin-left:6px; text-transform:uppercase; letter-spacing:0.04em; vertical-align:middle; }
    .badge-ok { background:rgba(42,166,117,0.15); color:var(--ok); border:1px solid var(--ok); }
    .badge-accent { background:rgba(239,138,23,0.15); color:var(--accent); border:1px solid var(--accent); }
    .badge-bad { background:rgba(180,81,81,0.15); color:var(--bad); border:1px solid var(--bad); }
    .badge-muted { background:rgba(159,179,196,0.08); color:var(--muted); border:1px solid var(--line); }
    .h2h-card { margin-top:8px; display:none; }
    .h2h-card.open { display:block; }
    .h2h-grid { display:grid; gap:8px; }
    .h2h-pair { border:1px solid var(--line); border-radius:8px; padding:8px; background:rgba(15,38,56,0.5); }
    .profile-panel { display:grid; gap:10px; }
    .profile-header { display:flex; justify-content:space-between; gap:10px; align-items:flex-start; flex-wrap:wrap; }
    .profile-title { font-size:0.95rem; font-weight:700; color:#f7fbff; }
    .profile-meta { font-size:0.74rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.04em; }
    .profile-cards { display:grid; gap:8px; grid-template-columns:repeat(auto-fit, minmax(120px, 1fr)); }
    .profile-card { border:1px solid var(--line); border-radius:8px; padding:8px; background:rgba(15,38,56,0.55); }
    .profile-card .label { font-size:0.68rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.05em; }
    .profile-card .value { margin-top:4px; font-size:0.88rem; color:#f7fbff; font-weight:700; }
    .profile-card .subvalue { margin-top:3px; font-size:0.74rem; color:var(--muted); }
    .trend-row { display:grid; gap:8px; grid-template-columns:repeat(2, minmax(0, 1fr)); }
    .trend-pill { border:1px solid var(--line); border-radius:8px; padding:8px; background:rgba(15,38,56,0.55); }
    .profile-actions { display:flex; gap:8px; flex-wrap:wrap; }
    .recent-match { border-top:1px solid rgba(159, 179, 196, 0.12); padding-top:8px; margin-top:8px; }
    .recent-match:first-child { border-top:0; padding-top:0; margin-top:0; }
    .form-w { color:var(--ok); font-weight:700; }
    .form-l { color:var(--bad); }
    .expand-panel { padding:10px 8px; background:rgba(8,20,30,0.85); border-top:1px solid var(--line); font-size:0.82rem; color:var(--muted); }
    .expand-panel .delta-pos { color:var(--ok); }
    .expand-panel .delta-neg { color:var(--bad); }
    .expand-panel .kv { margin-bottom:4px; }
    .lrow { cursor:pointer; }
    .lrow:active td { background:rgba(239,138,23,0.06); }
    .filter-row { margin: 0 0 8px; }
    .offline-banner {
      margin-top: 10px;
      padding: 10px;
      border: 1px solid var(--bad);
      border-radius: 10px;
      background: rgba(180, 81, 81, 0.12);
      color: #ffd4d4;
      font-size: 0.83rem;
    }
    body.offline section[id^='step'] { display: none !important; }
    body.offline .sticky { display: none; }
    .review-score { font-size: 1.05rem; font-weight: 700; color: var(--accent); margin-top: 6px; }
    .review-quip { margin-top: 8px; color: var(--accent); font-weight: 600; }
  </style>
</head>
<body>
  <main class='panel'>
    <header>
      <h1>Fusball Phone API</h1>
      <div class='muted'>Button-driven setup, score, confirm, submit</div>
      <div id='offlineBanner' class='offline-banner' style='display:none;'>API offline. Showing leaderboard snapshot only.</div>
      <div id='liveStatusCard' class='live-status review-card' aria-live='polite'>
        <div class='live-status-row'>
          <span id='liveStatusChip' class='status-chip'>Checking connection</span>
          <span id='liveStatusAge' class='muted'>Waiting for first refresh.</span>
        </div>
        <div id='liveStatusDetail' class='muted'>The page will show whether data is live, fetching, or using a cached snapshot.</div>
      </div>
      <div class='progress'>
          <button id='stepBtn1' type='button' class='active'>Mode</button>
          <button id='stepBtn2' type='button'>Players</button>
          <button id='stepBtn3' type='button'>Score</button>
          <button id='stepBtn4' type='button'>Confirm</button>
      </div>
    </header>

    <section id='step1' class='section active'>
      <h2>Step 1: Match Mode</h2>
      <div class='row'>
        <button id='modeSingles' class='btn active' type='button'>Singles</button>
        <button id='modeDoubles' class='btn' type='button'>Doubles</button>
      </div>
      <div class='muted' style='margin-top:10px;'>In singles, offense slots are used. In doubles, all four slots are required.</div>
    </section>

    <section id='step2' class='section'>
      <h2>Step 2: Players And Positions</h2>
      <div class='row' style='margin-bottom:8px;'>
        <button id='slotRedDef' class='btn slot' type='button'><span class='label'>Red Defense</span><span id='valRedDef' class='value'>Optional in singles</span></button>
        <button id='slotRedOff' class='btn slot active' type='button'><span class='label'>Red Offense</span><span id='valRedOff' class='value'>Tap a player</span></button>
        <button id='slotBlueDef' class='btn slot' type='button'><span class='label'>Blue Defense</span><span id='valBlueDef' class='value'>Optional in singles</span></button>
        <button id='slotBlueOff' class='btn slot' type='button'><span class='label'>Blue Offense</span><span id='valBlueOff' class='value'>Tap a player</span></button>
      </div>
      <div class='row' style='margin-bottom:10px;'>
        <button id='swapSidesBtn' class='btn small' type='button'>Swap Sides</button>
        <button id='swapRedBtn' class='btn small' type='button'>Swap Red</button>
        <button id='swapBlueBtn' class='btn small' type='button'>Swap Blue</button>
        <button id='randomBtn' class='btn small' type='button'>Random</button>
        <button id='autoBtn' class='btn small' type='button'>Auto</button>
        <button id='undoBtn' class='btn small' type='button'>Undo Last Pick</button>
        <button id='clearBtn' class='btn small' type='button'>Clear</button>
      </div>
      <div id='oddsText' class='status' style='margin-top:2px;'></div>
      <div id='presenceStatus' class='status'>No active players selected.</div>
      <div class='presence-list'>
        <h3 id='presentPlayersHeading'>Present Players (tap to assign)</h3>
        <div id='presentPlayersPanel' class='players'></div>
      </div>
      <div id='awayListWrap' class='presence-list'>
        <h3 id='awayPlayersHeading'>Away Players (tap to mark present)</h3>
        <div id='awayPlayersPanel' class='players'></div>
      </div>
      <div id='h2hToggleRow' class='row' style='margin-top:6px;display:none;'>
        <button id='h2hToggleBtn' class='btn small' type='button' onclick='toggleH2H()'>H2H &#9660;</button>
      </div>
      <div id='h2hCard' class='h2h-card review-card'></div>
    </section>

    <section id='step3' class='section'>
      <h2>Step 3: Final Score</h2>
      <div class='score-grid'>
        <div id='redScoreLabel' class='muted'>Red</div>
        <div id='blueScoreLabel' class='muted'>Blue</div>
        <div id='scoreRed' class='row'></div>
        <div id='scoreBlue' class='row'></div>
      </div>
      <div id='scoreHint' class='muted' style='margin-top:10px;'></div>
      <div id='statusText' class='status'></div>
    </section>

    <section id='step4' class='section'>
      <h2>Step 4: Confirm And Submit</h2>
      <div class='review-card' id='reviewText'>Complete setup to review match.</div>
      <div style='margin-top:10px;'>
        <input id='readPin' class='token' type='password' placeholder='Read PIN (optional if using writer PIN only)' />
      </div>
      <div style='margin-top:8px;'>
        <input id='writePin' class='token' type='password' placeholder='Writer PIN (required for writes)' />
      </div>
      <div class='muted' style='margin-top:8px;'>PINs are remembered for this tab session. Submit is enabled only when lineup and score are valid.</div>
    </section>

    <section id='leaderboardSection' class='section active'>
      <h2>Leaderboard</h2>
      <div id='leaderboardFreshness' class='muted'>Live standings refresh after successful submit and when you change filters.</div>
      <div class='row sort-row'>
        <button id='sortTotalBtn' class='btn sort active' type='button'>Total</button>
        <button id='sortAtkBtn' class='btn sort' type='button'>Offense</button>
        <button id='sortDefBtn' class='btn sort' type='button'>Defense</button>
        <button id='sortFormBtn' class='btn sort' type='button'>Form</button>
        <button id='sortStreakBtn' class='btn sort' type='button'>Streak</button>
        <button id='sortImprovedBtn' class='btn sort' type='button'>Improved</button>
      </div>
      <div class='row filter-row'>
        <button id='filterAllBtn' class='btn sort active' type='button'>All</button>
        <button id='filterThisQuarterBtn' class='btn sort' type='button'>This quarter</button>
        <button id='filterThisMonthBtn' class='btn sort' type='button'>This month</button>
        <button id='filterThisWeekBtn' class='btn sort' type='button'>This week</button>
      </div>
      <div id='metricHint' class='muted'></div>
      <table aria-label='Leaderboard'>
        <thead>
          <tr><th>#</th><th>Player</th><th id='lbMetricHeader'>Total</th></tr>
        </thead>
        <tbody id='leaderboardBody'>__TABLE_ROWS__</tbody>
      </table>
      <div class='add-player'>
        <div class='muted'>Add player</div>
        <div class='row' style='margin-top:6px;'>
          <input id='newPlayerName' class='token' type='text' placeholder='New player name' maxlength='30' />
          <button id='addPlayerBtn' class='btn small' type='button'>Add Player</button>
        </div>
        <div id='addPlayerStatus' class='status'></div>
      </div>
    </section>
  </main>

  <div class='sticky'>
    <div class='sticky-wrap'>
      <div id='summaryText' class='summary'>No lineup selected.</div>
      <div class='row'>
        <button id='backBtn' class='btn small' type='button'>Back</button>
        <button id='nextBtn' class='btn primary' type='button'>Next</button>
        <button id='submitBtn' class='btn primary' type='button' style='display:none;'>Submit Result</button>
      </div>
    </div>
  </div>

  <script>
    const slots = ['red_offense', 'red_defense', 'blue_offense', 'blue_defense'];
    const stepButtons = [null, document.getElementById('stepBtn1'), document.getElementById('stepBtn2'), document.getElementById('stepBtn3'), document.getElementById('stepBtn4')];
    const stepSections = [null, document.getElementById('step1'), document.getElementById('step2'), document.getElementById('step3'), document.getElementById('step4')];
    const leaderboardSection = document.getElementById('leaderboardSection');
    const slotToElement = {
      red_offense: document.getElementById('slotRedOff'),
      red_defense: document.getElementById('slotRedDef'),
      blue_offense: document.getElementById('slotBlueOff'),
      blue_defense: document.getElementById('slotBlueDef'),
    };
    const slotToValue = {
      red_offense: document.getElementById('valRedOff'),
      red_defense: document.getElementById('valRedDef'),
      blue_offense: document.getElementById('valBlueOff'),
      blue_defense: document.getElementById('valBlueDef'),
    };

    const state = {
      bootedAt: Date.now(),
      step: 1,
      mode: 'singles',
      activeSlot: 'red_offense',
      leaderboardSort: 'total',
      leaderboardFilter: 'all',
      leaderboardItems: [],
      playerStats: null,
      playerStatsScope: null,
      expandedPlayer: null,
      h2hOpen: false,
      isSubmitting: false,
      offline: false,
      readPinPromptPromise: null,
      healthTimerId: null,
      freshnessTimerId: null,
      inFlightGetControllers: new Set(),
      requestState: {},
      leaderboardSource: 'server',
      leaderboardCacheAt: null,
      leaderboardRequestVersion: 0,
      statsRequestVersion: 0,
      lastOnlineAt: null,
      lastOfflineAt: null,
      offlineReason: '',
      players: [],
      activePlayers: [],
      latestOdds: null,
      currentQuipKey: null,
      currentQuipText: null,
      currentQuipCategory: null,
      lastQuipIndexByCategory: {},
      selectionHistory: [],
      selected: {
        red_offense: null,
        red_defense: null,
        blue_offense: null,
        blue_defense: null,
      },
      score1: null,
      score2: null,
    };

    const READ_PIN_STORAGE_KEY = 'fusball_read_pin';
    const WRITE_PIN_STORAGE_KEY = 'fusball_write_pin';
    const LEGACY_TOKEN_STORAGE_KEY = 'fusball_token';
  const LEADERBOARD_CACHE_STORAGE_KEY = 'fusball_leaderboard_snapshot';

    const QUIPS_BY_CATEGORY = {
      expected_blowout: [
        'Called it. That one came with a warranty.',
        'Spreadsheet said easy and spreadsheet never lies.',
        'Pre-match forecast: pain. Outcome: accurate.',
        'That was not a match, that was a tutorial.',
        'Odds said cruise control and you set autopilot.',
        'Big favorite energy, fully delivered.',
        'You promised fireworks and brought a flamethrower.',
        'That scoreline was signed in advance.',
        'Expected business completed with zero drama.',
        'They queued confidence and shipped dominance.',
      ],
      expected_close_win: [
        'Favorite got the job done, just with extra paperwork.',
        'Predicted edge, sweaty execution.',
        'You won, but the stress meter also won.',
        'Expected W, unexpected cardio session.',
        'Victory arrived exactly on schedule, barely.',
        'That was a controlled burn, mostly controlled.',
        'Odds were right by a hairline margin.',
        'Close call, clean brag rights.',
        'You edged it. Style points pending review.',
        'Win confirmed, blood pressure not confirmed.',
      ],
      upset_win: [
        'Underdog just sent the rankings a breakup text.',
        'Prediction model is filing a formal complaint.',
        'That was theft in broad daylight and on camera.',
        'Upset served hot and with extra spice.',
        'You ignored the odds and wrote your own patch notes.',
        'Favorite status revoked effective immediately.',
        'That scoreboard just heckled the pre-game math.',
        'Underdog mode activated, chaos mode completed.',
        'The script was wrong and you made sure it knew.',
        'Odds got cooked and plated.',
      ],
      nail_biter: [
        'One ball either way and history changes.',
        'That finish was held together by nerves and denial.',
        'Clutch meter just exploded.',
        'Photo finish energy. No survivors.',
        'That was not clean, but it was legendary.',
        'Five-four: the universal language of panic.',
        'Everyone lost years off their lifespan there.',
        'You did not win calmly and that is okay.',
        'Last-ball drama sponsored by pure stubbornness.',
        'Nail-biter certified. Hands still shaking.',
      ],
      total_stomp: [
        'Mercy rule vibes without the mercy.',
        'That scoreline should come with parental guidance.',
        'Clean sweep, zero crumbs left.',
        'You speedran that lobby.',
        'They queued for a game and got a lecture instead.',
        'That was domination with subtitles.',
        'No comeback arc, only credits.',
        'Brutal efficiency and a tiny bit of disrespect.',
        'One side played foosball, the other took notes.',
        'That was an uninstall-level result.',
      ],
      even_match_outcome: [
        'Even odds, uneven confidence by the end.',
        'Coin flip matchup, loaded dice finish.',
        'Fifty-fifty on paper, spicy in practice.',
        'Balanced start, unbalanced bragging rights.',
        'That matchup was level until somebody snapped.',
        'Perfectly even pre-game, perfectly loud post-game.',
        'Model said toss-up, table said throwdown.',
        'Equal ratings, unequal celebrations.',
        'That was parity with extra attitude.',
        'Even matchup resolved by pure audacity.',
      ],
    };

    function formatElapsed(startedAt) {
      if (!startedAt) {
        return '';
      }
      const elapsedMs = Math.max(1000, Date.now() - startedAt);
      if (elapsedMs < 60000) {
        return `${Math.ceil(elapsedMs / 1000)}s`;
      }
      if (elapsedMs < 3600000) {
        return `${Math.ceil(elapsedMs / 60000)}m`;
      }
      return `${Math.ceil(elapsedMs / 3600000)}h`;
    }

    function formatAge(timestampMs) {
      if (!timestampMs) {
        return 'unknown';
      }
      const ageMs = Math.max(0, Date.now() - timestampMs);
      if (ageMs < 60000) {
        return 'just now';
      }
      if (ageMs < 3600000) {
        return `${Math.floor(ageMs / 60000)}m ago`;
      }
      if (ageMs < 86400000) {
        return `${Math.floor(ageMs / 3600000)}h ago`;
      }
      return `${Math.floor(ageMs / 86400000)}d ago`;
    }

    function ensureRequestMeta(key) {
      if (!state.requestState[key]) {
        state.requestState[key] = {
          label: key,
          inFlightAt: null,
          lastSuccessAt: null,
          lastFailureAt: null,
          lastError: '',
        };
      }
      return state.requestState[key];
    }

    function renderOfflineBanner() {
      const banner = document.getElementById('offlineBanner');
      if (!banner) {
        return;
      }
      if (!state.offline) {
        banner.style.display = 'none';
        return;
      }
      banner.style.display = 'block';
      const cacheText = state.leaderboardCacheAt
        ? ` Cached leaderboard age: ${formatAge(state.leaderboardCacheAt)}.`
        : ' Cached leaderboard age is unknown.';
      banner.textContent = `${state.offlineReason || 'API offline.'} Showing leaderboard snapshot only.${cacheText}`;
    }

    function renderLeaderboardFreshness() {
      const node = document.getElementById('leaderboardFreshness');
      if (!node) {
        return;
      }
      const meta = ensureRequestMeta('leaderboard');
      const scopeLabel = state.leaderboardFilter === 'this_month'
        ? 'this month'
        : state.leaderboardFilter === 'this_quarter'
          ? 'this quarter'
        : state.leaderboardFilter === 'this_week'
          ? 'this week'
          : 'all-time';
      if (meta.inFlightAt) {
        node.textContent = `Fetching ${scopeLabel} standings... ${formatElapsed(meta.inFlightAt)} elapsed.`;
        return;
      }
      if (state.offline) {
        if (state.leaderboardCacheAt) {
          node.textContent = `Snapshot mode. Showing cached leaderboard from ${formatAge(state.leaderboardCacheAt)} until the API is reachable again.`;
        } else {
          node.textContent = 'Snapshot mode. No cache age is available yet.';
        }
        return;
      }
      if (meta.lastSuccessAt) {
        const sourceText = state.leaderboardSource === 'server' ? 'from page load' : 'from the live API';
        node.textContent = `Live standings. Updated ${formatAge(meta.lastSuccessAt)} ${sourceText}.`;
        return;
      }
      node.textContent = 'Waiting for the first live leaderboard refresh.';
    }

    function renderLiveStatus() {
      const chip = document.getElementById('liveStatusChip');
      const age = document.getElementById('liveStatusAge');
      const detail = document.getElementById('liveStatusDetail');
      if (!chip || !age || !detail) {
        return;
      }

      const activeRequests = Object.values(state.requestState).filter((meta) => meta.inFlightAt && meta.showInLiveStatus !== false);
      if (activeRequests.length) {
        const current = activeRequests.sort((left, right) => left.inFlightAt - right.inFlightAt)[0];
        const extraCount = activeRequests.length - 1;
        chip.textContent = `Fetching ${current.label}${extraCount > 0 ? ` +${extraCount}` : ''}`;
        chip.className = 'status-chip fetching';
        age.textContent = `In progress for ${formatElapsed(current.inFlightAt)}.`;
        detail.textContent = 'Requests are active. The page will stamp each panel when fresh data lands.';
        return;
      }

      if (state.offline) {
        chip.textContent = 'Snapshot mode';
        chip.className = 'status-chip bad';
        age.textContent = state.lastOfflineAt
          ? `Lost connection ${formatAge(state.lastOfflineAt)}.`
          : 'Connection unavailable.';
        detail.textContent = state.leaderboardCacheAt
          ? `Showing cached leaderboard from ${formatAge(state.leaderboardCacheAt)}. Match entry stays disabled while offline.`
          : 'Match entry stays disabled while offline. No cached leaderboard timestamp is available.';
        return;
      }

      const leaderboardMeta = ensureRequestMeta('leaderboard');
      const presenceMeta = ensureRequestMeta('presence');
      chip.textContent = 'Live';
      chip.className = 'status-chip ok';
      age.textContent = leaderboardMeta.lastSuccessAt
        ? `Leaderboard updated ${formatAge(leaderboardMeta.lastSuccessAt)}.`
        : 'Waiting for the first leaderboard refresh.';
      if (presenceMeta.lastSuccessAt) {
        detail.textContent = `Presence updated ${formatAge(presenceMeta.lastSuccessAt)}. Writes are available.`;
      } else if (state.lastOnlineAt) {
        detail.textContent = `Connection healthy since ${formatAge(state.lastOnlineAt)}. Waiting for active-player data.`;
      } else {
        detail.textContent = 'Connection healthy. Waiting for live data.';
      }
    }

    function beginTrackedRequest(key, label) {
      const meta = ensureRequestMeta(key);
      meta.label = label || meta.label;
      meta.inFlightAt = Date.now();
      meta.lastError = '';
      meta.showInLiveStatus = key !== 'players';
      renderPresenceStatus();
      renderOddsStatus();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function completeTrackedRequest(key) {
      const meta = ensureRequestMeta(key);
      meta.inFlightAt = null;
      meta.lastSuccessAt = Date.now();
      renderPresenceStatus();
      renderOddsStatus();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function failTrackedRequest(key, errorMessage) {
      const meta = ensureRequestMeta(key);
      meta.inFlightAt = null;
      meta.lastFailureAt = Date.now();
      meta.lastError = errorMessage || 'Request failed.';
      renderPresenceStatus();
      renderOddsStatus();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function startFreshnessTicker() {
      if (state.freshnessTimerId) {
        window.clearInterval(state.freshnessTimerId);
      }
      renderOfflineBanner();
      renderLeaderboardFreshness();
      renderLiveStatus();
      state.freshnessTimerId = window.setInterval(() => {
        renderOfflineBanner();
        renderLeaderboardFreshness();
        renderLiveStatus();
        renderPresenceStatus();
        renderOddsStatus();
      }, 1000);
    }

    function seedInitialFreshness() {
      const leaderboardMeta = ensureRequestMeta('leaderboard');
      leaderboardMeta.label = 'leaderboard';
      leaderboardMeta.lastSuccessAt = state.bootedAt;
      state.lastOnlineAt = state.bootedAt;
      renderOfflineBanner();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function setStatus(text, type = '') {
      const node = document.getElementById('statusText');
      if (!node) return;
      node.textContent = text;
      node.className = 'status' + (type ? ' ' + type : '');
    }

    function setAddPlayerStatus(text, type = '') {
      const node = document.getElementById('addPlayerStatus');
      node.textContent = text;
      node.className = 'status' + (type ? ' ' + type : '');
    }

    function cacheLeaderboard(items) {
      try {
        const payload = {
          items: items || [],
          cachedAt: new Date().toISOString(),
          scope: state.leaderboardFilter,
        };
        localStorage.setItem(LEADERBOARD_CACHE_STORAGE_KEY, JSON.stringify(payload));
        state.leaderboardCacheAt = Date.parse(payload.cachedAt);
      } catch {
        // Ignore storage failures on private mode/storage-restricted browsers.
      }
      renderOfflineBanner();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function readCachedLeaderboard() {
      try {
        const raw = localStorage.getItem(LEADERBOARD_CACHE_STORAGE_KEY);
        if (!raw) return { items: [], cachedAt: null, scope: null };
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          return { items: parsed, cachedAt: null, scope: null };
        }
        if (parsed && Array.isArray(parsed.items)) {
          return {
            items: parsed.items,
            cachedAt: parsed.cachedAt || null,
            scope: parsed.scope || null,
          };
        }
        return { items: [], cachedAt: null, scope: null };
      } catch {
        return { items: [], cachedAt: null, scope: null };
      }
    }

    function setOfflineMode(reason = 'API offline.') {
      if (state.offline) return;
      state.offline = true;
      state.offlineReason = reason;
      state.lastOfflineAt = Date.now();
      abortInFlightGets();
      document.body.classList.add('offline');
      leaderboardSection.classList.add('active');
      const cached = readCachedLeaderboard();
      if (cached.cachedAt) {
        state.leaderboardCacheAt = Date.parse(cached.cachedAt);
      }
      if (cached.items.length) {
        state.leaderboardSource = 'cache';
        renderLeaderboard(cached.items);
      }
      renderOfflineBanner();
      setStatus('API offline. Match entry is disabled.', 'bad');
      renderPresenceStatus();
      renderOddsStatus();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function clearOfflineMode() {
      state.lastOnlineAt = Date.now();
      if (!state.offline) {
        renderLiveStatus();
        return;
      }
      state.offline = false;
      state.offlineReason = '';
      document.body.classList.remove('offline');
      leaderboardSection.classList.toggle('active', state.step === 1);
      renderOfflineBanner();
      setStatus('API online again.', 'ok');
      renderPresenceStatus();
      renderOddsStatus();
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function abortInFlightGets() {
      for (const controller of state.inFlightGetControllers) {
        controller.abort();
      }
      state.inFlightGetControllers.clear();
    }

    function startHealthMonitor() {
      if (state.healthTimerId) {
        window.clearInterval(state.healthTimerId);
      }

      const check = async () => {
        try {
          const response = await apiFetch('/api/health', {
            allowOffline: true,
            timeoutMs: 1200,
          });
          if (response.ok) {
            clearOfflineMode();
            return;
          }
          setOfflineMode('API offline.');
        } catch {
          setOfflineMode('API offline.');
        }
      };

      check();
      state.healthTimerId = window.setInterval(check, 5000);
    }

    function getStoredReadPin() {
      return (sessionStorage.getItem(READ_PIN_STORAGE_KEY) || '').trim();
    }

    function getStoredWritePin() {
      return (sessionStorage.getItem(WRITE_PIN_STORAGE_KEY) || sessionStorage.getItem(LEGACY_TOKEN_STORAGE_KEY) || '').trim();
    }

    function persistReadPin(pin) {
      const value = (pin || '').trim();
      if (value) {
        sessionStorage.setItem(READ_PIN_STORAGE_KEY, value);
      } else {
        sessionStorage.removeItem(READ_PIN_STORAGE_KEY);
      }
    }

    function persistWritePin(pin) {
      const value = (pin || '').trim();
      if (value) {
        sessionStorage.setItem(WRITE_PIN_STORAGE_KEY, value);
        // Keep legacy key in sync for backward-compatible local runs.
        sessionStorage.setItem(LEGACY_TOKEN_STORAGE_KEY, value);
      } else {
        sessionStorage.removeItem(WRITE_PIN_STORAGE_KEY);
        sessionStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
      }
    }

    function setReadPinInputValue(pin) {
      const input = document.getElementById('readPin');
      if (input) {
        input.value = pin;
      }
    }

    function setWritePinInputValue(pin) {
      const input = document.getElementById('writePin');
      if (input) {
        input.value = pin;
      }
    }

    function clearStoredReadPin() {
      persistReadPin('');
      setReadPinInputValue('');
    }

    function clearStoredWritePin() {
      persistWritePin('');
      setWritePinInputValue('');
    }

    function promptForReadPin(promptMessage = 'Enter read PIN', forcePrompt = false) {
      if (state.readPinPromptPromise) {
        return state.readPinPromptPromise;
      }

      state.readPinPromptPromise = Promise.resolve().then(() => {
        const existing = getStoredReadPin();
        if (existing && !forcePrompt) {
          return existing;
        }

        const entered = (window.prompt(promptMessage) || '').trim();
        if (!entered) {
          return '';
        }
        persistReadPin(entered);
        setReadPinInputValue(entered);
        return entered;
      }).finally(() => {
        state.readPinPromptPromise = null;
      });

      return state.readPinPromptPromise;
    }

    function promptForWritePin(promptMessage = 'Enter writer PIN', forcePrompt = false) {
      let writePin = '';
      const input = document.getElementById('writePin');
      if (!forcePrompt && input) {
        writePin = (input.value || '').trim();
      }
      if (writePin) {
        persistWritePin(writePin);
        return writePin;
      }

      writePin = forcePrompt ? '' : getStoredWritePin();
      if (writePin) {
        setWritePinInputValue(writePin);
        return writePin;
      }

      const entered = (window.prompt(promptMessage) || '').trim();
      if (!entered) {
        return '';
      }
      persistWritePin(entered);
      setWritePinInputValue(entered);
      return entered;
    }

    function ensureWritePin() {
      return promptForWritePin('Enter writer PIN');
    }

    async function retryReadAuth(url, options, suppliedReadPin, suppliedWritePin) {
      if (suppliedReadPin) {
        clearStoredReadPin();
        const enteredReadPin = await promptForReadPin('Incorrect read PIN. Enter read PIN.', true);
        if (enteredReadPin) {
          return apiFetch(url, { ...options, __authRetry: true, __trackingActive: true });
        }
        return null;
      }

      if (suppliedWritePin) {
        clearStoredWritePin();
        const enteredWritePin = promptForWritePin('Incorrect writer PIN. Enter writer PIN.', true);
        if (enteredWritePin) {
          return apiFetch(url, { ...options, __authRetry: true, __trackingActive: true });
        }
        return null;
      }

      const enteredReadPin = await promptForReadPin('Enter read PIN', true);
      if (enteredReadPin) {
        return apiFetch(url, { ...options, __authRetry: true, __trackingActive: true });
      }
      return null;
    }

    function retryWriteAuth(url, options, suppliedWritePin) {
      const promptMessage = suppliedWritePin
        ? 'Incorrect writer PIN. Enter writer PIN.'
        : 'Enter writer PIN';
      if (suppliedWritePin) {
        clearStoredWritePin();
      }
      const enteredWritePin = promptForWritePin(promptMessage, true);
      if (enteredWritePin) {
        return apiFetch(url, { ...options, __authRetry: true, __trackingActive: true });
      }
      return null;
    }

    async function apiFetch(url, options = {}) {
      const method = (options.method || 'GET').toUpperCase();
      if (state.offline && !options.allowOffline) {
        throw new Error('API offline.');
      }

      const trackKey = options.trackKey || '';
      const startedTracking = !!trackKey && !options.__trackingActive;
      if (startedTracking) {
        beginTrackedRequest(trackKey, options.trackLabel || trackKey);
      }

      const headers = new Headers(options.headers || {});
      const readPin = getStoredReadPin();
      const writePin = getStoredWritePin();
      const suppliedReadPin = !!readPin;
      const suppliedWritePin = !!writePin;
      if (readPin) {
        headers.set('X-Read-Pin', readPin);
      }
      if (writePin) {
        headers.set('X-Write-Pin', writePin);
        headers.set('X-Operator-Token', writePin);
      }

      const timeoutMs = typeof options.timeoutMs === 'number'
        ? options.timeoutMs
        : (method === 'GET' ? 2200 : 5000);
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
      if (method === 'GET') {
        state.inFlightGetControllers.add(controller);
      }

      let trackOutcome = 'pending';

      try {
        const response = await fetch(url, {
          ...options,
          headers,
          signal: controller.signal,
          cache: method === 'GET' ? 'no-store' : options.cache,
        });
        const authRetry = !!options.__authRetry;
        if (!authRetry && response.status === 401 && method === 'GET' && !options.allowOffline) {
          const retried = await retryReadAuth(url, options, suppliedReadPin, suppliedWritePin);
          if (retried) {
            trackOutcome = 'success';
            return retried;
          }
        }
        if (!authRetry && (response.status === 401 || response.status === 403) && method !== 'GET') {
          const retried = retryWriteAuth(url, options, suppliedWritePin);
          if (retried) {
            trackOutcome = 'success';
            return await retried;
          }
        }
        if (response.status === 503) {
          setOfflineMode('API offline.');
        }
        trackOutcome = 'success';
        return response;
      } catch (error) {
        trackOutcome = 'error';
        if (startedTracking) {
          failTrackedRequest(trackKey, error && error.message ? error.message : 'Request failed.');
        }
        if (error && error.name === 'AbortError') {
          if (state.offline && !options.allowOffline) {
            throw new Error('API offline.');
          }
          throw new Error('Request timed out.');
        }
        setOfflineMode('API offline.');
        throw new Error('API offline.');
      } finally {
        window.clearTimeout(timeoutId);
        if (method === 'GET') {
          state.inFlightGetControllers.delete(controller);
        }
        if (startedTracking && trackOutcome === 'success') {
          completeTrackedRequest(trackKey);
        }
      }
    }

    function setMode(mode) {
      if (state.offline) {
        setStatus('API offline. Leaderboard cache only.', 'bad');
        return;
      }
      state.mode = mode;
      document.getElementById('modeSingles').classList.toggle('active', mode === 'singles');
      document.getElementById('modeDoubles').classList.toggle('active', mode === 'doubles');
      slotToElement.red_defense.style.opacity = mode === 'doubles' ? '1' : '0.6';
      slotToElement.blue_defense.style.opacity = mode === 'doubles' ? '1' : '0.6';
      if (mode === 'singles') {
        state.selected.red_defense = null;
        state.selected.blue_defense = null;
        if (state.activeSlot === 'red_defense' || state.activeSlot === 'blue_defense') {
          setActiveSlot('red_offense');
        }
      } else {
        setActiveSlot('red_defense');
      }
      document.getElementById('swapRedBtn').disabled = mode === 'singles';
      document.getElementById('swapBlueBtn').disabled = mode === 'singles';
      renderSlots();
      updateSummary();
      updateReview();
      refreshOdds();
      renderPresenceStatus();
    }

    function setActiveSlot(slot) {
      if (state.mode === 'singles' && (slot === 'red_defense' || slot === 'blue_defense')) {
        return;
      }
      state.activeSlot = slot;
      for (const name of slots) {
        slotToElement[name].classList.toggle('active', name === slot);
      }
    }

    function nextEmptySlot() {
      const order = state.mode === 'doubles'
        ? ['red_defense', 'red_offense', 'blue_defense', 'blue_offense']
        : ['red_offense', 'blue_offense'];
      const cur = order.indexOf(state.activeSlot);
      for (let i = cur + 1; i < order.length; i++) {
        if (!state.selected[order[i]]) return order[i];
      }
      for (let i = 0; i < cur; i++) {
        if (!state.selected[order[i]]) return order[i];
      }
      return null;
    }

    function assignPlayer(playerName) {
      if (!state.activePlayers.includes(playerName.toLowerCase())) {
        setStatus(playerName + ' is not marked active.', 'bad');
        return;
      }
      state.selectionHistory.push(JSON.stringify(state.selected));
      for (const slot of slots) {
        if (state.selected[slot] === playerName) {
          state.selected[slot] = null;
        }
      }
      state.selected[state.activeSlot] = playerName;
      renderSlots();
      updateSummary();
      updateReview();
      const next = nextEmptySlot();
      if (next) setActiveSlot(next);
      refreshOdds();
    }

    function undoLastPick() {
      const previous = state.selectionHistory.pop();
      if (!previous) {
        return;
      }
      state.selected = JSON.parse(previous);
      renderSlots();
      updateSummary();
      updateReview();
      refreshOdds();
    }

    function swapSides() {
      const next = {
        red_offense: state.selected.blue_offense,
        red_defense: state.selected.blue_defense,
        blue_offense: state.selected.red_offense,
        blue_defense: state.selected.red_defense,
      };
      state.selectionHistory.push(JSON.stringify(state.selected));
      state.selected = next;
      renderSlots();
      updateSummary();
      updateReview();
      refreshOdds();
    }

    function swapTeam(team) {
      state.selectionHistory.push(JSON.stringify(state.selected));
      const tmp = state.selected[`${team}_offense`];
      state.selected[`${team}_offense`] = state.selected[`${team}_defense`];
      state.selected[`${team}_defense`] = tmp;
      renderSlots();
      updateSummary();
      updateReview();
      refreshOdds();
    }

    function renderSlots() {
      slotToValue.red_offense.textContent = state.selected.red_offense || 'Tap a player';
      slotToValue.red_defense.textContent = state.selected.red_defense || (state.mode === 'doubles' ? 'Tap a player' : 'Optional in singles');
      slotToValue.blue_offense.textContent = state.selected.blue_offense || 'Tap a player';
      slotToValue.blue_defense.textContent = state.selected.blue_defense || (state.mode === 'doubles' ? 'Tap a player' : 'Optional in singles');
    }

    function renderPlayerButtons() {
      const presentPanel = document.getElementById('presentPlayersPanel');
      const awayPanel = document.getElementById('awayPlayersPanel');
      const presentHeading = document.getElementById('presentPlayersHeading');
      const awayHeading = document.getElementById('awayPlayersHeading');
      presentPanel.innerHTML = '';
      awayPanel.innerHTML = '';

      const presentNames = [];
      const awayNames = [];
      for (const name of state.players) {
        const key = name.toLowerCase();
        if (state.activePlayers.includes(key)) {
          presentNames.push(name);
        } else {
          awayNames.push(name);
        }
      }

      for (const name of presentNames) {
        const row = document.createElement('div');
        row.className = 'player-item present-row';
        const assignBtn = document.createElement('button');
        assignBtn.type = 'button';
        assignBtn.className = 'btn small present-player';
        assignBtn.textContent = name;
        assignBtn.addEventListener('click', () => assignPlayer(name));

        const demoteBtn = document.createElement('button');
        demoteBtn.type = 'button';
        demoteBtn.className = 'btn small demote';
        demoteBtn.textContent = '−';
        demoteBtn.title = `Mark ${name} away`;
        demoteBtn.addEventListener('click', () => togglePresence(name, false));

        row.appendChild(assignBtn);
        row.appendChild(demoteBtn);
        presentPanel.appendChild(row);
      }

      for (const name of awayNames) {
        const row = document.createElement('div');
        row.className = 'player-item';
        const activateBtn = document.createElement('button');
        activateBtn.type = 'button';
        activateBtn.className = 'btn small away-player';
        activateBtn.textContent = name;
        activateBtn.addEventListener('click', () => togglePresence(name, true));
        row.appendChild(activateBtn);
        awayPanel.appendChild(row);
      }

      presentHeading.textContent = `Present Players (${presentNames.length}) - tap to assign`;
      awayHeading.textContent = `Away Players (${awayNames.length}) - tap to mark present`;

      if (presentNames.length === 0) {
        presentPanel.innerHTML = "<div class='muted'>No present players yet.</div>";
      }
      if (awayNames.length === 0) {
        awayPanel.innerHTML = "<div class='muted'>No away players.</div>";
      }

      renderPresenceStatus();
    }

    function renderPresenceStatus() {
      const node = document.getElementById('presenceStatus');
      const required = state.mode === 'doubles' ? 4 : 2;
      const meta = ensureRequestMeta('presence');
      let text = `${state.activePlayers.length} active player(s). Need ${required} for ${state.mode}.`;
      if (meta.inFlightAt) {
        text += ` Refreshing active players (${formatElapsed(meta.inFlightAt)}).`;
      } else if (state.offline) {
        text += ' Presence updates are unavailable while offline.';
      } else if (meta.lastSuccessAt) {
        text += ` Updated ${formatAge(meta.lastSuccessAt)}.`;
      }
      node.textContent = text;
      node.className = 'status' + (state.activePlayers.length >= required ? ' ok' : '');
      document.getElementById('randomBtn').disabled = state.activePlayers.length < required;
      document.getElementById('autoBtn').disabled = state.mode !== 'doubles';
    }

    function renderOddsStatus() {
      const node = document.getElementById('oddsText');
      if (!node) {
        return;
      }
      const redOff = state.selected.red_offense;
      const blueOff = state.selected.blue_offense;
      const meta = ensureRequestMeta('odds');
      if (!redOff || !blueOff) {
        node.textContent = '';
        node.className = 'status';
        return;
      }
      if (meta.inFlightAt) {
        node.textContent = `Calculating odds... ${formatElapsed(meta.inFlightAt)} elapsed.`;
        node.className = 'status';
        return;
      }
      if (!state.latestOdds) {
        if (meta.lastFailureAt) {
          node.textContent = 'Could not load odds for this matchup.';
          node.className = 'status bad';
        } else {
          node.textContent = 'Pick both sides to fetch matchup odds.';
          node.className = 'status';
        }
        return;
      }

      const redPct = Math.round(state.latestOdds.probability * 100);
      const bluePct = 100 - redPct;
      const [favored, favoredPct] = redPct >= 50 ? [redOff + ' side', redPct] : [blueOff + ' side', bluePct];
      const label = oddsLabel(state.latestOdds.probability);
      const upset = hasUpsetRisk(state.latestOdds.probability);
      const badgeHtml = `<span class='badge ${label.cls}'>${label.text}</span>` +
        (upset ? `<span class='badge badge-bad'>Upset Risk</span>` : '') +
        (meta.lastSuccessAt ? `<span class='badge badge-muted'>Updated ${formatAge(meta.lastSuccessAt)}</span>` : '');
      node.innerHTML = `Odds: ${state.latestOdds.ratio} \u2014 ${favored} favored (${favoredPct}%) \u2014 Predicted: ${state.latestOdds.predicted} ${badgeHtml}`;
      node.className = 'status ok';
    }

    function setScore(side, score) {
      if (side === 'red') {
        state.score1 = score;
      } else {
        state.score2 = score;
      }
      renderScoreButtons();
      updateSummary();
      updateReview();
      updateScoreHint();
    }

    function renderScoreButtons() {
      const redPanel = document.getElementById('scoreRed');
      const bluePanel = document.getElementById('scoreBlue');
      redPanel.innerHTML = '';
      bluePanel.innerHTML = '';
      for (let i = 0; i <= 5; i += 1) {
        const redBtn = document.createElement('button');
        redBtn.type = 'button';
        redBtn.className = 'btn score red-team' + (state.score1 === i ? ' active' : '');
        redBtn.textContent = String(i);
        redBtn.addEventListener('click', () => setScore('red', i));
        redPanel.appendChild(redBtn);

        const blueBtn = document.createElement('button');
        blueBtn.type = 'button';
        blueBtn.className = 'btn score blue-team' + (state.score2 === i ? ' active' : '');
        blueBtn.textContent = String(i);
        blueBtn.addEventListener('click', () => setScore('blue', i));
        bluePanel.appendChild(blueBtn);
      }
    }

    function buildPayload() {
      const redOff = state.selected.red_offense;
      const blueOff = state.selected.blue_offense;
      if (!redOff || !blueOff) {
        throw new Error('Select both offense players first.');
      }

      let team1 = [redOff.toLowerCase()];
      let team2 = [blueOff.toLowerCase()];

      if (state.mode === 'doubles') {
        const redDef = state.selected.red_defense;
        const blueDef = state.selected.blue_defense;
        if (!redDef || !blueDef) {
          throw new Error('Select both defense players for doubles.');
        }
        team1 = [redOff.toLowerCase(), redDef.toLowerCase()];
        team2 = [blueOff.toLowerCase(), blueDef.toLowerCase()];
      }

      if (state.score1 === null || state.score2 === null) {
        throw new Error('Select both scores before submit.');
      }

      return { team1, team2, score1: state.score1, score2: state.score2 };
    }

    function clearSelection() {
      state.selected = {
        red_offense: null,
        red_defense: null,
        blue_offense: null,
        blue_defense: null,
      };
      state.selectionHistory = [];
      state.score1 = null;
      state.score2 = null;
      setActiveSlot(state.mode === 'doubles' ? 'red_defense' : 'red_offense');
      renderSlots();
      renderScoreButtons();
      setStatus('Cleared form.');
      updateSummary();
      updateReview();
      refreshOdds();
      updateScoreHint();
    }

    function displayNameForKey(playerName) {
      const found = state.players.find((candidate) => candidate.toLowerCase() === playerName.toLowerCase());
      return found || playerName;
    }

    async function refreshPresence() {
      if (state.offline) {
        return;
      }
      const response = await apiFetch('/api/presence', {
        trackKey: 'presence',
        trackLabel: 'active players',
      });
      if (!response.ok) {
        throw new Error('Could not load active players.');
      }
      const payload = await response.json();
      state.activePlayers = (payload.items || []).map((name) => name.toLowerCase());
      renderPlayerButtons();
    }

    async function togglePresence(playerName, forceActive = null) {
      const key = playerName.toLowerCase();
      const nextActive = forceActive === null ? !state.activePlayers.includes(key) : !!forceActive;
      const response = await apiFetch('/api/presence', {
        method: 'POST',
        trackKey: 'presence',
        trackLabel: 'active players',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: key, active: nextActive }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setStatus(payload.error || 'Could not update active players.', 'bad');
        return;
      }
      await refreshPresence();
      setStatus(`${payload.name} marked ${payload.active ? 'active' : 'away'}.`, 'ok');
    }

    function selectedKeysPayload() {
      return {
        red_offense: state.selected.red_offense ? state.selected.red_offense.toLowerCase() : null,
        red_defense: state.selected.red_defense ? state.selected.red_defense.toLowerCase() : null,
        blue_offense: state.selected.blue_offense ? state.selected.blue_offense.toLowerCase() : null,
        blue_defense: state.selected.blue_defense ? state.selected.blue_defense.toLowerCase() : null,
      };
    }

    function applySelectedFromApi(selected) {
      state.selectionHistory.push(JSON.stringify(state.selected));
      state.selected = {
        red_offense: selected.red_offense ? displayNameForKey(selected.red_offense) : null,
        red_defense: selected.red_defense ? displayNameForKey(selected.red_defense) : null,
        blue_offense: selected.blue_offense ? displayNameForKey(selected.blue_offense) : null,
        blue_defense: selected.blue_defense ? displayNameForKey(selected.blue_defense) : null,
      };
      renderSlots();
      updateSummary();
      updateReview();
      refreshOdds();
    }

    async function randomizeLineup() {
      if (state.offline) {
        setStatus('API offline. Leaderboard cache only.', 'bad');
        return;
      }
      const response = await apiFetch('/api/lineup/random', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: state.mode }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setStatus(payload.error || 'Could not build random lineup.', 'bad');
        return;
      }
      applySelectedFromApi(payload.selected || {});
      setStatus('Random lineup assigned from active players.', 'ok');
    }

    async function autoBalanceLineup() {
      if (state.offline) {
        setStatus('API offline. Leaderboard cache only.', 'bad');
        return;
      }
      if (state.mode !== 'doubles') {
        setStatus('Auto balance is available in doubles mode.', 'bad');
        return;
      }
      const response = await apiFetch('/api/lineup/auto', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: state.mode, selected: selectedKeysPayload() }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setStatus(payload.error || 'Could not auto-balance lineup.', 'bad');
        return;
      }
      applySelectedFromApi(payload.selected || {});
      setStatus('Lineup auto-balanced for best match quality.', 'ok');
    }

    function leaderboardSortValue(row) {
      const s = state.playerStats;
      const k = row.name.toLowerCase();
      if (state.leaderboardSort === 'offense') return Number(row.offense_level || 0);
      if (state.leaderboardSort === 'defense') return Number(row.defense_level || 0);
      if (state.leaderboardSort === 'form') return s && s[k] ? Number(s[k].win_rate || 0) : 0;
      if (state.leaderboardSort === 'streak') return s && s[k] ? Number(s[k].streak || 0) : 0;
      if (state.leaderboardSort === 'improved') return s && s[k] ? Number(s[k].improved || 0) : 0;
      return Number(row.level || 0);
    }

    function leaderboardMetric(row) {
      const s = state.playerStats;
      const k = row.name.toLowerCase();
      if (state.leaderboardSort === 'offense') return String(row.offense_level);
      if (state.leaderboardSort === 'defense') return String(row.defense_level);
      if (state.leaderboardSort === 'form') {
        if (!s || !s[k]) return '\u2014';
        const f = s[k].recent_form_5;
        return f.split('').map(c => `<span class='form-${c.toLowerCase()}'>${c}</span>`).join(' ');
      }
      if (state.leaderboardSort === 'streak') return s && s[k] ? String(s[k].streak) : '\u2014';
      if (state.leaderboardSort === 'improved') {
        if (!s || !s[k]) return '\u2014';
        const v = s[k].improved;
        return `<span class='${v >= 0 ? "delta-pos" : "delta-neg"}'>${v >= 0 ? '+' : ''}${v}</span>`;
      }
      return String(row.level);
    }

    function applyLeaderboardFilter(items) {
      return items;
    }

    function setLeaderboardSort(mode) {
      if (mode === 'improved' && state.leaderboardFilter === 'all') {
        return;
      }
      state.leaderboardSort = mode;
      const ids = ['sortTotalBtn','sortAtkBtn','sortDefBtn','sortFormBtn','sortStreakBtn','sortImprovedBtn'];
      const modes = ['total','offense','defense','form','streak','improved'];
      const headers = ['Total','Offense','Defense','Form','Streak','Improved'];
      ids.forEach((id, i) => document.getElementById(id).classList.toggle('active', modes[i] === mode));
      const hdr = document.getElementById('lbMetricHeader');
      if (hdr) hdr.textContent = headers[modes.indexOf(mode)] || 'Total';
      const hint = document.getElementById('metricHint');
      if (hint) {
        hint.textContent = mode === 'improved'
          ? 'Improved: delta on all-time leaderboard baseline.'
          : '';
      }
      const statsNeeded = ['form','streak','improved'].includes(mode);
      if (statsNeeded && (!state.playerStats || state.playerStatsScope !== state.leaderboardFilter)) {
        fetchLeaderboardStats().catch(() => undefined);
      } else {
        renderLeaderboard(state.leaderboardItems);
      }
    }

    function fetchLeaderboardStats() {
      const requestVersion = state.statsRequestVersion + 1;
      const requestScope = state.leaderboardFilter;
      state.statsRequestVersion = requestVersion;
      return apiFetch('/api/stats?scope=' + encodeURIComponent(state.leaderboardFilter), {
        trackKey: 'stats',
        trackLabel: 'leaderboard stats',
      })
        .then(r => {
          if (!r.ok) {
            throw new Error('Could not load leaderboard stats.');
          }
          return r.json();
        })
        .then(data => {
          if (requestVersion !== state.statsRequestVersion || requestScope !== state.leaderboardFilter) {
            return data;
          }
          state.playerStats = data;
          state.playerStatsScope = requestScope;
          renderLeaderboard(state.leaderboardItems);
          return data;
        });
    }

    function setLeaderboardFilter(f) {
      state.leaderboardFilter = f;
      state.playerStats = null;
      state.playerStatsScope = null;
      document.getElementById('filterAllBtn').classList.toggle('active', f === 'all');
      document.getElementById('filterThisQuarterBtn').classList.toggle('active', f === 'this_quarter');
      document.getElementById('filterThisMonthBtn').classList.toggle('active', f === 'this_month');
      document.getElementById('filterThisWeekBtn').classList.toggle('active', f === 'this_week');

      const improvedBtn = document.getElementById('sortImprovedBtn');
      improvedBtn.disabled = f === 'all';
      if (f === 'all' && state.leaderboardSort === 'improved') {
        setLeaderboardSort('total');
      }

      if (!state.offline) {
        refreshLeaderboard().catch(() => undefined);
      }

      const needsStats = ['form', 'streak', 'improved'].includes(state.leaderboardSort);
      if (needsStats && !state.offline) {
        fetchLeaderboardStats().catch(() => undefined);
      }
    }

    function renderLeaderboard(items) {
      state.leaderboardItems = items || [];
      const body = document.getElementById('leaderboardBody');
      const filtered = applyLeaderboardFilter(state.leaderboardItems);
      if (!filtered || filtered.length === 0) {
        body.innerHTML = "<tr><td colspan='3'>No players found.</td></tr>";
        return;
      }
      const ordered = [...filtered].sort((a, b) => {
        const diff = leaderboardSortValue(b) - leaderboardSortValue(a);
        if (diff !== 0) return diff;
        return Number(a.position || 999) - Number(b.position || 999);
      });
      body.innerHTML = ordered.map((row, idx) => {
        const playerKey = row.name.toLowerCase();
        const metric = leaderboardMetric(row);
        const rank = idx + 1;
        return `<tr class='lrow' onclick='togglePlayerHistory(this, "${playerKey}")'><td>${rank}</td><td><div>${row.name}</div><div class="sub">Off\u00a0${row.offense_level} \u00b7 Def\u00a0${row.defense_level}</div></td><td>${metric}</td></tr>`;
      }).join('');
    }

    function formatSignedDelta(value) {
      const numeric = Number(value || 0);
      const fixed = numeric.toFixed(1);
      return `<span class='${numeric >= 0 ? 'delta-pos' : 'delta-neg'}'>${numeric >= 0 ? '+' : ''}${fixed}</span>`;
    }

    function recentFormText(form) {
      if (!form) return 'No recent form';
      return form.split('').map(ch => ch === 'W' ? `<span class='form-w'>W</span>` : `<span class='form-l'>L</span>`).join(' ');
    }

    function renderProfileOpponentCard(label, item, actionLabel, playerKey) {
      if (!item) {
        return `<div class='profile-card'><div class='label'>${label}</div><div class='value'>No data yet</div></div>`;
      }
      return `<div class='profile-card'>` +
        `<div class='label'>${label}</div>` +
        `<div class='value'>${item.player}</div>` +
        `<div class='subvalue'>${item.wins}-${item.losses}` + (item.draws ? ` (${item.draws}D)` : '') + ` in ${item.matches} match${item.matches === 1 ? '' : 'es'}</div>` +
        (actionLabel
          ? `<div class='subvalue' style='margin-top:8px;'><button class='btn small' type='button' onclick='openPlayerH2H("${playerKey}", "${item.player.toLowerCase()}")'>${actionLabel}</button></div>`
          : '') +
        `</div>`;
    }

    function renderRecentMatches(matches) {
      if (!matches || matches.length === 0) {
        return `<div class='kv'>No matches recorded yet.</div>`;
      }
      return matches.map(match => {
        const result = match.won ? `<span class='form-w'>W</span>` : `<span class='form-l'>L</span>`;
        const date = match.timestamp ? match.timestamp.slice(0, 10) : '?';
        const lineup = `${match.team.join(' + ')} vs ${match.opponents.join(' + ')}`;
        return `<div class='recent-match'>` +
          `<div class='kv'>${result} ${date} <strong>${match.score_for}-${match.score_against}</strong></div>` +
          `<div class='sub'>${lineup}</div>` +
          `<div class='kv'>Off ${formatSignedDelta(match.delta.offense)} Def ${formatSignedDelta(match.delta.defense)}</div>` +
          `</div>`;
      }).join('');
    }

    function renderPlayerProfile(data) {
      const summary = data.summary || {};
      const bestPartner = renderProfileOpponentCard('Best Partner', data.best_partner, '', data.player);
      const toughestOpponent = renderProfileOpponentCard('Toughest Opponent', data.toughest_opponent, 'Open H2H', data.player);
      const streakValue = summary.streak ? `${summary.streak} straight wins` : 'No current streak';
      return `<div class='profile-panel'>` +
        `<div class='profile-header'>` +
          `<div>` +
            `<div class='profile-title'>${displayNameForKey(data.player)}</div>` +
            `<div class='profile-meta'>${summary.wins || 0}-${(summary.games || 0) - (summary.wins || 0)} in ${summary.games || 0} match${summary.games === 1 ? '' : 'es'} · ${Math.round((summary.win_rate || 0) * 100)}% win rate</div>` +
          `</div>` +
          `<div class='profile-meta'>Form ${recentFormText(summary.recent_form_5 || '')}</div>` +
        `</div>` +
        `<div class='profile-cards'>` +
          `<div class='profile-card'><div class='label'>Current Streak</div><div class='value'>${streakValue}</div><div class='subvalue'>Last match ${summary.last_match ? summary.last_match.slice(0, 10) : 'n/a'}</div></div>` +
          bestPartner +
          toughestOpponent +
        `</div>` +
        `<div class='trend-row'>` +
          `<div class='trend-pill'><div class='label'>Offense Trend</div><div class='value'>${formatSignedDelta((data.trend || {}).offense)}</div><div class='subvalue'>Recent matches</div></div>` +
          `<div class='trend-pill'><div class='label'>Defense Trend</div><div class='value'>${formatSignedDelta((data.trend || {}).defense)}</div><div class='subvalue'>Recent matches</div></div>` +
        `</div>` +
        `<div>` +
          `<div style='font-size:0.75rem;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.04em;'>Recent Matches</div>` +
          renderRecentMatches(data.recent_matches || []) +
        `</div>` +
        `<div class='profile-actions'>` +
          `<button class='btn small' type='button' onclick='setLeaderboardFilter(state.leaderboardFilter)'>Refresh Scope</button>` +
        `</div>` +
      `</div>`;
    }

    function openPlayerH2H(playerKey, otherPlayerKey) {
      setStep(2);
      state.selected.red_offense = displayNameForKey(playerKey);
      state.selected.blue_offense = displayNameForKey(otherPlayerKey);
      if (state.mode === 'doubles') {
        state.selected.red_defense = null;
        state.selected.blue_defense = null;
      }
      state.h2hOpen = true;
      renderSelection();
      refreshH2H();
    }

    async function togglePlayerHistory(rowEl, playerKey) {
      if (state.offline) {
        return;
      }
      const nextEl = rowEl.nextElementSibling;
      if (nextEl && nextEl.classList.contains('expand-row')) {
        nextEl.remove();
        if (state.expandedPlayer === playerKey) { state.expandedPlayer = null; return; }
      }
      state.expandedPlayer = playerKey;
      const tr = document.createElement('tr');
      tr.className = 'expand-row';
      const td = document.createElement('td');
      td.colSpan = 3;
      td.className = 'expand-panel';
      td.innerHTML = '<div class="kv">Loading player profile...</div>';
      tr.appendChild(td);
      rowEl.after(tr);
      try {
        const resp = await apiFetch(`/api/player/${encodeURIComponent(playerKey)}/profile?scope=${encodeURIComponent(state.leaderboardFilter)}&recent_limit=5`, {
          trackKey: 'profile',
          trackLabel: 'player profile',
        });
        if (!resp.ok) { td.innerHTML = '<div class="kv">No profile available.</div>'; return; }
        const data = await resp.json();
        td.innerHTML = renderPlayerProfile(data);
      } catch { td.innerHTML = '<div class="kv">Could not load profile.</div>'; }
    }

    function updateSummary() {
      const red = formatTeamDisplay('red');
      const blue = formatTeamDisplay('blue');
      const score = (state.score1 === null || state.score2 === null) ? '?-?' : `${state.score1}-${state.score2}`;
      document.getElementById('summaryText').textContent = `${state.mode.toUpperCase()} | Red: ${red} vs Blue: ${blue} | Score: ${score}`;
      document.getElementById('redScoreLabel').textContent = red;
      document.getElementById('blueScoreLabel').textContent = blue;
      document.getElementById('nextBtn').disabled = !isStepComplete(state.step);
      for (let i = 1; i <= 4; i++) {
        stepButtons[i].disabled = !isStepReachable(i);
      }
    }

    function isStepComplete(step) {
      if (step === 1) return true;
      if (step === 2) {
        if (!state.selected.red_offense || !state.selected.blue_offense) return false;
        if (state.mode === 'doubles' && (!state.selected.red_defense || !state.selected.blue_defense)) return false;
        return true;
      }
      if (step === 3) {
        if (state.score1 === null || state.score2 === null) return false;
        return Math.max(state.score1, state.score2) === 5 && Math.min(state.score1, state.score2) !== 5;
      }
      return true;
    }

    function isStepReachable(step) {
      for (let i = 1; i < step; i++) {
        if (!isStepComplete(i)) return false;
      }
      return true;
    }

    function isFinishedScore(score1, score2) {
      if (score1 === null || score2 === null) {
        return false;
      }
      return Math.max(score1, score2) === 5 && Math.min(score1, score2) !== 5;
    }

    function parsePredictedLosingGoals(predicted) {
      if (!predicted || typeof predicted !== 'string') {
        return null;
      }
      const parts = predicted.split('-').map((value) => Number.parseInt(value, 10));
      if (parts.length !== 2 || Number.isNaN(parts[0]) || Number.isNaN(parts[1])) {
        return null;
      }
      return Math.min(parts[0], parts[1]);
    }

    function classifyQuipCategory(probability, predicted, score1, score2) {
      if (!isFinishedScore(score1, score2)) {
        return null;
      }

      const winnerGoals = Math.max(score1, score2);
      const loserGoals = Math.min(score1, score2);
      const margin = winnerGoals - loserGoals;
      const redFavored = probability >= 0.5;
      const redWon = score1 > score2;
      const upset = redWon !== redFavored;
      const confidence = Math.max(probability, 1 - probability);
      const predictedLosingGoals = parsePredictedLosingGoals(predicted);

      if (winnerGoals === 5 && loserGoals <= 1) {
        return 'total_stomp';
      }
      if (margin === 1) {
        return 'nail_biter';
      }
      if (upset) {
        return 'upset_win';
      }
      if (Math.abs(probability - 0.5) <= 0.06) {
        return 'even_match_outcome';
      }
      if (confidence >= 0.7 && (margin >= 3 || (predictedLosingGoals !== null && loserGoals <= predictedLosingGoals))) {
        return 'expected_blowout';
      }
      return 'expected_close_win';
    }

    function selectQuipForCategory(category) {
      const options = QUIPS_BY_CATEGORY[category] || [];
      if (!options.length) {
        return 'Table speaks louder than predictions.';
      }

      let index = Math.floor(Math.random() * options.length);
      const previous = state.lastQuipIndexByCategory[category];
      if (options.length > 1 && previous === index) {
        index = (index + 1 + Math.floor(Math.random() * (options.length - 1))) % options.length;
      }

      state.lastQuipIndexByCategory[category] = index;
      return options[index];
    }

    function resolveCurrentQuip() {
      if (!state.latestOdds) {
        state.currentQuipKey = null;
        state.currentQuipText = null;
        state.currentQuipCategory = null;
        return null;
      }

      const category = classifyQuipCategory(
        state.latestOdds.probability,
        state.latestOdds.predicted,
        state.score1,
        state.score2,
      );
      if (!category) {
        state.currentQuipKey = null;
        state.currentQuipText = null;
        state.currentQuipCategory = null;
        return null;
      }

      const key = `${category}|${state.latestOdds.predicted}|${state.score1}-${state.score2}`;
      if (state.currentQuipKey === key && state.currentQuipText) {
        return { category: state.currentQuipCategory, text: state.currentQuipText };
      }

      state.currentQuipCategory = category;
      state.currentQuipKey = key;
      state.currentQuipText = selectQuipForCategory(category);
      return { category: category, text: state.currentQuipText };
    }

    function updateScoreHint() {
      const node = document.getElementById('scoreHint');
      if (!node) return;
      if (!state.latestOdds) {
        node.textContent = 'Pick players to see odds and matchup context.';
        return;
      }

      let topLine = `Predicted: ${state.latestOdds.predicted}`;
      if (state.score1 !== null && state.score2 !== null) {
        topLine += `  |  Final: ${state.score1}-${state.score2}`;
      }
      node.innerHTML = '';
      const topNode = document.createElement('div');
      topNode.textContent = topLine;
      node.appendChild(topNode);
      const quip = resolveCurrentQuip();
      if (quip) {
        const quipNode = document.createElement('div');
        quipNode.style.marginTop = '10px';
        const em = document.createElement('em');
        em.textContent = quip.text;
        quipNode.appendChild(em);
        node.appendChild(quipNode);
      }
    }

    function updateReview() {
      const review = document.getElementById('reviewText');
      try {
        const payload = buildPayload();
        const redDisplay = formatTeamDisplay('red', ' + ');
        const blueDisplay = formatTeamDisplay('blue', ' + ');
        const winner = payload.score1 > payload.score2 ? redDisplay : blueDisplay;
        const oddsText = state.latestOdds
          ? `<div><strong>Odds:</strong> ${state.latestOdds.ratio} (${Math.round(state.latestOdds.probability * 100)}% red-side win)</div>`
          : '';
        const quipState = resolveCurrentQuip();
        const quip = quipState
          ? `<div class='review-quip'>${quipState.text}</div>`
          : '';
        review.innerHTML =
          `<div><strong>Red:</strong> ${redDisplay}</div>` +
          `<div><strong>Blue:</strong> ${blueDisplay}</div>` +
          `<div class='review-score'>Final Score: ${payload.score1} - ${payload.score2}</div>` +
          `<div><strong>Winner:</strong> ${winner}</div>` +
          oddsText +
          quip;
      } catch {
        review.textContent = 'Complete lineup and score to enable submit.';
      }
    }

    function teamDisplayMembers(team, placeholder = '?') {
      if (team === 'red') {
        return state.mode === 'doubles'
          ? [state.selected.red_defense || placeholder, state.selected.red_offense || placeholder]
          : [state.selected.red_offense || placeholder];
      }
      return state.mode === 'doubles'
        ? [state.selected.blue_defense || placeholder, state.selected.blue_offense || placeholder]
        : [state.selected.blue_offense || placeholder];
    }

    function formatTeamDisplay(team, separator = ' / ', placeholder = '?') {
      return teamDisplayMembers(team, placeholder).join(separator);
    }

    function setStep(step) {
      if (state.offline) {
        setStatus('API offline. Leaderboard cache only.', 'bad');
        return;
      }
      const target = Math.max(1, Math.min(step, 4));
      for (let i = 1; i < target; i++) {
        if (!isStepComplete(i)) return;
      }
      state.step = target;
      for (let i = 1; i <= 4; i += 1) {
        stepButtons[i].classList.toggle('active', i === state.step);
        stepSections[i].classList.toggle('active', i === state.step);
        stepButtons[i].disabled = !isStepReachable(i);
      }
      leaderboardSection.classList.toggle('active', state.step === 1);
      document.getElementById('backBtn').style.visibility = state.step === 1 ? 'hidden' : 'visible';
      document.getElementById('nextBtn').style.display = state.step === 4 ? 'none' : 'inline-block';
      document.getElementById('submitBtn').style.display = state.step === 4 ? 'inline-block' : 'none';
      document.getElementById('nextBtn').disabled = !isStepComplete(state.step);
      if (state.step === 4) {
        updateReview();
      }
    }

    async function refreshLeaderboard() {
      if (state.offline) {
        const cached = readCachedLeaderboard();
        if (cached.cachedAt) {
          state.leaderboardCacheAt = Date.parse(cached.cachedAt);
        }
        state.leaderboardSource = 'cache';
        renderLeaderboard(cached.items);
        renderLeaderboardFreshness();
        renderLiveStatus();
        return;
      }
      const requestVersion = state.leaderboardRequestVersion + 1;
      const requestScope = state.leaderboardFilter;
      state.leaderboardRequestVersion = requestVersion;
      const response = await apiFetch('/api/leaderboard?limit=50&scope=' + encodeURIComponent(state.leaderboardFilter), {
        trackKey: 'leaderboard',
        trackLabel: 'leaderboard',
      });
      if (!response.ok) {
        throw new Error('Could not refresh leaderboard.');
      }
      const payload = await response.json();
      if (requestVersion !== state.leaderboardRequestVersion || requestScope !== state.leaderboardFilter) {
        return;
      }
      const items = payload.items || [];
      state.leaderboardSource = 'live';
      renderLeaderboard(items);
      cacheLeaderboard(items);
      renderLeaderboardFreshness();
      renderLiveStatus();
    }

    function predictedScore(prob) {
      const p = prob >= 0.5 ? prob : 1 - prob;
      let loser;
      if (p >= 0.93) loser = 0;
      else if (p >= 0.82) loser = 1;
      else if (p >= 0.70) loser = 2;
      else if (p >= 0.58) loser = 3;
      else loser = 4;
      return prob >= 0.5 ? `5-${loser}` : `${loser}-5`;
    }

    function oddsLabel(prob) {
      const p = Math.max(prob, 1 - prob);
      if (p >= 0.70) return { text: 'Strong Fav', cls: 'badge-accent' };
      if (p >= 0.55) return { text: 'Favorite', cls: 'badge-ok' };
      return { text: 'Even', cls: 'badge-muted' };
    }

    function hasUpsetRisk(prob) {
      const redOff = state.selected.red_offense;
      const blueOff = state.selected.blue_offense;
      if (!redOff || !blueOff || !state.leaderboardItems.length) return false;
      const ri = state.leaderboardItems.find(r => r.name.toLowerCase() === redOff.toLowerCase());
      const bi = state.leaderboardItems.find(r => r.name.toLowerCase() === blueOff.toLowerCase());
      if (!ri || !bi) return false;
      const redPos = Number(ri.position);
      const bluePos = Number(bi.position);
      return (redPos > bluePos && prob > 0.52) || (bluePos > redPos && prob < 0.48);
    }

    function refreshH2H() {
      const redOff = state.selected.red_offense;
      const blueOff = state.selected.blue_offense;
      const redDef = state.selected.red_defense;
      const blueDef = state.selected.blue_defense;
      const card = document.getElementById('h2hCard');
      const toggleRow = document.getElementById('h2hToggleRow');
      if (!redOff || !blueOff) {
        toggleRow.style.display = 'none';
        card.classList.remove('open');
        return;
      }
      toggleRow.style.display = '';
      if (!state.h2hOpen) return;
      card.innerHTML = '<span class="muted">Loading head-to-head...</span>';
      const pairs = state.mode === 'doubles' && redDef && blueDef
        ? [
            { left: redDef, right: blueDef, label: 'Defense vs Defense' },
            { left: redOff, right: blueOff, label: 'Offense vs Offense' },
            { left: redDef, right: blueOff, label: 'Red Defense vs Blue Offense' },
            { left: redOff, right: blueDef, label: 'Red Offense vs Blue Defense' },
          ]
        : [{ left: redOff, right: blueOff, label: 'Singles H2H' }];

      Promise.all(pairs.map(pair =>
        apiFetch(`/api/h2h?p1=${encodeURIComponent(pair.left.toLowerCase())}&p2=${encodeURIComponent(pair.right.toLowerCase())}`, {
          trackKey: 'h2h',
          trackLabel: 'head-to-head',
        })
          .then(r => r.json())
          .then(d => ({ pair, data: d }))
      ))
        .then(results => {
          card.innerHTML = `<div class='profile-meta' style='margin-bottom:8px;'>${state.mode === 'doubles' ? 'Player-pair H2H' : 'Head-to-head'}</div>` +
            `<div class='h2h-grid'>` +
            results.map(({ pair, data }) => {
              if (data.matches === 0) {
                return `<div class='h2h-pair'><div class='label'>${pair.label}</div><div class='kv'><strong>${pair.left}</strong> vs <strong>${pair.right}</strong></div><div class='sub'>No recorded matches yet.</div></div>`;
              }
              const last = data.last_match ? data.last_match.slice(0, 10) : '?';
              return `<div class='h2h-pair'>` +
                `<div class='label'>${pair.label}</div>` +
                `<div class='kv'><strong>${pair.left}</strong> ${data.p1_wins}\u2013${data.p2_wins} <strong>${pair.right}</strong>${data.draws ? ` (${data.draws}D)` : ''}</div>` +
                `<div class='sub'>${data.matches} match${data.matches === 1 ? '' : 'es'} · last ${last}</div>` +
                `</div>`;
            }).join('') +
            `</div>`;
        })
        .catch(() => { card.innerHTML = '<span class="muted">Could not load H2H data.</span>'; });
    }

    function toggleH2H() {
      state.h2hOpen = !state.h2hOpen;
      const card = document.getElementById('h2hCard');
      const btn = document.getElementById('h2hToggleBtn');
      card.classList.toggle('open', state.h2hOpen);
      btn.textContent = state.h2hOpen ? 'H2H \u25b4' : 'H2H \u25be';
      if (state.h2hOpen) refreshH2H();
    }

    async function refreshOdds() {
      if (state.offline) {
        return;
      }
      const redOff = state.selected.red_offense;
      const blueOff = state.selected.blue_offense;
      if (!redOff || !blueOff) {
        state.latestOdds = null;
        renderOddsStatus();
        updateScoreHint();
        refreshH2H();
        return;
      }
      renderOddsStatus();
      const params = new URLSearchParams({ red_off: redOff.toLowerCase(), blue_off: blueOff.toLowerCase(), mode: state.mode });
      if (state.mode === 'doubles') {
        if (state.selected.red_defense) params.set('red_def', state.selected.red_defense.toLowerCase());
        if (state.selected.blue_defense) params.set('blue_def', state.selected.blue_defense.toLowerCase());
      }
      try {
        const resp = await apiFetch('/api/odds?' + params.toString(), {
          trackKey: 'odds',
          trackLabel: 'odds',
        });
        if (!resp.ok) {
          state.latestOdds = null;
          renderOddsStatus();
          updateScoreHint();
          return;
        }
        const data = await resp.json();
        const score = predictedScore(data.probability);
        state.latestOdds = { probability: data.probability, ratio: data.ratio, predicted: score };
        renderOddsStatus();
        updateScoreHint();
        refreshH2H();
      } catch {
        state.latestOdds = null;
        renderOddsStatus();
        updateScoreHint();
      }
    }

    async function loadPlayers() {
      const response = await apiFetch('/api/players', {
        trackKey: 'players',
        trackLabel: 'player list',
      });
      if (!response.ok) {
        throw new Error('Could not load players.');
      }
      const payload = await response.json();
      state.players = (payload.items || []).slice().sort((left, right) => left.localeCompare(right));
      renderPlayerButtons();
    }

    async function submitMatch() {
      if (state.isSubmitting) {
        setStatus('Submission already in progress...', 'bad');
        return;
      }

      const writePin = ensureWritePin();
      if (!writePin) {
        setStatus('Enter writer PIN first.', 'bad');
        return;
      }

      let payload;
      try {
        payload = buildPayload();
      } catch (error) {
        setStatus(error.message, 'bad');
        return;
      }

      state.isSubmitting = true;
      const submitBtn = document.getElementById('submitBtn');
      const originalSubmitLabel = submitBtn.textContent;
      submitBtn.disabled = true;
      submitBtn.textContent = 'Submitting...';
      setStatus('Submitting result...');

      try {
        const response = await apiFetch('/api/matches', {
          method: 'POST',
          trackKey: 'submit',
          trackLabel: 'match submit',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });

        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
          setStatus(result.error || 'Submit failed.', 'bad');
          return;
        }

        setStatus('Result submitted. Leaderboard refreshed.', 'ok');
        await refreshLeaderboard();
        setStep(2);
      } finally {
        state.isSubmitting = false;
        submitBtn.disabled = false;
        submitBtn.textContent = originalSubmitLabel;
      }
    }

    async function addPlayer() {
      const writePin = ensureWritePin();
      if (!writePin) {
        setAddPlayerStatus('Writer PIN is required to add players.', 'bad');
        return;
      }

      const input = document.getElementById('newPlayerName');
      const name = input.value.trim();
      if (!name) {
        setAddPlayerStatus('Enter a player name.', 'bad');
        return;
      }

      setAddPlayerStatus('Adding player...');
      const response = await apiFetch('/api/players', {
        method: 'POST',
        trackKey: 'players',
        trackLabel: 'player add',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ name }),
      });

      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        setAddPlayerStatus(result.error || 'Could not add player.', 'bad');
        return;
      }

      input.value = '';
      setAddPlayerStatus(`Added ${result.name}.`, 'ok');
      await loadPlayers();
      await refreshPresence();
      await refreshLeaderboard();
    }

    document.getElementById('modeSingles').addEventListener('click', () => setMode('singles'));
    document.getElementById('modeDoubles').addEventListener('click', () => setMode('doubles'));
    document.getElementById('slotRedOff').addEventListener('click', () => setActiveSlot('red_offense'));
    document.getElementById('slotRedDef').addEventListener('click', () => setActiveSlot('red_defense'));
    document.getElementById('slotBlueOff').addEventListener('click', () => setActiveSlot('blue_offense'));
    document.getElementById('slotBlueDef').addEventListener('click', () => setActiveSlot('blue_defense'));
    document.getElementById('swapSidesBtn').addEventListener('click', swapSides);
    document.getElementById('swapRedBtn').addEventListener('click', () => swapTeam('red'));
    document.getElementById('swapBlueBtn').addEventListener('click', () => swapTeam('blue'));
    document.getElementById('randomBtn').addEventListener('click', () => randomizeLineup().catch((e) => setStatus(e.message, 'bad')));
    document.getElementById('autoBtn').addEventListener('click', () => autoBalanceLineup().catch((e) => setStatus(e.message, 'bad')));
    document.getElementById('undoBtn').addEventListener('click', undoLastPick);
    document.getElementById('clearBtn').addEventListener('click', clearSelection);
    document.getElementById('sortTotalBtn').addEventListener('click', () => setLeaderboardSort('total'));
    document.getElementById('sortAtkBtn').addEventListener('click', () => setLeaderboardSort('offense'));
    document.getElementById('sortDefBtn').addEventListener('click', () => setLeaderboardSort('defense'));
    document.getElementById('sortFormBtn').addEventListener('click', () => setLeaderboardSort('form'));
    document.getElementById('sortStreakBtn').addEventListener('click', () => setLeaderboardSort('streak'));
    document.getElementById('sortImprovedBtn').addEventListener('click', () => setLeaderboardSort('improved'));
    document.getElementById('filterAllBtn').addEventListener('click', () => setLeaderboardFilter('all'));
    document.getElementById('filterThisQuarterBtn').addEventListener('click', () => setLeaderboardFilter('this_quarter'));
    document.getElementById('filterThisMonthBtn').addEventListener('click', () => setLeaderboardFilter('this_month'));
    document.getElementById('filterThisWeekBtn').addEventListener('click', () => setLeaderboardFilter('this_week'));
    document.getElementById('addPlayerBtn').addEventListener('click', () => addPlayer().catch((e) => setAddPlayerStatus(e.message, 'bad')));
    document.getElementById('newPlayerName').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        addPlayer().catch((err) => setAddPlayerStatus(err.message, 'bad'));
      }
    });
    document.getElementById('nextBtn').addEventListener('click', () => setStep(state.step + 1));
    document.getElementById('backBtn').addEventListener('click', () => setStep(state.step - 1));
    document.getElementById('submitBtn').addEventListener('click', () => submitMatch().catch((e) => setStatus(e.message, 'bad')));
    stepButtons[1].addEventListener('click', () => setStep(1));
    stepButtons[2].addEventListener('click', () => setStep(2));
    stepButtons[3].addEventListener('click', () => setStep(3));
    stepButtons[4].addEventListener('click', () => setStep(4));

    setMode('singles');
    setActiveSlot('red_offense');
    seedInitialFreshness();
    startFreshnessTicker();
    renderScoreButtons();
    renderSlots();
    updateSummary();
    updateReview();
    updateScoreHint();
    setLeaderboardFilter('all');
    loadPlayers()
      .then(() => refreshPresence())
      .catch((e) => setStatus(e.message, 'bad'));
    startHealthMonitor();

    const readPinInput = document.getElementById('readPin');
    const writePinInput = document.getElementById('writePin');
    const savedReadPin = getStoredReadPin();
    const savedWritePin = getStoredWritePin();
    if (savedReadPin) {
      readPinInput.value = savedReadPin;
    }
    if (savedWritePin) {
      writePinInput.value = savedWritePin;
    }
    readPinInput.addEventListener('input', () => {
      persistReadPin(readPinInput.value);
    });
    writePinInput.addEventListener('input', () => {
      persistWritePin(writePinInput.value);
    });
  </script>
</body>
</html>"""
    return html.replace("__TABLE_ROWS__", table_rows)


def create_app(
  db_dir: Path | None = None,
  operator_token: str | None = None,
  read_pin_hash: str | None = None,
  write_pin_hash: str | None = None,
  database_url: str | None = None,
  write_store: BaseWriteStore | None = None,
) -> Flask:
  """Create the phone API app.

  Args:
    db_dir: Directory containing shelve files. Defaults to app directory.
    operator_token: Legacy shared secret required for write requests.
    read_pin_hash: Optional password hash for read access.
    write_pin_hash: Optional password hash for write access.
    database_url: Optional Postgres URL enabling Neon write-store mode.
    write_store: Optional explicit write-store override (primarily for tests).
  """
  app = Flask(__name__)
  data_dir = db_dir or ROOT_DIR
  app.config["OPERATOR_TOKEN"] = operator_token
  app.config["READ_PIN_HASH"] = read_pin_hash
  app.config["WRITE_PIN_HASH"] = write_pin_hash
  app.config["DATABASE_URL"] = database_url or os.environ.get("DATABASE_URL")
  _RECENT_MATCH_SIGNATURES.clear()
  active_players: set[str] = set()

  write_store_error: str | None = None
  active_write_store = write_store
  if active_write_store is None:
    try:
      active_write_store = create_write_store(
        WriteStoreConfig(
          db_dir=data_dir,
          database_url=app.config["DATABASE_URL"],
        )
      )
    except Exception as exc:
      write_store_error = str(exc)

  def _resolve_write_store() -> tuple[BaseWriteStore | None, object | None]:
    if active_write_store is not None:
      return active_write_store, None
    if write_store_error:
      return None, (jsonify({"error": f"write store unavailable: {write_store_error}"}), 503)
    return None, (jsonify({"error": "write store unavailable"}), 503)

  def _read_auth_enabled() -> bool:
    return bool(app.config.get("READ_PIN_HASH") or app.config.get("WRITE_PIN_HASH"))

  def _write_pin_enabled() -> bool:
    return bool(app.config.get("WRITE_PIN_HASH"))

  def _request_supplied_read_credentials() -> bool:
    return bool(request.headers.get(READ_PIN_HEADER) or request.headers.get(WRITE_PIN_HEADER))

  def _has_read_access() -> bool:
    if not _read_auth_enabled():
      return True

    read_pin = request.headers.get(READ_PIN_HEADER)
    write_pin = request.headers.get(WRITE_PIN_HEADER)
    read_ok = _verify_secret(app.config.get("READ_PIN_HASH"), read_pin)
    write_ok = _verify_secret(app.config.get("WRITE_PIN_HASH"), write_pin)
    return read_ok or write_ok

  def _check_write_access() -> tuple[bool, int, str]:
    if _write_pin_enabled():
      write_pin = request.headers.get(WRITE_PIN_HEADER)
      if _verify_secret(app.config.get("WRITE_PIN_HASH"), write_pin):
        return True, 200, ""
      if write_pin:
        return False, 403, "incorrect writer PIN"
      return False, 403, "writer authorization required"

    token = app.config.get("OPERATOR_TOKEN")
    if not token:
      return False, 503, "write endpoint not configured"

    provided_token = request.headers.get(OPERATOR_TOKEN_HEADER)
    if provided_token != token:
      if provided_token:
        return False, 401, "incorrect operator token"
      return False, 401, "unauthorized"
    return True, 200, ""

  def require_read_access() -> object | None:
    if _has_read_access():
      return None
    message = "incorrect reader or writer PIN" if _request_supplied_read_credentials() else "authentication required"
    return jsonify({"error": message}), 401

  def require_write_access() -> object | None:
    allowed, status, message = _check_write_access()
    if allowed:
      return None
    return jsonify({"error": message}), status

  @app.get("/api/health")
  def health() -> object:
    return jsonify({"ok": True})

  @app.get("/api/leaderboard")
  def leaderboard() -> object:
    denied = require_read_access()
    if denied is not None:
      return denied

    limit = request.args.get("limit", default=50, type=int)
    limit = max(1, min(limit, 200))
    scope = request.args.get("scope", default="all", type=str)
    if scope not in {"all", "this_quarter", "this_month", "this_week"}:
      return jsonify({"error": "invalid scope"}), 400
    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None

    rows = _load_leaderboard(store, limit, scope=scope)
    return jsonify({"count": len(rows), "items": rows})

  @app.get("/api/players")
  def players() -> object:
    denied = require_read_access()
    if denied is not None:
      return denied

    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None
    names = [capwords(name) for name in store.list_player_keys()]
    return jsonify({"count": len(names), "items": names})

  @app.get("/api/presence")
  def presence_get() -> object:
    denied = require_read_access()
    if denied is not None:
      return denied

    active = sorted(capwords(name) for name in active_players)
    return jsonify({"count": len(active), "items": active})

  @app.post("/api/presence")
  def presence_set() -> object:
    denied = require_write_access()
    if denied is not None:
      return denied

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
      return jsonify({"error": "request body must be a JSON object"}), 400

    try:
      name = _normalize_player_name(payload.get("name"))
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 400

    active = payload.get("active")
    if not isinstance(active, bool):
      return jsonify({"error": "active must be true or false"}), 400

    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None

    if store.missing_players([name]):
      return jsonify({"error": "unknown player"}), 400

    if active:
      active_players.add(name)
    else:
      active_players.discard(name)

    return jsonify({"ok": True, "name": capwords(name), "active": active, "count": len(active_players)})

  @app.post("/api/presence/clear")
  def presence_clear() -> object:
    denied = require_write_access()
    if denied is not None:
      return denied

    active_players.clear()
    return jsonify({"ok": True, "count": 0})

  @app.post("/api/lineup/random")
  def random_lineup() -> object:
    denied = require_write_access()
    if denied is not None:
      return denied

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
      return jsonify({"error": "request body must be a JSON object"}), 400

    mode = payload.get("mode")
    if mode not in {"singles", "doubles"}:
      return jsonify({"error": "mode must be 'singles' or 'doubles'"}), 400

    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None

    known_players = set(store.list_player_keys())
    eligible = active_players.intersection(known_players)
    try:
      selected = _lineup_from_active_players(eligible, mode)
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 400

    return jsonify({"ok": True, "mode": mode, "selected": selected})

  @app.post("/api/lineup/auto")
  def auto_lineup() -> object:
    denied = require_write_access()
    if denied is not None:
      return denied

    try:
      selected = _validate_auto_payload(request.get_json(silent=True))
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 400

    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None

    ratings = store.get_player_ratings(list(selected.values()))
    missing = [name for name in selected.values() if name not in ratings]
    if missing:
      return jsonify({"error": "all selected players must exist"}), 400

    lineup = best_balanced_lineup(
      ratings,
      defense_a=selected["red_defense"],
      offense_a=selected["red_offense"],
      offense_b=selected["blue_offense"],
      defense_b=selected["blue_defense"],
    )

    if lineup is None:
      return jsonify({"error": "could not compute balanced lineup"}), 400

    return jsonify(
      {
        "ok": True,
        "mode": "doubles",
        "selected": {
          "red_defense": lineup[0],
          "red_offense": lineup[1],
          "blue_offense": lineup[2],
          "blue_defense": lineup[3],
        },
      }
    )

  @app.post("/api/players")
  def add_player() -> object:
    denied = require_write_access()
    if denied is not None:
      return denied

    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None

    try:
      player_name = _validate_new_player_name(request.get_json(silent=True))
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 400

    uses_lock = store.uses_local_lock
    if uses_lock and not _acquire_write_lock(data_dir, owner="phone"):
      return jsonify({"error": "another writer is active"}), 409

    try:
      result = store.add_player(player_name)
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 409
    except Exception:
      return jsonify({"error": "failed to persist player"}), 500
    finally:
      if uses_lock:
        _release_write_lock(data_dir)

    return jsonify(result), 201

  @app.get("/api/h2h")
  def h2h() -> object:
    denied = require_read_access()
    if denied is not None:
      return denied

    p1 = request.args.get("p1", "").strip().lower()
    p2 = request.args.get("p2", "").strip().lower()
    if not p1 or not p2 or p1 == p2:
      return jsonify({"error": "two distinct player names required"}), 400

    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None
    return jsonify(store.query_h2h(p1, p2))

  @app.get("/api/stats")
  def player_stats() -> object:
    denied = require_read_access()
    if denied is not None:
      return denied

    scope = request.args.get("scope", default="all", type=str)
    if scope not in {"all", "this_quarter", "this_month", "this_week"}:
      return jsonify({"error": "invalid scope"}), 400

    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None

    try:
      return jsonify(store.query_player_stats(scope=scope))
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 400

  @app.get("/api/player/<name>/history")
  def player_history(name: str) -> object:
    denied = require_read_access()
    if denied is not None:
      return denied

    name = name.strip().lower()
    n = request.args.get("n", default=10, type=int)
    n = max(1, min(n, 50))

    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None
    snapshots = store.query_rating_snapshots(name, n)
    return jsonify({"player": name, "count": len(snapshots), "snapshots": snapshots})

  @app.get("/api/player/<name>/profile")
  def player_profile(name: str) -> object:
    denied = require_read_access()
    if denied is not None:
      return denied

    name = name.strip().lower()
    scope = request.args.get("scope", default="all", type=str)
    if scope not in {"all", "this_quarter", "this_month", "this_week"}:
      return jsonify({"error": "invalid scope"}), 400
    recent_limit = request.args.get("recent_limit", default=5, type=int)
    recent_limit = max(1, min(recent_limit, 10))

    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None

    try:
      return jsonify(store.query_player_profile(name, scope=scope, recent_limit=recent_limit))
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 400

  @app.get("/api/odds")
  def match_odds() -> object:
    denied = require_read_access()
    if denied is not None:
      return denied

    red_off = request.args.get("red_off", "").strip().lower()
    blue_off = request.args.get("blue_off", "").strip().lower()
    red_def = request.args.get("red_def", "").strip().lower()
    blue_def = request.args.get("blue_def", "").strip().lower()
    mode = request.args.get("mode", "singles")
    if not red_off or not blue_off:
      return jsonify({"error": "offense players required"}), 400

    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None

    team1 = [red_off, red_def] if mode == "doubles" and red_def else [red_off]
    team2 = [blue_off, blue_def] if mode == "doubles" and blue_def else [blue_off]

    ratings = store.get_player_ratings(team1 + team2)
    if not ratings:
      return jsonify({"error": "no player data"}), 503
    missing = [n for n in team1 + team2 if n not in ratings]
    if missing:
      return jsonify({"error": "unknown players"}), 400

    probability, ratio = odds_ratio_for_teams(ratings, team1, team2)
    return jsonify({"probability": round(probability, 3), "ratio": ratio})

  @app.post("/api/matches")
  def submit_match() -> object:
    denied = require_write_access()
    if denied is not None:
      return denied

    store, error_response = _resolve_write_store()
    if error_response is not None:
      return error_response
    assert store is not None

    try:
      team1, team2, score1, score2 = _validate_match_payload(
        store,
        request.get_json(silent=True),
      )
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 400

    signature = _match_signature(team1, team2, score1, score2)
    now_monotonic = time.monotonic()
    if _is_recent_duplicate(signature, now_monotonic):
      return jsonify({"error": "duplicate match submission detected"}), 409

    uses_lock = store.uses_local_lock
    if uses_lock and not _acquire_write_lock(data_dir, owner="phone"):
      return jsonify({"error": "another writer is active"}), 409

    try:
      if _is_recent_duplicate(signature, time.monotonic()):
        return jsonify({"error": "duplicate match submission detected"}), 409
      result = store.submit_match(team1, team2, score1, score2, source="phone_api")
      _remember_match_signature(signature, time.monotonic())
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 400
    except Exception:
      return jsonify({"error": "failed to persist match result"}), 500
    finally:
      if uses_lock:
        _release_write_lock(data_dir)

    return jsonify(result), 201

  @app.get("/phone")
  def phone_view() -> str:
    store, error_response = _resolve_write_store()
    if error_response is not None:
      return _render_phone_html([])
    assert store is not None
    rows = _load_leaderboard(store, limit=50)
    return _render_phone_html(rows)

  @app.get("/")
  def root() -> object:
    return redirect("/phone", code=302)

  return app


def main() -> None:
  parser = argparse.ArgumentParser(description="Run the Fusball phone API server")
  parser.add_argument(
    "--db-dir",
    default=os.environ.get("FUSBALL_PHONE_API_DB_DIR"),
    help="Directory containing playerdb/recentplayers/match_history/logfile files",
  )
  args = parser.parse_args()

  db_dir = Path(args.db_dir).resolve() if args.db_dir else ROOT_DIR
  app = create_app(
    db_dir=db_dir,
    operator_token=os.environ.get("FUSBALL_PHONE_API_TOKEN"),
    read_pin_hash=os.environ.get("READ_PIN_HASH"),
    write_pin_hash=os.environ.get("WRITE_PIN_HASH"),
    database_url=os.environ.get("DATABASE_URL"),
  )
  app.run(host="0.0.0.0", port=8080, debug=False)


if __name__ == "__main__":
    main()

