"""baseline — schema completo consolidado

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-28

Cria todas as tabelas, índices, trigger e seeds a partir do zero.
Substitui as migrações incrementais anteriores (0e0205747d8e → e5f6a7b8c9d0).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # ── niches ────────────────────────────────────────────────────────────────
    op.create_table(
        "niches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("niche_score_multiplier", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("name", name="uq_niches_name"),
        sa.UniqueConstraint("slug", name="uq_niches_slug"),
    )
    op.create_index("ix_niches_slug", "niches", ["slug"], unique=True)

    op.execute("""
        INSERT INTO niches (id, name, slug, description, niche_score_multiplier) VALUES
            (uuid_generate_v4(), 'E-commerce',           'ecommerce',           'Lojas virtuais, marketplaces, dropshipping',          1.00),
            (uuid_generate_v4(), 'Beleza e Estética',    'beleza-estetica',     'Salões, nail designers, barbearias, lash designers',  1.00),
            (uuid_generate_v4(), 'Academia e Fitness',   'academia-fitness',    'Academias, personal trainers, estúdios fitness',      0.90),
            (uuid_generate_v4(), 'Saúde e Bem-estar',    'saude-bem-estar',     'Clínicas, nutricionistas, psicólogos, spas',          0.90),
            (uuid_generate_v4(), 'Imóveis',              'imoveis',             'Construtoras, imobiliárias, corretores',              0.85),
            (uuid_generate_v4(), 'Financeiro',           'financeiro',          'Fintechs, seguros, investimentos, crédito',           0.85),
            (uuid_generate_v4(), 'Alimentação',          'alimentacao',         'Restaurantes, cafés, delivery, food service',         0.85),
            (uuid_generate_v4(), 'Pet Shop',             'pet-shop',            'Petshops, clínicas veterinárias, grooming',           0.85),
            (uuid_generate_v4(), 'Moda e Vestuário',     'moda-vestuario',      'Boutiques, moda feminina, acessórios',                0.80),
            (uuid_generate_v4(), 'Educação',             'educacao',            'Cursos, faculdades, treinamentos corporativos',       0.80),
            (uuid_generate_v4(), 'Serviços Jurídicos',   'servicos-juridicos',  'Escritórios de advocacia, legaltech',                 0.75),
            (uuid_generate_v4(), 'Construção e Reformas','construcao-reformas', 'Construtoras, reformadores, decoração de interiores', 0.75),
            (uuid_generate_v4(), 'Tecnologia',           'tecnologia',          'Empresas e profissionais de TI, SaaS, startups',      0.70),
            (uuid_generate_v4(), 'Contabilidade',        'contabilidade',       'Contadores, assessores fiscais, BPO financeiro',      0.70),
            (uuid_generate_v4(), 'Indústria',            'industria',           'Manufatura, automação industrial, B2B',               0.60)
        ON CONFLICT (slug) DO NOTHING
    """)

    # ── campanhas ─────────────────────────────────────────────────────────────
    op.create_table(
        "campanhas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("objective", sa.Text(), nullable=True),
        sa.Column("source_config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("slug", name="uq_campanhas_slug"),
    )
    op.create_index("ix_campanhas_slug", "campanhas", ["slug"], unique=True)

    # ── sources ───────────────────────────────────────────────────────────────
    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("base_score_multiplier", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("name", name="uq_sources_name"),
    )
    op.create_index("ix_sources_name", "sources", ["name"], unique=True)

    op.execute("""
        INSERT INTO sources (id, name, label, channel, base_score_multiplier) VALUES
            (uuid_generate_v4(), 'paid_traffic', 'Tráfego Pago',      'paid',    1.0),
            (uuid_generate_v4(), 'meta_ads',     'Meta Ads',          'paid',    1.0),
            (uuid_generate_v4(), 'google_ads',   'Google Ads',        'paid',    1.0),
            (uuid_generate_v4(), 'google_maps',  'Google Maps',       'manual',  0.9),
            (uuid_generate_v4(), 'whatsapp',     'WhatsApp',          'direct',  0.8),
            (uuid_generate_v4(), 'instagram',    'Instagram (Apify)', 'social',  0.75),
            (uuid_generate_v4(), 'chatbot',      'Chatbot',           'direct',  0.7),
            (uuid_generate_v4(), 'csv_import',   'Importação CSV',    'manual',  0.6),
            (uuid_generate_v4(), 'web_scraping', 'Web Scraping',      'organic', 0.4)
        ON CONFLICT (name) DO NOTHING
    """)

    # ── leads ─────────────────────────────────────────────────────────────────
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campanha_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("niche_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="captured"),
        sa.Column("instagram_username", sa.String(100), nullable=True),
        sa.Column("instagram_bio", sa.Text(), nullable=True),
        sa.Column("instagram_followers", sa.Integer(), nullable=True),
        sa.Column("instagram_following", sa.Integer(), nullable=True),
        sa.Column("instagram_posts", sa.Integer(), nullable=True),
        sa.Column("instagram_engagement_rate", sa.Float(), nullable=True),
        sa.Column("instagram_account_type", sa.String(20), nullable=True),
        sa.Column("instagram_profile_url", sa.String(500), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="RESTRICT", name="fk_leads_source_id"),
        sa.ForeignKeyConstraint(["campanha_id"], ["campanhas.id"], ondelete="SET NULL", name="fk_leads_campanha_id"),
        sa.ForeignKeyConstraint(["niche_id"], ["niches.id"], ondelete="SET NULL", name="fk_leads_niche_id"),
    )
    op.create_index("uq_leads_email", "leads", [sa.text("LOWER(email)")], unique=True)
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_index("ix_leads_source_id", "leads", ["source_id"])
    op.create_index("ix_leads_niche_id", "leads", ["niche_id"])
    op.create_index("ix_leads_campanha_id", "leads", ["campanha_id"])
    op.create_index("ix_leads_instagram_username", "leads", ["instagram_username"])
    op.create_index("ix_leads_created", "leads", [sa.text("created_at DESC")])

    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_leads_updated_at
            BEFORE UPDATE ON leads
            FOR EACH ROW EXECUTE FUNCTION update_updated_at()
    """)

    # ── scores ────────────────────────────────────────────────────────────────
    op.create_table(
        "scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("temperature", sa.String(10), nullable=False),
        sa.Column("breakdown", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_scores_lead_id", "scores", ["lead_id"])

    # ── enrichments ───────────────────────────────────────────────────────────
    op.create_table(
        "enrichments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cnpj_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("instagram_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("bigdatacorp_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("serasa_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("facebook_capi_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("has_cnpj", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("estimated_revenue_tier", sa.String(20), nullable=True),
        sa.Column("years_in_business", sa.Integer(), nullable=True),
        sa.Column("sources_used", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("lead_id"),
    )
    op.create_index("ix_enrichments_lead_id", "enrichments", ["lead_id"])

    # ── orchestration_decisions ───────────────────────────────────────────────
    op.create_table(
        "orchestration_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("need_identified", sa.Text(), nullable=True),
        sa.Column("offer", sa.String(50), nullable=True),
        sa.Column("approach", sa.String(50), nullable=True),
        sa.Column("tone", sa.String(50), nullable=True),
        sa.Column("best_time", sa.String(30), nullable=True),
        sa.Column("best_time_reason", sa.Text(), nullable=True),
        sa.Column("score_adjustment", sa.Float(), nullable=False, server_default="0"),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("objections", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("opening_message", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(50), nullable=False, server_default="gpt-4o-mini"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_orchestration_lead_id", "orchestration_decisions", ["lead_id"])

    # ── outreach_attempts ─────────────────────────────────────────────────────
    op.create_table(
        "outreach_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_outreach_lead_id", "outreach_attempts", ["lead_id"])
    op.create_index("ix_outreach_status", "outreach_attempts", ["status"])


def downgrade() -> None:
    op.drop_table("outreach_attempts")
    op.drop_table("orchestration_decisions")
    op.drop_table("enrichments")
    op.drop_table("scores")
    op.execute("DROP TRIGGER IF EXISTS trg_leads_updated_at ON leads")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at")
    op.drop_table("leads")
    op.drop_table("sources")
    op.drop_table("campanhas")
    op.drop_table("niches")
