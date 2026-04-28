"""generic orchestration and new niches

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-27

Adds:
- orchestration_decisions.need_identified (TEXT) — necessidade identificada pelo AI
- 7 new niche slugs with calibrated multipliers
- Recalibrates existing niche multipliers for "business owners wanting to sell more" context
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orchestration_decisions",
        sa.Column("need_identified", sa.Text(), nullable=True),
    )

    # Recalibrate existing niches for generic "sell more" context
    op.execute("""
        UPDATE niches SET niche_score_multiplier = CASE slug
            WHEN 'ecommerce'          THEN 1.00
            WHEN 'saude-bem-estar'    THEN 0.90
            WHEN 'financeiro'         THEN 0.85
            WHEN 'imoveis'            THEN 0.85
            WHEN 'educacao'           THEN 0.80
            WHEN 'servicos-juridicos' THEN 0.75
            WHEN 'tecnologia'         THEN 0.70
            WHEN 'industria'          THEN 0.60
            ELSE niche_score_multiplier
        END
    """)

    # Insert new niches
    op.execute("""
        INSERT INTO niches (id, name, slug, description, niche_score_multiplier) VALUES
            (gen_random_uuid(), 'Beleza e Estética',    'beleza-estetica',     'Salões, nail designers, barbearias, lash designers', 1.00),
            (gen_random_uuid(), 'Academia e Fitness',   'academia-fitness',    'Academias, personal trainers, estúdios fitness',    0.90),
            (gen_random_uuid(), 'Alimentação',          'alimentacao',         'Restaurantes, cafés, delivery, food service',       0.85),
            (gen_random_uuid(), 'Pet Shop',             'pet-shop',            'Petshops, clínicas veterinárias, grooming',         0.85),
            (gen_random_uuid(), 'Moda e Vestuário',     'moda-vestuario',      'Boutiques, moda feminina, acessórios',              0.80),
            (gen_random_uuid(), 'Construção e Reformas','construcao-reformas', 'Construtoras, reformadores, decoração de interiores',0.75),
            (gen_random_uuid(), 'Contabilidade',        'contabilidade',       'Contadores, assessores fiscais, BPO financeiro',    0.70)
        ON CONFLICT (slug) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_column("orchestration_decisions", "need_identified")

    op.execute("""
        DELETE FROM niches WHERE slug IN (
            'beleza-estetica', 'academia-fitness', 'alimentacao',
            'pet-shop', 'moda-vestuario', 'construcao-reformas', 'contabilidade'
        )
    """)
