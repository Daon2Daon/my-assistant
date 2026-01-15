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
