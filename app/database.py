"""
데이터베이스 연결 및 세션 관리
SQLAlchemy를 사용한 SQLite 데이터베이스 설정
"""

from pathlib import Path

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
    from app.models import user, setting, reminder, log, watchlist, price_alert, youtube_setting

    # 테이블 생성
    Base.metadata.create_all(bind=engine)
    print("✅ 데이터베이스 테이블이 생성되었습니다.")


def _migrations_youtube_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "migrations" / "youtube"


def _sqlite_table_exists(cursor, name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    )
    return cursor.fetchone() is not None


def _migrate_youtube_settings(conn, cursor) -> None:
    """youtube_settings 테이블 생성(없을 때만), 시드, 환경변수 부트스트랩."""
    mig_dir = _migrations_youtube_dir()
    ddl_path = mig_dir / "000_sqlite_settings.sql"
    seed_path = mig_dir / "000_seed_settings.sql"
    if not ddl_path.is_file() or not seed_path.is_file():
        print("⚠️  YouTube 마이그레이션 파일을 찾을 수 없습니다.")
        return

    if not _sqlite_table_exists(cursor, "youtube_settings"):
        print("🔄 마이그레이션 실행: youtube_settings 테이블 생성")
        cursor.executescript(ddl_path.read_text(encoding="utf-8"))
        conn.commit()

    print("🔄 YouTube 설정 시드 적용 (INSERT OR IGNORE)")
    cursor.executescript(seed_path.read_text(encoding="utf-8"))
    conn.commit()

    _apply_youtube_bootstrap_from_env(conn, cursor)
    conn.commit()
    print("✅ youtube_settings 마이그레이션 완료")


def _youtube_setting_row_is_empty(cursor, category: str, key: str) -> bool:
    cursor.execute(
        "SELECT value, value_enc, is_secret FROM youtube_settings WHERE category = ? AND key = ?",
        (category, key),
    )
    row = cursor.fetchone()
    if not row:
        return False
    value, value_enc, is_secret = row[0], row[1], int(row[2] or 0)
    if is_secret:
        return value_enc is None or (isinstance(value_enc, bytes) and len(value_enc) == 0)
    return value is None or value == ""


def _apply_youtube_bootstrap_from_env(conn, cursor) -> None:
    """YOUTUBE_BOOTSTRAP_* 환경변수를 비어 있는 행에만 반영 (비밀은 Fernet)."""
    from cryptography.fernet import Fernet

    from app.config import settings as app_settings

    fernet: Fernet | None = None
    key_str = (app_settings.YOUTUBE_SETTINGS_FERNET_KEY or "").strip()
    if key_str:
        try:
            fernet = Fernet(key_str.encode("utf-8"))
        except Exception as e:
            print(f"⚠️  YOUTUBE_SETTINGS_FERNET_KEY가 유효하지 않습니다: {e}")

    def update_plain(category: str, key: str, val: str) -> None:
        cursor.execute(
            """
            UPDATE youtube_settings
            SET value = ?, updated_at = CURRENT_TIMESTAMP
            WHERE category = ? AND key = ?
            """,
            (val, category, key),
        )

    def update_secret(category: str, key: str, val: str) -> None:
        if not fernet:
            print("⚠️  YouTube bootstrap: 비밀 필드 저장을 건너뜁니다 (Fernet 키 없음)")
            return
        enc = fernet.encrypt(val.encode("utf-8"))
        cursor.execute(
            """
            UPDATE youtube_settings
            SET value = NULL, value_enc = ?, updated_at = CURRENT_TIMESTAMP
            WHERE category = ? AND key = ?
            """,
            (enc, category, key),
        )

    bootstrap_plain = [
        ("database", "host", app_settings.YOUTUBE_BOOTSTRAP_DB_HOST),
        ("database", "port", app_settings.YOUTUBE_BOOTSTRAP_DB_PORT),
        ("database", "dbname", app_settings.YOUTUBE_BOOTSTRAP_DB_NAME),
        ("database", "username", app_settings.YOUTUBE_BOOTSTRAP_DB_USER),
        ("database", "schema", app_settings.YOUTUBE_BOOTSTRAP_DB_SCHEMA),
        ("database", "sslmode", app_settings.YOUTUBE_BOOTSTRAP_DB_SSLMODE),
        ("ai_gateway", "base_url", app_settings.YOUTUBE_BOOTSTRAP_LITELLM_BASE_URL),
        ("ai_gateway", "primary_model", app_settings.YOUTUBE_BOOTSTRAP_PRIMARY_MODEL),
        ("ai_gateway", "fallback_model", app_settings.YOUTUBE_BOOTSTRAP_FALLBACK_MODEL),
        ("ai_gateway", "tagging_model", app_settings.YOUTUBE_BOOTSTRAP_TAGGING_MODEL),
    ]
    bootstrap_secret = [
        ("database", "password", app_settings.YOUTUBE_BOOTSTRAP_DB_PASSWORD),
        ("ai_gateway", "api_key", app_settings.YOUTUBE_BOOTSTRAP_LITELLM_API_KEY),
        ("polling", "youtube_api_key", app_settings.YOUTUBE_BOOTSTRAP_YOUTUBE_API_KEY),
    ]

    for category, key, val in bootstrap_plain:
        if not (val and str(val).strip()):
            continue
        if _youtube_setting_row_is_empty(cursor, category, key):
            update_plain(category, key, str(val).strip())

    for category, key, val in bootstrap_secret:
        if not (val and str(val).strip()):
            continue
        if _youtube_setting_row_is_empty(cursor, category, key):
            update_secret(category, key, str(val).strip())


def run_migrations():
    """
    데이터베이스 마이그레이션 실행
    앱 시작 시 자동으로 필요한 마이그레이션 적용
    """
    import sqlite3

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

        _migrate_youtube_settings(conn, cursor)

        conn.close()

    except Exception as e:
        print(f"⚠️  마이그레이션 중 오류 발생: {e}")
        # 오류가 발생해도 앱 시작은 계속 진행
