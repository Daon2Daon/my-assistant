"""
YouTube 모니터 모듈: PostgreSQL 동적 Async 엔진 매니저.

- 접속 정보는 SQLite `youtube_settings`에서 런타임 로딩 (SettingsManager)
- 설정이 바뀌면 다음 요청부터 새 엔진을 사용하도록 재생성
- 최초 연결 성공 시 `migrations/youtube/NNN_*.sql` (000 제외)을 버전 순으로 멱등 적용
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import ssl as ssl_std
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import asyncpg.exceptions
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncConnection, create_async_engine

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


def _numbered_postgres_migrations(mig_dir: Path) -> list[tuple[int, Path]]:
    """
    `001_*.sql`, `002_*.sql` … 만 순서대로 반환한다.
    `000_*.sql`(SQLite 시드 등)은 PG 스키마 적용 대상에서 제외한다.
    """
    out: list[tuple[int, Path]] = []
    for path in sorted(mig_dir.glob("[0-9][0-9][0-9]_*.sql")):
        prefix = path.name[:3]
        if not prefix.isdigit():
            continue
        ver = int(prefix)
        if ver == 0:
            continue
        out.append((ver, path))
    out.sort(key=lambda x: x[0])
    return out


def _is_transaction_boundary_statement(stmt: str) -> bool:
    """SQLAlchemy `begin()` 트랜잭션 안에서 파일에 있는 BEGIN/COMMIT은 건너뛴다."""
    raw = stmt.strip()
    if not raw:
        return False
    head = raw.split(None, 1)[0].upper().rstrip(";")
    return head in ("BEGIN", "COMMIT", "ROLLBACK")


def _is_comment_only_sql(stmt: str) -> bool:
    """세미콜론 분리 결과가 주석만 있으면 asyncpg에 보내지 않는다."""
    for raw_line in stmt.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("--"):
            continue
        return False
    return True


def _is_create_schema_migrations_table_statement(stmt: str, schema: str) -> bool:
    """001_init 의 schema_migrations 테이블 생성 구문인지."""
    parts: list[str] = []
    for line in stmt.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        parts.append(s)
    if not parts:
        return False
    joined = re.sub(r"\s+", " ", " ".join(parts)).strip().rstrip(";").strip().lower()
    return joined.startswith(f"create table if not exists {schema.lower()}.schema_migrations")


def _is_pg_typename_nsp_conflict(exc: Exception) -> bool:
    """테이블행 타입 이름이 같은 스키마에 이미 있을 때 (중단된 적용·레이스 등)."""
    msg = str(getattr(exc, "orig", exc)).lower()
    return "pg_type_typname_nsp_index" in msg


def _is_redundant_create_schema_statement(stmt: str, schema: str) -> bool:
    """
    001_init_schema.sql 의 CREATE SCHEMA IF NOT EXISTS … 구문.

    _ensure_app_schema()에서 이미 스키마를 보장하므로 SQL로 재실행할 필요가 없다.
    일부 환경에서는 스키마가 이미 있어도 CREATE SCHEMA 구문에 대해
    CREATE 권한 검사가 이루어져 permission denied 가 난다.
    """
    parts: list[str] = []
    for line in stmt.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        parts.append(s)
    if not parts:
        return False
    joined = re.sub(r"\s+", " ", " ".join(parts)).strip().rstrip(";").strip()
    return joined.lower() == f"create schema if not exists {schema.lower()}"


async def _load_applied_versions(engine: AsyncEngine, schema: str) -> set[int]:
    """
    schema_migrations 테이블에서 이미 적용된 버전 번호 집합을 반환한다.
    테이블이 아직 존재하지 않으면 빈 집합을 반환한다.
    """
    async with engine.connect() as conn:
        try:
            return await _fetch_applied_migration_versions(conn, schema)
        except Exception:
            return set()


async def _apply_migration_sql(conn: AsyncConnection, sql: str, schema: str) -> None:
    """
    단일 마이그레이션 SQL을 현재 트랜잭션(conn) 안에서 실행한다.

    - CREATE SCHEMA IF NOT EXISTS: _ensure_app_schema()가 이미 보장하므로 건너뜀
    - BEGIN / COMMIT / ROLLBACK: engine.begin() 트랜잭션과 충돌하므로 건너뜀
    - schema_migrations 테이블 생성: 부분 롤백 시 고아 타입이 남을 수 있어 savepoint로 감쌈
    """
    for stmt in _split_postgres_sql_script(sql):
        if not stmt.strip() or _is_comment_only_sql(stmt):
            continue
        if _is_transaction_boundary_statement(stmt):
            continue
        if _is_redundant_create_schema_statement(stmt, schema):
            continue
        if _is_create_schema_migrations_table_statement(stmt, schema):
            async with conn.begin_nested():
                try:
                    await conn.execute(text(stmt))
                except IntegrityError as exc:
                    if _is_pg_typename_nsp_conflict(exc):
                        raise RuntimeError(
                            f"'{schema}.schema_migrations' 이름이 이미 사용 중입니다 "
                            "(이전 마이그레이션 중단으로 타입만 남은 경우가 많습니다). "
                            "DB 슈퍼유저/소유자로 다음 실행 후 다시 '스키마 적용' 하세요.\n"
                            f"  DROP TYPE IF EXISTS {schema}.schema_migrations CASCADE;"
                        ) from exc
                    raise
        else:
            await conn.execute(text(stmt))


async def _fetch_applied_migration_versions(conn: Any, schema: str) -> set[int]:
    safe = _validated_pg_schema(schema, "youtube")
    result = await conn.execute(text(f"SELECT version FROM {safe}.schema_migrations"))
    rows = result.fetchall()
    return {int(row[0]) for row in rows}


def _dsn_signature(cfg: DatabaseSettings) -> str:
    """엔진 재생성 감지용 시그니처(비밀번호 제외)."""
    raw = cfg.signature().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _asyncpg_ssl(sslmode: str | None) -> Any:
    """
    libpq sslmode 문자열을 asyncpg `ssl` 인자로 변환한다.
    DSN 쿼리의 sslmode= 는 asyncpg.connect()에 그대로 전달되면 TypeError가 난다.
    """
    mode = (sslmode or "prefer").lower().strip()
    if mode == "disable":
        return False
    if mode in ("allow", "prefer"):
        return None
    if mode == "require":
        return True
    if mode in ("verify-ca", "verify-full"):
        return ssl_std.create_default_context()
    return None


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

    if pwd:
        auth = f"{user}:{pwd}"
    else:
        auth = user
    return f"postgresql+asyncpg://{auth}@{host}:{port}/{dbname}"


def _split_postgres_sql_script(sql: str) -> list[str]:
    """
    세미콜론 기준으로 SQL 문을 나눈다. asyncpg는 한 번의 execute에 복수 문을 둘 수 없다.

    단일 인용부('' 포함)와 달러인용($$ … $$, $tag$ … $tag$) 안의 세미콜론은 구분자로 쓰지 않는다.
    """
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql)

    def flush() -> None:
        piece = "".join(buf).strip()
        buf.clear()
        if piece:
            statements.append(piece)

    while i < n:
        # Line comment (not inside string — strings handled in their branches)
        if sql[i] == "-" and i + 1 < n and sql[i + 1] == "-":
            while i < n and sql[i] != "\n":
                buf.append(sql[i])
                i += 1
            continue

        # Block comment
        if sql[i] == "/" and i + 1 < n and sql[i + 1] == "*":
            buf.append(sql[i])
            buf.append(sql[i + 1])
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                buf.append(sql[i])
                i += 1
            if i + 1 < n:
                buf.append(sql[i])
                buf.append(sql[i + 1])
                i += 2
            continue

        # Dollar-quoted literal (PL/pgSQL bodies, etc.)
        if sql[i] == "$":
            j = i + 1
            while j < n and sql[j] != "$":
                j += 1
            if j >= n:
                buf.append(sql[i])
                i += 1
                continue
            tag = sql[i : j + 1]
            tail = sql[j + 1 :]
            close_rel = tail.find(tag)
            if close_rel < 0:
                buf.append(sql[i])
                i += 1
                continue
            end = j + 1 + close_rel + len(tag)
            buf.append(sql[i:end])
            i = end
            continue

        # Single-quoted literal
        if sql[i] == "'":
            buf.append(sql[i])
            i += 1
            while i < n:
                if sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        buf.append("''")
                        i += 2
                        continue
                    buf.append("'")
                    i += 1
                    break
                buf.append(sql[i])
                i += 1
            continue

        if sql[i] == ";":
            flush()
            i += 1
            continue

        buf.append(sql[i])
        i += 1

    flush()
    return statements


_PG_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validated_pg_schema(name: str | None, default: str = "youtube") -> str:
    """
    설정값으로부터 안전한 PostgreSQL 스키마 이름만 허용한다 (SQL 식별자 주입 방지).

    `public`은 이 앱의 마이그레이션 대상 스키마가 아니며, CREATE SCHEMA 시 권한 이슈가 잦다.
    SettingsManager에서도 정규화하지만, 여기서 한 번 더 `youtube`로 통일한다.
    """
    raw = (name or default).strip()
    if raw.lower() == "public":
        return default
    if _PG_IDENT_RE.fullmatch(raw):
        return raw
    return default


async def _pg_namespace_schema_exists(conn: AsyncConnection, schema: str) -> bool:
    """pg_catalog 기준으로 스키마 존재 여부 (연결 권한으로 조회 가능)."""
    r = await conn.execute(
        text("SELECT 1 FROM pg_namespace WHERE nspname = :name LIMIT 1"),
        {"name": schema},
    )
    return r.first() is not None


async def _pg_extension_exists(conn: AsyncConnection, extname: str) -> bool:
    """확장이 이미 이 데이터베이스에 설치되어 있는지 (관리자·슈퍼유저가 선설치한 경우)."""
    r = await conn.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = :name LIMIT 1"),
        {"name": extname},
    )
    return r.first() is not None


class SchemaPrivilegeError(RuntimeError):
    """앱 역할이 스키마를 생성할 수 없을 때. 관리자에게 위임해야 한다."""


class ExtensionPrivilegeError(RuntimeError):
    """앱 역할이 CREATE EXTENSION 을 실행할 수 없을 때. 관리자가 확장을 선설치하거나 권한을 줘야 한다."""


async def _ensure_app_schema(engine: AsyncEngine, app_schema: str) -> None:
    """
    앱 스키마가 존재하는지 확인하고, 없으면 생성을 시도한다.

    마이그레이션 SQL(001_init_schema.sql)은 CREATE SCHEMA IF NOT EXISTS 를 포함하는데,
    스키마가 없고 권한도 없으면 트랜잭션 안에서 ProgrammingError 가 발생한다.
    마이그레이션 실행 전에 이 함수로 스키마를 미리 보장하면, SQL 안의
    CREATE SCHEMA IF NOT EXISTS 는 스키마가 이미 있어 NOTICE 만 내고 통과한다.

    기본 스키마 `public`은 거의 항상 클러스터에 이미 있다. 설정만 `public`으로 두었을 때
    CREATE SCHEMA public 이 DB 레벨 CREATE 권한을 요구해 앱 역할에서
    permission denied for database 가 나는 경우가 있으므로, public 에 대해서는
    생성을 시도하지 않는다.
    """
    if app_schema.lower() == "public":
        return

    autocommit_engine = engine.execution_options(isolation_level="AUTOCOMMIT")
    async with autocommit_engine.connect() as conn:
        if await _pg_namespace_schema_exists(conn, app_schema):
            return
        try:
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {app_schema}"))
        except ProgrammingError as exc:
            orig = getattr(exc, "orig", None)
            if isinstance(orig, asyncpg.exceptions.InsufficientPrivilegeError):
                raise SchemaPrivilegeError(
                    f"스키마 '{app_schema}' 가 존재하지 않고 현재 DB 사용자에게 생성 권한도 없습니다.\n"
                    "DB 관리자(슈퍼유저 또는 소유자)가 다음 중 하나를 실행한 뒤 재시도하세요.\n"
                    f"  CREATE SCHEMA {app_schema} AUTHORIZATION 앱역할이름;\n"
                    f"  또는: GRANT CREATE ON DATABASE 데이터베이스이름 TO 앱역할이름;"
                ) from exc
            raise


async def _ensure_pg_trgm_extension(engine: AsyncEngine, app_schema: str) -> None:
    """
    앱 스키마에 pg_trgm 확장을 AUTOCOMMIT 모드로 보장한다.

    isolation_level은 SQLAlchemy 2.x에서 연결(connection) 레벨에서만 유효하므로
    engine.execution_options(isolation_level="AUTOCOMMIT")으로 파생 엔진을 만든 뒤 connect 한다.

    - pg_extension 에 pg_trgm 이 이미 있으면 → 설치를 시도하지 않는다.
    - 없으면 앱 스키마에 설치 시도. 권한이 없으면 ExtensionPrivilegeError.
    - public 스키마는 사용하지 않는다.
      public 이 없는 환경에서는 SCHEMA public 명시 시 InvalidSchemaNameError 가 발생한다.
    """
    autocommit_engine = engine.execution_options(isolation_level="AUTOCOMMIT")
    async with autocommit_engine.connect() as conn:
        if await _pg_extension_exists(conn, "pg_trgm"):
            return
        try:
            await conn.execute(text(f"CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA {app_schema}"))
        except ProgrammingError as exc:
            orig = getattr(exc, "orig", None)
            if isinstance(orig, asyncpg.exceptions.InsufficientPrivilegeError):
                raise ExtensionPrivilegeError(
                    "pg_trgm 확장을 현재 DB 사용자로 설치할 수 없습니다.\n"
                    "DB 관리자(슈퍼유저 또는 소유자)가 한 번만 다음을 실행한 뒤 재시도하세요.\n"
                    f"  CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA {app_schema};\n"
                    "호스팅 콘솔(Neon, Supabase, RDS 등)에서는 대시보드 → Extensions 에서 활성화하세요."
                ) from exc
            raise


async def ensure_schema(engine: AsyncEngine) -> None:
    """PG 연결 성공 시 schema/테이블을 멱등 생성하고, 미적용 마이그레이션을 순서대로 적용한다."""
    cfg = get_youtube_settings_manager().get_database()
    app_schema = _validated_pg_schema(cfg.schema, "youtube")

    await _ensure_app_schema(engine, app_schema)
    await _ensure_pg_trgm_extension(engine, app_schema)

    mig_dir = _migrations_dir()
    numbered = _numbered_postgres_migrations(mig_dir)
    if not numbered or numbered[0][0] != 1:
        raise FileNotFoundError(
            f"초기 스키마 마이그레이션(001_*.sql)을 찾을 수 없습니다: {mig_dir}"
        )

    applied = await _load_applied_versions(engine, app_schema)
    for ver, path in numbered:
        if ver in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        async with engine.begin() as conn:
            await _apply_migration_sql(conn, sql, app_schema)


def _sync_dispose_async_engine(engine: AsyncEngine) -> None:
    """
    이벤트 루프가 이미 닫힌 뒤(GC 등) 비동기 dispose를 호출할 수 없을 때 풀만 동기 정리한다.
    APScheduler 스레드에서 asyncio.run()으로 만든 루프가 수명 종료될 때 누수·좀비 연결을 줄인다.
    """
    try:
        engine.sync_engine.dispose(close=True)
    except Exception:
        pass


class DBEngineManager:
    """
    SettingsManager 기반으로 동적 AsyncEngine을 제공한다.

    - 이벤트 루프별로 별도 엔진을 둔다. FastAPI(uvicorn) 루프와 APScheduler가
      `asyncio.run()`으로 쓰는 루프가 다르면, 단일 AsyncEngine을 공유할 때
      asyncpg에서 "attached to a different loop"가 발생한다.
    - get_engine(): (현재 루프, 설정 시그니처)에 맞는 엔진을 반환·필요 시 생성
    - recreate_engine(): 등록된 모든 루프의 엔진을 dispose 후 무효화

    APScheduler는 `asyncio.run()`으로 매 실행마다 새 이벤트 루프를 생성한다.
    새 루프마다 `ensure_schema`를 재실행하면 PostgreSQL에 불필요한 DDL 쿼리가
    반복되므로, 이미 초기화에 성공한 DSN 시그니처는 `_initialized_sigs`에 기록하여
    이후 새 루프에서는 스키마·마이그레이션 체크를 건너뛴다.
    설정이 바뀌거나 `recreate_engine()`이 호출되면 초기화 기록을 리셋한다.
    """

    def __init__(self) -> None:
        # 루프 객체가 GC되면 항목이 자동 제거된다. 값은 (엔진, DSN 시그니처).
        self._engines: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, tuple[AsyncEngine, str]] = (
            weakref.WeakKeyDictionary()
        )
        # ensure_schema를 한 번이라도 성공한 DSN 시그니처 집합.
        # 새 이벤트 루프(APScheduler asyncio.run)에서도 중복 DDL을 방지한다.
        self._initialized_sigs: set[str] = set()

    async def _dispose_all_registered(self) -> None:
        engines = [eng for (eng, _) in self._engines.values()]
        self._engines.clear()
        self._initialized_sigs.clear()
        for eng in engines:
            await eng.dispose()

    async def get_engine(self) -> AsyncEngine:
        loop = asyncio.get_running_loop()
        mgr = get_youtube_settings_manager()
        cfg = mgr.get_database()
        sig = _dsn_signature(cfg)

        entry = self._engines.get(loop)
        if entry is not None:
            engine, stored_sig = entry
            if stored_sig == sig:
                return engine
            await engine.dispose()
            del self._engines[loop]

        dsn = _build_async_dsn(cfg)
        ssl_arg = _asyncpg_ssl(cfg.sslmode)
        _schema = _validated_pg_schema(cfg.schema, "youtube")
        connect_args: dict[str, Any] = {
            "server_settings": {"search_path": _schema},
            "ssl": ssl_arg if ssl_arg is not None else False,
        }

        engine = create_async_engine(
            dsn,
            pool_size=2,
            max_overflow=1,
            pool_timeout=30,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        weakref.finalize(loop, _sync_dispose_async_engine, engine)
        # 동일 DSN으로 다른 루프(APScheduler asyncio.run 등)에서 재진입 시
        # 이미 성공한 ensure_schema를 재실행하지 않는다.
        if sig not in self._initialized_sigs:
            await ensure_schema(engine)
            self._initialized_sigs.add(sig)
        self._engines[loop] = (engine, sig)
        return engine

    async def dispose_current_loop_engine(self) -> None:
        """현재 루프의 엔진을 dispose하고 캐시에서 제거.

        APScheduler는 asyncio.run()으로 잡마다 새 이벤트 루프를 생성한다.
        잡 완료 시 이 메서드를 호출해 PG 연결 슬롯을 즉시 반환해야
        "remaining connection slots are reserved for superuser" 오류를 막을 수 있다.
        """
        loop = asyncio.get_running_loop()
        if loop in self._engines:
            engine, _ = self._engines[loop]
            del self._engines[loop]
            await engine.dispose()

    async def recreate_engine(self) -> None:
        await self._dispose_all_registered()
        # settings cache는 다음 호출에서 다시 읽도록 무효화
        get_youtube_settings_manager().invalidate("database")

    async def apply_schema(self) -> None:
        """
        현재 루프의 엔진에 ensure_schema를 강제 재실행한다.
        엔진이 캐시되어 있으면 재사용하고, 없으면 신규 생성 후 ensure_schema를 한 번만 호출한다.
        _initialized_sigs에서 해당 시그니처를 제거해 get_engine() 경로에서도 재실행되도록 한다.
        """
        loop = asyncio.get_running_loop()
        cfg = get_youtube_settings_manager().get_database()
        sig = _dsn_signature(cfg)

        # 강제 재적용이므로 초기화 기록을 먼저 제거한다.
        self._initialized_sigs.discard(sig)

        entry = self._engines.get(loop)
        if entry is not None and entry[1] == sig:
            await ensure_schema(entry[0])
            self._initialized_sigs.add(sig)
        else:
            # 신규 생성: get_engine()이 내부적으로 ensure_schema를 호출한다.
            await self.get_engine()

    async def test_connection_only(self) -> EngineHealth:
        """
        순수 연결 확인 전용. 스키마 생성을 실행하지 않는다.
        UI의 '연결 테스트' 버튼에 사용한다.
        """
        import time

        mgr = get_youtube_settings_manager()
        cfg = mgr.get_database()
        if not cfg.is_configured:
            return EngineHealth(ok=False, message="DB 설정이 없습니다. 호스트·사용자·DB 이름을 먼저 입력하세요.")
        try:
            dsn = _build_async_dsn(cfg)
            ssl_arg = _asyncpg_ssl(cfg.sslmode)
            connect_args: dict[str, Any] = {
                "server_settings": {"search_path": _validated_pg_schema(cfg.schema, "youtube")},
                "ssl": ssl_arg if ssl_arg is not None else False,
            }
            tmp_engine = create_async_engine(
                dsn,
                pool_size=1,
                max_overflow=0,
                pool_pre_ping=False,
                connect_args=connect_args,
            )
            try:
                start = time.perf_counter()
                async with tmp_engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                elapsed = (time.perf_counter() - start) * 1000.0
                return EngineHealth(ok=True, latency_ms=elapsed, message="연결 성공")
            finally:
                await tmp_engine.dispose()
        except Exception as e:
            return EngineHealth(ok=False, message=str(e))

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

