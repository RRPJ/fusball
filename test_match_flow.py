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

from services.match_history import append_match_history, replay_scope_ratings  # noqa: E402
from services.match_log import append_match_log  # noqa: E402
from services.match_service import best_balanced_lineup, calculate_rating_update  # noqa: E402
from services.phone_write_store import ShelveWriteStore  # noqa: E402
from services.store_contracts import ReplayParityError  # noqa: E402


def _lineup_quality(players: dict[str, tuple], lineup: list[str]) -> float:
    """Calculate quality for a lineup in slot order [A def, A off, B off, B def]."""
    team_a = (players[lineup[1]][0], players[lineup[0]][1])
    team_b = (players[lineup[2]][0], players[lineup[3]][1])
    return trueskill.quality([team_a, team_b])


class MatchFlowTests(unittest.TestCase):
    def assertRatingPairAlmostEqual(self, actual: tuple, expected: tuple) -> None:
        for actual_rating, expected_rating in zip(actual, expected):
            self.assertAlmostEqual(actual_rating.mu, expected_rating.mu, places=10)
            self.assertAlmostEqual(actual_rating.sigma, expected_rating.sigma, places=10)

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
                players["alice"] = (
                    trueskill.Rating(mu=34, sigma=6),
                    trueskill.Rating(mu=33, sigma=6),
                )
                players["bob"] = (
                    trueskill.Rating(mu=32, sigma=6),
                    trueskill.Rating(mu=31, sigma=6),
                )
                players["carol"] = (
                    trueskill.Rating(mu=29, sigma=7),
                    trueskill.Rating(mu=28, sigma=7),
                )
                players["dave"] = (
                    trueskill.Rating(mu=27, sigma=7),
                    trueskill.Rating(mu=26, sigma=7),
                )

            team1 = ["alice", "bob"]
            team2 = ["carol", "dave"]

            with shelve.open(db_path) as players:
                before_ratings = {name: players[name] for team in (team1, team2) for name in team}
                updated = calculate_rating_update(players, team1, team2, 5, 3)

                for name in team1 + team2:
                    players[name] = updated[name]

                after_ratings = {name: players[name] for team in (team1, team2) for name in team}

            append_match_log(log_path, team1, team2, team1, before_ratings, after_ratings)
            append_match_history(
                tmp_path,
                team1,
                team2,
                team1,
                5,
                3,
                before_ratings,
                after_ratings,
                source="test",
            )

            with shelve.open(db_path) as players:
                self.assertNotEqual(players["alice"][0].mu, before_ratings["alice"][0].mu)
                self.assertNotEqual(players["dave"][1].mu, before_ratings["dave"][1].mu)

            log_text = Path(log_path).read_text(encoding="utf-8")
            self.assertIn("match played between ['alice', 'bob'] and ['carol', 'dave']", log_text)
            self.assertIn("won by ['alice', 'bob']", log_text)
            for name in ("alice", "bob", "carol", "dave"):
                self.assertIn(f": {name}: offensive before:", log_text)
                self.assertIn(f": {name}: defensive before:", log_text)

            with shelve.open(str(tmp_path / "match_history")) as history:
                self.assertEqual(len(history), 1)
                key = next(iter(history.keys()))
                record = history[key]
                self.assertEqual(record["team1"], team1)
                self.assertEqual(record["team2"], team2)
                self.assertEqual(record["winner"], team1)
                self.assertEqual(record["score1"], 5)
                self.assertEqual(record["score2"], 3)
                self.assertEqual(record["source"], "test")
                self.assertEqual(len(record["players"]), 4)

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
        self.assertGreaterEqual(
            _lineup_quality(players, result), _lineup_quality(players, current_layout)
        )

        repeat = best_balanced_lineup(players, "ada", "bert", "cara", "dion")
        self.assertEqual(result, repeat)
        self.assertIsNone(best_balanced_lineup(players, "ada", "bert", "cara", "missing"))

    def test_replay_matches_materialized_ratings_after_sequential_matches(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                for name in ("alice", "bob", "carol", "dave"):
                    players[name] = (trueskill.Rating(), trueskill.Rating())

            store = ShelveWriteStore(tmp_path)
            store.submit_match(["alice"], ["bob"], 5, 3, source="test")
            store.submit_match(["carol", "alice"], ["dave", "bob"], 5, 4, source="test")

            replayed = replay_scope_ratings(tmp_path, "all")
            with shelve.open(db_path) as players:
                materialized = dict(players.items())

            self.assertEqual(set(replayed), set(materialized))
            for name in materialized:
                self.assertRatingPairAlmostEqual(replayed[name], materialized[name])

    def test_shelve_submit_is_idempotent_and_records_actor_event(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with shelve.open(str(tmp_path / "playerdb")) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())
                players["bob"] = (trueskill.Rating(), trueskill.Rating())

            store = ShelveWriteStore(tmp_path)
            first = store.submit_match(
                ["alice"],
                ["bob"],
                5,
                3,
                source="test",
                actor_subject="user_operator",
                idempotency_key="request-1",
            )
            second = store.submit_match(
                ["alice"],
                ["bob"],
                5,
                3,
                source="test",
                actor_subject="user_operator",
                idempotency_key="request-1",
            )

            self.assertEqual(first["match_id"], second["match_id"])
            with self.assertRaisesRegex(
                ValueError,
                "idempotency key was already used",
            ):
                store.submit_match(
                    ["alice"],
                    ["bob"],
                    5,
                    2,
                    source="test",
                    actor_subject="user_operator",
                    idempotency_key="request-1",
                )
            with shelve.open(str(tmp_path / "match_history")) as history:
                self.assertEqual(len(history), 1)
                record = history[first["match_id"]]
                self.assertEqual(record["submitted_by"], "user_operator")
                self.assertEqual(record["status"], "active")
            with shelve.open(str(tmp_path / "match_events")) as events:
                self.assertEqual(len(events), 1)
                event = next(iter(events.values()))
                self.assertEqual(event["actor_subject"], "user_operator")
                self.assertEqual(event["event_type"], "submit")

    def test_voided_records_are_excluded_from_replay(self) -> None:
        records = [
            {
                "timestamp": "2026-01-01T12:00:00.000000Z",
                "source": "test",
                "team1": ["alice"],
                "team2": ["bob"],
                "winner": ["alice"],
                "score1": 5,
                "score2": 3,
                "players": [],
                "status": "voided",
            }
        ]

        from services.match_history import replay_ratings_from_records

        self.assertEqual(replay_ratings_from_records(records), {})

    def test_void_and_restore_rebuild_ratings_symmetrically(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with shelve.open(str(tmp_path / "playerdb")) as players:
                for name in ("alice", "bob", "carol"):
                    players[name] = (trueskill.Rating(), trueskill.Rating())

            store = ShelveWriteStore(tmp_path)
            first = store.submit_match(
                ["alice"],
                ["bob"],
                5,
                3,
                source="test",
                idempotency_key="submit-1",
            )
            store.submit_match(
                ["alice"],
                ["carol"],
                5,
                4,
                source="test",
                idempotency_key="submit-2",
            )
            with shelve.open(str(tmp_path / "playerdb")) as players:
                original = dict(players.items())

            voided = store.change_match_status(
                first["match_id"],
                "voided",
                "user_admin",
                "Incorrect result",
                "void-1",
                expected_version=1,
            )
            self.assertEqual(voided["status"], "voided")
            repeated_void = store.change_match_status(
                first["match_id"],
                "voided",
                "user_admin",
                "Incorrect result",
                "void-1",
            )
            self.assertTrue(repeated_void["idempotent"])
            with shelve.open(str(tmp_path / "playerdb")) as players:
                after_void = dict(players.items())
            self.assertTrue(
                any(
                    not _ratings_match_for_test(after_void[name], original[name])
                    for name in original
                )
            )

            restored = store.change_match_status(
                first["match_id"],
                "active",
                "user_admin",
                "Correction reversed",
                "restore-1",
                expected_version=2,
            )
            self.assertEqual(restored["status"], "active")
            with shelve.open(str(tmp_path / "playerdb")) as players:
                after_restore = dict(players.items())
            for name in original:
                self.assertRatingPairAlmostEqual(after_restore[name], original[name])

    def test_lifecycle_refuses_materialized_rating_drift(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with shelve.open(str(tmp_path / "playerdb")) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())
                players["bob"] = (trueskill.Rating(), trueskill.Rating())

            store = ShelveWriteStore(tmp_path)
            result = store.submit_match(["alice"], ["bob"], 5, 3, source="test")
            with shelve.open(str(tmp_path / "playerdb")) as players:
                players["alice"] = (
                    trueskill.Rating(mu=99, sigma=1),
                    players["alice"][1],
                )

            with self.assertRaises(ReplayParityError):
                store.change_match_status(
                    result["match_id"],
                    "voided",
                    "user_admin",
                    "Should be blocked",
                    "void-drifted",
                )

            with shelve.open(str(tmp_path / "match_history")) as history:
                self.assertEqual(history[result["match_id"]]["status"], "active")


def _ratings_match_for_test(left: tuple, right: tuple) -> bool:
    return all(
        abs(left_rating.mu - right_rating.mu) <= 1e-9
        and abs(left_rating.sigma - right_rating.sigma) <= 1e-9
        for left_rating, right_rating in zip(left, right)
    )


if __name__ == "__main__":
    unittest.main()
