"""enrichment orchestration outreach

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-26

Adiciona:
  - tabela enrichments (enriquecimento de leads via CNPJ.ws, BigDataCorp, Serasa)
  - tabela orchestration_decisions (decisões GPT-4o-mini por lead)
  - tabela outreach_attempts (tentativas de abordagem WhatsApp/DM)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── enrichments ───────────────────────────────────────────────────────────
    op.create_table(
        'enrichments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cnpj_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('instagram_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('bigdatacorp_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('serasa_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('facebook_capi_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('has_cnpj', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('estimated_revenue_tier', sa.String(20), nullable=True),
        sa.Column('years_in_business', sa.Integer(), nullable=True),
        sa.Column('sources_used', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('enriched_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lead_id'),
    )
    op.create_index('idx_enrichments_lead_id', 'enrichments', ['lead_id'])

    # ── orchestration_decisions ────────────────────────────────────────────────
    op.create_table(
        'orchestration_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('offer', sa.String(50), nullable=True),
        sa.Column('approach', sa.String(50), nullable=True),
        sa.Column('tone', sa.String(50), nullable=True),
        sa.Column('best_time', sa.String(30), nullable=True),
        sa.Column('best_time_reason', sa.Text(), nullable=True),
        sa.Column('score_adjustment', sa.Float(), nullable=False, server_default='0'),
        sa.Column('final_score', sa.Float(), nullable=True),
        sa.Column('objections', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('opening_message', sa.Text(), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('model_used', sa.String(50), nullable=False, server_default='gpt-4o-mini'),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_orchestration_lead_id', 'orchestration_decisions', ['lead_id'])

    # ── outreach_attempts ──────────────────────────────────────────────────────
    op.create_table(
        'outreach_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='scheduled'),
        sa.Column('message_text', sa.Text(), nullable=True),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('attempt_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_outreach_lead_id', 'outreach_attempts', ['lead_id'])
    op.create_index('idx_outreach_status', 'outreach_attempts', ['status'])


def downgrade() -> None:
    op.drop_table('outreach_attempts')
    op.drop_table('orchestration_decisions')
    op.drop_table('enrichments')
