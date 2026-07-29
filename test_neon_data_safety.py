from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import services.neon_data_safety as data_safety  # noqa: E402
from services.neon_data_safety import (  # noqa: E402
    DataSafetyError,
    decrypt_export_artifact,
    encrypt_export_artifact,
    integrity_report,
    validate_export_artifact,
)


def _empty_artifact() -> dict:
    migrations = data_safety._migration_manifest()
    tables = {table: [] for table in data_safety.TABLE_SPECS}
    snapshot = {
        "database": {"name": "test", "server_version": "16"},
        "migrations": migrations,
        "tables": tables,
    }
    artifact = {
        "format": data_safety.EXPORT_FORMAT,
        "format_version": data_safety.EXPORT_FORMAT_VERSION,
        "exported_at": "2026-07-29T12:00:00+00:00",
        "source": snapshot["database"],
        "schema": {"migrations": migrations},
        "tables": tables,
        "integrity": integrity_report(snapshot),
    }
    artifact["artifact_sha256"] = data_safety._sha256(artifact)
    return artifact


class NeonDataSafetyTests(unittest.TestCase):
    def test_timestamp_checksums_are_timezone_independent(self) -> None:
        utc_value = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
        local_value = utc_value.astimezone(timezone(timedelta(hours=2)))

        self.assertEqual(
            data_safety._sha256({"timestamp": utc_value}),
            data_safety._sha256({"timestamp": local_value}),
        )

    def test_encrypted_artifact_round_trip_validates_checksums(self) -> None:
        artifact = _empty_artifact()
        key = Fernet.generate_key().decode("ascii")

        encrypted = encrypt_export_artifact(artifact, key)
        restored = decrypt_export_artifact(encrypted, key)

        self.assertEqual(restored, artifact)
        self.assertNotIn(b"fusball-neon-export", encrypted)

    def test_rejects_tampered_artifact(self) -> None:
        artifact = _empty_artifact()
        artifact["exported_at"] = "changed"

        with self.assertRaisesRegex(DataSafetyError, "artifact checksum mismatch"):
            validate_export_artifact(artifact)

    def test_rejects_schema_from_another_application_version(self) -> None:
        artifact = _empty_artifact()
        artifact["schema"]["migrations"] = []
        artifact["artifact_sha256"] = data_safety._sha256(
            {key: value for key, value in artifact.items() if key != "artifact_sha256"}
        )

        with self.assertRaisesRegex(DataSafetyError, "schema is not compatible"):
            validate_export_artifact(artifact)

    def test_readiness_hides_connection_error_details(self) -> None:
        class FailingPsycopg:
            @staticmethod
            def connect(*args, **kwargs):
                raise RuntimeError("postgresql://secret@host/database")

        with patch.dict(sys.modules, {"psycopg": FailingPsycopg}):
            result = data_safety.check_neon_readiness("postgresql://secret")

        self.assertEqual(
            result,
            {"ok": False, "store": "neon", "reason": "database_unavailable"},
        )
        self.assertNotIn("secret", str(result))


if __name__ == "__main__":
    unittest.main()
