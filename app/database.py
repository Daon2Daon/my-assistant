"""
데이터베이스 연결 및 세션 관리
SQLAlchemy를 사용한 SQLite 데이터베이스 설정
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

# 데이터베이스 URL (SQLite)
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# 엔진 생성
# check_same_thread=False는 SQLite에서 여러 스레드에서 접근을 허용
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=settings.DEBUG  # DEBUG 모드일 때 SQL 쿼리 로깅
)

# 세션 로컬 클래스 생성
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base 클래스 생성 (모든 ORM 모델의 부모 클래스)
Base = declarative_base()


def get_db():
    """
    데이터베이스 세션을 생성하고 반환하는 의존성 함수
    FastAPI의 Depends에서 사용

    Yields:
        Session: 데이터베이스 세션
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    데이터베이스 초기화
    모든 테이블을 생성
    """
    # 모든 모델을 임포트해야 Base.metadata에 등록됨
    from app.models import user, setting, reminder, log, watchlist, price_alert

    # 테이블 생성
    Base.metadata.create_all(bind=engine)
    print("✅ 데이터베이스 테이블이 생성되었습니다.")


def run_migrations():
    """
    데이터베이스 마이그레이션 실행
    앱 시작 시 자동으로 필요한 마이그레이션 적용
    """
    import sqlite3
    from pathlib import Path

    # DB 파일 경로
    db_path = Path(SQLALCHEMY_DATABASE_URL.replace("sqlite:///", ""))

    if not db_path.exists():
        print("ℹ️  신규 DB - 마이그레이션 불필요")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 마이그레이션 1: price_alerts에 reference_price 컬럼 추가
        cursor.execute("PRAGMA table_info(price_alerts)")
        columns = [column[1] for column in cursor.fetchall()]

        if "reference_price" not in columns:
            print("🔄 마이그레이션 실행: price_alerts.reference_price 컬럼 추가")
            cursor.execute("""
                ALTER TABLE price_alerts
                ADD COLUMN reference_price REAL
            """)
            conn.commit()
            print("✅ 마이그레이션 완료: reference_price 컬럼 추가됨")
        else:
            print("✓ price_alerts.reference_price 컬럼 이미 존재")

        conn.close()

    except Exception as e:
        print(f"⚠️  마이그레이션 중 오류 발생: {e}")
        # 오류가 발생해도 앱 시작은 계속 진행
