"""source_as_entity

Revision ID: a1b2c3d4e5f6
Revises: 0e0205747d8e
Create Date: 2026-04-22 00:00:00.000000

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0e0205747d8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCES_SEED = [
    ('paid_traffic', 'Tráfego Pago',   'paid',    1.0),
    ('chatbot',      'Chatbot',         'direct',  0.7),
    ('web_scraping', 'Web Scraping',    'organic', 0.4),
    ('meta_ads',     'Meta Ads',        'paid',    1.0),
    ('google_ads',   'Google Ads',      'paid',    1.0),
    ('whatsapp',     'WhatsApp',        'direct',  0.8),
    ('csv_import',   'Importação CSV',  'manual',  0.6),
]


def upgrade() -> None:
    # 1. Criar tabela sources
    op.create_table(
        'sources',
        sa.Column('id', PG_UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('label', sa.String(100), nullable=False),
        sa.Column('channel', sa.String(50), nullable=False),
        sa.Column('base_score_multiplier', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('name', name='uq_sources_name'),
    )
    op.create_index('ix_sources_name', 'sources', ['name'], unique=True)

    # 2. Seed das fontes
    sources_table = sa.table(
        'sources',
        sa.column('id', PG_UUID(as_uuid=True)),
        sa.column('name', sa.String),
        sa.column('label', sa.String),
        sa.column('channel', sa.String),
        sa.column('base_score_multiplier', sa.Float),
    )
    op.bulk_insert(sources_table, [
        {'id': str(uuid4()), 'name': name, 'label': label, 'channel': channel, 'base_score_multiplier': mult}
        for name, label, channel, mult in SOURCES_SEED
    ])

    # 3. Adicionar coluna source_id em leads (nullable temporariamente para preencher)
    op.add_column('leads', sa.Column('source_id', PG_UUID(as_uuid=True), nullable=True))

    # 4. Popular source_id baseado no valor textual de source
    op.execute("""
        UPDATE leads l
        SET source_id = s.id
        FROM sources s
        WHERE s.name = l.source
    """)

    # 5. Para leads com source desconhecido, usar web_scraping como fallback
    op.execute("""
        UPDATE leads
        SET source_id = (SELECT id FROM sources WHERE name = 'web_scraping')
        WHERE source_id IS NULL
    """)

    # 6. Tornar source_id NOT NULL e adicionar FK
    op.alter_column('leads', 'source_id', nullable=False)
    op.create_foreign_key('fk_leads_source_id', 'leads', 'sources', ['source_id'], ['id'])
    op.create_index('ix_leads_source_id', 'leads', ['source_id'], unique=False)

    # 7. Remover coluna source (string) antiga
    op.drop_index('idx_leads_source', table_name='leads', if_exists=True)
    op.drop_column('leads', 'source')


def downgrade() -> None:
    op.add_column('leads', sa.Column('source', sa.String(50), nullable=True))

    op.execute("""
        UPDATE leads l
        SET source = s.name
        FROM sources s
        WHERE s.id = l.source_id
    """)

    op.alter_column('leads', 'source', nullable=False)
    op.create_index('idx_leads_source', 'leads', ['source'], unique=False)

    op.drop_index('ix_leads_source_id', table_name='leads')
    op.drop_constraint('fk_leads_source_id', 'leads', type_='foreignkey')
    op.drop_column('leads', 'source_id')

    op.drop_index('ix_sources_name', table_name='sources')
    op.drop_table('sources')
