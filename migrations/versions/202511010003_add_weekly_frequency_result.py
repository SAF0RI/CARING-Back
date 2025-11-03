"""add weekly_result and frequency_result tables

Revision ID: 202511010003_add_weekly_frequency_result
Revises: 202511010002_add_notification
Create Date: 2025-11-03 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202511010003_add_weekly_frequency_result'
down_revision = '202511010002_add_notification'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'weekly_result',
        sa.Column('weekly_result_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('user.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('latest_voice_composite_id', sa.BigInteger(), sa.ForeignKey('voice_composite.voice_composite_id', ondelete='CASCADE'), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.UniqueConstraint('user_id', name='uq_weekly_user'),
    )
    op.create_index('idx_weekly_user', 'weekly_result', ['user_id'])
    op.create_index('idx_weekly_latest_vc', 'weekly_result', ['latest_voice_composite_id'])

    op.create_table(
        'frequency_result',
        sa.Column('frequency_result_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('user.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('latest_voice_composite_id', sa.BigInteger(), sa.ForeignKey('voice_composite.voice_composite_id', ondelete='CASCADE'), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.UniqueConstraint('user_id', name='uq_freq_user'),
    )
    op.create_index('idx_freq_user', 'frequency_result', ['user_id'])
    op.create_index('idx_freq_latest_vc', 'frequency_result', ['latest_voice_composite_id'])


def downgrade() -> None:
    op.drop_index('idx_freq_latest_vc', table_name='frequency_result')
    op.drop_index('idx_freq_user', table_name='frequency_result')
    op.drop_table('frequency_result')

    op.drop_index('idx_weekly_latest_vc', table_name='weekly_result')
    op.drop_index('idx_weekly_user', table_name='weekly_result')
    op.drop_table('weekly_result')


