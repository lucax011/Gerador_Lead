"""multi_offer_support — múltiplas ofertas por campanha com operador AND/OR

Revision ID: 0003_multi_offer
Revises: 0002_motor_audiencia
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_multi_offer"
down_revision = "0002_motor_audiencia"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # offers: array de {slug, description, icp, ticket} — substitui os campos singulares para novas campanhas
    op.add_column("campanhas", sa.Column("offers", postgresql.JSONB(), nullable=False, server_default="[]"))
    # operador AND/OR para compatibilidade multi-oferta
    op.add_column("campanhas", sa.Column("offer_operator", sa.String(3), nullable=False, server_default="OR"))
    # threshold configurável por campanha (padrão 70)
    op.add_column("campanhas", sa.Column("compatibility_threshold", sa.Integer(), nullable=False, server_default="70"))
    # guard-rail de custo OpenAI por varredura (padrão 500)
    op.add_column("campanhas", sa.Column("max_leads_per_sweep", sa.Integer(), nullable=False, server_default="500"))


def downgrade() -> None:
    op.drop_column("campanhas", "max_leads_per_sweep")
    op.drop_column("campanhas", "compatibility_threshold")
    op.drop_column("campanhas", "offer_operator")
    op.drop_column("campanhas", "offers")
