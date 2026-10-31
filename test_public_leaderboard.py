from __future__ import annotations

import os
import re
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
    def test_public_page_welcomes_visitors_and_links_to_phone(self) -> None:
        client = create_app(operator_token="test-token").test_client()

        page = client.get("/").get_data(as_text=True)

        self.assertIn("Matchday Gazette", page)
        self.assertIn("Hiscores", page)
        self.assertIn('href="/phone"', page)
        self.assertIn("css/public.css?v=", page)

    def test_rendered_page_at_phone_and_desktop_widths(self) -> None:
        edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        browser = shutil.which("chromium") or shutil.which("google-chrome")
        if edge.is_file():
            browser = str(edge)
        if not browser:
            self.skipTest("Chromium or Microsoft Edge is required for the browser regression")

        page = create_app(operator_token="test-token").test_client().get("/").get_data(as_text=True)
        for asset in ("css/public.css", "js/public.js"):
            page = re.sub(
                rf"/static/{re.escape(asset)}\?v=[^\"']+",
                (ROOT / "app" / "static" / asset).as_uri(),
                page,
            )
        setup = """
        <script>
        window.fetch = async () => ({ok: true, json: async () => ({items: [
          {position: 1, name: 'A player', player_id: 'a player', level: 20,
           offense_level: 11, defense_level: 9}
        ]})});
        document.addEventListener('DOMContentLoaded', () => setTimeout(() => {
          const button = document.querySelector('[data-metric="total"]');
          button.focus();
          const outline = getComputedStyle(button).outlineStyle;
          const fail = document.documentElement.scrollWidth > window.innerWidth ||
            button.getBoundingClientRect().height < 44 || outline === 'none' ||
            !document.querySelector('#leaderboardBody').textContent.includes('A player') ||
            button.getAttribute('aria-pressed') !== 'true';
          window.parent.postMessage(fail ? 'fail' : 'pass', '*');
        }, 100));
        </script>
        """
        page = page.replace("</head>", setup + "</head>")
        with TemporaryDirectory(prefix=".public-layout-test-", dir=ROOT) as directory:
            html = Path(directory) / "page.html"
            html.write_text(page, encoding="utf-8")
            env = {**os.environ, "TEMP": directory, "TMP": directory, "TMPDIR": directory}
            for width in (390, 1280):
                with self.subTest(width=width):
                    wrapper = Path(directory) / f"wrapper-{width}.html"
                    wrapper.write_text(
                        "<!doctype html><body>"
                        "<script>window.addEventListener('message', e => "
                        "{ document.body.dataset.testResult = e.data; });</script>"
                        f'<iframe width="{width}" height="850" src="{html.as_uri()}"></iframe>'
                        "</body>",
                        encoding="utf-8",
                    )
                    result = subprocess.run(
                        [
                            browser,
                            "--headless",
                            "--disable-gpu",
                            "--no-sandbox",
                            "--disable-extensions",
                            f"--user-data-dir={directory}\\browser-{width}",
                            "--window-size=1400,1000",
                            "--virtual-time-budget=5000",
                            "--dump-dom",
                            wrapper.as_uri(),
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
        private_with_ids = client.get("/api/leaderboard?include_player_id=1").get_json()["items"]
        stats = client.get("/api/public/stats").get_json()

        self.assertEqual({row["name"] for row in public}, {"John Smith"})
        self.assertEqual({row["player_id"] for row in public}, {"john smith", "john  smith"})
        self.assertTrue(all("player_id" not in row for row in private))
        self.assertEqual(
            {row["player_id"] for row in private_with_ids}, {"john smith", "john  smith"}
        )
        self.assertEqual(
            [
                {key: value for key, value in row.items() if key != "player_id"}
                for row in private_with_ids
            ],
            private,
        )
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
