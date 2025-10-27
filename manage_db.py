#!/usr/bin/env python3
"""
데이터베이스 초기화 및 관리 스크립트
"""

from app.database import create_tables, drop_tables, engine
from app.models import Base
import sys


def init_database():
    """데이터베이스 테이블 생성"""
    print("데이터베이스 테이블을 생성합니다...")
    try:
        create_tables()
        print("✅ 데이터베이스 테이블 생성 완료!")
    except Exception as e:
        print(f"❌ 데이터베이스 테이블 생성 실패: {e}")
        sys.exit(1)


def reset_database():
    """데이터베이스 테이블 재생성 (기존 데이터 삭제)"""
    print("⚠️  기존 데이터를 모두 삭제하고 테이블을 재생성합니다...")
    try:
        drop_tables()
        create_tables()
        print("✅ 데이터베이스 재생성 완료!")
    except Exception as e:
        print(f"❌ 데이터베이스 재생성 실패: {e}")
        sys.exit(1)


def show_tables():
    """생성된 테이블 목록 표시"""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    print("📋 생성된 테이블 목록:")
    for table in tables:
        print(f"  - {table}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "init":
            init_database()
            show_tables()
        elif command == "reset":
            reset_database()
            show_tables()
        elif command == "show":
            show_tables()
        else:
            print("사용법: python manage_db.py [init|reset|show]")
            print("  init  - 테이블 생성")
            print("  reset - 테이블 재생성 (데이터 삭제)")
            print("  show  - 테이블 목록 표시")
    else:
        print("사용법: python manage_db.py [init|reset|show]")
        print("  init  - 테이블 생성")
        print("  reset - 테이블 재생성 (데이터 삭제)")
        print("  show  - 테이블 목록 표시")
