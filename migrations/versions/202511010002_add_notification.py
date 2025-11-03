"""add notification table

Revision ID: 202511010002_add_notification
Revises: 202511010001_add_fcm_token
Create Date: 2025-11-01 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202511010002_add_notification'
down_revision = '202511010001_add_fcm_token'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'notification',
        sa.Column('notification_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('voice_id', sa.BigInteger(), sa.ForeignKey('voice.voice_id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('top_emotion', sa.String(length=16), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Index('idx_notification_voice', 'voice_id'),
        sa.Index('idx_notification_created', 'created_at')
    )


def downgrade() -> None:
    op.drop_table('notification')

