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
import re
import shelve
from pathlib import Path
from string import capwords

from flask import Flask, jsonify, request

from odds import playerLevel
import trueskill as _trueskill
from services.match_history import (
    append_match_history,
    query_h2h,
    query_player_stats,
    query_rating_snapshots,
)
from services.match_log import append_match_log
from services.match_service import calculate_rating_update
from services.player_store import rank_labels_by_name, ranked_players


ROOT_DIR = Path(__file__).resolve().parent
WRITE_LOCK_NAME = "phone_api_write.lock"
OPERATOR_TOKEN_HEADER = "X-Operator-Token"


def _playerdb_exists(db_dir: Path) -> bool:
    """Return whether any shelve artifact for playerdb exists in the directory."""
    return any(db_dir.glob("playerdb*"))


def _load_leaderboard(db_dir: Path, limit: int = 50) -> list[dict[str, object]]:
    db_path = db_dir / "playerdb"
    if not _playerdb_exists(db_dir):
        return []

    with shelve.open(str(db_path)) as players:
        ranked = ranked_players(players.items())
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


def _load_player_names(db_dir: Path) -> list[str]:
    db_path = db_dir / "playerdb"
    if not _playerdb_exists(db_dir):
        return []

    with shelve.open(str(db_path)) as players:
        return sorted(capwords(name) for name in players.keys())


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


def _validate_match_payload(db_dir: Path, payload: object) -> tuple[list[str], list[str], int, int]:
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

    db_path = db_dir / "playerdb"
    with shelve.open(str(db_path)) as players:
        missing = [name for name in all_players if name not in players]
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


def _submit_match_result(
    db_dir: Path,
    team1: list[str],
    team2: list[str],
    score1: int,
    score2: int,
) -> dict[str, object]:
  db_path = db_dir / "playerdb"
  logfile_path = db_dir / "logfile.log"
  winning_team = team1 if score1 > score2 else team2

  with shelve.open(str(db_path)) as players:
    before_ratings = {
      name: players[name]
      for team in (team1, team2)
      for name in team
    }
    updated = calculate_rating_update(players, team1, team2, score1, score2)

    for name in team1 + team2:
      players[name] = updated[name]

    after_ratings = {
      name: players[name]
      for team in (team1, team2)
      for name in team
    }

  try:
    append_match_log(
      str(logfile_path),
      team1,
      team2,
      winning_team,
      before_ratings,
      after_ratings,
    )
    append_match_history(
      db_dir,
      team1,
      team2,
      winning_team,
      score1,
      score2,
      before_ratings,
      after_ratings,
      source="phone_api",
    )
  except Exception:
    with shelve.open(str(db_path)) as players:
      for name, rating in before_ratings.items():
        players[name] = rating
    raise

  return {
    "ok": True,
    "team1": team1,
    "team2": team2,
    "score1": score1,
    "score2": score2,
    "winner": winning_team,
  }


def _submit_new_player(db_dir: Path, player_name: str) -> dict[str, object]:
    db_path = db_dir / "playerdb"
    with shelve.open(str(db_path)) as players:
        if player_name in players:
            raise ValueError("player already exists")
        players[player_name] = (_trueskill.Rating(), _trueskill.Rating())

    with shelve.open(str(db_dir / "recentplayers")) as recent:
        names = recent.get("names", [])
        merged = [player_name] + [n for n in names if n != player_name]
        recent["names"] = merged

    return {
        "ok": True,
        "name": capwords(player_name),
    }


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
  <title>Dustin Fusball Phone Console</title>
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
    .players { max-height: 220px; overflow: auto; padding-right: 4px; }
    .score-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 10px; align-items: center; }
    .status { margin-top: 8px; font-size: 0.84rem; min-height: 18px; color: var(--muted); }
    .status.ok { color: var(--ok); }
    .status.bad { color: var(--bad); }
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
    .form-w { color:var(--ok); font-weight:700; }
    .form-l { color:var(--bad); }
    .expand-panel { padding:10px 8px; background:rgba(8,20,30,0.85); border-top:1px solid var(--line); font-size:0.82rem; color:var(--muted); }
    .expand-panel .delta-pos { color:var(--ok); }
    .expand-panel .delta-neg { color:var(--bad); }
    .expand-panel .kv { margin-bottom:4px; }
    .lrow { cursor:pointer; }
    .lrow:active td { background:rgba(239,138,23,0.06); }
    .filter-row { margin: 0 0 8px; }
  </style>
