from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import psycopg
import trueskill

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.auth import NeonUserRoleStore  # noqa: E402
from services.neon_data_safety import (  # noqa: E402
    build_export_artifact,
    restore_export_artifact,
)
from services.neon_migrations import apply_migrations  # noqa: E402
from services.phone_write_store import NeonWriteStore  # noqa: E402
from services.store_contracts import ReplayParityError  # noqa: E402

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "TEST_DATABASE_URL is required for Neon store integration tests")
class NeonWriteStoreIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        assert DATABASE_URL is not None
        self.database_url = DATABASE_URL
        with psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS match_events")
                cur.execute("DROP TABLE IF EXISTS recent_players")
                cur.execute("DROP TABLE IF EXISTS match_history")
                cur.execute("DROP TABLE IF EXISTS rating_baselines")
                cur.execute("DROP TABLE IF EXISTS app_users")
                cur.execute("DROP TABLE IF EXISTS players")
                cur.execute("DROP TABLE IF EXISTS schema_migrations")
            apply_migrations(conn)
            with conn.cursor() as cur:
                default = trueskill.Rating()
                cur.executemany(
                    """
                    INSERT INTO players (
                        name, offense_mu, offense_sigma, defense_mu, defense_sigma
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (name, default.mu, default.sigma, default.mu, default.sigma)
                        for name in ("alice", "bob")
                    ],
                )
                cur.execute(
                    """
                    INSERT INTO rating_baselines (
                        player_name, offense_mu, offense_sigma,
                        defense_mu, defense_sigma, source
                    )
                    SELECT name, offense_mu, offense_sigma,
                           defense_mu, defense_sigma, 'test'
                    FROM players
                    """
                )

    def test_submit_match_rolls_back_ratings_when_history_insert_fails(self) -> None:
        store = NeonWriteStore(self.database_url)
        before = store.get_player_ratings(["alice", "bob"])

        with psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE match_history CASCADE")

        with self.assertRaises(psycopg.errors.UndefinedTable):
            store.submit_match(["alice"], ["bob"], 5, 3, source="test")

        after = store.get_player_ratings(["alice", "bob"])
        for name in ("alice", "bob"):
            self.assertAlmostEqual(after[name][0].mu, before[name][0].mu, places=10)
            self.assertAlmostEqual(after[name][0].sigma, before[name][0].sigma, places=10)
            self.assertAlmostEqual(after[name][1].mu, before[name][1].mu, places=10)
            self.assertAlmostEqual(after[name][1].sigma, before[name][1].sigma, places=10)

    def test_user_role_store_excludes_disabled_users(self) -> None:
        with psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO app_users (
                        provider_subject, display_name, role, status
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    [
                        ("user_active", "Active Operator", "operator", "active"),
                        ("user_disabled", "Disabled Admin", "admin", "disabled"),
                    ],
                )

        role_store = NeonUserRoleStore(self.database_url)
        actor = role_store.resolve_actor("user_active")
        self.assertIsNotNone(actor)
        assert actor is not None
        self.assertEqual(actor.role, "operator")
        self.assertIsNone(role_store.resolve_actor("user_disabled"))

    def test_submit_match_persists_actor_event_and_idempotency(self) -> None:
        store = NeonWriteStore(self.database_url)
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
        with psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT submitted_by, status FROM match_history")
                self.assertEqual(cur.fetchall(), [("user_operator", "active")])
                cur.execute("SELECT event_type, actor_subject, request_id FROM match_events")
                self.assertEqual(
                    cur.fetchall(),
                    [("submit", "user_operator", "request-1")],
                )

    def test_void_restore_replays_ratings_and_refuses_drift(self) -> None:
        store = NeonWriteStore(self.database_url)
        submitted = store.submit_match(
            ["alice"],
            ["bob"],
            5,
            3,
            source="test",
            idempotency_key="submit-1",
        )
        original = store.get_player_ratings(["alice", "bob"])

        voided = store.change_match_status(
            submitted["match_id"],
            "voided",
            "user_admin",
            "Incorrect result",
            "void-1",
            expected_version=1,
        )
        self.assertEqual(voided["status"], "voided")
        self.assertEqual(store.query_h2h("alice", "bob")["matches"], 0)

        restored = store.change_match_status(
            submitted["match_id"],
            "active",
            "user_admin",
            "Correction reversed",
            "restore-1",
            expected_version=2,
        )
        self.assertEqual(restored["status"], "active")
        after_restore = store.get_player_ratings(["alice", "bob"])
        for name in original:
            self.assertAlmostEqual(after_restore[name][0].mu, original[name][0].mu)
            self.assertAlmostEqual(after_restore[name][1].mu, original[name][1].mu)

        with psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE players SET offense_mu = 99 WHERE name = 'alice'")
        with self.assertRaises(ReplayParityError):
            store.change_match_status(
                submitted["match_id"],
                "voided",
                "user_admin",
                "Blocked drift",
                "void-drift",
            )

    def test_lifecycle_transaction_rolls_back_status_and_event_on_rating_failure(self) -> None:
        store = NeonWriteStore(self.database_url)
        submitted = store.submit_match(
            ["alice"],
            ["bob"],
            5,
            3,
            source="test",
            idempotency_key="submit-rollback",
        )

        with psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE OR REPLACE FUNCTION reject_rating_update() RETURNS trigger AS $$
                    BEGIN
                        RAISE EXCEPTION 'forced rating update failure';
                    END;
                    $$ LANGUAGE plpgsql
                    """
                )
                cur.execute(
                    """
                    CREATE TRIGGER reject_rating_update
                    BEFORE UPDATE ON players
                    FOR EACH ROW EXECUTE FUNCTION reject_rating_update()
                    """
                )

        with self.assertRaises(psycopg.errors.RaiseException):
            store.change_match_status(
                submitted["match_id"],
                "voided",
                "user_admin",
                "Must roll back",
                "void-rollback",
            )

        with psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, version FROM match_history WHERE id = %s",
                    (submitted["match_id"],),
                )
                self.assertEqual(cur.fetchone(), ("active", 1))
                cur.execute("SELECT event_type FROM match_events ORDER BY created_at, id")
                self.assertEqual(cur.fetchall(), [("submit",)])

    def test_export_restore_drill_preserves_checksums_and_replay(self) -> None:
        store = NeonWriteStore(self.database_url)
        store.submit_match(
            ["alice"],
            ["bob"],
            5,
            3,
            source="restore-drill",
            actor_subject="user_operator",
            idempotency_key="restore-drill-submit",
        )
        with psycopg.connect(self.database_url, autocommit=True) as conn:
            artifact = build_export_artifact(conn)
            self.assertTrue(artifact["integrity"]["ok"])
            with conn.cursor() as cur:
                cur.execute(
                    """
                    TRUNCATE match_events, recent_players, match_history,
                             rating_baselines, app_users, players
                    """
                )

        with psycopg.connect(self.database_url, autocommit=False) as conn:
            restored = restore_export_artifact(conn, artifact)
            conn.commit()

        self.assertTrue(restored["ok"])
        self.assertEqual(
            restored["table_sha256"],
            artifact["integrity"]["table_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
