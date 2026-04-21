-- Initial schema bootstrap (Alembic manages subsequent migrations)
CREATE SCHEMA IF NOT EXISTS public;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- for fuzzy email deduplication

CREATE TABLE IF NOT EXISTS leads (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(255)  NOT NULL,
    email       VARCHAR(320)  NOT NULL,
    phone       VARCHAR(30),
    company     VARCHAR(255),
    source      VARCHAR(50)   NOT NULL,
    status      VARCHAR(50)   NOT NULL DEFAULT 'captured',
    metadata    JSONB         NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_email ON leads (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_leads_status  ON leads (status);
CREATE INDEX IF NOT EXISTS idx_leads_source  ON leads (source);
CREATE INDEX IF NOT EXISTS idx_leads_created ON leads (created_at DESC);

CREATE TABLE IF NOT EXISTS scores (
    id          SERIAL PRIMARY KEY,
    lead_id     UUID          NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    score       FLOAT         NOT NULL,
    temperature VARCHAR(10)   NOT NULL,
    breakdown   JSONB         NOT NULL DEFAULT '{}',
    scored_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    notes       TEXT
);

CREATE INDEX IF NOT EXISTS idx_scores_lead_id ON scores (lead_id);

-- Trigger: keep updated_at fresh
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_leads_updated_at ON leads;
CREATE TRIGGER trg_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
