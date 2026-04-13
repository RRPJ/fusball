CREATE TABLE IF NOT EXISTS players (
    name TEXT PRIMARY KEY,
    offense_mu DOUBLE PRECISION NOT NULL,
    offense_sigma DOUBLE PRECISION NOT NULL,
    defense_mu DOUBLE PRECISION NOT NULL,
    defense_sigma DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recent_players (
    position INTEGER PRIMARY KEY,
    name TEXT NOT NULL REFERENCES players(name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS match_history (
    id TEXT PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    team1 JSONB NOT NULL,
    team2 JSONB NOT NULL,
    winner JSONB NOT NULL,
    score1 INTEGER NOT NULL,
    score2 INTEGER NOT NULL,
    players_payload JSONB NOT NULL,
    record_payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_match_history_ts ON match_history (ts DESC);
CREATE INDEX IF NOT EXISTS ix_match_history_source ON match_history (source);
