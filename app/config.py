"""
애플리케이션 설정 관리
환경변수를 로드하고 전역 설정을 제공합니다.
"""

import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


class Settings:
    """애플리케이션 설정 클래스"""

    # Google API
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
    )

    # OpenWeatherMap
    OPENWEATHER_API_KEY: str = os.getenv("OPENWEATHER_API_KEY", "")

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/assistant.db")

    # App
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-this")
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")  # 차트 이미지 등 공개 URL (프로덕션 필수)

    # Admin Login
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    SESSION_SECRET_KEY: str = os.getenv(
        "SESSION_SECRET_KEY", "change-this-to-random-32-chars-min"
    )
    SESSION_MAX_AGE: int = int(os.getenv("SESSION_MAX_AGE", "86400"))  # 24시간

    # YouTube monitor: SQLite 설정 암호화 (Fernet, 32바이트 url-safe base64)
    YOUTUBE_SETTINGS_FERNET_KEY: str = os.getenv("YOUTUBE_SETTINGS_FERNET_KEY", "")

    # YouTube monitor: 첫 기동 시 빈 youtube_settings 행에만 주입 (이미 값이 있으면 덮어쓰지 않음)
    YOUTUBE_BOOTSTRAP_DB_HOST: str = os.getenv("YOUTUBE_BOOTSTRAP_DB_HOST", "")
    YOUTUBE_BOOTSTRAP_DB_PORT: str = os.getenv("YOUTUBE_BOOTSTRAP_DB_PORT", "")
    YOUTUBE_BOOTSTRAP_DB_NAME: str = os.getenv("YOUTUBE_BOOTSTRAP_DB_NAME", "")
    YOUTUBE_BOOTSTRAP_DB_USER: str = os.getenv("YOUTUBE_BOOTSTRAP_DB_USER", "")
    YOUTUBE_BOOTSTRAP_DB_PASSWORD: str = os.getenv("YOUTUBE_BOOTSTRAP_DB_PASSWORD", "")
    YOUTUBE_BOOTSTRAP_DB_SCHEMA: str = os.getenv("YOUTUBE_BOOTSTRAP_DB_SCHEMA", "")
    YOUTUBE_BOOTSTRAP_DB_SSLMODE: str = os.getenv("YOUTUBE_BOOTSTRAP_DB_SSLMODE", "")

    YOUTUBE_BOOTSTRAP_LITELLM_BASE_URL: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_LITELLM_BASE_URL", ""
    )
    YOUTUBE_BOOTSTRAP_LITELLM_API_KEY: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_LITELLM_API_KEY", ""
    )
    YOUTUBE_BOOTSTRAP_PRIMARY_MODEL: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_PRIMARY_MODEL", ""
    )
    YOUTUBE_BOOTSTRAP_FALLBACK_MODEL: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_FALLBACK_MODEL", ""
    )
    YOUTUBE_BOOTSTRAP_TAGGING_MODEL: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_TAGGING_MODEL", ""
    )

    YOUTUBE_BOOTSTRAP_YOUTUBE_API_KEY: str = os.getenv(
        "YOUTUBE_BOOTSTRAP_YOUTUBE_API_KEY", ""
    )


# 전역 설정 인스턴스
settings = Settings()
