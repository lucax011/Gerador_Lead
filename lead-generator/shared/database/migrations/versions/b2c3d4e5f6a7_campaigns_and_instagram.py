"""campaigns_and_instagram

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-26 00:00:00.000000

Adds:
  - campanhas table (campaign entity)
  - campanha_id FK on leads
  - instagram_* public profile columns on leads
  - instagram source seed
  - Extended lead status values (no schema change needed — status is VARCHAR)
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create campanhas table
    op.create_table(
        'campanhas',
        sa.Column('id', PG_UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='draft'),
        sa.Column('objective', sa.Text(), nullable=True),
        sa.Column('source_config', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('slug', name='uq_campanhas_slug'),
    )
    op.create_index('ix_campanhas_slug', 'campanhas', ['slug'], unique=True)

    # 2. Add campanha_id FK to leads
    op.add_column('leads', sa.Column('campanha_id', PG_UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_leads_campanha_id', 'leads', 'campanhas', ['campanha_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_leads_campanha_id', 'leads', ['campanha_id'], unique=False)

    # 3. Add instagram public profile columns to leads
    op.add_column('leads', sa.Column('instagram_username', sa.String(100), nullable=True))
    op.add_column('leads', sa.Column('instagram_bio', sa.Text(), nullable=True))
    op.add_column('leads', sa.Column('instagram_followers', sa.Integer(), nullable=True))
    op.add_column('leads', sa.Column('instagram_following', sa.Integer(), nullable=True))
    op.add_column('leads', sa.Column('instagram_posts', sa.Integer(), nullable=True))
    op.add_column('leads', sa.Column('instagram_engagement_rate', sa.Float(), nullable=True))
    op.add_column('leads', sa.Column('instagram_account_type', sa.String(20), nullable=True))
    op.add_column('leads', sa.Column('instagram_profile_url', sa.String(500), nullable=True))
    op.create_index('ix_leads_instagram_username', 'leads', ['instagram_username'], unique=False)

    # 4. Seed instagram source
    sources_table = sa.table(
        'sources',
        sa.column('id', PG_UUID(as_uuid=True)),
        sa.column('name', sa.String),
        sa.column('label', sa.String),
        sa.column('channel', sa.String),
        sa.column('base_score_multiplier', sa.Float),
    )
    op.bulk_insert(sources_table, [
        {
            'id': str(uuid4()),
            'name': 'instagram',
            'label': 'Instagram (Apify)',
            'channel': 'social',
            'base_score_multiplier': 0.75,
        }
    ])


def downgrade() -> None:
    # Remove instagram source seed
    op.execute("DELETE FROM sources WHERE name = 'instagram'")

    # Remove instagram columns
    op.drop_index('ix_leads_instagram_username', table_name='leads')
    op.drop_column('leads', 'instagram_profile_url')
    op.drop_column('leads', 'instagram_account_type')
    op.drop_column('leads', 'instagram_engagement_rate')
    op.drop_column('leads', 'instagram_posts')
    op.drop_column('leads', 'instagram_following')
    op.drop_column('leads', 'instagram_followers')
    op.drop_column('leads', 'instagram_bio')
    op.drop_column('leads', 'instagram_username')

    # Remove campanha_id from leads
    op.drop_index('ix_leads_campanha_id', table_name='leads')
    op.drop_constraint('fk_leads_campanha_id', 'leads', type_='foreignkey')
    op.drop_column('leads', 'campanha_id')

    # Drop campanhas table
    op.drop_index('ix_campanhas_slug', table_name='campanhas')
    op.drop_table('campanhas')
