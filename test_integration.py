from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from phone_api import create_app  # noqa: E402
from startup import run_diagnostics  # noqa: E402


class PhoneOnlyIntegrationTests(unittest.TestCase):
    def test_startup_diagnostics_run_against_custom_data_dir(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            self.assertTrue(run_diagnostics(tmp_path))
            self.assertTrue((tmp_path / "startup.log").exists())

    def test_phone_api_health_endpoint_starts_without_kiosk_modules(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            app = create_app(db_dir=tmp_path, operator_token="secret-token")
            client = app.test_client()

            response = client.get("/api/health")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {"ok": True})


if __name__ == "__main__":
    unittest.main()
