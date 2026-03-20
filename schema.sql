-- TeamSync AI — PostgreSQL Schema
-- Run once via asyncpg on startup (CREATE ... IF NOT EXISTS is idempotent)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─────────────────────────────────────────────
-- Teams
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS teams (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(100) NOT NULL,
    code       VARCHAR(20)  UNIQUE NOT NULL,   -- e.g. "SPRINT3", "NEXUS"
    created_at TIMESTAMP    DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- Tasks — replaces database.json entirely
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
    id         VARCHAR(20)  NOT NULL,
    team_id    UUID         NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    title      VARCHAR(200) NOT NULL,
    tag        VARCHAR(50)  DEFAULT 'general',
    assignee   VARCHAR(50),
    status     VARCHAR(20)  DEFAULT 'todo'
                            CHECK (status IN ('todo', 'inProgress', 'done')),
    deadline   DATE,
    created_at TIMESTAMP    DEFAULT NOW(),
    updated_at TIMESTAMP    DEFAULT NOW(),
    PRIMARY KEY (id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_team_status   ON tasks(team_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline_open ON tasks(deadline) WHERE status != 'done';

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tasks_updated_at ON tasks;
CREATE TRIGGER tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();