from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import shelve
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import trueskill
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from phone_api import WRITE_LOCK_NAME, create_app  # noqa: E402
from services.match_service import best_balanced_lineup  # noqa: E402


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

    def test_root_redirects_to_phone(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.get("/", follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), "/phone")

    def test_phone_page_includes_quip_catalog_with_variety(self) -> None:
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
            categories = [
                "expected_blowout",
                "expected_close_win",
                "upset_win",
                "nail_biter",
                "total_stomp",
                "even_match_outcome",
            ]
            for category in categories:
                pattern = rf"{category}: \[(.*?)\]"
                match = re.search(pattern, html, re.DOTALL)
                self.assertIsNotNone(match)
                assert match is not None
                lines = re.findall(r"'[^']+'", match.group(1))
                self.assertGreaterEqual(len(lines), 10)

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

            duplicate = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
                headers={"X-Operator-Token": self.operator_token},
            )
            self.assertEqual(duplicate.status_code, 409)

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

    def test_presence_api_tracks_active_players(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())
                players["bob"] = (trueskill.Rating(), trueskill.Rating())

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()

            empty = client.get("/api/presence")
            self.assertEqual(empty.status_code, 200)
            empty_payload = empty.get_json()
            assert empty_payload is not None
            self.assertEqual(empty_payload["count"], 0)

            add_active = client.post(
                "/api/presence",
                json={"name": "alice", "active": True},
                headers={"X-Operator-Token": self.operator_token},
            )
            self.assertEqual(add_active.status_code, 200)

            presence = client.get("/api/presence")
            payload = presence.get_json()
            assert payload is not None
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["items"], ["Alice"])

            clear = client.post(
                "/api/presence/clear",
                headers={"X-Operator-Token": self.operator_token},
            )
            self.assertEqual(clear.status_code, 200)
            cleared = client.get("/api/presence")
            cleared_payload = cleared.get_json()
            assert cleared_payload is not None
            self.assertEqual(cleared_payload["count"], 0)

    def test_random_lineup_uses_only_active_players(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                for name in ["alice", "bob", "carol", "dave", "eve"]:
                    players[name] = (trueskill.Rating(), trueskill.Rating())

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()

            for name in ["alice", "bob", "carol", "dave"]:
                response = client.post(
                    "/api/presence",
                    json={"name": name, "active": True},
                    headers={"X-Operator-Token": self.operator_token},
                )
                self.assertEqual(response.status_code, 200)

            lineup_resp = client.post(
                "/api/lineup/random",
                json={"mode": "doubles"},
                headers={"X-Operator-Token": self.operator_token},
            )
            self.assertEqual(lineup_resp.status_code, 200)
            payload = lineup_resp.get_json()
            assert payload is not None
            selected = payload["selected"]
            chosen = {selected["red_defense"], selected["red_offense"], selected["blue_defense"], selected["blue_offense"]}
            self.assertEqual(len(chosen), 4)
            self.assertTrue(chosen.issubset({"alice", "bob", "carol", "dave"}))

    def test_auto_lineup_reorders_to_best_balance(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(mu=38, sigma=4), trueskill.Rating(mu=28, sigma=4))
                players["bob"] = (trueskill.Rating(mu=30, sigma=4), trueskill.Rating(mu=36, sigma=4))
                players["carol"] = (trueskill.Rating(mu=34, sigma=4), trueskill.Rating(mu=30, sigma=4))
                players["dave"] = (trueskill.Rating(mu=26, sigma=4), trueskill.Rating(mu=34, sigma=4))
                expected = best_balanced_lineup(
                    players,
                    defense_a="alice",
                    offense_a="bob",
                    offense_b="carol",
                    defense_b="dave",
                )

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.post(
                "/api/lineup/auto",
                json={
                    "mode": "doubles",
                    "selected": {
                        "red_defense": "alice",
                        "red_offense": "bob",
                        "blue_offense": "carol",
                        "blue_defense": "dave",
                    },
                },
                headers={"X-Operator-Token": self.operator_token},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            assert payload is not None
            selected = payload["selected"]
            self.assertEqual(
                [selected["red_defense"], selected["red_offense"], selected["blue_offense"], selected["blue_defense"]],
                expected,
            )

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

    def test_leaderboard_and_odds_can_use_injected_store(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            class StubStore:
                uses_local_lock = False

                def __init__(self) -> None:
                    self._ratings = {
                        "alice": (trueskill.Rating(mu=35, sigma=6), trueskill.Rating(mu=33, sigma=6)),
                        "bob": (trueskill.Rating(mu=30, sigma=7), trueskill.Rating(mu=29, sigma=7)),
                    }

                def list_player_keys(self) -> list[str]:
                    return sorted(self._ratings.keys())

                def get_player_ratings(self, names: list[str]):
                    return {name: self._ratings[name] for name in names if name in self._ratings}

                def leaderboard_ratings(self, scope: str):
                    if scope != "all":
                        return {}
                    return dict(self._ratings)

                def missing_players(self, names: list[str]) -> list[str]:
                    return [name for name in names if name not in self._ratings]

                def add_player(self, player_name: str):
                    raise NotImplementedError

                def submit_match(self, team1: list[str], team2: list[str], score1: int, score2: int, source: str):
                    raise NotImplementedError

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token, write_store=StubStore())
            client = app.test_client()

            leaderboard = client.get("/api/leaderboard?limit=2")
            self.assertEqual(leaderboard.status_code, 200)
            leaderboard_payload = leaderboard.get_json()
            assert leaderboard_payload is not None
            self.assertEqual(leaderboard_payload["count"], 2)
            self.assertEqual(leaderboard_payload["items"][0]["name"], "Alice")

            odds = client.get("/api/odds?red_off=alice&blue_off=bob")
            self.assertEqual(odds.status_code, 200)
            odds_payload = odds.get_json()
            assert odds_payload is not None
            self.assertIn("probability", odds_payload)
            self.assertIn("ratio", odds_payload)

    def test_history_endpoints_can_use_injected_store(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            class StubStore:
                uses_local_lock = False

                def list_player_keys(self) -> list[str]:
                    return ["alice", "bob"]

                def get_player_ratings(self, names: list[str]):
                    ratings = {
                        "alice": (trueskill.Rating(mu=35, sigma=6), trueskill.Rating(mu=33, sigma=6)),
                        "bob": (trueskill.Rating(mu=30, sigma=7), trueskill.Rating(mu=29, sigma=7)),
                    }
                    return {name: ratings[name] for name in names if name in ratings}

                def leaderboard_ratings(self, scope: str):
                    return {}

                def missing_players(self, names: list[str]) -> list[str]:
                    return []

                def add_player(self, player_name: str):
                    raise NotImplementedError

                def submit_match(self, team1: list[str], team2: list[str], score1: int, score2: int, source: str):
                    raise NotImplementedError

                def query_h2h(self, p1: str, p2: str):
                    return {
                        "p1": p1,
                        "p2": p2,
                        "matches": 2,
                        "p1_wins": 1,
                        "p2_wins": 1,
                        "draws": 0,
                        "last_match": "2026-04-01T12:00:00.000000Z",
                    }

                def query_player_stats(self, scope: str = "all"):
                    return {
                        "alice": {
                            "games": 2,
                            "wins": 1,
                            "win_rate": 0.5,
                            "streak": 0,
                            "improved": 0.0,
                            "recent_form_5": "WL",
                            "last_match": "2026-04-01T12:00:00.000000Z",
                        }
                    }

                def query_rating_snapshots(self, player: str, n: int = 10):
                    return [
                        {
                            "timestamp": "2026-04-01T12:00:00.000000Z",
                            "won": True,
                            "before": {"offense_mu": 25.0, "offense_sigma": 8.333, "defense_mu": 25.0, "defense_sigma": 8.333},
                            "after": {"offense_mu": 30.0, "offense_sigma": 8.0, "defense_mu": 30.0, "defense_sigma": 8.0},
                        }
                    ][:n]

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token, write_store=StubStore())
            client = app.test_client()

            h2h = client.get("/api/h2h?p1=alice&p2=bob")
            self.assertEqual(h2h.status_code, 200)
            h2h_payload = h2h.get_json()
            assert h2h_payload is not None
            self.assertEqual(h2h_payload["matches"], 2)

            stats = client.get("/api/stats")
            self.assertEqual(stats.status_code, 200)
            stats_payload = stats.get_json()
            assert stats_payload is not None
            self.assertIn("alice", stats_payload)

            history = client.get("/api/player/alice/history?n=1")
            self.assertEqual(history.status_code, 200)
            history_payload = history.get_json()
            assert history_payload is not None
            self.assertEqual(history_payload["count"], 1)

    def test_dual_pin_auth_read_and_write_matrix(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())
                players["bob"] = (trueskill.Rating(), trueskill.Rating())

            app = create_app(
                db_dir=tmp_path,
                read_pin_hash=generate_password_hash("read-1234"),
                write_pin_hash=generate_password_hash("write-5678"),
            )
            client = app.test_client()

            read_no_auth = client.get("/api/leaderboard")
            self.assertEqual(read_no_auth.status_code, 401)

            read_with_read_pin = client.get("/api/leaderboard", headers={"X-Read-Pin": "read-1234"})
            self.assertEqual(read_with_read_pin.status_code, 200)

            read_with_writer_pin = client.get("/api/leaderboard", headers={"X-Write-Pin": "write-5678"})
            self.assertEqual(read_with_writer_pin.status_code, 200)

            write_no_auth = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
            )
            self.assertEqual(write_no_auth.status_code, 403)

            write_with_read_pin = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
                headers={"X-Read-Pin": "read-1234"},
            )
            self.assertEqual(write_with_read_pin.status_code, 403)

            write_with_writer_pin = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
                headers={"X-Write-Pin": "write-5678"},
            )
            self.assertEqual(write_with_writer_pin.status_code, 201)


