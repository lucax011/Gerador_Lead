-- Initial schema bootstrap (Alembic manages subsequent migrations)
CREATE SCHEMA IF NOT EXISTS public;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ── Niches ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS niches (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(100)  NOT NULL UNIQUE,
    slug        VARCHAR(100)  NOT NULL UNIQUE,
    description TEXT,
    is_active   BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_niches_slug ON niches (slug);

INSERT INTO niches (id, name, slug, description) VALUES
    (uuid_generate_v4(), 'Tecnologia',        'tecnologia',        'Empresas e profissionais de TI, SaaS, startups'),
    (uuid_generate_v4(), 'Saúde e Bem-estar', 'saude-bem-estar',   'Clínicas, planos de saúde, suplementos'),
    (uuid_generate_v4(), 'Educação',          'educacao',          'Cursos, faculdades, treinamentos corporativos'),
    (uuid_generate_v4(), 'Imóveis',           'imoveis',           'Construtoras, imobiliárias, corretores'),
    (uuid_generate_v4(), 'E-commerce',        'ecommerce',         'Lojas virtuais, marketplaces, dropshipping'),
    (uuid_generate_v4(), 'Serviços Jurídicos','servicos-juridicos', 'Escritórios de advocacia, legaltech'),
    (uuid_generate_v4(), 'Financeiro',        'financeiro',        'Fintechs, seguros, investimentos'),
    (uuid_generate_v4(), 'Indústria',         'industria',         'Manufatura, automação industrial, B2B')
ON CONFLICT (slug) DO NOTHING;

-- ── Campanhas ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campanhas (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(255) NOT NULL,
    slug        VARCHAR(255) NOT NULL UNIQUE,
    status      VARCHAR(50)  NOT NULL DEFAULT 'draft',
    objective   TEXT,
    source_config JSONB      NOT NULL DEFAULT '{}',
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_campanhas_slug ON campanhas (slug);

-- ── Sources ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sources (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                  VARCHAR(50)   NOT NULL UNIQUE,
    label                 VARCHAR(100)  NOT NULL,
    channel               VARCHAR(50)   NOT NULL,
    base_score_multiplier FLOAT         NOT NULL DEFAULT 0.5,
    is_active             BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sources_name ON sources (name);

-- Seed: fontes iniciais
INSERT INTO sources (id, name, label, channel, base_score_multiplier) VALUES
    (uuid_generate_v4(), 'paid_traffic',  'Tráfego Pago',    'paid',    1.0),
    (uuid_generate_v4(), 'chatbot',       'Chatbot',         'direct',  0.7),
    (uuid_generate_v4(), 'web_scraping',  'Web Scraping',    'organic', 0.4),
    (uuid_generate_v4(), 'meta_ads',      'Meta Ads',        'paid',    1.0),
    (uuid_generate_v4(), 'google_ads',    'Google Ads',      'paid',    1.0),
    (uuid_generate_v4(), 'whatsapp',      'WhatsApp',        'direct',  0.8),
    (uuid_generate_v4(), 'csv_import',    'Importação CSV',  'manual',  0.6),
    (uuid_generate_v4(), 'instagram',     'Instagram (Apify)', 'social', 0.75)
ON CONFLICT (name) DO NOTHING;

-- ── Leads ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leads (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                     VARCHAR(255)  NOT NULL,
    email                    VARCHAR(320)  NOT NULL,
    phone                    VARCHAR(30),
    company                  VARCHAR(255),
    source_id                UUID          NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    campanha_id              UUID          REFERENCES campanhas(id) ON DELETE SET NULL,
    status                   VARCHAR(50)   NOT NULL DEFAULT 'captured',
    niche_id                 UUID          REFERENCES niches(id) ON DELETE SET NULL,
    -- Instagram public profile (populated by ApifyInstagramSource or enricher)
    instagram_username       VARCHAR(100),
    instagram_bio            TEXT,
    instagram_followers      INTEGER,
    instagram_following      INTEGER,
    instagram_posts          INTEGER,
    instagram_engagement_rate FLOAT,
    instagram_account_type   VARCHAR(20),
    instagram_profile_url    VARCHAR(500),
    metadata                 JSONB         NOT NULL DEFAULT '{}',
    created_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_leads_email ON leads (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_leads_status    ON leads (status);
CREATE INDEX IF NOT EXISTS idx_leads_source_id ON leads (source_id);
CREATE INDEX IF NOT EXISTS idx_leads_niche_id        ON leads (niche_id);
CREATE INDEX IF NOT EXISTS idx_leads_campanha_id     ON leads (campanha_id);
CREATE INDEX IF NOT EXISTS idx_leads_instagram_user  ON leads (instagram_username);
CREATE INDEX IF NOT EXISTS idx_leads_created         ON leads (created_at DESC);

-- ── Scores ────────────────────────────────────────────────────────────────────
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

-- ── Trigger: keep updated_at fresh ───────────────────────────────────────────
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
