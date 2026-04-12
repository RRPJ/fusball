from __future__ import annotations

import shelve
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import trueskill

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from odds import findRank, playerLevel, win_probability  # noqa: E402
from services.match_history import append_match_history  # noqa: E402
from services.match_service import calculate_rating_update  # noqa: E402


def seed_players(db: shelve.Shelf) -> None:
    db["alice"] = (trueskill.Rating(mu=35, sigma=6), trueskill.Rating(mu=34, sigma=6))
    db["bob"] = (trueskill.Rating(mu=30, sigma=7), trueskill.Rating(mu=28, sigma=7))
    db["carol"] = (trueskill.Rating(mu=27, sigma=8), trueskill.Rating(mu=26, sigma=8))
    db["dave"] = (trueskill.Rating(mu=24, sigma=8), trueskill.Rating(mu=23, sigma=8))


def _assert_history_matches_current_ratings(tmpdir: str) -> None:
    tmp_path = Path(tmpdir)
    db_path = str(tmp_path / "playerdb")

    team1 = ["alice", "bob"]
    team2 = ["carol", "dave"]

    with shelve.open(db_path) as db:
        before_ratings = {
            name: db[name]
            for team in (team1, team2)
            for name in team
        }

        updated = calculate_rating_update(db, team1, team2, 5, 3)
        for name in team1 + team2:
            db[name] = updated[name]

        after_ratings = {
            name: db[name]
            for team in (team1, team2)
            for name in team
        }

    record_key = append_match_history(
        tmp_path,
        team1,
        team2,
        team1,
        5,
        3,
        before_ratings,
        after_ratings,
        source="smoke_check",
    )

    with shelve.open(str(tmp_path / "match_history")) as history:
        record = history[record_key]

    if record["team1"] != team1 or record["team2"] != team2:
        raise AssertionError("History record team assignments mismatch")
    if record["winner"] != team1:
        raise AssertionError("History record winner mismatch")
    if record["score1"] != 5 or record["score2"] != 3:
        raise AssertionError("History record score mismatch")

    players_in_record = {entry["name"]: entry for entry in record["players"]}
    with shelve.open(db_path) as db:
        for name in team1 + team2:
            if name not in players_in_record:
                raise AssertionError(f"Player {name} missing from history record")

            entry = players_in_record[name]
            current = db[name]
            after = entry["after"]
            if abs(after["offense_mu"] - float(current[0].mu)) > 1e-9:
                raise AssertionError(f"offense_mu mismatch for {name}")
            if abs(after["offense_sigma"] - float(current[0].sigma)) > 1e-9:
                raise AssertionError(f"offense_sigma mismatch for {name}")
            if abs(after["defense_mu"] - float(current[1].mu)) > 1e-9:
                raise AssertionError(f"defense_mu mismatch for {name}")
            if abs(after["defense_sigma"] - float(current[1].sigma)) > 1e-9:
                raise AssertionError(f"defense_sigma mismatch for {name}")


def run_checks() -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "playerdb")

        with shelve.open(db_path) as db:
            seed_players(db)

        with shelve.open(db_path) as db:
            ranked = sorted(db.items(), key=lambda kv: playerLevel(kv[1]), reverse=True)
            if ranked[0][0] != "alice":
                raise AssertionError("Expected alice to be top-ranked in seeded data")

            rank_label = findRank(db, "alice")
            if not rank_label:
                raise AssertionError("findRank returned an empty label")

            team1 = [db["alice"], db["bob"]]
            team2 = [db["carol"], db["dave"]]
            probability = win_probability(team1, team2)
            if not 0.0 < probability < 1.0:
                raise AssertionError(f"Win probability out of range: {probability}")

        _assert_history_matches_current_ratings(tmpdir)

    print("Smoke check passed: ranking, probability, and history consistency are healthy.")


if __name__ == "__main__":
    run_checks()
