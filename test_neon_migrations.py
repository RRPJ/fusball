from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.neon_migrations import MigrationError, discover_migrations  # noqa: E402


class NeonMigrationTests(unittest.TestCase):
    def test_discovers_migrations_in_version_order_with_stable_checksums(self) -> None:
        with TemporaryDirectory() as tmpdir:
            migrations_dir = Path(tmpdir)
            (migrations_dir / "0002_second.sql").write_text(
                "CREATE TABLE second_table (id INTEGER);",
                encoding="utf-8",
            )
            (migrations_dir / "0001_first.sql").write_text(
                "CREATE TABLE first_table (id INTEGER);",
                encoding="utf-8",
            )

            first_discovery = discover_migrations(migrations_dir)
            second_discovery = discover_migrations(migrations_dir)

            self.assertEqual([migration.version for migration in first_discovery], ["0001", "0002"])
            self.assertEqual(
                [migration.checksum for migration in first_discovery],
                [migration.checksum for migration in second_discovery],
            )

    def test_rejects_migration_filename_without_ordered_version(self) -> None:
        with TemporaryDirectory() as tmpdir:
            migrations_dir = Path(tmpdir)
            (migrations_dir / "initial.sql").write_text("SELECT 1;", encoding="utf-8")

            with self.assertRaisesRegex(MigrationError, "invalid migration filename"):
                discover_migrations(migrations_dir)


if __name__ == "__main__":
    unittest.main()
