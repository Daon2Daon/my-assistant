"""SettingsManager: Fernet, 캐시, 카테고리별 조회 테스트."""

from cryptography.fernet import Fernet
from sqlalchemy.orm import sessionmaker

from app.models.youtube_setting import YoutubeSetting
from app.services.youtube.settings_manager import (
    SettingsManager,
    YoutubeSettingsSecretError,
    mask_secret,
)


def _make_manager(db_session, fernet_key: str | None) -> SettingsManager:
    """SettingsManager는 조회 후 세션을 닫으므로, 매번 새 세션을 만드는 팩토리를 사용한다."""
    engine = db_session.get_bind()
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SettingsManager(session_factory=factory, fernet_key=fernet_key, cache_ttl_sec=60.0)


def test_mask_secret():
    assert mask_secret("abcd", keep_last=2) == "**cd"
    assert mask_secret("abcdefgh", keep_last=4) == "****efgh"
    assert mask_secret("x", keep_last=4) == "x"
    assert mask_secret("") == ""


def test_fernet_secret_roundtrip(db_session):
    key = Fernet.generate_key().decode("utf-8")
    f = Fernet(key.encode("utf-8"))
    secret = "litellm-secret-key"
    enc = f.encrypt(secret.encode("utf-8"))

    db_session.add(
        YoutubeSetting(
            category="ai_gateway",
            key="api_key",
            value=None,
            value_enc=enc,
            value_type="string",
            is_secret=1,
            description="test",
        )
    )
    db_session.commit()

    mgr = _make_manager(db_session, key)
    cfg = mgr.get_ai_gateway()
    assert cfg.api_key == secret


def test_read_secret_without_fernet_raises(db_session):
    key = Fernet.generate_key().decode("utf-8")
    enc = Fernet(key.encode("utf-8")).encrypt(b"secret")
    db_session.add(
        YoutubeSetting(
            category="ai_gateway",
            key="api_key",
            value=None,
            value_enc=enc,
            value_type="string",
            is_secret=1,
        )
    )
    db_session.commit()

    mgr = _make_manager(db_session, "")
    try:
        mgr.get_ai_gateway()
        assert False, "expected YoutubeSettingsSecretError"
    except YoutubeSettingsSecretError:
        pass


def test_cache_returns_same_instance_until_invalidate(db_session):
    key = Fernet.generate_key().decode("utf-8")
    db_session.add(
        YoutubeSetting(
            category="database",
            key="host",
            value="192.168.1.1",
            value_type="string",
            is_secret=0,
        )
    )
    db_session.commit()

    mgr = _make_manager(db_session, key)
    a = mgr.get_database()
    b = mgr.get_database()
    assert a is b
    assert a.host == "192.168.1.1"

    row = db_session.query(YoutubeSetting).filter_by(category="database", key="host").one()
    row.value = "10.0.0.1"
    db_session.commit()

    c = mgr.get_database()
    assert c.host == "192.168.1.1"

    mgr.invalidate("database")
    d = mgr.get_database()
    assert d.host == "10.0.0.1"


def test_invalidate_all_clears_cache(db_session):
    key = Fernet.generate_key().decode("utf-8")
    db_session.add(
        YoutubeSetting(
            category="database",
            key="host",
            value="h1",
            value_type="string",
            is_secret=0,
        )
    )
    db_session.commit()
    mgr = _make_manager(db_session, key)
    mgr.get_database()
    mgr.invalidate(None)
    row = db_session.query(YoutubeSetting).filter_by(category="database", key="host").one()
    row.value = "h2"
    db_session.commit()
    assert mgr.get_database().host == "h2"


def test_category_typed_values(db_session):
    key = Fernet.generate_key().decode("utf-8")
    rows = [
        YoutubeSetting(
            category="polling",
            key="master_interval_min",
            value="15",
            value_type="int",
            is_secret=0,
        ),
        YoutubeSetting(
            category="polling",
            key="youtube_daily_quota",
            value="5000",
            value_type="int",
            is_secret=0,
        ),
        YoutubeSetting(
            category="ai_gateway",
            key="temperature",
            value="0.7",
            value_type="float",
            is_secret=0,
        ),
        YoutubeSetting(
            category="notification",
            key="telegram_enabled",
            value="false",
            value_type="bool",
            is_secret=0,
        ),
    ]
    for r in rows:
        db_session.add(r)
    db_session.commit()

    mgr = _make_manager(db_session, key)
    p = mgr.get_polling()
    assert p.master_interval_min == 15
    assert p.youtube_daily_quota == 5000
    assert mgr.get_ai_gateway().temperature == 0.7
    assert mgr.get_notification().telegram_enabled is False


def test_database_settings_is_configured_and_signature(db_session):
    key = Fernet.generate_key().decode("utf-8")
    for c, k, v in [
        ("database", "host", "db.example.com"),
        ("database", "port", "5432"),
        ("database", "dbname", "yt"),
        ("database", "username", "u"),
        ("database", "password", "secret-db-pass"),
        ("database", "schema", "youtube"),
        ("database", "sslmode", "require"),
    ]:
        is_sec = 1 if k == "password" else 0
        if is_sec:
            enc = Fernet(key.encode("utf-8")).encrypt(v.encode("utf-8"))
            db_session.add(
                YoutubeSetting(
                    category=c,
                    key=k,
                    value=None,
                    value_enc=enc,
                    value_type="string",
                    is_secret=1,
                )
            )
        else:
            db_session.add(
                YoutubeSetting(
                    category=c,
                    key=k,
                    value=v,
                    value_type="int" if k == "port" else "string",
                    is_secret=0,
                )
            )
    db_session.commit()

    mgr = _make_manager(db_session, key)
    d = mgr.get_database()
    assert d.is_configured is True
    assert d.password == "secret-db-pass"
    assert d.signature().split(":") == [
        "db.example.com",
        "5432",
        "yt",
        "u",
        "youtube",
        "require",
    ]
