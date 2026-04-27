"""niche score multiplier

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-27

Adiciona:
  - coluna niche_score_multiplier na tabela niches (0.0 a 1.0)
  - seed de multipliers por nicho baseado em aderência aos produtos NichaChat/Consórcio
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "niches",
        sa.Column(
            "niche_score_multiplier",
            sa.Float(),
            nullable=False,
            server_default="0.5",
        ),
    )

    # Multipliers calibrados para os produtos NichaChat (CRM WhatsApp) e Consórcio
    # Alto (0.9-1.0): nicho com alta propensão a contratar CRM ou consórcio
    # Médio (0.6-0.8): nicho com interesse moderado
    # Baixo (0.3-0.5): nicho com baixa aderência histórica
    op.execute("""
        UPDATE niches SET niche_score_multiplier = CASE slug
            WHEN 'ecommerce'          THEN 1.0   -- lojas precisam muito de CRM/WhatsApp
            WHEN 'servicos-juridicos' THEN 0.9   -- advocacia = ticket alto, boa conversão consórcio
            WHEN 'saude-bem-estar'    THEN 0.9   -- clínicas = CRM intenso + consórcio imóvel
            WHEN 'financeiro'         THEN 0.85  -- fintechs e corretores = boa aderência
            WHEN 'imoveis'            THEN 0.85  -- consórcio imóvel direto
            WHEN 'educacao'           THEN 0.75  -- cursos e treinamentos = CRM moderado
            WHEN 'tecnologia'         THEN 0.7   -- startups às vezes têm CRM próprio
            WHEN 'industria'          THEN 0.6   -- ciclo longo de decisão, B2B complexo
            ELSE 0.5
        END
    """)


def downgrade() -> None:
    op.drop_column("niches", "niche_score_multiplier")
