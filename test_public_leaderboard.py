from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import trueskill

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

from phone_api import create_app  # noqa: E402


class PublicLeaderboardTests(unittest.TestCase):
    def test_colliding_display_names_keep_separate_identifiers(self) -> None:
        class Store:
            uses_local_lock = False

            def leaderboard_ratings(self, scope: str):
                rating = (trueskill.Rating(), trueskill.Rating())
                return {"john smith": rating, "john  smith": rating}

            def query_player_stats(self, scope: str = "all"):
                return {"john smith": {"streak": 1}, "john  smith": {"streak": 3}}

            def query_player_profile(self, player: str, scope: str = "all", recent_limit: int = 5):
                return {
                    "player": player,
                    "summary": {"streak": self.query_player_stats()[player]["streak"]},
                }

        client = create_app(operator_token="test-token", write_store=Store()).test_client()
        public = client.get("/api/public/leaderboard").get_json()["items"]
        private = client.get("/api/leaderboard").get_json()["items"]
        stats = client.get("/api/public/stats").get_json()

        self.assertEqual({row["name"] for row in public}, {"John Smith"})
        self.assertEqual({row["player_id"] for row in public}, {"john smith", "john  smith"})
        self.assertTrue(all("player_id" not in row for row in private))
        for row in public:
            identifier = row["player_id"]
            profile = client.get(f"/api/public/player/{identifier}/profile").get_json()
            self.assertEqual(profile["player"], identifier)
            self.assertEqual(profile["summary"]["streak"], stats[identifier]["streak"])

    def test_browser_uses_identifiers_for_stats_and_profiles(self) -> None:
        edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        browser = shutil.which("chromium") or shutil.which("google-chrome")
        if edge.is_file():
            browser = str(edge)
        if not browser:
            self.skipTest("Chromium or Microsoft Edge is required for the browser regression")

        with TemporaryDirectory(prefix=".public-ui-test-", dir=ROOT) as directory:
            env = {**os.environ, "TEMP": directory, "TMP": directory, "TMPDIR": directory}
            result = subprocess.run(
                [
                    browser,
                    "--headless",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-extensions",
                    f"--user-data-dir={directory}",
                    "--virtual-time-budget=5000",
                    "--dump-dom",
                    (ROOT / "tests" / "public_leaderboard.html").as_uri(),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                env=env,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('data-test-result="pass"', result.stdout, result.stdout)
