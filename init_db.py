"""
데이터베이스 초기화 스크립트
모든 테이블을 생성하고 초기 데이터를 입력
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(str(Path(__file__).parent))

from app.database import init_db, engine, SessionLocal
from app.models import User, Setting, Reminder, Log
from sqlalchemy import inspect


def check_tables():
    """
    생성된 테이블 확인
    """
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    print("\n📋 생성된 테이블 목록:")
    for table in tables:
        print(f"  - {table}")
        columns = inspector.get_columns(table)
        for col in columns:
            print(f"    └─ {col['name']}: {col['type']}")

    return tables


def create_sample_data():
    """
    샘플 데이터 생성 (선택 사항)
    """
    db = SessionLocal()
    try:
        # 기존 데이터가 있는지 확인
        existing_user = db.query(User).first()
        if existing_user:
            print("\n⚠️  이미 데이터가 존재합니다. 샘플 데이터 생성을 건너뜁니다.")
            return

        # 샘플 사용자 생성
        sample_user = User(
            kakao_access_token=None,
            kakao_refresh_token=None,
            google_access_token=None,
            google_refresh_token=None,
        )
        db.add(sample_user)
        db.commit()
        db.refresh(sample_user)

        print(f"\n✅ 샘플 사용자 생성 완료 (user_id: {sample_user.user_id})")

        # 샘플 로그 생성
        sample_log = Log(
            category="system",
            status="INFO",
            message="데이터베이스 초기화 완료"
        )
        db.add(sample_log)
        db.commit()

        print("✅ 샘플 로그 생성 완료")

    except Exception as e:
        print(f"\n❌ 샘플 데이터 생성 실패: {e}")
        db.rollback()
    finally:
        db.close()


def main():
    """
    메인 함수
    """
    print("=" * 60)
    print("🚀 My Assistant 데이터베이스 초기화")
    print("=" * 60)

    try:
        # 데이터베이스 초기화 (테이블 생성)
        init_db()

        # 테이블 확인
        tables = check_tables()

        if len(tables) == 0:
            print("\n❌ 테이블이 생성되지 않았습니다.")
            return

        print(f"\n✅ 총 {len(tables)}개의 테이블이 성공적으로 생성되었습니다.")

        # 샘플 데이터 생성 여부 확인
        response = input("\n샘플 데이터를 생성하시겠습니까? (y/n): ")
        if response.lower() == 'y':
            create_sample_data()
        else:
            print("샘플 데이터 생성을 건너뜁니다.")

        print("\n" + "=" * 60)
        print("✨ 데이터베이스 초기화가 완료되었습니다!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
