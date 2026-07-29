-- Durable presence for the phone API "checked in" lineup workflow.
--
-- Vercel-hosted phone API instances are ephemeral, so an in-process
-- active-players set (used by local/shelve deployments) does not survive
-- across requests or cold starts once the write store is Neon-backed. This
-- table gives hosted deployments a durable, expiring presence record while
-- leaving the local shelve-backed store's in-memory behavior untouched.
CREATE TABLE IF NOT EXISTS player_presence (
    player_name TEXT PRIMARY KEY REFERENCES players(name) ON DELETE CASCADE,
    marked_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_player_presence_expires_at
    ON player_presence (expires_at);
