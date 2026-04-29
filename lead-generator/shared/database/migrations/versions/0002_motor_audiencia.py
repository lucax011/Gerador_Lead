"""motor_audiencia — campos de oferta em campanhas e offer_tags em leads

Revision ID: 0002_motor_audiencia
Revises: 0001_baseline
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_motor_audiencia"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Campos de oferta na tabela campanhas
    op.add_column("campanhas", sa.Column("offer_description", sa.Text(), nullable=True))
    op.add_column("campanhas", sa.Column("ideal_customer_profile", sa.Text(), nullable=True))
    op.add_column("campanhas", sa.Column("ticket", sa.String(100), nullable=True))
    op.add_column("campanhas", sa.Column("focus_segments", postgresql.JSONB(), nullable=False, server_default="[]"))

    # Histórico de offer_tags nos leads
    op.add_column("leads", sa.Column("offer_tags", postgresql.JSONB(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("leads", "offer_tags")
    op.drop_column("campanhas", "focus_segments")
    op.drop_column("campanhas", "ticket")
    op.drop_column("campanhas", "ideal_customer_profile")
    op.drop_column("campanhas", "offer_description")
