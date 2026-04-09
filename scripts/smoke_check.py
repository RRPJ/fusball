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


def seed_players(db: shelve.Shelf) -> None:
    db["alice"] = (trueskill.Rating(mu=35, sigma=6), trueskill.Rating(mu=34, sigma=6))
    db["bob"] = (trueskill.Rating(mu=30, sigma=7), trueskill.Rating(mu=28, sigma=7))
    db["carol"] = (trueskill.Rating(mu=27, sigma=8), trueskill.Rating(mu=26, sigma=8))
    db["dave"] = (trueskill.Rating(mu=24, sigma=8), trueskill.Rating(mu=23, sigma=8))


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

    print("Smoke check passed: ranking and probability logic are healthy.")


if __name__ == "__main__":
    run_checks()