class C3AnalyticsApiTests(unittest.TestCase):
    operator_token = "secret-token"

    @staticmethod
    def _write_history_record(
        tmpdir: Path,
        timestamp: datetime,
        team1: list[str],
        team2: list[str],
        winner: list[str],
        score1: int,
        score2: int,
        players: list[dict] | None = None,
    ) -> None:
        key = f"{timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ')}_test"
        with shelve.open(str(tmpdir / "match_history")) as history:
            history[key] = {
                "timestamp": timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                "source": "test",
                "team1": team1,
                "team2": team2,
                "winner": winner,
                "score1": score1,
                "score2": score2,
                "players": players or [],
            }

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

    def test_scoped_leaderboard_hides_inactive_players(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            now = datetime.now(timezone.utc)
            this_week_ts = now - timedelta(days=1)
            this_month_ts = now - timedelta(days=10)
            previous_month_ts = (now.replace(day=1, hour=12, minute=0, second=0, microsecond=0) - timedelta(days=1))

            self._write_history_record(tmp_path, previous_month_ts, ["alice"], ["bob"], ["alice"], 5, 3)
            self._write_history_record(tmp_path, this_month_ts, ["carol"], ["dave"], ["carol"], 5, 2)
            self._write_history_record(tmp_path, this_week_ts, ["eve"], ["frank"], ["eve"], 5, 1)

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()

            month_resp = client.get("/api/leaderboard?scope=this_month")
            self.assertEqual(month_resp.status_code, 200)
            month_payload = month_resp.get_json()
            assert month_payload is not None
            month_names = {item["name"].lower() for item in month_payload["items"]}
            self.assertIn("carol", month_names)
            self.assertIn("dave", month_names)
            self.assertIn("eve", month_names)
            self.assertIn("frank", month_names)
            self.assertNotIn("alice", month_names)
            self.assertNotIn("bob", month_names)

            week_resp = client.get("/api/leaderboard?scope=this_week")
            self.assertEqual(week_resp.status_code, 200)
            week_payload = week_resp.get_json()
            assert week_payload is not None
            week_names = {item["name"].lower() for item in week_payload["items"]}
            self.assertIn("eve", week_names)
            self.assertIn("frank", week_names)
            self.assertNotIn("carol", week_names)
            self.assertNotIn("dave", week_names)

    def test_leaderboard_rejects_invalid_scope(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.get("/api/leaderboard?scope=unknown")
            self.assertEqual(response.status_code, 400)

    def test_stats_improved_uses_scope_baseline_to_current_all_level(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            now = datetime.now(timezone.utc)
            start_week = (now - timedelta(days=now.weekday())).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # A pre-month match moves all-time level to 12.0
            self._write_history_record(
                tmp_path,
                start_month - timedelta(days=1),
                ["alice"],
                ["bob"],
                ["alice"],
                5,
                3,
                players=[
                    {
                        "name": "alice",
                        "before": {"offense_mu": 25.0, "offense_sigma": 8.333, "defense_mu": 25.0, "defense_sigma": 8.333},
                        "after": {"offense_mu": 31.0, "offense_sigma": 8.0, "defense_mu": 31.0, "defense_sigma": 8.0},
                    }
                ],
            )

            # First this-month match baseline starts at 12.0 and ends at 20.0 (+8 this month)
            self._write_history_record(
                tmp_path,
                start_month + timedelta(days=1),
                ["alice"],
                ["bob"],
                ["alice"],
                5,
                1,
                players=[
                    {
                        "name": "alice",
                        "before": {"offense_mu": 31.0, "offense_sigma": 8.0, "defense_mu": 31.0, "defense_sigma": 8.0},
                        "after": {"offense_mu": 35.0, "offense_sigma": 7.5, "defense_mu": 35.0, "defense_sigma": 7.5},
                    }
                ],
            )

            # This-week match baseline starts at 20.0 and ends at 23.0 (+3 this week)
            self._write_history_record(
                tmp_path,
                max(start_week + timedelta(days=1), start_month + timedelta(days=2)),
                ["alice"],
                ["bob"],
                ["alice"],
                5,
                0,
                players=[
                    {
                        "name": "alice",
                        "before": {"offense_mu": 35.0, "offense_sigma": 7.5, "defense_mu": 35.0, "defense_sigma": 7.5},
                        "after": {"offense_mu": 37.0, "offense_sigma": 7.0, "defense_mu": 37.0, "defense_sigma": 7.0},
                    }
                ],
            )

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()

            month_stats = client.get("/api/stats?scope=this_month")
            self.assertEqual(month_stats.status_code, 200)
            month_payload = month_stats.get_json()
            assert month_payload is not None
            self.assertAlmostEqual(month_payload["alice"]["improved"], 18.0, places=2)

            week_stats = client.get("/api/stats?scope=this_week")
            self.assertEqual(week_stats.status_code, 200)
            week_payload = week_stats.get_json()
            assert week_payload is not None
            self.assertAlmostEqual(week_payload["alice"]["improved"], 7.0, places=2)


if __name__ == "__main__":
    unittest.main()
