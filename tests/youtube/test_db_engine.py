import pytest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import text

from app.services.youtube.db_engine import _split_postgres_sql_script, ensure_schema


def test_split_postgres_sql_script_dollar_quote_keeps_body():
    s = (
        "SELECT 1;"
        "CREATE FUNCTION f() RETURNS void AS $$ BEGIN x := 1; y := 2; END; $$ LANGUAGE plpgsql;"
        "SELECT 2;"
    )
    parts = _split_postgres_sql_script(s)
    assert len(parts) == 3
    assert parts[0].strip() == "SELECT 1"
    assert "BEGIN x := 1; y := 2; END;" in parts[1]
    assert parts[2].strip() == "SELECT 2"


def test_split_postgres_sql_script_single_quotes():
    s = "INSERT INTO t VALUES ('a;b'); SELECT 1;"
    parts = _split_postgres_sql_script(s)
    assert len(parts) == 2
    assert "a;b" in parts[0]


@pytest.mark.asyncio
async def test_ensure_schema_executes_sql_and_records_migration(monkeypatch, tmp_path):
    # migrations 경로를 테스트용으로 우회하기 위해 _migrations_dir를 monkeypatch
    init_sql = "CREATE SCHEMA IF NOT EXISTS youtube;"
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

