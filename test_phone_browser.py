from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import trueskill
from flask import request
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

from phone_api import create_app  # noqa: E402
from services.auth import AuthActor  # noqa: E402
from services.phone_write_store import ShelveWriteStore  # noqa: E402


class PhoneBrowserTests(unittest.TestCase):
    def test_managed_corrections_in_browser(self) -> None:
        import shelve

        edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        browser = (
            str(edge)
            if edge.is_file()
            else shutil.which("chromium") or shutil.which("google-chrome")
        )
        if not browser:
            self.skipTest("Chromium or Microsoft Edge is required")

        class StubAuthenticator:
            def authenticate(self, request):
                role = request.headers.get("Authorization", "").removeprefix("Bearer ")
                return (
                    AuthActor(f"user_{role}", role.title(), role)
                    if role in {"reader", "operator", "admin"}
                    else None
                )

        with TemporaryDirectory(prefix=".phone-admin-test-", dir=ROOT) as directory:
            db_dir = Path(directory)
            with shelve.open(str(db_dir / "playerdb")) as players:
                players["alice"] = (trueskill.Rating(), trueskill.Rating())
                players["bob"] = (trueskill.Rating(), trueskill.Rating())
            store = ShelveWriteStore(db_dir)
            store.submit_match(["alice"], ["bob"], 5, 3, source="test", actor_subject="user_admin")
            app = create_app(
                db_dir=db_dir,
                auth_mode="clerk",
                authenticator=StubAuthenticator(),
                write_store=store,
            )

            @app.after_request
            def inject_browser_test(response):
                if request.path == "/phone":
                    script = (ROOT / "tests" / "phone_corrections.js").read_text(encoding="utf-8")
                    html = (
                        response.get_data(as_text=True)
                        .replace(
                            "<script>const AUTH_MODE",
                            "<script>window.Clerk = { isSignedIn: true, session: { "
                            "getToken: async () => "
                            "new URLSearchParams(location.search).get('role') "
                            "}, load: async () => {}, mountUserButton: () => {}, "
                            "addListener: () => {} };</script><script>const AUTH_MODE",
                        )
                        .replace("</body>", f"<script>{script}</script></body>")
                    )
                    response.set_data(html)
                return response

            server = make_server("127.0.0.1", 0, app, threaded=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for role, viewport in (
                    ("reader", "390,844"),
                    ("operator", "390,844"),
                    ("admin", "1200,900"),
                ):
                    with self.subTest(role=role):
                        result = subprocess.run(
                            [
                                browser,
                                "--headless",
                                "--disable-gpu",
                                "--no-sandbox",
                                "--disable-extensions",
                                f"--user-data-dir={db_dir / ('profile-' + role)}",
                                f"--window-size={viewport}",
                                "--virtual-time-budget=15000",
                                "--dump-dom",
                                f"http://127.0.0.1:{server.server_port}/phone?role={role}",
                            ],
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=60,
                            env={
                                **os.environ,
                                "TEMP": directory,
                                "TMP": directory,
                                "TMPDIR": directory,
                            },
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        marker = re.search(r'data-test-result="([^"]+)"', result.stdout)
                        self.assertEqual(marker.group(1) if marker else "no result", "pass")
            finally:
                server.shutdown()
                thread.join()
                server.server_close()

    def test_phone_welcomes_operators_to_match_entry(self) -> None:
        response = create_app(operator_token="test-token").test_client().get("/phone")
        self.assertIn(b"Matchday Gazette", response.data)
        self.assertIn(b"Record a match", response.data)

    def test_phone_stylesheet_url_changes_when_styles_change(self) -> None:
        original_read = Path.read_bytes

        def changed_style(path: Path) -> bytes:
            data = original_read(path)
            return data + b"\n" if path.name == "phone-gazette.css" else data

        before = create_app(operator_token="test-token").test_client().get("/phone").data
        with patch.object(Path, "read_bytes", changed_style):
            after = create_app(operator_token="test-token").test_client().get("/phone").data
        pattern = rb"css/phone-gazette.css\?v=([a-f0-9]+)"
        self.assertNotEqual(re.search(pattern, before).group(1), re.search(pattern, after).group(1))

    def test_match_entry_in_browser(self) -> None:
        edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        browser = (
            str(edge)
            if edge.is_file()
            else shutil.which("chromium") or shutil.which("google-chrome")
        )
        if not browser:
            self.skipTest("Chromium or Microsoft Edge is required")

        with TemporaryDirectory(prefix=".phone-ui-test-", dir=ROOT) as directory:
            app = create_app(db_dir=Path(directory), operator_token="test-token")

            @app.after_request
            def inject_browser_test(response):
                if request.path == "/phone":
                    script = (ROOT / "tests" / "phone_match_entry.js").read_text(encoding="utf-8")
                    html = response.get_data(as_text=True).replace(
                        "</body>", f"<script>{script}</script></body>"
                    )
                    response.set_data(html)
                return response

            client = app.test_client()
            for name in ("Alice", "Bob", "Carol", "Dave"):
                response = client.post(
                    "/api/players",
                    json={"name": name},
                    headers={"X-Operator-Token": "test-token"},
                )
                self.assertEqual(response.status_code, 201, response.data)
                response = client.post(
                    "/api/presence",
                    json={"name": name, "active": True},
                    headers={"X-Operator-Token": "test-token"},
                )
                self.assertEqual(response.status_code, 200, response.data)

            server = make_server("127.0.0.1", 0, app, threaded=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for mode, viewport in (("singles", "390,844"), ("doubles", "1200,900")):
                    with self.subTest(mode=mode):
                        profile = Path(directory) / f"profile-{mode}"
                        env = {
                            **os.environ,
                            "TEMP": directory,
                            "TMP": directory,
                            "TMPDIR": directory,
                        }
                        result = subprocess.run(
                            [
                                browser,
                                "--headless",
                                "--disable-gpu",
                                "--no-sandbox",
                                "--disable-extensions",
                                f"--user-data-dir={profile}",
                                f"--window-size={viewport}",
                                "--virtual-time-budget=15000",
                                "--dump-dom",
                                f"http://127.0.0.1:{server.server_port}/phone?test={mode}",
                            ],
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=60,
                            env=env,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        marker = re.search(r'data-test-result="([^"]+)"', result.stdout)
                        self.assertEqual(marker.group(1) if marker else "no result", "pass")
            finally:
                server.shutdown()
                thread.join()
                server.server_close()
