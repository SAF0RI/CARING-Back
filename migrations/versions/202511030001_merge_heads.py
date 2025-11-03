"""merge heads

Revision ID: 202511030001_merge_heads
Revises: add_question_tables, 202511010003_add_weekly_frequency_result
Create Date: 2025-11-03 23:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202511030001_merge_heads'
down_revision = ('add_question_tables', '202511010003_add_weekly_frequency_result')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass


