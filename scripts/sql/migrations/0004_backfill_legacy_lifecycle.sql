WITH earliest_player_snapshots AS (
    SELECT DISTINCT ON (LOWER(player_entry->>'name'))
        LOWER(player_entry->>'name') AS player_name,
        (player_entry->'before'->>'offense_mu')::DOUBLE PRECISION AS offense_mu,
        (player_entry->'before'->>'offense_sigma')::DOUBLE PRECISION AS offense_sigma,
        (player_entry->'before'->>'defense_mu')::DOUBLE PRECISION AS defense_mu,
        (player_entry->'before'->>'defense_sigma')::DOUBLE PRECISION AS defense_sigma
    FROM match_history
    CROSS JOIN LATERAL jsonb_array_elements(players_payload) AS player_entry
    WHERE player_entry->>'name' IS NOT NULL
      AND player_entry->'before'->>'offense_mu' IS NOT NULL
      AND player_entry->'before'->>'offense_sigma' IS NOT NULL
      AND player_entry->'before'->>'defense_mu' IS NOT NULL
      AND player_entry->'before'->>'defense_sigma' IS NOT NULL
    ORDER BY LOWER(player_entry->>'name'), ts ASC, id ASC
)
INSERT INTO rating_baselines (
    player_name,
    offense_mu,
    offense_sigma,
    defense_mu,
    defense_sigma,
    source
)
SELECT
    players.name,
    COALESCE(snapshots.offense_mu, players.offense_mu),
    COALESCE(snapshots.offense_sigma, players.offense_sigma),
    COALESCE(snapshots.defense_mu, players.defense_mu),
    COALESCE(snapshots.defense_sigma, players.defense_sigma),
    CASE
        WHEN snapshots.player_name IS NULL THEN 'neon_current_no_history'
        ELSE 'neon_first_history_before'
    END
FROM players
LEFT JOIN earliest_player_snapshots AS snapshots
    ON snapshots.player_name = LOWER(players.name)
ON CONFLICT (player_name) DO NOTHING;

INSERT INTO match_events (
    id,
    match_id,
    event_type,
    actor_subject,
    reason,
    request_id,
    from_status,
    to_status,
    created_at
)
SELECT
    'migration-' || md5(match_history.id),
    match_history.id,
    'submit',
    COALESCE(match_history.submitted_by, 'migration:neon-legacy'),
    'Backfilled existing Neon history',
    NULL,
    NULL,
    match_history.status,
    match_history.ts
FROM match_history
WHERE NOT EXISTS (
    SELECT 1
    FROM match_events
    WHERE match_events.match_id = match_history.id
      AND match_events.event_type = 'submit'
)
ON CONFLICT (id) DO NOTHING;
