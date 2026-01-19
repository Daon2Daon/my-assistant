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

    # Kakao API
    KAKAO_REST_API_KEY: str = os.getenv("KAKAO_REST_API_KEY", "")
    KAKAO_REDIRECT_URI: str = os.getenv(
        "KAKAO_REDIRECT_URI", "http://localhost:8000/auth/kakao/callback"
    )

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

    # Admin Login
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    SESSION_SECRET_KEY: str = os.getenv(
        "SESSION_SECRET_KEY", "change-this-to-random-32-chars-min"
    )
    SESSION_MAX_AGE: int = int(os.getenv("SESSION_MAX_AGE", "86400"))  # 24시간

    # API URLs
    KAKAO_AUTH_URL: str = "https://kauth.kakao.com/oauth/authorize"
    KAKAO_TOKEN_URL: str = "https://kauth.kakao.com/oauth/token"
    KAKAO_API_URL: str = "https://kapi.kakao.com"


# 전역 설정 인스턴스
settings = Settings()
