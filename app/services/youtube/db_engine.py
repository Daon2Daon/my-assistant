"""
YouTube 모니터 모듈: PostgreSQL 동적 Async 엔진 매니저.

- 접속 정보는 SQLite `youtube_settings`에서 런타임 로딩 (SettingsManager)
- 설정이 바뀌면 다음 요청부터 새 엔진을 사용하도록 재생성
- 최초 연결 성공 시 `migrations/youtube/001_init_schema.sql` 를 멱등 적용
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.services.youtube.settings_manager import DatabaseSettings, get_youtube_settings_manager


class DBNotConfiguredError(RuntimeError):
    """PostgreSQL 접속 설정이 없는 상태."""


@dataclass(frozen=True)
class EngineHealth:
    ok: bool
    latency_ms: float | None = None
    message: str | None = None


def _migrations_dir() -> Path:
    # app/services/youtube/db_engine.py -> app/services/youtube -> app/services -> app -> repo root
    return Path(__file__).resolve().parents[3] / "migrations" / "youtube"


def _dsn_signature(cfg: DatabaseSettings) -> str:
    """엔진 재생성 감지용 시그니처(비밀번호 제외)."""
    raw = cfg.signature().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _build_async_dsn(cfg: DatabaseSettings) -> str:
    if not cfg.is_configured:
        raise DBNotConfiguredError(
            "DB 설정이 없습니다. /youtube/settings/database 에서 설정하세요."
        )
    user = quote_plus(cfg.username)
    pwd = quote_plus(cfg.password or "")
    host = cfg.host
    port = int(cfg.port)
    dbname = quote_plus(cfg.dbname)

    # sslmode는 asyncpg에서 querystring으로 처리 가능
    sslmode = quote_plus(cfg.sslmode or "prefer")
    if pwd:
        auth = f"{user}:{pwd}"
    else:
        auth = user
    return f"postgresql+asyncpg://{auth}@{host}:{port}/{dbname}?sslmode={sslmode}"


async def ensure_schema(engine: AsyncEngine) -> None:
    """PG 연결 성공 시 schema/테이블을 멱등 생성."""
    mig_dir = _migrations_dir()
    init_path = mig_dir / "001_init_schema.sql"
    if not init_path.is_file():
        raise FileNotFoundError(f"마이그레이션 파일을 찾을 수 없습니다: {init_path}")

    sql = init_path.read_text(encoding="utf-8")
    async with engine.begin() as conn:
        await conn.execute(text(sql))
        # 버전 기록: 1 (멱등)
        await conn.execute(
            text(
                """
                INSERT INTO youtube.schema_migrations(version, description)
                VALUES (1, 'init schema')
                ON CONFLICT (version) DO NOTHING
                """
            )
        )


class DBEngineManager:
    """
    SettingsManager 기반으로 동적 AsyncEngine을 제공한다.

    - get_engine(): 설정 시그니처가 변경되면 엔진을 dispose 후 재생성
    - recreate_engine(): 외부에서 강제로 엔진 무효화
    """

    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._signature: Optional[str] = None

    async def _dispose_existing(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None

    async def get_engine(self) -> AsyncEngine:
        mgr = get_youtube_settings_manager()
        cfg = mgr.get_database()
        sig = _dsn_signature(cfg)
        if self._engine is None or self._signature != sig:
            await self._dispose_existing()
            dsn = _build_async_dsn(cfg)
            self._engine = create_async_engine(
                dsn,
                pool_size=5,
                max_overflow=5,
                pool_pre_ping=True,
                connect_args={
                    "server_settings": {"search_path": cfg.schema or "youtube"}
                },
            )
            self._signature = sig
            # schema는 최초 생성 시/DSN 변경 시 보장
            await ensure_schema(self._engine)
        return self._engine

    async def recreate_engine(self) -> None:
        await self._dispose_existing()
        self._signature = None
        # settings cache는 다음 호출에서 다시 읽도록 무효화
        get_youtube_settings_manager().invalidate("database")

    async def health_check(self) -> EngineHealth:
        import time

        try:
            engine = await self.get_engine()
            start = time.perf_counter()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            elapsed = (time.perf_counter() - start) * 1000.0
            return EngineHealth(ok=True, latency_ms=elapsed)
        except Exception as e:
            return EngineHealth(ok=False, message=str(e))


db_engine_manager = DBEngineManager()

