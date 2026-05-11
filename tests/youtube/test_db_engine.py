import pytest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import text

from app.services.youtube.db_engine import ensure_schema


@pytest.mark.asyncio
async def test_ensure_schema_executes_sql_and_records_migration(monkeypatch, tmp_path):
    # migrations 경로를 테스트용으로 우회하기 위해 _migrations_dir를 monkeypatch
    init_sql = "CREATE SCHEMA IF NOT EXISTS youtube; SELECT 1;"
    mig_dir = tmp_path / "migrations" / "youtube"
    mig_dir.mkdir(parents=True)
    (mig_dir / "001_init_schema.sql").write_text(init_sql, encoding="utf-8")

    import app.services.youtube.db_engine as mod

    monkeypatch.setattr(mod, "_migrations_dir", lambda: mig_dir)

    # AsyncEngine.begin() -> async context manager mock
    conn = AsyncMock()
    begin_cm = AsyncMock()
    begin_cm.__aenter__.return_value = conn
    begin_cm.__aexit__.return_value = False

    engine = MagicMock()
    engine.begin.return_value = begin_cm

    await ensure_schema(engine)

    # 1) init schema 실행 (TextClause 인스턴스는 매번 새로 생성되므로 text 비교)
    assert any(
        getattr(call.args[0], "text", None) == init_sql for call in conn.execute.call_args_list
    )
    # 2) schema_migrations 기록
    assert any(
        "INSERT INTO youtube.schema_migrations" in str(call.args[0])
        for call in conn.execute.call_args_list
    )

