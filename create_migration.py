#!/usr/bin/env python3
"""
Alembic 마이그레이션 파일 자동 생성 스크립트
"""

from alembic import command
from alembic.config import Config

# Alembic 설정 로드
alembic_cfg = Config("alembic.ini")

# 모델 변경사항을 자동으로 감지하여 마이그레이션 파일 생성
command.revision(alembic_cfg, autogenerate=True, message="add all tables")

print("✅ 마이그레이션 파일이 생성되었습니다!")
