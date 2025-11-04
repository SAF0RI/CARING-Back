"""fix voice_content score_bps: 음수 데이터 보정

Revision ID: 202511040001_fix_voice_content_score_bps
Revises: 202511030001_merge_heads
Create Date: 2025-11-04

스코어 스케일 복구:
- 과거 음수 score_bps 데이터를 올바른 스케일로 보정
- score_bps < 0 and score_bps >= -10000인 경우만 보정
- ((score_bps/10000.0)+1.0)*5000 공식 적용
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202511040001_fix_voice_content_score_bps'
down_revision = '202511030001_merge_heads'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """과거 음수 score_bps 데이터 보정"""
    # 임시 가정: 음수는 10,000 스케일 없이 *10000만 한 값(예: -0.8→-8000)
    # 절대값이 1만 이하인 음수만 보정하고, 나머지는 수동 확인
    op.execute("""
        UPDATE voice_content
        SET score_bps = LEAST(
            GREATEST(
                CAST(ROUND(((score_bps/10000.0)+1.0)*5000) AS SIGNED),
                0
            ),
            10000
        )
        WHERE score_bps < 0 AND score_bps >= -10000
    """)


def downgrade() -> None:
    """다운그레이드: 보정된 값을 다시 원래 음수로 복원할 수 없으므로 무시"""
    # 보정된 값을 원래 음수로 복원하는 것은 불가능하므로
    # 다운그레이드는 수행하지 않음
    pass

