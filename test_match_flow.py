from __future__ import annotations

import shelve
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import trueskill

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.match_log import append_match_log  # noqa: E402
from services.match_service import best_balanced_lineup, calculate_rating_update  # noqa: E402


def _lineup_quality(players: dict[str, tuple], lineup: list[str]) -> float:
    """Calculate quality for a lineup in slot order [A def, A off, B off, B def]."""
    team_a = (players[lineup[1]][0], players[lineup[0]][1])
    team_b = (players[lineup[2]][0], players[lineup[3]][1])
    return trueskill.quality([team_a, team_b])


class MatchFlowTests(unittest.TestCase):
    def test_rating_update_win_and_draw_cycles(self) -> None:
        players = {
            "alice": (trueskill.Rating(mu=25, sigma=8), trueskill.Rating(mu=25, sigma=8)),
            "bob": (trueskill.Rating(mu=25, sigma=8), trueskill.Rating(mu=25, sigma=8)),
            "carol": (trueskill.Rating(mu=25, sigma=8), trueskill.Rating(mu=25, sigma=8)),
            "dave": (trueskill.Rating(mu=25, sigma=8), trueskill.Rating(mu=25, sigma=8)),
        }

        updated_win = calculate_rating_update(
            players,
            ["alice", "bob"],
            ["carol", "dave"],
            5,
            2,
        )
        self.assertGreater(updated_win["alice"][0].mu, players["alice"][0].mu)
        self.assertGreater(updated_win["bob"][1].mu, players["bob"][1].mu)
        self.assertLess(updated_win["carol"][0].mu, players["carol"][0].mu)
        self.assertLess(updated_win["dave"][1].mu, players["dave"][1].mu)

        draw_players = {
            "eve": (trueskill.Rating(mu=30, sigma=6), trueskill.Rating(mu=30, sigma=6)),
            "frank": (trueskill.Rating(mu=30, sigma=6), trueskill.Rating(mu=30, sigma=6)),
        }
        updated_draw = calculate_rating_update(draw_players, ["eve"], ["frank"], 3, 3)

        self.assertAlmostEqual(updated_draw["eve"][0].mu, draw_players["eve"][0].mu, places=10)
        self.assertAlmostEqual(updated_draw["eve"][1].mu, draw_players["eve"][1].mu, places=10)
        self.assertAlmostEqual(updated_draw["frank"][0].mu, draw_players["frank"][0].mu, places=10)
        self.assertAlmostEqual(updated_draw["frank"][1].mu, draw_players["frank"][1].mu, places=10)

    def test_match_save_flow_persists_and_logs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            log_path = str(tmp_path / "logfile.log")

            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(mu=34, sigma=6), trueskill.Rating(mu=33, sigma=6))
                players["bob"] = (trueskill.Rating(mu=32, sigma=6), trueskill.Rating(mu=31, sigma=6))
                players["carol"] = (trueskill.Rating(mu=29, sigma=7), trueskill.Rating(mu=28, sigma=7))
                players["dave"] = (trueskill.Rating(mu=27, sigma=7), trueskill.Rating(mu=26, sigma=7))

            team1 = ["alice", "bob"]
            team2 = ["carol", "dave"]

            with shelve.open(db_path) as players:
                before_ratings = {
                    name: players[name]
                    for team in (team1, team2)
                    for name in team
                }
                updated = calculate_rating_update(players, team1, team2, 5, 3)

                for name in team1 + team2:
                    players[name] = updated[name]

                after_ratings = {
                    name: players[name]
                    for team in (team1, team2)
                    for name in team
                }

            append_match_log(log_path, team1, team2, team1, before_ratings, after_ratings)

            with shelve.open(db_path) as players:
                self.assertNotEqual(players["alice"][0].mu, before_ratings["alice"][0].mu)
                self.assertNotEqual(players["dave"][1].mu, before_ratings["dave"][1].mu)

            log_text = Path(log_path).read_text(encoding="utf-8")
            self.assertIn("match played between ['alice', 'bob'] and ['carol', 'dave']", log_text)
            self.assertIn("won by ['alice', 'bob']", log_text)
            for name in ("alice", "bob", "carol", "dave"):
                self.assertIn(f": {name}: offensive before:", log_text)
                self.assertIn(f": {name}: defensive before:", log_text)

    def test_auto_balance_lineup_behavior(self) -> None:
        players = {
            "ada": (trueskill.Rating(mu=20, sigma=7), trueskill.Rating(mu=38, sigma=6)),
            "bert": (trueskill.Rating(mu=39, sigma=6), trueskill.Rating(mu=18, sigma=7)),
            "cara": (trueskill.Rating(mu=22, sigma=7), trueskill.Rating(mu=36, sigma=6)),
            "dion": (trueskill.Rating(mu=37, sigma=6), trueskill.Rating(mu=21, sigma=7)),
        }

        current_layout = ["ada", "bert", "cara", "dion"]
        result = best_balanced_lineup(players, "ada", "bert", "cara", "dion")
        self.assertIsNotNone(result)

        assert result is not None
        self.assertEqual(sorted(result), sorted(current_layout))
        self.assertGreaterEqual(_lineup_quality(players, result), _lineup_quality(players, current_layout))

        repeat = best_balanced_lineup(players, "ada", "bert", "cara", "dion")
        self.assertEqual(result, repeat)
        self.assertIsNone(best_balanced_lineup(players, "ada", "bert", "cara", "missing"))


if __name__ == "__main__":
    unittest.main()
