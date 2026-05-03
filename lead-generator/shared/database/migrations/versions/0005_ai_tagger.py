"""ai_tagger — tags e perfil_resumido no lead; keywords_alvo na campanha

Revision ID: 0005_ai_tagger
Revises: 0004_sweep_jobs
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_ai_tagger"
down_revision = "0004_sweep_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("tags", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("leads", sa.Column("perfil_resumido", sa.Text(), nullable=True))
    op.add_column("campanhas", sa.Column("keywords_alvo", postgresql.JSONB(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("leads", "tags")
    op.drop_column("leads", "perfil_resumido")
    op.drop_column("campanhas", "keywords_alvo")
