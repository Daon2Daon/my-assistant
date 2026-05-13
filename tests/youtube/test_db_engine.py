import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.youtube.db_engine import (
    _is_comment_only_sql,
    _is_transaction_boundary_statement,
    _numbered_postgres_migrations,
    _split_postgres_sql_script,
    ensure_schema,
)


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


def test_numbered_postgres_migrations_skips_000(tmp_path):
    mig_dir = tmp_path / "migrations" / "youtube"
    mig_dir.mkdir(parents=True)
    (mig_dir / "000_seed.sql").write_text("-- sqlite", encoding="utf-8")
    (mig_dir / "001_init.sql").write_text("--", encoding="utf-8")
    (mig_dir / "002_next.sql").write_text("--", encoding="utf-8")
    got = _numbered_postgres_migrations(mig_dir)
    assert [v for v, _ in got] == [1, 2]


def test_is_comment_only_sql():
    assert _is_comment_only_sql("-- a\n-- b\n")
    assert not _is_comment_only_sql("-- a\nSELECT 1;\n")


def test_is_transaction_boundary_statement():
    assert _is_transaction_boundary_statement("BEGIN;")
    assert _is_transaction_boundary_statement("begin")
    assert _is_transaction_boundary_statement("COMMIT")
    assert not _is_transaction_boundary_statement("SELECT 1")


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

    # schema_migrations 버전 조회용 connect()
    connect_conn = AsyncMock()
    applied_rows = MagicMock()
    applied_rows.fetchall.return_value = [(1,)]
    connect_conn.execute = AsyncMock(return_value=applied_rows)
    connect_cm = AsyncMock()
    connect_cm.__aenter__.return_value = connect_conn
    connect_cm.__aexit__.return_value = False

    engine = MagicMock()
    engine.begin.return_value = begin_cm
    engine.connect.return_value = connect_cm

    await ensure_schema(engine)

    # 1) init schema 실행
    assert any("CREATE SCHEMA IF NOT EXISTS youtube" in str(call.args[0]) for call in conn.execute.call_args_list)
    # 2) schema_migrations 기록
    assert any(
        "INSERT INTO youtube.schema_migrations" in str(call.args[0])
        for call in conn.execute.call_args_list
    )

