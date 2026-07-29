from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import re
import shelve
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import trueskill
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from odds import playerLevel  # noqa: E402
from phone_api import WRITE_LOCK_NAME, create_app  # noqa: E402
from services.auth import AuthActor  # noqa: E402
from services.match_service import best_balanced_lineup, calculate_rating_update  # noqa: E402
from services.phone_write_store import ShelveWriteStore  # noqa: E402


class PhoneApiTests(unittest.TestCase):
    operator_token = "secret-token"

    def test_health_returns_unavailable_when_store_is_not_ready(self) -> None:
        class UnavailableStore:
            uses_local_lock = False

            @staticmethod
            def readiness() -> dict[str, object]:
                return {
                    "ok": False,
                    "store": "neon",
                    "reason": "database_unavailable",
                }

        app = create_app(operator_token=self.operator_token, write_store=UnavailableStore())
        response = app.test_client().get("/api/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json(),
            {
                "ok": False,
                "store": "neon",
                "reason": "database_unavailable",
            },
        )

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
            self.assertAlmostEqual(payload["items"][0]["level"], 16.5, places=2)
            self.assertAlmostEqual(payload["items"][1]["level"], 8.5, places=2)
            self.assertGreaterEqual(payload["items"][0]["level"], payload["items"][1]["level"])

    def test_leaderboard_rank_labels_use_rounded_average_level(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(mu=19.4, sigma=6.0), trueskill.Rating(mu=19.4, sigma=6.0))
                players["bob"] = (trueskill.Rating(mu=18.6, sigma=6.0), trueskill.Rating(mu=18.6, sigma=6.0))
                players["carol"] = (trueskill.Rating(mu=17.4, sigma=6.0), trueskill.Rating(mu=17.4, sigma=6.0))

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.get("/api/leaderboard?limit=3")
            self.assertEqual(response.status_code, 200)

            payload = response.get_json()
            assert payload is not None
            items_by_name = {item["name"].lower(): item for item in payload["items"]}
            self.assertEqual(items_by_name["alice"]["rank"], "1-2")
            self.assertEqual(items_by_name["bob"]["rank"], "1-2")
            self.assertEqual(items_by_name["carol"]["rank"], "3")

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
            self.assertIn("Fusball Phone API", html)
            self.assertIn("Leaderboard", html)
            self.assertIn("Alice", html)
            self.assertIn("id='liveStatusCard' class='live-status review-card'", html)
            self.assertIn("id='leaderboardFreshness' class='muted'", html)
            self.assertIn("The page will show whether data is live, fetching, or using a cached snapshot.", html)

    def test_phone_page_uses_unnumbered_progress_buttons_and_mode_only_leaderboard(self) -> None:
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
            self.assertIn("id='stepBtn1' type='button' class='active'>Mode</button>", html)
            self.assertIn("id='stepBtn2' type='button'>Players</button>", html)
            self.assertIn("id='stepBtn3' type='button'>Score</button>", html)
            self.assertIn("id='stepBtn4' type='button'>Confirm</button>", html)
            self.assertNotIn("1 Mode", html)
            self.assertNotIn("2 Players", html)
            self.assertNotIn("3 Score", html)
            self.assertNotIn("4 Confirm", html)
            self.assertIn("id='leaderboardSection' class='section active'>", html)
            self.assertLess(html.index(">All</button>"), html.index(">This quarter</button>"))
            self.assertLess(html.index(">This quarter</button>"), html.index(">This month</button>"))
            self.assertLess(html.index(">This month</button>"), html.index(">This week</button>"))

            # The phone UI's JS logic now lives in a versioned static asset
            # rather than being embedded in the /phone HTML response.
            js = client.get("/static/js/phone.js").get_data(as_text=True)
            self.assertIn(
                "const leaderboardSection = document.getElementById('leaderboardSection');", js
            )
            self.assertIn("leaderboardSection.classList.toggle('active', state.step === 1);", js)
            self.assertIn(
                "const LEADERBOARD_CACHE_STORAGE_KEY = 'fusball_leaderboard_snapshot';", js
            )
            self.assertIn("function renderLiveStatus()", js)
            self.assertIn("function renderLeaderboardFreshness()", js)
            self.assertIn("function startFreshnessTicker()", js)
            self.assertIn("trackKey: 'leaderboard'", js)
            self.assertIn(
                "document.getElementById('filterThisQuarterBtn').classList.toggle("
                "'active', f === 'this_quarter');",
                js,
            )
            self.assertIn(
                "document.getElementById('filterThisQuarterBtn').addEventListener("
                "'click', () => setLeaderboardFilter('this_quarter'));",
                js,
            )

    def test_phone_page_uses_compact_always_visible_player_lists(self) -> None:
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
            self.assertIn("id='presentPlayersHeading'>Present Players (tap to assign)</h3>", html)
            self.assertIn("id='presentPlayersPanel' class='players'", html)
            self.assertIn("id='awayPlayersHeading'>Away Players (tap to mark present)</h3>", html)
            self.assertIn("id='awayPlayersPanel' class='players'", html)

            css = client.get("/static/css/phone.css").get_data(as_text=True)
            self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr));", css)
            self.assertIn("@media (min-width: 560px)", css)
            self.assertIn("grid-template-columns: repeat(auto-fit, minmax(156px, 1fr));", css)
            self.assertNotIn("presence-collapsed", css)

            js = client.get("/static/js/phone.js").get_data(as_text=True)
            self.assertIn(
                "presentHeading.textContent = "
                "`Present Players (${presentNames.length}) - tap to assign`",
                js,
            )
            self.assertIn(
                "awayHeading.textContent = "
                "`Away Players (${awayNames.length}) - tap to mark present`",
                js,
            )
            self.assertIn(
                "state.players = (payload.items || []).slice().sort("
                "(left, right) => left.localeCompare(right));",
                js,
            )
            self.assertNotIn("awayToggleBtn", js)
            self.assertNotIn("presence-collapsed", js)

    def test_phone_page_formats_doubles_display_as_defense_then_offense(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.get("/phone")
            self.assertEqual(response.status_code, 200)

            js = client.get("/static/js/phone.js").get_data(as_text=True)
            self.assertIn(
                "state.selected.red_defense || placeholder, "
                "state.selected.red_offense || placeholder",
                js,
            )
            self.assertIn(
                "state.selected.blue_defense || placeholder, "
                "state.selected.blue_offense || placeholder",
                js,
            )
            self.assertIn("const red = formatTeamDisplay('red');", js)
            self.assertIn("const blue = formatTeamDisplay('blue');", js)
            self.assertIn("const redDisplay = formatTeamDisplay('red', ' + ');", js)
            self.assertIn("const blueDisplay = formatTeamDisplay('blue', ' + ');", js)

    def test_phone_page_includes_profile_panel_and_pairwise_h2h_hooks(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()
            response = client.get("/phone")
            self.assertEqual(response.status_code, 200)

            js = client.get("/static/js/phone.js").get_data(as_text=True)
            self.assertIn("Loading player profile...", js)
            self.assertIn(
                "/api/player/${encodeURIComponent(playerKey)}/profile?"
                "scope=${encodeURIComponent(state.leaderboardFilter)}&recent_limit=5",
                js,
            )
            self.assertIn("Current teams H2H", js)
            self.assertIn("/api/team-h2h?team1=${team1}&team2=${team2}", js)
            self.assertIn("function openPlayerH2H(playerKey, otherPlayerKey)", js)
            self.assertIn("setMode('singles');", js)

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

            js = client.get("/static/js/phone.js").get_data(as_text=True)
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
                match = re.search(pattern, js, re.DOTALL)
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

            (tmp_path / WRITE_LOCK_NAME).write_text("another-writer", encoding="utf-8")

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

            idempotent_headers = {
                "X-Operator-Token": self.operator_token,
                "Idempotency-Key": "phone-request-1",
            }
            first_idempotent = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 2},
                headers=idempotent_headers,
            )
            second_idempotent = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 2},
                headers=idempotent_headers,
            )
            self.assertEqual(first_idempotent.status_code, 201)
            self.assertEqual(second_idempotent.status_code, 201)
            self.assertEqual(
                first_idempotent.get_json()["match_id"],
                second_idempotent.get_json()["match_id"],
            )

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
                    if scope not in {"all", "this_quarter"}:
                        return {}
                    return dict(self._ratings)

                def missing_players(self, names: list[str]) -> list[str]:
                    return [name for name in names if name not in self._ratings]

                def add_player(self, player_name: str):
                    raise NotImplementedError

                def submit_match(self, team1: list[str], team2: list[str], score1: int, score2: int, source: str, **kwargs):
                    raise NotImplementedError

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token, write_store=StubStore())
            client = app.test_client()

            leaderboard = client.get("/api/leaderboard?limit=2")
            self.assertEqual(leaderboard.status_code, 200)
            leaderboard_payload = leaderboard.get_json()
            assert leaderboard_payload is not None
            self.assertEqual(leaderboard_payload["count"], 2)
            self.assertEqual(leaderboard_payload["items"][0]["name"], "Alice")

            quarterly = client.get("/api/leaderboard?limit=2&scope=this_quarter")
            self.assertEqual(quarterly.status_code, 200)
            quarterly_payload = quarterly.get_json()
            assert quarterly_payload is not None
            self.assertEqual(quarterly_payload["count"], 2)

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

                def submit_match(self, team1: list[str], team2: list[str], score1: int, score2: int, source: str, **kwargs):
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

                def query_team_h2h(self, team1: list[str], team2: list[str]):
                    return {
                        "team1": [name.title() for name in team1],
                        "team2": [name.title() for name in team2],
                        "matches": 1,
                        "team1_wins": 1,
                        "team2_wins": 0,
                        "draws": 0,
                        "last_match": "2026-04-02T12:00:00.000000Z",
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

                def query_player_profile(self, player: str, scope: str = "all", recent_limit: int = 5):
                    return {
                        "player": player,
                        "summary": {
                            "games": 2,
                            "wins": 1,
                            "win_rate": 0.5,
                            "streak": 0,
                            "recent_form_5": "WL",
                            "last_match": "2026-04-01T12:00:00.000000Z",
                        },
                        "trend": {"offense": 1.5, "defense": -0.5},
                        "best_partner": None,
                        "toughest_opponent": {
                            "player": "Bob",
                            "matches": 2,
                            "wins": 1,
                            "losses": 1,
                            "draws": 0,
                            "win_share": 0.5,
                        },
                        "recent_matches": [
                            {
                                "timestamp": "2026-04-01T12:00:00.000000Z",
                                "won": True,
                                "team": ["Alice"],
                                "opponents": ["Bob"],
                                "score_for": 5,
                                "score_against": 3,
                                "delta": {"offense": 1.5, "defense": -0.5},
                            }
                        ][:recent_limit],
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

            profile = client.get("/api/player/alice/profile?scope=this_month&recent_limit=1")
            self.assertEqual(profile.status_code, 200)
            profile_payload = profile.get_json()
            assert profile_payload is not None
            self.assertEqual(profile_payload["player"], "alice")
            self.assertEqual(profile_payload["summary"]["games"], 2)
            self.assertEqual(len(profile_payload["recent_matches"]), 1)

            team_h2h = client.get("/api/team-h2h?team1=alice,bob&team2=carol,dave")
            self.assertEqual(team_h2h.status_code, 200)
            team_h2h_payload = team_h2h.get_json()
            assert team_h2h_payload is not None
            self.assertEqual(team_h2h_payload["matches"], 1)

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
            self.assertEqual(read_no_auth.get_json(), {"error": "authentication required"})

            read_with_wrong_read_pin = client.get("/api/leaderboard", headers={"X-Read-Pin": "wrong-read"})
            self.assertEqual(read_with_wrong_read_pin.status_code, 401)
            self.assertEqual(read_with_wrong_read_pin.get_json(), {"error": "incorrect reader or writer PIN"})

            read_with_wrong_write_pin = client.get("/api/leaderboard", headers={"X-Write-Pin": "wrong-write"})
            self.assertEqual(read_with_wrong_write_pin.status_code, 401)
            self.assertEqual(read_with_wrong_write_pin.get_json(), {"error": "incorrect reader or writer PIN"})

            read_with_read_pin = client.get("/api/leaderboard", headers={"X-Read-Pin": "read-1234"})
            self.assertEqual(read_with_read_pin.status_code, 200)

            read_with_writer_pin = client.get("/api/leaderboard", headers={"X-Write-Pin": "write-5678"})
            self.assertEqual(read_with_writer_pin.status_code, 200)

            write_no_auth = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
            )
            self.assertEqual(write_no_auth.status_code, 403)
            self.assertEqual(write_no_auth.get_json(), {"error": "writer authorization required"})

            write_with_read_pin = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
                headers={"X-Read-Pin": "read-1234"},
            )
            self.assertEqual(write_with_read_pin.status_code, 403)
            self.assertEqual(write_with_read_pin.get_json(), {"error": "writer authorization required"})

            write_with_wrong_writer_pin = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
                headers={"X-Write-Pin": "wrong-write"},
            )
            self.assertEqual(write_with_wrong_writer_pin.status_code, 403)
            self.assertEqual(write_with_wrong_writer_pin.get_json(), {"error": "incorrect writer PIN"})

            write_with_writer_pin = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
                headers={"X-Write-Pin": "write-5678"},
            )
            self.assertEqual(write_with_writer_pin.status_code, 201)

    def test_managed_auth_role_matrix_and_strict_legacy_rejection(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())
                players["bob"] = (trueskill.Rating(), trueskill.Rating())

            class StubAuthenticator:
                def authenticate(self, request):
                    role = request.headers.get("X-Test-Role")
                    if role not in {"reader", "operator", "admin"}:
                        return None
                    return AuthActor(f"user_{role}", role.title(), role)

            app = create_app(
                db_dir=tmp_path,
                operator_token=self.operator_token,
                auth_mode="clerk",
                authenticator=StubAuthenticator(),
            )
            client = app.test_client()

            self.assertEqual(client.get("/api/leaderboard").status_code, 401)
            legacy_read = client.get(
                "/api/leaderboard",
                headers={"X-Read-Pin": "legacy-read"},
            )
            self.assertEqual(legacy_read.status_code, 401)
            reader_read = client.get(
                "/api/leaderboard",
                headers={"X-Test-Role": "reader"},
            )
            self.assertEqual(reader_read.status_code, 200)
            identity = client.get(
                "/api/auth/me",
                headers={"X-Test-Role": "reader"},
            )
            self.assertEqual(
                identity.get_json(),
                {
                    "subject": "user_reader",
                    "display_name": "Reader",
                    "role": "reader",
                },
            )

            reader_write = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
                headers={"X-Test-Role": "reader"},
            )
            self.assertEqual(reader_write.status_code, 403)
            self.assertEqual(
                reader_write.get_json(),
                {"error": "operator authorization required"},
            )

            operator_write = client.post(
                "/api/matches",
                json={"team1": ["alice"], "team2": ["bob"], "score1": 5, "score2": 3},
                headers={"X-Test-Role": "operator"},
            )
            self.assertEqual(operator_write.status_code, 201)

    def test_hybrid_auth_accepts_legacy_pin(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            class AnonymousAuthenticator:
                def authenticate(self, request):
                    return None

            app = create_app(
                db_dir=tmp_path,
                read_pin_hash=generate_password_hash("read-1234"),
                write_pin_hash=generate_password_hash("write-5678"),
                auth_mode="hybrid",
                authenticator=AnonymousAuthenticator(),
            )
            client = app.test_client()
            response = client.get(
                "/api/leaderboard",
                headers={"X-Read-Pin": "read-1234"},
            )
            self.assertEqual(response.status_code, 200)

    def test_strict_clerk_mode_wires_dedicated_login_flow(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with shelve.open(str(tmp_path / "playerdb")) as players:
                players["private-player"] = (
                    trueskill.Rating(),
                    trueskill.Rating(),
                )

            class AnonymousAuthenticator:
                def authenticate(self, request):
                    return None

            frontend_domain = "correct.clerk.accounts.dev"
            encoded_domain = base64.urlsafe_b64encode(
                f"{frontend_domain}$".encode("ascii")
            ).decode("ascii").rstrip("=")
            app = create_app(
                db_dir=tmp_path,
                auth_mode="clerk",
                authenticator=AnonymousAuthenticator(),
                clerk_publishable_key=f"pk_test_{encoded_domain}",
                clerk_frontend_api_url="https://incorrect.clerk.accounts.dev",
            )
            client = app.test_client()
            html = client.get("/phone").get_data(as_text=True)

            self.assertIn("const AUTH_MODE = 'clerk';", html)
            self.assertIn(f"https://{frontend_domain}/npm/@clerk/ui@1", html)
            self.assertIn("@clerk/clerk-js@6/dist/clerk.browser.js", html)
            self.assertNotIn("incorrect.clerk.accounts.dev", html)
            self.assertIn("id='adminMatchesSection'", html)
            self.assertIn("<body class='strict-auth-pending'>", html)
            self.assertNotIn("id='clerkSignIn'", html)
            self.assertIn("id='appContent' style='display:none;'", html)
            self.assertIn("id='stickyBar' class='sticky' style='display:none;'", html)
            self.assertNotIn("Private-Player", html)
            self.assertIn(
                "id='adminNavBtn' class='btn small' type='button' style='display:none;", html
            )

            js = client.get("/static/js/phone.js").get_data(as_text=True)
            self.assertIn("window.__internal_ClerkUICtor", js)
            self.assertIn("headers.set('Authorization', `Bearer ${managedToken}`);", js)
            self.assertIn(
                "window.location.replace(`/login?next=${encodeURIComponent(returnPath)}`)",
                js,
            )
            self.assertIn("afterSignOutUrl: '/login'", js)
            self.assertIn("/api/admin/matches?limit=30", js)
            self.assertIn("expected_version: match.version", js)
            self.assertIn("match.submitted_by_display_name", js)
            self.assertIn(
                "names.length === 2 ? [names[1], names[0]] : names",
                js,
            )

            login_response = client.get("/login?next=/phone")
            self.assertEqual(login_response.status_code, 200)
            login_html = login_response.get_data(as_text=True)
            self.assertIn("<body class='login-page'>", login_html)
            self.assertIn("id='clerkSignIn' class='clerk-sign-in'", login_html)
            self.assertIn('const LOGIN_NEXT = "/phone";', login_html)
            self.assertIn(f"https://{frontend_domain}/npm/@clerk/ui@1", login_html)
            self.assertIn("/static/js/login.js?v=", login_html)

            login_js = client.get("/static/js/login.js").get_data(as_text=True)
            self.assertIn("Clerk.mountSignIn", login_js)
            self.assertIn("window.location.replace(LOGIN_NEXT)", login_js)
            self.assertIn("fallbackRedirectUrl: LOGIN_NEXT", login_js)

            unsafe_login_html = client.get(
                "/login?next=https://example.com/stolen"
            ).get_data(as_text=True)
            self.assertIn('const LOGIN_NEXT = "/phone";', unsafe_login_html)
            self.assertNotIn("example.com", unsafe_login_html)

    def test_login_route_is_disabled_outside_strict_clerk_mode(self) -> None:
        class AnonymousAuthenticator:
            def authenticate(self, request):
                return None

        for auth_mode in ("legacy", "hybrid"):
            with self.subTest(auth_mode=auth_mode):
                with TemporaryDirectory() as tmpdir:
                    app = create_app(
                        db_dir=Path(tmpdir),
                        operator_token=self.operator_token,
                        auth_mode=auth_mode,
                        authenticator=AnonymousAuthenticator(),
                    )
                    response = app.test_client().get(
                        "/login", follow_redirects=False
                    )
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.headers.get("Location"), "/phone")

    def test_admin_can_list_void_and_restore_match(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with shelve.open(str(tmp_path / "playerdb")) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())
                players["bob"] = (trueskill.Rating(), trueskill.Rating())
            store = ShelveWriteStore(tmp_path)
            submitted = store.submit_match(
                ["alice"],
                ["bob"],
                5,
                3,
                source="test",
                actor_subject="user_reader",
            )

            class StubAuthenticator:
                def authenticate(self, request):
                    role = request.headers.get("X-Test-Role")
                    if role not in {"reader", "admin"}:
                        return None
                    return AuthActor(f"user_{role}", role.title(), role)

            app = create_app(
                db_dir=tmp_path,
                auth_mode="clerk",
                authenticator=StubAuthenticator(),
                write_store=store,
            )
            client = app.test_client()
            with patch(
                "phone_api.resolve_managed_display_names",
                return_value={"user_reader": "Reader"},
            ):
                reader_list = client.get(
                    "/api/admin/matches",
                    headers={"X-Test-Role": "reader"},
                )
                self.assertEqual(reader_list.status_code, 403)

                admin_headers = {"X-Test-Role": "admin"}
                matches = client.get("/api/admin/matches", headers=admin_headers)
                self.assertEqual(matches.status_code, 200)
                item = matches.get_json()["items"][0]
                self.assertEqual(item["status"], "active")
                self.assertEqual(item["version"], 1)
                self.assertEqual(item["submitted_by"], "user_reader")
                self.assertEqual(item["submitted_by_display_name"], "Reader")
                vercel_encoded_match_id = submitted["match_id"].replace(":", "%253A")

                void_headers = {
                    **admin_headers,
                    "Idempotency-Key": "void-api-1",
                }
                (tmp_path / WRITE_LOCK_NAME).write_text("another-writer", encoding="utf-8")
                locked = client.post(
                    f"/api/admin/matches/{vercel_encoded_match_id}/void",
                    headers=void_headers,
                    json={"reason": "Incorrect score", "expected_version": 1},
                )
                self.assertEqual(locked.status_code, 409)
                (tmp_path / WRITE_LOCK_NAME).unlink()

                voided = client.post(
                    f"/api/admin/matches/{vercel_encoded_match_id}/void",
                    headers=void_headers,
                    json={"reason": "Incorrect score", "expected_version": 1},
                )
                self.assertEqual(voided.status_code, 200)
                self.assertEqual(voided.get_json()["status"], "voided")

                stale_restore = client.post(
                    f"/api/admin/matches/{submitted['match_id']}/restore",
                    headers={**admin_headers, "Idempotency-Key": "restore-stale"},
                    json={"reason": "Restore result", "expected_version": 1},
                )
                self.assertEqual(stale_restore.status_code, 409)

                restored = client.post(
                    f"/api/admin/matches/{submitted['match_id']}/restore",
                    headers={**admin_headers, "Idempotency-Key": "restore-api-1"},
                    json={"reason": "Restore result", "expected_version": 2},
                )
                self.assertEqual(restored.status_code, 200)
                self.assertEqual(restored.get_json()["status"], "active")

                audited = client.get("/api/admin/matches", headers=admin_headers).get_json()
                self.assertEqual(
                    [event["event_type"] for event in audited["items"][0]["events"]],
                    ["submit", "void", "restore"],
                )
                self.assertEqual(
                    audited["items"][0]["events"][-1]["actor_subject"],
                    "user_admin",
                )


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

    def test_player_profile_returns_recent_match_context_and_summaries(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            db_path = str(tmp_path / "playerdb")
            with shelve.open(db_path) as players:
                for name in ["alice", "bob", "carol", "dave"]:
                    players[name] = (trueskill.Rating(mu=25, sigma=8.333), trueskill.Rating(mu=25, sigma=8.333))

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()

            match_responses = [
                client.post(
                    "/api/matches",
                    json={"team1": ["alice", "bob"], "team2": ["carol", "dave"], "score1": 5, "score2": 3},
                    headers={"X-Operator-Token": self.operator_token},
                ),
                client.post(
                    "/api/matches",
                    json={"team1": ["alice", "bob"], "team2": ["carol", "dave"], "score1": 3, "score2": 5},
                    headers={"X-Operator-Token": self.operator_token},
                ),
                client.post(
                    "/api/matches",
                    json={"team1": ["alice"], "team2": ["carol"], "score1": 2, "score2": 5},
                    headers={"X-Operator-Token": self.operator_token},
                ),
            ]
            for response in match_responses:
                self.assertEqual(response.status_code, 201)

            response = client.get("/api/player/alice/profile?scope=all&recent_limit=5")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            assert payload is not None
            self.assertEqual(payload["player"], "alice")
            self.assertEqual(payload["summary"]["games"], 3)
            self.assertEqual(payload["summary"]["wins"], 1)
            self.assertEqual(payload["best_partner"]["player"], "Bob")
            self.assertEqual(payload["best_partner"]["matches"], 2)
            self.assertEqual(payload["toughest_opponent"]["player"], "Carol")
            self.assertEqual(payload["recent_matches"][0]["team"], ["Alice"])
            self.assertEqual(payload["recent_matches"][0]["opponents"], ["Carol"])
            self.assertEqual(payload["recent_matches"][1]["team"], ["Bob", "Alice"])
            self.assertEqual(payload["recent_matches"][1]["opponents"], ["Dave", "Carol"])

    def test_player_profile_scope_trend_matches_returned_recent_matches(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
            local_now = now.astimezone()
            quarter_start_month = ((local_now.month - 1) // 3) * 3 + 1
            start_quarter_local = local_now.replace(
                month=quarter_start_month,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            in_scope_ts = (start_quarter_local + timedelta(days=10)).astimezone(timezone.utc)
            out_scope_ts = (start_quarter_local - timedelta(days=1)).astimezone(timezone.utc)

            def player_entry(name: str, off_before: float, off_after: float, def_before: float, def_after: float) -> dict:
                return {
                    "name": name,
                    "before": {
                        "offense_mu": off_before,
                        "offense_sigma": 8.333,
                        "defense_mu": def_before,
                        "defense_sigma": 8.333,
                    },
                    "after": {
                        "offense_mu": off_after,
                        "offense_sigma": 8.0,
                        "defense_mu": def_after,
                        "defense_sigma": 8.0,
                    },
                }

            self._write_history_record(
                tmp_path,
                out_scope_ts,
                ["alice", "bob"],
                ["carol", "dave"],
                ["alice", "bob"],
                5,
                2,
                players=[
                    player_entry("alice", 20.0, 99.0, 20.0, 50.0),
                    player_entry("bob", 20.0, 20.0, 20.0, 20.0),
                    player_entry("carol", 20.0, 20.0, 20.0, 20.0),
                    player_entry("dave", 20.0, 20.0, 20.0, 20.0),
                ],
            )
            self._write_history_record(
                tmp_path,
                in_scope_ts,
                ["alice", "bob"],
                ["carol", "dave"],
                ["alice", "bob"],
                5,
                3,
                players=[
                    player_entry("alice", 25.0, 30.1, 18.0, 16.6),
                    player_entry("bob", 20.0, 20.0, 20.0, 20.0),
                    player_entry("carol", 20.0, 20.0, 20.0, 20.0),
                    player_entry("dave", 20.0, 20.0, 20.0, 20.0),
                ],
            )
            self._write_history_record(
                tmp_path,
                (in_scope_ts + timedelta(days=1)),
                ["alice", "bob"],
                ["carol", "dave"],
                ["carol", "dave"],
                4,
                5,
                players=[
                    player_entry("alice", 30.1, 27.3, 16.6, 19.4),
                    player_entry("bob", 20.0, 20.0, 20.0, 20.0),
                    player_entry("carol", 20.0, 20.0, 20.0, 20.0),
                    player_entry("dave", 20.0, 20.0, 20.0, 20.0),
                ],
            )

            with patch("services.match_history._current_utc", return_value=now):
                app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
                client = app.test_client()
                response = client.get("/api/player/alice/profile?scope=this_quarter&recent_limit=5")
                self.assertEqual(response.status_code, 200)
                payload = response.get_json()
                assert payload is not None
                self.assertEqual(len(payload["recent_matches"]), 2)
                self.assertAlmostEqual(payload["trend"]["offense"], 2.3, places=2)
                self.assertAlmostEqual(payload["trend"]["defense"], 1.4, places=2)

    def test_team_h2h_is_order_sensitive_for_doubles(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            self._write_history_record(tmp_path, datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc), ["alice", "bob"], ["carol", "dave"], ["alice", "bob"], 5, 3)
            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()

            matching = client.get("/api/team-h2h?team1=alice,bob&team2=carol,dave")
            self.assertEqual(matching.status_code, 200)
            matching_payload = matching.get_json()
            assert matching_payload is not None
            self.assertEqual(matching_payload["matches"], 1)
            self.assertEqual(matching_payload["team1_wins"], 1)

            reordered = client.get("/api/team-h2h?team1=bob,alice&team2=carol,dave")
            self.assertEqual(reordered.status_code, 200)
            reordered_payload = reordered.get_json()
            assert reordered_payload is not None
            self.assertEqual(reordered_payload["matches"], 0)

    def test_scoped_leaderboard_hides_inactive_players(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
            local_now = now.astimezone()
            quarter_start_month = ((local_now.month - 1) // 3) * 3 + 1
            start_quarter_local = local_now.replace(
                month=quarter_start_month,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            start_week_local = (local_now - timedelta(days=local_now.weekday())).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            start_month_local = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_week = start_week_local.astimezone(timezone.utc)
            this_quarter_ts = (start_quarter_local + ((local_now - start_quarter_local) / 3)).astimezone(timezone.utc)
            week_base_local = max(start_week_local, start_month_local)
            this_week_ts = (week_base_local + ((local_now - week_base_local) / 2)).astimezone(timezone.utc)
            this_month_ts = (start_month_local + ((local_now - start_month_local) / 4)).astimezone(timezone.utc)
            previous_quarter_ts = (start_quarter_local - timedelta(hours=1)).astimezone(timezone.utc)

            self._write_history_record(tmp_path, previous_quarter_ts, ["alice"], ["bob"], ["alice"], 5, 3)
            self._write_history_record(tmp_path, this_quarter_ts, ["gina"], ["hank"], ["gina"], 5, 4)
            self._write_history_record(tmp_path, this_month_ts, ["carol"], ["dave"], ["carol"], 5, 2)
            self._write_history_record(tmp_path, this_week_ts, ["eve"], ["frank"], ["eve"], 5, 1)

            with patch("services.match_history._current_utc", return_value=now):
                app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
                client = app.test_client()

                quarter_resp = client.get("/api/leaderboard?scope=this_quarter")
                self.assertEqual(quarter_resp.status_code, 200)
                quarter_payload = quarter_resp.get_json()
                assert quarter_payload is not None
                quarter_names = {item["name"].lower() for item in quarter_payload["items"]}
                self.assertIn("gina", quarter_names)
                self.assertIn("hank", quarter_names)
                self.assertIn("carol", quarter_names)
                self.assertIn("dave", quarter_names)
                self.assertIn("eve", quarter_names)
                self.assertIn("frank", quarter_names)
                self.assertNotIn("alice", quarter_names)
                self.assertNotIn("bob", quarter_names)

                month_resp = client.get("/api/leaderboard?scope=this_month")
                self.assertEqual(month_resp.status_code, 200)
                month_payload = month_resp.get_json()
                assert month_payload is not None
                month_names = {item["name"].lower() for item in month_payload["items"]}
                if this_quarter_ts >= start_month_local.astimezone(timezone.utc):
                    self.assertIn("gina", month_names)
                    self.assertIn("hank", month_names)
                else:
                    self.assertNotIn("gina", month_names)
                    self.assertNotIn("hank", month_names)
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
                if this_month_ts >= start_week:
                    self.assertIn("carol", week_names)
                    self.assertIn("dave", week_names)
                else:
                    self.assertNotIn("carol", week_names)
                    self.assertNotIn("dave", week_names)

    def test_scoped_leaderboard_levels_use_average_total_level(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            now = datetime.now(timezone.utc)
            local_now = now.astimezone()
            quarter_start_month = ((local_now.month - 1) // 3) * 3 + 1
            start_quarter_local = local_now.replace(
                month=quarter_start_month,
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            start_week_local = (local_now - timedelta(days=local_now.weekday())).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            start_month_local = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            this_quarter_ts = (start_quarter_local + ((local_now - start_quarter_local) / 3)).astimezone(timezone.utc)
            week_base_local = max(start_week_local, start_month_local)
            this_month_ts = (start_month_local + ((local_now - start_month_local) / 4)).astimezone(timezone.utc)
            this_week_ts = (week_base_local + ((local_now - week_base_local) / 2)).astimezone(timezone.utc)

            self._write_history_record(tmp_path, this_quarter_ts, ["gina"], ["hank"], ["gina"], 5, 4)
            self._write_history_record(tmp_path, this_month_ts, ["carol"], ["dave"], ["carol"], 5, 2)
            self._write_history_record(tmp_path, this_week_ts, ["eve"], ["frank"], ["eve"], 5, 1)

            expected_quarter = playerLevel(calculate_rating_update(
                {
                    "gina": (trueskill.Rating(), trueskill.Rating()),
                    "hank": (trueskill.Rating(), trueskill.Rating()),
                    "carol": (trueskill.Rating(), trueskill.Rating()),
                    "dave": (trueskill.Rating(), trueskill.Rating()),
                    "eve": (trueskill.Rating(), trueskill.Rating()),
                    "frank": (trueskill.Rating(), trueskill.Rating()),
                },
                ["gina"],
                ["hank"],
                5,
                4,
            )["gina"])
            expected_month = playerLevel(calculate_rating_update(
                {
                    "carol": (trueskill.Rating(), trueskill.Rating()),
                    "dave": (trueskill.Rating(), trueskill.Rating()),
                    "eve": (trueskill.Rating(), trueskill.Rating()),
                    "frank": (trueskill.Rating(), trueskill.Rating()),
                },
                ["carol"],
                ["dave"],
                5,
                2,
            )["carol"])
            expected_week = playerLevel(calculate_rating_update(
                {
                    "eve": (trueskill.Rating(), trueskill.Rating()),
                    "frank": (trueskill.Rating(), trueskill.Rating()),
                },
                ["eve"],
                ["frank"],
                5,
                1,
            )["eve"])

            app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
            client = app.test_client()

            quarter_resp = client.get("/api/leaderboard?scope=this_quarter")
            self.assertEqual(quarter_resp.status_code, 200)
            quarter_payload = quarter_resp.get_json()
            assert quarter_payload is not None
            quarter_items = {item["name"].lower(): item for item in quarter_payload["items"]}
            self.assertAlmostEqual(quarter_items["gina"]["level"], round(expected_quarter, 2), places=2)

            month_resp = client.get("/api/leaderboard?scope=this_month")
            self.assertEqual(month_resp.status_code, 200)
            month_payload = month_resp.get_json()
            assert month_payload is not None
            month_items = {item["name"].lower(): item for item in month_payload["items"]}
            self.assertAlmostEqual(month_items["carol"]["level"], round(expected_month, 2), places=2)

            week_resp = client.get("/api/leaderboard?scope=this_week")
            self.assertEqual(week_resp.status_code, 200)
            week_payload = week_resp.get_json()
            assert week_payload is not None
            week_items = {item["name"].lower(): item for item in week_payload["items"]}
            self.assertAlmostEqual(week_items["eve"]["level"], round(expected_week, 2), places=2)

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
            now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
            local_now = now.astimezone()
            start_week_local = (local_now - timedelta(days=local_now.weekday())).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            start_month_local = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            start_week = start_week_local.astimezone(timezone.utc)
            start_month = start_month_local.astimezone(timezone.utc)

            pre_scope_ts = (min(start_month_local, start_week_local) - timedelta(hours=1)).astimezone(timezone.utc)
            week_base_local = max(start_week_local, start_month_local)
            month_match_ts = (start_month_local + ((local_now - start_month_local) / 4)).astimezone(timezone.utc)
            week_match_ts = (week_base_local + ((local_now - week_base_local) / 2)).astimezone(timezone.utc)

            # A pre-scope match moves all-time level to 7.0.
            self._write_history_record(
                tmp_path,
                pre_scope_ts,
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

            # The first in-month match starts at 7.0 and ends at 12.5.
            self._write_history_record(
                tmp_path,
                month_match_ts,
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

            # The latest in-week match ends at 16.0.
            self._write_history_record(
                tmp_path,
                week_match_ts,
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

            with patch("services.match_history._current_utc", return_value=now):
                app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
                client = app.test_client()

                month_stats = client.get("/api/stats?scope=this_month")
                self.assertEqual(month_stats.status_code, 200)
                month_payload = month_stats.get_json()
                assert month_payload is not None
                self.assertAlmostEqual(month_payload["alice"]["improved"], 9.0, places=2)

                quarter_stats = client.get("/api/stats?scope=this_quarter")
                self.assertEqual(quarter_stats.status_code, 200)
                quarter_payload = quarter_stats.get_json()
                assert quarter_payload is not None
                self.assertAlmostEqual(quarter_payload["alice"]["improved"], 16.0, places=2)

                week_stats = client.get("/api/stats?scope=this_week")
                self.assertEqual(week_stats.status_code, 200)
                week_payload = week_stats.get_json()
                assert week_payload is not None
                expected_week_improved = 9.0 if month_match_ts >= start_week else 3.5
                self.assertAlmostEqual(week_payload["alice"]["improved"], expected_week_improved, places=2)

    def test_stats_scope_uses_only_scoped_matches_for_form_and_streak(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
            local_now = now.astimezone()
            start_week_local = (local_now - timedelta(days=local_now.weekday())).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            start_month_local = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            pre_scope_ts = (min(start_month_local, start_week_local) - timedelta(hours=1)).astimezone(timezone.utc)
            week_match_ts = (max(start_week_local, start_month_local) + timedelta(hours=12)).astimezone(timezone.utc)

            self._write_history_record(tmp_path, pre_scope_ts, ["alice"], ["bob"], ["alice"], 5, 3)
            self._write_history_record(tmp_path, week_match_ts, ["alice"], ["bob"], ["alice"], 5, 1)

            with patch("services.match_history._current_utc", return_value=now):
                app = create_app(db_dir=tmp_path, operator_token=self.operator_token)
                client = app.test_client()

                all_stats = client.get("/api/stats")
                self.assertEqual(all_stats.status_code, 200)
                all_payload = all_stats.get_json()
                assert all_payload is not None
                self.assertEqual(all_payload["alice"]["games"], 2)
                self.assertEqual(all_payload["alice"]["streak"], 2)
                self.assertEqual(all_payload["alice"]["recent_form_5"], "WW")

                week_stats = client.get("/api/stats?scope=this_week")
                self.assertEqual(week_stats.status_code, 200)
                week_payload = week_stats.get_json()
                assert week_payload is not None
                self.assertEqual(week_payload["alice"]["games"], 1)
                self.assertEqual(week_payload["alice"]["streak"], 1)
                self.assertEqual(week_payload["alice"]["recent_form_5"], "W")


if __name__ == "__main__":
    unittest.main()