</head>
<body>
  <main class='panel'>
    <header>
      <h1>Dustin Fusball Phone Console</h1>
      <div class='muted'>Button-driven setup, score, confirm, submit</div>
      <div class='progress'>
        <button id='stepBtn1' type='button' class='active'>1 Mode</button>
        <button id='stepBtn2' type='button'>2 Players</button>
        <button id='stepBtn3' type='button'>3 Score</button>
        <button id='stepBtn4' type='button'>4 Confirm</button>
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
        <button id='undoBtn' class='btn small' type='button'>Undo Last Pick</button>
        <button id='clearBtn' class='btn small' type='button'>Clear</button>
      </div>
      <div id='playersPanel' class='row players'></div>
      <div id='oddsText' class='status' style='margin-top:8px;'></div>
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
      <div id='statusText' class='status'></div>
    </section>

    <section id='step4' class='section'>
      <h2>Step 4: Confirm And Submit</h2>
      <div class='review-card' id='reviewText'>Complete setup to review match.</div>
      <div style='margin-top:10px;'>
        <input id='operatorToken' class='token' type='password' placeholder='Operator token (X-Operator-Token)' />
      </div>
      <div class='muted' style='margin-top:8px;'>Token is remembered for this tab session. Submit is enabled only when lineup and score are valid.</div>
    </section>

    <section class='section active'>
      <h2>Leaderboard</h2>
      <div class='muted'>Refreshes after successful submit.</div>
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
        <button id='filterMin5Btn' class='btn sort' type='button'>Min 5 games</button>
        <button id='filterRecent30Btn' class='btn sort' type='button'>Last 30d</button>
      </div>
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
      step: 1,
      mode: 'singles',
      activeSlot: 'red_offense',
      leaderboardSort: 'total',
      leaderboardFilter: 'all',
      leaderboardItems: [],
      playerStats: null,
      expandedPlayer: null,
      h2hOpen: false,
      players: [],
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

    function setStatus(text, type = '') {
      const node = document.getElementById('statusText');
      node.textContent = text;
      node.className = 'status' + (type ? ' ' + type : '');
    }

    function setAddPlayerStatus(text, type = '') {
      const node = document.getElementById('addPlayerStatus');
      node.textContent = text;
      node.className = 'status' + (type ? ' ' + type : '');
    }

    function ensureOperatorToken() {
      const tokenInput = document.getElementById('operatorToken');
      let token = (tokenInput.value || '').trim();
      if (token) {
        return token;
      }

      const entered = (window.prompt('Enter operator token') || '').trim();
      if (!entered) {
        return '';
      }

      tokenInput.value = entered;
      sessionStorage.setItem('fusball_token', entered);
      return entered;
    }

    function setMode(mode) {
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
      const panel = document.getElementById('playersPanel');
      panel.innerHTML = '';
      for (const name of state.players) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn small';
        button.textContent = name;
        button.addEventListener('click', () => assignPlayer(name));
        panel.appendChild(button);
      }
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
    }

    function renderScoreButtons() {
      const redPanel = document.getElementById('scoreRed');
      const bluePanel = document.getElementById('scoreBlue');
      redPanel.innerHTML = '';
      bluePanel.innerHTML = '';
      for (let i = 0; i <= 5; i += 1) {
        const redBtn = document.createElement('button');
        redBtn.type = 'button';
        redBtn.className = 'btn small' + (state.score1 === i ? ' active' : '');
        redBtn.textContent = String(i);
        redBtn.addEventListener('click', () => setScore('red', i));
        redPanel.appendChild(redBtn);

        const blueBtn = document.createElement('button');
        blueBtn.type = 'button';
        blueBtn.className = 'btn small' + (state.score2 === i ? ' active' : '');
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
      if (state.leaderboardFilter === 'all' || !state.playerStats) return items;
      const s = state.playerStats;
      const now = Date.now();
      const ms30d = 30 * 24 * 60 * 60 * 1000;
      return items.filter(row => {
        const k = row.name.toLowerCase();
        const ps = s[k];
        if (!ps) return false;
        if (state.leaderboardFilter === 'min5') return ps.games >= 5;
        if (state.leaderboardFilter === 'recent30') {
          if (!ps.last_match) return false;
          return (now - new Date(ps.last_match).getTime()) <= ms30d;
        }
        return true;
      });
    }

    function setLeaderboardSort(mode) {
      state.leaderboardSort = mode;
      const ids = ['sortTotalBtn','sortAtkBtn','sortDefBtn','sortFormBtn','sortStreakBtn','sortImprovedBtn'];
      const modes = ['total','offense','defense','form','streak','improved'];
      const headers = ['Total','Offense','Defense','Form','Streak','Improved'];
      ids.forEach((id, i) => document.getElementById(id).classList.toggle('active', modes[i] === mode));
      const hdr = document.getElementById('lbMetricHeader');
      if (hdr) hdr.textContent = headers[modes.indexOf(mode)] || 'Total';
      const statsNeeded = ['form','streak','improved'].includes(mode);
      if (statsNeeded && !state.playerStats) {
        fetch('/api/stats').then(r => r.json()).then(data => { state.playerStats = data; renderLeaderboard(state.leaderboardItems); });
      } else {
        renderLeaderboard(state.leaderboardItems);
      }
    }

    function setLeaderboardFilter(f) {
      state.leaderboardFilter = f;
      document.getElementById('filterAllBtn').classList.toggle('active', f === 'all');
      document.getElementById('filterMin5Btn').classList.toggle('active', f === 'min5');
      document.getElementById('filterRecent30Btn').classList.toggle('active', f === 'recent30');
      const needsStats = f !== 'all';
      if (needsStats && !state.playerStats) {
        fetch('/api/stats').then(r => r.json()).then(data => { state.playerStats = data; renderLeaderboard(state.leaderboardItems); });
      } else {
        renderLeaderboard(state.leaderboardItems);
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

    async function togglePlayerHistory(rowEl, playerKey) {
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
      td.innerHTML = '<div class="kv">Loading progression…</div>';
      tr.appendChild(td);
      rowEl.after(tr);
      try {
        const resp = await fetch(`/api/player/${encodeURIComponent(playerKey)}/history?n=6`);
        if (!resp.ok) { td.innerHTML = '<div class="kv">No history available.</div>'; return; }
        const data = await resp.json();
        if (!data.snapshots || data.snapshots.length === 0) { td.innerHTML = '<div class="kv">No matches recorded yet.</div>'; return; }
        const rows = data.snapshots.slice(-5).reverse().map(s => {
          const dOff = (s.after.offense_mu - s.before.offense_mu).toFixed(1);
          const dDef = (s.after.defense_mu - s.before.defense_mu).toFixed(1);
          const offStr = `<span class='${dOff >= 0 ? "delta-pos" : "delta-neg"}'>${dOff >= 0 ? '+' : ''}${dOff}</span>`;
          const defStr = `<span class='${dDef >= 0 ? "delta-pos" : "delta-neg"}'>${dDef >= 0 ? '+' : ''}${dDef}</span>`;
          const result = s.won ? `<span class='form-w'>W</span>` : `<span class='form-l'>L</span>`;
          const date = s.timestamp ? s.timestamp.slice(0, 10) : '?';
          return `<div class='kv'>${result} ${date} Off ${offStr} Def ${defStr}</div>`;
        }).join('');
        td.innerHTML = `<div style='font-size:0.75rem;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.04em;'>Last ${data.snapshots.length} matches</div>${rows}`;
      } catch { td.innerHTML = '<div class="kv">Could not load history.</div>'; }
    }

    function updateSummary() {
      const red = state.mode === 'doubles'
        ? `${state.selected.red_offense || '?'} / ${state.selected.red_defense || '?'}`
        : `${state.selected.red_offense || '?'}`;
      const blue = state.mode === 'doubles'
        ? `${state.selected.blue_offense || '?'} / ${state.selected.blue_defense || '?'}`
        : `${state.selected.blue_offense || '?'}`;
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

    function updateReview() {
      const review = document.getElementById('reviewText');
      try {
        const payload = buildPayload();
        const winner = payload.score1 > payload.score2 ? payload.team1.join(' + ') : payload.team2.join(' + ');
        review.innerHTML =
          `<div><strong>Red:</strong> ${payload.team1.join(' + ')}</div>` +
          `<div><strong>Blue:</strong> ${payload.team2.join(' + ')}</div>` +
          `<div><strong>Score:</strong> ${payload.score1} - ${payload.score2}</div>` +
          `<div><strong>Winner:</strong> ${winner}</div>`;
      } catch {
        review.textContent = 'Complete lineup and score to enable submit.';
      }
    }

    function setStep(step) {
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
      document.getElementById('backBtn').style.visibility = state.step === 1 ? 'hidden' : 'visible';
      document.getElementById('nextBtn').style.display = state.step === 4 ? 'none' : 'inline-block';
      document.getElementById('submitBtn').style.display = state.step === 4 ? 'inline-block' : 'none';
      document.getElementById('nextBtn').disabled = !isStepComplete(state.step);
      if (state.step === 4) {
        updateReview();
      }
    }

    async function refreshLeaderboard() {
      const response = await fetch('/api/leaderboard?limit=50');
      if (!response.ok) {
        throw new Error('Could not refresh leaderboard.');
      }
      const payload = await response.json();
      renderLeaderboard(payload.items || []);
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
      const card = document.getElementById('h2hCard');
      const toggleRow = document.getElementById('h2hToggleRow');
      if (!redOff || !blueOff) {
        toggleRow.style.display = 'none';
        card.classList.remove('open');
        return;
      }
      toggleRow.style.display = '';
      if (!state.h2hOpen) return;
      card.innerHTML = '<span class="muted">Loading\u2026</span>';
      fetch(`/api/h2h?p1=${encodeURIComponent(redOff.toLowerCase())}&p2=${encodeURIComponent(blueOff.toLowerCase())}`)
        .then(r => r.json())
        .then(d => {
          if (d.matches === 0) {
            card.innerHTML = '<span class="muted">No recorded matches between these players yet.</span>';
          } else {
            const last = d.last_match ? d.last_match.slice(0, 10) : '?';
            card.innerHTML =
              `<div><strong>${redOff}</strong> ${d.p1_wins}\u2013${d.p2_wins} <strong>${blueOff}</strong>` +
              (d.draws ? ` (${d.draws} draw${d.draws > 1 ? 's' : ''})` : '') +
              `</div><div class='muted' style='margin-top:4px;'>` +
              `${d.matches} match${d.matches > 1 ? 'es' : ''} \u00b7 last ${last}</div>`;
          }
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
      const redOff = state.selected.red_offense;
      const blueOff = state.selected.blue_offense;
      const node = document.getElementById('oddsText');
      if (!node) return;
      if (!redOff || !blueOff) { node.textContent = ''; node.className = 'status'; refreshH2H(); return; }
      const params = new URLSearchParams({ red_off: redOff.toLowerCase(), blue_off: blueOff.toLowerCase(), mode: state.mode });
      if (state.mode === 'doubles') {
        if (state.selected.red_defense) params.set('red_def', state.selected.red_defense.toLowerCase());
        if (state.selected.blue_defense) params.set('blue_def', state.selected.blue_defense.toLowerCase());
      }
      try {
        const resp = await fetch('/api/odds?' + params.toString());
        if (!resp.ok) { node.textContent = ''; return; }
        const data = await resp.json();
        const redPct = Math.round(data.probability * 100);
        const bluePct = 100 - redPct;
        const score = predictedScore(data.probability);
        const [favored, favoredPct] = redPct >= 50 ? [redOff + ' side', redPct] : [blueOff + ' side', bluePct];
        const label = oddsLabel(data.probability);
        const upset = hasUpsetRisk(data.probability);
        const badgeHtml = `<span class='badge ${label.cls}'>${label.text}</span>` +
          (upset ? `<span class='badge badge-bad'>Upset Risk</span>` : '');
        node.innerHTML = `Odds: ${data.ratio} \u2014 ${favored} favored (${favoredPct}%) \u2014 Predicted: ${score} ${badgeHtml}`;
        node.className = 'status ok';
        refreshH2H();
      } catch {
        node.textContent = '';
        node.className = 'status';
      }
    }

    async function loadPlayers() {
      const response = await fetch('/api/players');
      if (!response.ok) {
        throw new Error('Could not load players.');
      }
      const payload = await response.json();
      state.players = payload.items || [];
      renderPlayerButtons();
    }

    async function submitMatch() {
      const token = document.getElementById('operatorToken').value.trim();
      if (!token) {
        setStatus('Enter operator token first.', 'bad');
        return;
      }

      let payload;
      try {
        payload = buildPayload();
      } catch (error) {
        setStatus(error.message, 'bad');
        return;
      }

      setStatus('Submitting result...');
      const response = await fetch('/api/matches', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Operator-Token': token,
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
    }

    async function addPlayer() {
      const token = ensureOperatorToken();
      if (!token) {
        setAddPlayerStatus('Operator token is required to add players.', 'bad');
        return;
      }

      const input = document.getElementById('newPlayerName');
      const name = input.value.trim();
      if (!name) {
        setAddPlayerStatus('Enter a player name.', 'bad');
        return;
      }

      setAddPlayerStatus('Adding player...');
      const response = await fetch('/api/players', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Operator-Token': token,
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
    document.getElementById('undoBtn').addEventListener('click', undoLastPick);
    document.getElementById('clearBtn').addEventListener('click', clearSelection);
    document.getElementById('sortTotalBtn').addEventListener('click', () => setLeaderboardSort('total'));
    document.getElementById('sortAtkBtn').addEventListener('click', () => setLeaderboardSort('offense'));
    document.getElementById('sortDefBtn').addEventListener('click', () => setLeaderboardSort('defense'));
    document.getElementById('sortFormBtn').addEventListener('click', () => setLeaderboardSort('form'));
    document.getElementById('sortStreakBtn').addEventListener('click', () => setLeaderboardSort('streak'));
    document.getElementById('sortImprovedBtn').addEventListener('click', () => setLeaderboardSort('improved'));
    document.getElementById('filterAllBtn').addEventListener('click', () => setLeaderboardFilter('all'));
    document.getElementById('filterMin5Btn').addEventListener('click', () => setLeaderboardFilter('min5'));
    document.getElementById('filterRecent30Btn').addEventListener('click', () => setLeaderboardFilter('recent30'));
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
    renderScoreButtons();
    renderSlots();
    updateSummary();
    updateReview();
    refreshLeaderboard().catch(() => undefined);
    loadPlayers().catch((e) => setStatus(e.message, 'bad'));

    const tokenInput = document.getElementById('operatorToken');
    const savedToken = sessionStorage.getItem('fusball_token');
    if (savedToken) {
      tokenInput.value = savedToken;
    }
    tokenInput.addEventListener('input', () => {
      const val = tokenInput.value.trim();
      if (val) {
        sessionStorage.setItem('fusball_token', val);
      } else {
        sessionStorage.removeItem('fusball_token');
      }
    });
  </script>
</body>
</html>"""
    return html.replace("__TABLE_ROWS__", table_rows)


def create_app(db_dir: Path | None = None, operator_token: str | None = None) -> Flask:
  """Create the phone API app.

  Args:
    db_dir: Directory containing shelve files. Defaults to app directory.
    operator_token: Shared secret required for write requests.
  """
  app = Flask(__name__)
  data_dir = db_dir or ROOT_DIR
  app.config["OPERATOR_TOKEN"] = operator_token

  @app.get("/api/health")
  def health() -> object:
    return jsonify({"ok": True})

  @app.get("/api/leaderboard")
  def leaderboard() -> object:
    limit = request.args.get("limit", default=50, type=int)
    limit = max(1, min(limit, 200))
    rows = _load_leaderboard(data_dir, limit)
    return jsonify({"count": len(rows), "items": rows})

  @app.get("/api/players")
  def players() -> object:
    names = _load_player_names(data_dir)
    return jsonify({"count": len(names), "items": names})

  @app.post("/api/players")
  def add_player() -> object:
    token = app.config.get("OPERATOR_TOKEN")
    if not token:
      return jsonify({"error": "write endpoint not configured"}), 503

    provided_token = request.headers.get(OPERATOR_TOKEN_HEADER)
    if provided_token != token:
      return jsonify({"error": "unauthorized"}), 401

    try:
      player_name = _validate_new_player_name(request.get_json(silent=True))
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 400

    if not _acquire_write_lock(data_dir, owner="phone"):
      return jsonify({"error": "another writer is active"}), 409

    try:
      result = _submit_new_player(data_dir, player_name)
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 409
    except Exception:
      return jsonify({"error": "failed to persist player"}), 500
    finally:
      _release_write_lock(data_dir)

    return jsonify(result), 201

  @app.get("/api/h2h")
  def h2h() -> object:
    p1 = request.args.get("p1", "").strip().lower()
    p2 = request.args.get("p2", "").strip().lower()
    if not p1 or not p2 or p1 == p2:
      return jsonify({"error": "two distinct player names required"}), 400
    return jsonify(query_h2h(data_dir, p1, p2))

  @app.get("/api/stats")
  def player_stats() -> object:
    return jsonify(query_player_stats(data_dir))

  @app.get("/api/player/<name>/history")
  def player_history(name: str) -> object:
    name = name.strip().lower()
    n = request.args.get("n", default=10, type=int)
    n = max(1, min(n, 50))
    snapshots = query_rating_snapshots(data_dir, name, n)
    return jsonify({"player": name, "count": len(snapshots), "snapshots": snapshots})

  @app.get("/api/odds")
  def match_odds() -> object:
    red_off = request.args.get("red_off", "").strip().lower()
    blue_off = request.args.get("blue_off", "").strip().lower()
    red_def = request.args.get("red_def", "").strip().lower()
    blue_def = request.args.get("blue_def", "").strip().lower()
    mode = request.args.get("mode", "singles")
    if not red_off or not blue_off:
      return jsonify({"error": "offense players required"}), 400
    team1 = [red_off, red_def] if mode == "doubles" and red_def else [red_off]
    team2 = [blue_off, blue_def] if mode == "doubles" and blue_def else [blue_off]
    db_path = data_dir / "playerdb"
    if not _playerdb_exists(data_dir):
      return jsonify({"error": "no player data"}), 503
    with shelve.open(str(db_path)) as pl:
      missing = [n for n in team1 + team2 if n not in pl]
      if missing:
        return jsonify({"error": "unknown players"}), 400
      from services.match_service import odds_ratio_for_teams
      probability, ratio = odds_ratio_for_teams(pl, team1, team2)
    return jsonify({"probability": round(probability, 3), "ratio": ratio})

  @app.post("/api/matches")
  def submit_match() -> object:
    token = app.config.get("OPERATOR_TOKEN")
    if not token:
      return jsonify({"error": "write endpoint not configured"}), 503

    provided_token = request.headers.get(OPERATOR_TOKEN_HEADER)
    if provided_token != token:
      return jsonify({"error": "unauthorized"}), 401

    try:
      team1, team2, score1, score2 = _validate_match_payload(
        data_dir,
        request.get_json(silent=True),
      )
    except ValueError as exc:
      return jsonify({"error": str(exc)}), 400

    if not _acquire_write_lock(data_dir, owner="phone"):
      return jsonify({"error": "another writer is active"}), 409

    try:
      result = _submit_match_result(data_dir, team1, team2, score1, score2)
    except Exception:
      return jsonify({"error": "failed to persist match result"}), 500
    finally:
      _release_write_lock(data_dir)

    return jsonify(result), 201

  @app.get("/phone")
  def phone_view() -> str:
    rows = _load_leaderboard(data_dir, limit=50)
    return _render_phone_html(rows)

  return app


def main() -> None:
  parser = argparse.ArgumentParser(description="Run the phone API server")
  parser.add_argument(
    "--db-dir",
    default=os.environ.get("FUSBALL_PHONE_API_DB_DIR"),
    help="Directory containing playerdb/recentplayers/tagdb/logfile files",
  )
  args = parser.parse_args()

  db_dir = Path(args.db_dir).resolve() if args.db_dir else ROOT_DIR
  app = create_app(db_dir=db_dir, operator_token=os.environ.get("FUSBALL_PHONE_API_TOKEN"))
  app.run(host="0.0.0.0", port=8080, debug=False)


if __name__ == "__main__":
    main()

