"""Rev: head

Revision ID: head
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'head'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # user 테이블에 user_code, connecting_user_code 추가
    op.add_column('user', sa.Column('user_code', sa.String(length=20), nullable=True))
    op.add_column('user', sa.Column('connecting_user_code', sa.String(length=20), nullable=True))
    
    # 기존 데이터에 user_code 생성
    op.execute("""
        UPDATE `user` 
        SET `user_code` = CONCAT(
            SUBSTRING(MD5(CONCAT(user_id, username)), 1, 8)
        )
        WHERE `user_code` IS NULL
    """)
    
    # NOT NULL 제약 추가
    op.alter_column('user', 'user_code',
                    existing_type=sa.String(length=20),
                    nullable=False)
    
    # UNIQUE 제약 추가
    op.create_unique_constraint('unique_user_code', 'user', ['user_code'])
    
    # role CHECK 제약 변경
    op.drop_constraint('check_user_role', 'user', type_='check')
    op.create_check_constraint(
        'check_user_role',
        'user',
        "role IN ('USER','CARE')"
    )


def downgrade() -> None:
    # 제약 조건 제거
    op.drop_constraint('check_user_role', 'user', type_='check')
    op.drop_constraint('unique_user_code', 'user', type_='unique')
    
    # 컬럼 제거
    op.drop_column('user', 'connecting_user_code')
    op.drop_column('user', 'user_code')
    
    # 원래 role 제약 복구
    op.create_check_constraint(
        'check_user_role',
        'user',
        "role IN ('USER','GUARDIAN','ADMIN')"
    )
