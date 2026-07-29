ALTER TABLE match_history
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'voided')),
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS submitted_by TEXT,
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_match_history_idempotency_key
    ON match_history (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS match_events (
    id TEXT PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES match_history(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL CHECK (event_type IN ('submit', 'void', 'restore')),
    actor_subject TEXT NOT NULL,
    reason TEXT,
    request_id TEXT,
    from_status TEXT,
    to_status TEXT NOT NULL CHECK (to_status IN ('active', 'voided')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_match_events_request_id
    ON match_events (request_id)
    WHERE request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_match_events_match_created
    ON match_events (match_id, created_at, id);

CREATE TABLE IF NOT EXISTS rating_baselines (
    player_name TEXT PRIMARY KEY REFERENCES players(name) ON DELETE RESTRICT,
    offense_mu DOUBLE PRECISION NOT NULL,
    offense_sigma DOUBLE PRECISION NOT NULL,
    defense_mu DOUBLE PRECISION NOT NULL,
    defense_sigma DOUBLE PRECISION NOT NULL,
    source TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
