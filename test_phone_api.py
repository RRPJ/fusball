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

from phone_api import WRITE_LOCK_NAME, create_app  # noqa: E402


class PhoneApiTests(unittest.TestCase):
    operator_token = "secret-token"

    def test_leaderboard_api_returns_sorted_items(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(mu=35, sigma=6), trueskill.Rating(mu=34, sigma=6))
                players["bob"] = (trueskill.Rating(mu=30, sigma=7), trueskill.Rating(mu=29, sigma=7))
                players["carol"] = (trueskill.Rating(mu=27, sigma=8), trueskill.Rating(mu=26, sigma=8))

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.get("/api/leaderboard?limit=2")
            self.assertEqual(response.status_code, 200)

            payload = response.get_json()
            assert payload is not None
            self.assertEqual(payload["count"], 2)
            self.assertEqual(payload["items"][0]["name"], "Alice")
            self.assertGreaterEqual(payload["items"][0]["level"], payload["items"][1]["level"])

    def test_phone_page_renders_table(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.get("/phone")
            self.assertEqual(response.status_code, 200)

            html = response.get_data(as_text=True)
            self.assertIn("Dustin Fusball Phone Console", html)
            self.assertIn("Leaderboard", html)
            self.assertIn("Alice", html)

    def test_match_submit_requires_operator_token(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())
                players["bob"] = (trueskill.Rating(), trueskill.Rating())

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
            )

            self.assertEqual(response.status_code, 401)

    def test_match_submit_rejects_conflicting_writer(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())
                players["bob"] = (trueskill.Rating(), trueskill.Rating())

            (tmp_path / WRITE_LOCK_NAME).write_text("kiosk", encoding="utf-8")

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
                headers={"X-Operator-Token": self.operator_token},
            )

            self.assertEqual(response.status_code, 409)

    def test_match_submit_updates_ratings_and_log(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(mu=30, sigma=6), trueskill.Rating(mu=30, sigma=6))
                players["bob"] = (trueskill.Rating(mu=30, sigma=6), trueskill.Rating(mu=30, sigma=6))

            with shelve.open(db_path) as players:
                before_alice = players["alice"]
                before_bob = players["bob"]

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
                headers={"X-Operator-Token": self.operator_token},
            )

            self.assertEqual(response.status_code, 201)
            payload = response.get_json()
            assert payload is not None
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["winner"], ["alice"])

            with shelve.open(db_path) as players:
                self.assertGreater(players["alice"][0].mu, before_alice[0].mu)
                self.assertLess(players["bob"][0].mu, before_bob[0].mu)

            log_text = (tmp_path / "logfile.log").read_text(encoding="utf-8")
            self.assertIn("match played between ['alice'] and ['bob']", log_text)
            self.assertIn("won by ['alice']", log_text)

            with shelve.open(str(tmp_path / "match_history")) as history:
                self.assertEqual(len(history), 1)
                key = next(iter(history.keys()))
                record = history[key]
                self.assertEqual(record["team1"], ["alice"])
                self.assertEqual(record["team2"], ["bob"])
                self.assertEqual(record["winner"], ["alice"])
                self.assertEqual(record["score1"], 5)
                self.assertEqual(record["score2"], 3)
                self.assertEqual(record["source"], "phone_api")

    def test_players_api_returns_names(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())
                players["bob"] = (trueskill.Rating(), trueskill.Rating())

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.get("/api/players")
            self.assertEqual(response.status_code, 200)

            payload = response.get_json()
            assert payload is not None
            self.assertEqual(payload["count"], 2)
            self.assertIn("Alice", payload["items"])
            self.assertIn("Bob", payload["items"])

    def test_add_player_requires_operator_token(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.post("/api/players", json={"name": "Rutger"})

            self.assertEqual(response.status_code, 401)

    def test_add_player_creates_player_and_rejects_duplicate(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()

            create_response = client.post(
                "/api/players",
                json={"name": "Rutger"},
                headers={"X-Operator-Token": self.operator_token},
            )
            self.assertEqual(create_response.status_code, 201)

            payload = create_response.get_json()
            assert payload is not None
            self.assertEqual(payload["name"], "Rutger")

            with shelve.open(str(tmp_path / "playerdb")) as players:
                self.assertIn("rutger", players)

            duplicate_response = client.post(
                "/api/players",
                json={"name": "rutger"},
                headers={"X-Operator-Token": self.operator_token},
            )
            self.assertEqual(duplicate_response.status_code, 409)

    def test_match_submit_rejects_invalid_finished_score(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())
                players["bob"] = (trueskill.Rating(), trueskill.Rating())

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 5},
                headers={"X-Operator-Token": self.operator_token},
            )

            self.assertEqual(response.status_code, 400)


class C3AnalyticsApiTests(unittest.TestCase):
    operator_token = "secret-token"

    def _app_with_history(self, tmpdir: Path):
        from services.match_history import append_match_history
        from services.match_service import calculate_rating_update

        db_path = str(tmpdir / "playerdb")
        with shelve.open(db_path) as players:
            players["alice"] = (trueskill.Rating(mu=34, sigma=6), trueskill.Rating(mu=33, sigma=6))
            players["bob"] = (trueskill.Rating(mu=30, sigma=6), trueskill.Rating(mu=30, sigma=6))

        with shelve.open(db_path) as players:
            before = {n: players[n] for n in ["alice", "bob"]}
            updated = calculate_rating_update(players, ["alice"], ["bob"], 5, 3)
            for n in ["alice", "bob"]:
                players[n] = updated[n]
            after = {n: players[n] for n in ["alice", "bob"]}

        append_match_history(tmpdir, ["alice"], ["bob"], ["alice"], 5, 3, before, after, source="test")

        return create_app(db_dir=tmpdir, operator_token=self.operator_token)

    def test_h2h_returns_match_count(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            app = self._app_with_history(tmp_path)
            client = app.test_client()
            response = client.get("/api/h2h?p1=alice&p2=bob")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            assert payload is not None
            self.assertEqual(payload["matches"], 1)
            self.assertEqual(payload["p1_wins"], 1)
            self.assertEqual(payload["p2_wins"], 0)
            self.assertEqual(payload["p1"], "alice")

    def test_h2h_rejects_missing_params(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            self.assertEqual(client.get("/api/h2h?p1=alice").status_code, 400)

    def test_stats_returns_per_player_entry(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            app = self._app_with_history(tmp_path)
            client = app.test_client()
            response = client.get("/api/stats")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            assert payload is not None
            self.assertIn("alice", payload)
            self.assertEqual(payload["alice"]["games"], 1)
            self.assertEqual(payload["alice"]["wins"], 1)
            self.assertEqual(payload["alice"]["streak"], 1)
            self.assertIn("bob", payload)
            self.assertEqual(payload["bob"]["streak"], 0)

    def test_player_history_returns_snapshots(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            app = self._app_with_history(tmp_path)
            client = app.test_client()
            response = client.get("/api/player/alice/history")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            assert payload is not None
            self.assertEqual(payload["player"], "alice")
            self.assertEqual(payload["count"], 1)
            snap = payload["snapshots"][0]
            self.assertTrue(snap["won"])
            self.assertIn("before", snap)
            self.assertIn("after", snap)
            self.assertIn("offense_mu", snap["after"])

    def test_player_history_empty_when_no_history(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.get("/api/player/alice/history")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            assert payload is not None
            self.assertEqual(payload["count"], 0)


if __name__ == "__main__":
    unittest.main()
