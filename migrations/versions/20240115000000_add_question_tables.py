"""Rev: add question and voice_question tables

Revision ID: add_question_tables
Revises: 20240101000000_add_user_code
Create Date: 2024-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'add_question_tables'
down_revision = None  # 첫 번째 마이그레이션으로 설정
branch_labels = None
depends_on = None


def upgrade() -> None:
    # user, voice, voice_content, voice_analyze 테이블 생성
    op.create_table(
        'user',
        sa.Column('user_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('user_code', sa.String(length=20), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password', sa.String(length=72), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('birthdate', sa.Date(), nullable=False),
        sa.Column('connecting_user_code', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('user_id'),
        sa.UniqueConstraint('user_code', name='unique_user_code'),
        sa.UniqueConstraint('username', name='username'),
        sa.CheckConstraint("role IN ('USER','CARE')", name='check_user_role')
    )
    
    op.create_table(
        'voice',
        sa.Column('voice_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('voice_key', sa.String(length=1024), nullable=False),
        sa.Column('voice_name', sa.String(length=255), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('sample_rate', sa.Integer(), nullable=True),
        sa.Column('bit_rate', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('voice_id'),
        sa.ForeignKeyConstraint(['user_id'], ['user.user_id'], ondelete='CASCADE'),
        sa.Index('idx_voice_user_created', 'user_id', 'created_at')
    )
    
    op.create_table(
        'voice_content',
        sa.Column('voice_content_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('voice_id', sa.BigInteger(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('score_bps', sa.SmallInteger(), nullable=True),
        sa.Column('magnitude_x1000', sa.Integer(), nullable=True),
        sa.Column('locale', sa.String(length=10), nullable=True),
        sa.Column('provider', sa.String(length=32), nullable=True),
        sa.Column('model_version', sa.String(length=32), nullable=True),
        sa.Column('confidence_bps', sa.SmallInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('voice_content_id'),
        sa.UniqueConstraint('voice_id', name='uq_vc_voice'),
        sa.ForeignKeyConstraint(['voice_id'], ['voice.voice_id'], ondelete='CASCADE')
    )
    
    op.create_table(
        'voice_analyze',
        sa.Column('voice_analyze_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('voice_id', sa.BigInteger(), nullable=False),
        sa.Column('happy_bps', sa.SmallInteger(), nullable=False),
        sa.Column('sad_bps', sa.SmallInteger(), nullable=False),
        sa.Column('neutral_bps', sa.SmallInteger(), nullable=False),
        sa.Column('angry_bps', sa.SmallInteger(), nullable=False),
        sa.Column('fear_bps', sa.SmallInteger(), nullable=False),
        sa.Column('top_emotion', sa.String(length=16), nullable=True),
        sa.Column('top_confidence_bps', sa.SmallInteger(), nullable=True),
        sa.Column('model_version', sa.String(length=32), nullable=True),
        sa.Column('analyzed_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('voice_analyze_id'),
        sa.UniqueConstraint('voice_id', name='uq_va_voice'),
        sa.ForeignKeyConstraint(['voice_id'], ['voice.voice_id'], ondelete='CASCADE'),
        sa.CheckConstraint("happy_bps <= 10000 AND sad_bps <= 10000 AND neutral_bps <= 10000 AND angry_bps <= 10000 AND fear_bps <= 10000", name='check_emotion_bps_range'),
        sa.CheckConstraint("happy_bps + sad_bps + neutral_bps + angry_bps + fear_bps = 10000", name='check_emotion_bps_sum')
    )
    
    # question 테이블 생성
    op.create_table(
        'question',
        sa.Column('question_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('question_category', sa.String(length=50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('question_id'),
        sa.CheckConstraint("question_category IN ('emotion', 'stress', 'physical', 'social', 'self_reflection')", name='check_question_category')
    )
    
    # voice_question 테이블 생성
    op.create_table(
        'voice_question',
        sa.Column('voice_question_id', sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column('voice_id', sa.BigInteger(), nullable=False),
        sa.Column('question_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('voice_question_id'),
        sa.UniqueConstraint('voice_id', 'question_id', name='uq_voice_question'),
        sa.ForeignKeyConstraint(['voice_id'], ['voice.voice_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['question.question_id'], ondelete='CASCADE')
    )


def downgrade() -> None:
    # voice_question 테이블 삭제
    op.drop_table('voice_question')
    
    # question 테이블 삭제
    op.drop_table('question')
    
    # voice_analyze 테이블 삭제
    op.drop_table('voice_analyze')
    
    # voice_content 테이블 삭제
    op.drop_table('voice_content')
    
    # voice 테이블 삭제
    op.drop_table('voice')
    
    # user 테이블 삭제
    op.drop_table('user')
