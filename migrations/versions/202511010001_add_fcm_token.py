"""add fcm_token table

Revision ID: 202511010001_add_fcm_token
Revises: 202510310001_add_voice_composite
Create Date: 2025-11-01 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202511010001_add_fcm_token'
down_revision = '202510310001_add_voice_composite'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'fcm_token',
        sa.Column('token_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('user.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('fcm_token', sa.String(length=255), nullable=False),
        sa.Column('device_id', sa.String(length=255), nullable=True),
        sa.Column('platform', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.SmallInteger(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=False),
        sa.UniqueConstraint('user_id', 'device_id', name='uq_fcm_user_device'),
        sa.Index('idx_fcm_token', 'fcm_token'),
        sa.Index('idx_user_active', 'user_id', 'is_active'),
        sa.Index('idx_device_token', 'device_id', 'fcm_token')
    )


def downgrade() -> None:
    op.drop_table('fcm_token')

