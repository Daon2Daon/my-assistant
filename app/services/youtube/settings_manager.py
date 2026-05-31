"""
YouTube 모듈 런타임 설정 로더 (SQLite youtube_settings)
Fernet으로 is_secret 필드 복호화, 카테고리별 60초 TTL 메모리 캐시.
"""

from __future__ import annotations

import json
import time
import json as _json
from dataclasses import dataclass, field, replace
from typing import Any, Callable, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.models.youtube_setting import YoutubeSetting


class YoutubeSettingsSecretError(RuntimeError):
    """비밀 필드 복호화에 실패했거나 Fernet 키가 없을 때."""


def _fernet_from_key(key: str | None) -> Fernet | None:
    if not (key and key.strip()):
        return None
    try:
        return Fernet(key.strip().encode("utf-8"))
    except Exception as e:
        raise YoutubeSettingsSecretError(f"YOUTUBE_SETTINGS_FERNET_KEY가 유효하지 않습니다: {e}") from e


def mask_secret(plain: str, keep_last: int = 4) -> str:
    """API 응답용 마스킹 (마지막 keep_last 자만 표시)."""
    if not plain:
        return ""
    if len(plain) <= keep_last:
        return plain
    return "*" * (len(plain) - keep_last) + plain[-keep_last:]


def _raw_row_value(row: YoutubeSetting, fernet: Fernet | None) -> str:
    if int(row.is_secret or 0):
        blob = row.value_enc
        if not blob:
            return ""
        if fernet is None:
            raise YoutubeSettingsSecretError(
                "비밀 설정을 읽으려면 YOUTUBE_SETTINGS_FERNET_KEY가 필요합니다."
            )
        try:
            return fernet.decrypt(blob).decode("utf-8")
        except InvalidToken as e:
            raise YoutubeSettingsSecretError("암호화된 설정 복호화에 실패했습니다.") from e
    return row.value if row.value is not None else ""


def _coerce_value(raw: str, value_type: str | None) -> Any:
    vt = (value_type or "string").lower()
    if vt == "string":
        return raw
    if vt == "int":
        return int(raw) if raw not in ("", None) else 0
    if vt == "float":
        return float(raw) if raw not in ("", None) else 0.0
    if vt == "bool":
        return str(raw).lower() in ("1", "true", "yes", "on")
    if vt == "json":
        return json.loads(raw) if raw else None
    return raw


def _row_typed(row: YoutubeSetting | None, fernet: Fernet | None) -> Any:
    if row is None:
        return None
    raw = _raw_row_value(row, fernet)
    return _coerce_value(raw, row.value_type)


def _normalize_postgres_schema_name_for_youtube_app(raw: str | None) -> str:
    """
    UI/SQLite에 저장된 PG 스키마명을 런타임에 맞게 정리한다.

    이 앱의 PostgreSQL 마이그레이션(`migrations/youtube/*.sql`)은 객체를 `youtube` 스키마에
    만든다. PostgreSQL 기본 스키마 이름인 `public`만 설정에 넣는 경우,
    `CREATE SCHEMA public` / search_path와 실제 테이블 위치가 엇갈리고,
    앱 DB 역할에 CREATE 권한이 없으면 마이그레이션이 반복 실패한다.
    """
    s = (raw or "youtube").strip()
    if s.lower() == "public":
        return "youtube"
    return s


@dataclass
class DatabaseSettings:
    host: str = ""
    port: int = 5432
    dbname: str = "youtube_monitor"
    username: str = ""
    password: str = ""
    schema: str = "youtube"
    sslmode: str = "prefer"

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.username and self.dbname)

    def signature(self) -> str:
        """DSN 변경 감지용 (비밀번호 제외)."""
        return f"{self.host}:{self.port}:{self.dbname}:{self.username}:{self.schema}:{self.sslmode}"

    @classmethod
    def from_rows(cls, rows: list[YoutubeSetting], fernet: Fernet | None) -> DatabaseSettings:
        by_key = {r.key: r for r in rows}
        return cls(
            host=str(_row_typed(by_key.get("host"), fernet) or ""),
            port=int(_row_typed(by_key.get("port"), fernet) or 5432),
            dbname=str(_row_typed(by_key.get("dbname"), fernet) or "youtube_monitor"),
            username=str(_row_typed(by_key.get("username"), fernet) or ""),
            password=str(_row_typed(by_key.get("password"), fernet) or ""),
            schema=_normalize_postgres_schema_name_for_youtube_app(
                str(_row_typed(by_key.get("schema"), fernet) or "youtube")
            ),
            sslmode=str(_row_typed(by_key.get("sslmode"), fernet) or "prefer"),
        )


@dataclass
class AIGatewaySettings:
    base_url: str = "http://litellm:4000"
    api_key: str = ""
    primary_model: str = "gemini/gemini-2.5-flash"
    fallback_model: str = "gemini/gemini-2.5-flash"
    tagging_model: str = "gemini/gemini-2.5-flash"
    # 주간 리뷰 합성 전용 모델 (/v1/chat/completions 경로).
    # 비어 있으면 fallback_model → tagging_model 순으로 대체 시도.
    # 기존 영상 분석(Path A)과 달리 OpenAI 호환 엔드포인트를 사용하므로,
    # 게이트웨이에 등록된 chat completions 지원 모델명을 지정해야 한다.
    digest_model: str = ""
    temperature: float = 0.3
    max_tokens: int = 8192
    daily_budget_usd: float = 2.0

    @classmethod
    def from_rows(cls, rows: list[YoutubeSetting], fernet: Fernet | None) -> AIGatewaySettings:
        by_key = {r.key: r for r in rows}
        return cls(
            base_url=str(_row_typed(by_key.get("base_url"), fernet) or "http://litellm:4000"),
            api_key=str(_row_typed(by_key.get("api_key"), fernet) or ""),
            primary_model=str(
                _row_typed(by_key.get("primary_model"), fernet) or "gemini/gemini-2.5-flash"
            ),
            fallback_model=str(
                _row_typed(by_key.get("fallback_model"), fernet) or "gemini/gemini-2.5-flash"
            ),
            tagging_model=str(
                _row_typed(by_key.get("tagging_model"), fernet) or "gemini/gemini-2.5-flash"
            ),
            digest_model=str(_row_typed(by_key.get("digest_model"), fernet) or ""),
            temperature=float(_row_typed(by_key.get("temperature"), fernet) or 0.3),
            max_tokens=int(_row_typed(by_key.get("max_tokens"), fernet) or 8192),
            daily_budget_usd=float(_row_typed(by_key.get("daily_budget_usd"), fernet) or 2.0),
        )


@dataclass
class PromptSettings:
    # 영상 분석 프롬프트 (경로 A·B 공통, 단일). 비어 있으면 analyzer 코드 기본값 사용.
    analysis_prompt: str = ""
    # 주간 리뷰 합성 프롬프트. 비어 있으면 digest_service.DEFAULT_DIGEST_PROMPT 사용.
    digest_prompt: str = ""

    @classmethod
    def from_rows(cls, rows: list[YoutubeSetting], fernet: Fernet | None) -> "PromptSettings":
        by_key = {r.key: r for r in rows}
        # 하위호환: analysis_prompt 없으면 기존 primary_prompt 를 승계.
        analysis = str(_row_typed(by_key.get("analysis_prompt"), fernet) or "")
        if not analysis:
            analysis = str(_row_typed(by_key.get("primary_prompt"), fernet) or "")
        return cls(
            analysis_prompt=analysis,
            digest_prompt=str(_row_typed(by_key.get("digest_prompt"), fernet) or ""),
        )


@dataclass
class PollingSettings:
    master_interval_min: int = 12
    # 미분석(pending) 영상을 DB에서 집어 AI 분석하는 스케줄 잡 주기(분). 미설정 시 master_interval_min과 동일하게 취급.
    pending_analysis_interval_min: int = 12
    default_channel_interval_min: int = 720
    youtube_api_key: str = ""
    youtube_daily_quota: int = 10000
    window_hours: int = 24
    max_concurrent_channels: int = 5
    max_concurrent_analyses: int = 3
    # Gemini 무료 티어 등 분당 호출 제한 대응: 영상 분석 사이 대기 시간(초)
    analysis_interval_sec: int = 120

    @classmethod
    def from_rows(cls, rows: list[YoutubeSetting], fernet: Fernet | None) -> PollingSettings:
        by_key = {r.key: r for r in rows}
        master_interval_min = int(_row_typed(by_key.get("master_interval_min"), fernet) or 12)
        raw_pending = _row_typed(by_key.get("pending_analysis_interval_min"), fernet)
        if raw_pending in (None, ""):
            pending_analysis_interval_min = master_interval_min
        else:
            pending_analysis_interval_min = int(raw_pending)
            if pending_analysis_interval_min < 1:
                pending_analysis_interval_min = master_interval_min
            elif pending_analysis_interval_min > 10080:
                pending_analysis_interval_min = 10080
        return cls(
            master_interval_min=master_interval_min,
            pending_analysis_interval_min=pending_analysis_interval_min,
            default_channel_interval_min=int(
                _row_typed(by_key.get("default_channel_interval_min"), fernet) or 720
            ),
            youtube_api_key=str(_row_typed(by_key.get("youtube_api_key"), fernet) or ""),
            youtube_daily_quota=int(_row_typed(by_key.get("youtube_daily_quota"), fernet) or 10000),
            window_hours=int(_row_typed(by_key.get("window_hours"), fernet) or 24),
            max_concurrent_channels=int(
                _row_typed(by_key.get("max_concurrent_channels"), fernet) or 5
            ),
            max_concurrent_analyses=int(
                _row_typed(by_key.get("max_concurrent_analyses"), fernet) or 3
            ),
            analysis_interval_sec=int(
                _row_typed(by_key.get("analysis_interval_sec"), fernet) or 120
            ),
        )


def is_quiet_hours_now(enabled: bool, start_str: str, end_str: str) -> bool:
    """현재 KST 시각이 알림 제한 시간대인지 확인.

    자정 경계를 넘는 구간(예: 22:00 ~ 08:00)도 올바르게 처리한다.
    enabled=False 이면 항상 False 반환.
    """
    if not enabled:
        return False
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt

        now_kst = _dt.now(ZoneInfo("Asia/Seoul"))
        now_min = now_kst.hour * 60 + now_kst.minute

        def _parse(t: str) -> int:
            h, m = t.split(":")
            return int(h) * 60 + int(m)

        start_min = _parse(start_str)
        end_min = _parse(end_str)

        if start_min <= end_min:
            # 같은 날 안에서 (예: 09:00 ~ 22:00)
            return start_min <= now_min < end_min
        else:
            # 자정 경계를 넘는 구간 (예: 22:00 ~ 08:00)
            return now_min >= start_min or now_min < end_min
    except Exception:
        return False


@dataclass
class NotificationSettings:
    telegram_enabled: bool = True
    # 발송 모드: "immediate" (분석 직후 즉시) | "scheduled" (등록된 일정에 일괄)
    send_mode: str = "immediate"
    # 예약 발송 시각 목록 — "HH:MM" 형식 (24h), 최대 10개
    scheduled_times: List[str] = field(default_factory=list)
    # 예약발송 Cron 한 회 실행당 최대 발송 건수 (잔여는 다음 회차)
    scheduled_max_per_run: int = 5
    wait_between_messages_sec: int = 30
    low_confidence_threshold: float = 0.5
    # 알림 제한 시간 (Quiet Hours) — immediate 모드에서만 적용
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "22:00"  # KST HH:MM, 제한 시작
    quiet_hours_end: str = "08:00"    # KST HH:MM, 제한 종료 & 플러시 잡 실행 시각

    @classmethod
    def from_rows(cls, rows: list[YoutubeSetting], fernet: Fernet | None) -> NotificationSettings:
        by_key = {r.key: r for r in rows}
        te_row = by_key.get("telegram_enabled")
        if te_row is None:
            telegram_enabled = True
        else:
            telegram_enabled = bool(_row_typed(te_row, fernet))

        raw_times = _row_typed(by_key.get("scheduled_times"), fernet)
        if isinstance(raw_times, list):
            scheduled_times = [str(t) for t in raw_times]
        elif isinstance(raw_times, str):
            try:
                parsed = _json.loads(raw_times)
                scheduled_times = [str(t) for t in parsed] if isinstance(parsed, list) else []
            except Exception:
                scheduled_times = []
        else:
            scheduled_times = []

        raw_cap = _row_typed(by_key.get("scheduled_max_per_run"), fernet)
        if raw_cap in (None, ""):
            scheduled_max_per_run = 5
        else:
            scheduled_max_per_run = int(raw_cap)
            if scheduled_max_per_run < 1:
                scheduled_max_per_run = 1
            elif scheduled_max_per_run > 50:
                scheduled_max_per_run = 50

        qh_enabled_row = by_key.get("quiet_hours_enabled")
        if qh_enabled_row is None:
            quiet_hours_enabled = False
        else:
            raw_qh = _row_typed(qh_enabled_row, fernet)
            # "True"/"False" 문자열 또는 실제 bool 모두 처리
            quiet_hours_enabled = str(raw_qh).lower() in ("1", "true", "yes", "on")

        return cls(
            telegram_enabled=telegram_enabled,
            send_mode=str(_row_typed(by_key.get("send_mode"), fernet) or "immediate"),
            scheduled_times=scheduled_times,
            scheduled_max_per_run=scheduled_max_per_run,
            wait_between_messages_sec=int(
                _row_typed(by_key.get("wait_between_messages_sec"), fernet) or 30
            ),
            low_confidence_threshold=float(
                _row_typed(by_key.get("low_confidence_threshold"), fernet) or 0.5
            ),
            quiet_hours_enabled=quiet_hours_enabled,
            quiet_hours_start=str(
                _row_typed(by_key.get("quiet_hours_start"), fernet) or "22:00"
            ),
            quiet_hours_end=str(
                _row_typed(by_key.get("quiet_hours_end"), fernet) or "08:00"
            ),
        )


@dataclass
class DigestSettings:
    """주간 리뷰(Weekly Digest) 설정."""

    enabled: bool = False
    # 리뷰 기간(주). 1~8로 보정.
    period_weeks: int = 1
    # 예약 발송 일정: [{"day_of_week": "sun", "time": "20:00"}, ...]
    schedule_times: List[dict] = field(default_factory=list)
    telegram_enabled: bool = True
    # 대상 필터 (타입 간 AND, 타입 내 OR). 각각 None/빈 리스트 = 제한 없음(전체).
    categories: Optional[List[str]] = None
    channel_pks: Optional[List[int]] = None
    tags: Optional[List[str]] = None

    @classmethod
    def from_rows(cls, rows: list[YoutubeSetting], fernet: Fernet | None) -> "DigestSettings":
        by_key = {r.key: r for r in rows}

        enabled_row = by_key.get("enabled")
        enabled = (
            str(_row_typed(enabled_row, fernet)).lower() in ("1", "true", "yes", "on")
            if enabled_row is not None
            else False
        )

        raw_weeks = _row_typed(by_key.get("period_weeks"), fernet)
        period_weeks = int(raw_weeks) if raw_weeks not in (None, "") else 1
        if period_weeks < 1:
            period_weeks = 1
        elif period_weeks > 8:
            period_weeks = 8

        raw_times = _row_typed(by_key.get("schedule_times"), fernet)
        if isinstance(raw_times, list):
            schedule_times = [t for t in raw_times if isinstance(t, dict)]
        elif isinstance(raw_times, str):
            try:
                parsed = _json.loads(raw_times)
                schedule_times = [t for t in parsed if isinstance(t, dict)] if isinstance(parsed, list) else []
            except Exception:
                schedule_times = []
        else:
            schedule_times = []

        te_row = by_key.get("telegram_enabled")
        telegram_enabled = (
            bool(_row_typed(te_row, fernet)) if te_row is not None else True
        )

        def _as_list(raw: Any) -> Optional[list]:
            """JSON 리스트(또는 리스트 문자열)를 list로. 비거나 파싱 실패 시 None."""
            val = raw
            if isinstance(val, str):
                if not val.strip():
                    return None
                try:
                    val = _json.loads(val)
                except Exception:
                    return None
            return val if isinstance(val, list) else None

        cats_list = _as_list(_row_typed(by_key.get("categories"), fernet))
        categories: Optional[List[str]] = None
        if cats_list is not None:
            cleaned = [str(c) for c in cats_list if str(c).strip()]
            categories = cleaned or None

        chan_list = _as_list(_row_typed(by_key.get("channel_pks"), fernet))
        channel_pks: Optional[List[int]] = None
        if chan_list is not None:
            ints: List[int] = []
            for c in chan_list:
                try:
                    ints.append(int(c))
                except (TypeError, ValueError):
                    continue
            channel_pks = ints or None

        tags_list = _as_list(_row_typed(by_key.get("tags"), fernet))
        tags: Optional[List[str]] = None
        if tags_list is not None:
            cleaned_tags = [str(t) for t in tags_list if str(t).strip()]
            tags = cleaned_tags or None

        return cls(
            enabled=enabled,
            period_weeks=period_weeks,
            schedule_times=schedule_times,
            telegram_enabled=telegram_enabled,
            categories=categories,
            channel_pks=channel_pks,
            tags=tags,
        )


class SettingsManager:
    """카테고리별 설정 조회 + TTL 캐시."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        fernet_key: str | None = None,
        cache_ttl_sec: float = 60.0,
    ):
        self._session_factory = session_factory
        self._cache_ttl = cache_ttl_sec
        self._cache: dict[str, tuple[Any, float]] = {}
        resolved_key = (
            app_settings.YOUTUBE_SETTINGS_FERNET_KEY if fernet_key is None else fernet_key
        )
        self._fernet = _fernet_from_key(resolved_key)

    def invalidate(self, category: str | None = None) -> None:
        if category is None:
            self._cache.clear()
        else:
            self._cache.pop(category, None)

    def _get_cached(self, category: str, loader: Callable[[], Any]) -> Any:
        now = time.monotonic()
        hit = self._cache.get(category)
        if hit is not None:
            val, exp = hit
            if now < exp:
                return val
        val = loader()
        self._cache[category] = (val, now + self._cache_ttl)
        return val

    def _fetch_category(self, category: str) -> list[YoutubeSetting]:
        db = self._session_factory()
        try:
            return db.query(YoutubeSetting).filter(YoutubeSetting.category == category).all()
        finally:
            db.close()

    def get_database(self) -> DatabaseSettings:
        def load() -> DatabaseSettings:
            rows = self._fetch_category("database")
            return DatabaseSettings.from_rows(rows, self._fernet)

        return self._get_cached("database", load)

    def get_ai_gateway(self) -> AIGatewaySettings:
        def load() -> AIGatewaySettings:
            rows = self._fetch_category("ai_gateway")
            cfg = AIGatewaySettings.from_rows(rows, self._fernet)
            # DB에 api_key가 없을 때만: 컨테이너 .env의 BOOTSTRAP 값으로 보완(시드 이후에 env만 채운 경우 등)
            env_key = (app_settings.YOUTUBE_BOOTSTRAP_LITELLM_API_KEY or "").strip()
            if env_key and not (cfg.api_key or "").strip():
                cfg = replace(cfg, api_key=env_key)
            return cfg

        return self._get_cached("ai_gateway", load)

    def get_polling(self) -> PollingSettings:
        def load() -> PollingSettings:
            rows = self._fetch_category("polling")
            return PollingSettings.from_rows(rows, self._fernet)

        return self._get_cached("polling", load)

    def get_prompts(self) -> PromptSettings:
        def load() -> PromptSettings:
            rows = self._fetch_category("prompts")
            return PromptSettings.from_rows(rows, self._fernet)

        return self._get_cached("prompts", load)

    def get_notification(self) -> NotificationSettings:
        def load() -> NotificationSettings:
            rows = self._fetch_category("notification")
            return NotificationSettings.from_rows(rows, self._fernet)

        return self._get_cached("notification", load)

    def get_digest(self) -> DigestSettings:
        def load() -> DigestSettings:
            rows = self._fetch_category("digest")
            return DigestSettings.from_rows(rows, self._fernet)

        return self._get_cached("digest", load)


_manager_singleton: SettingsManager | None = None


def get_youtube_settings_manager() -> SettingsManager:
    """앱 기본 SessionLocal + config Fernet 키로 매니저 반환 (싱글톤)."""
    global _manager_singleton
    if _manager_singleton is None:
        from app.database import SessionLocal

        _manager_singleton = SettingsManager(
            session_factory=SessionLocal, fernet_key=None, cache_ttl_sec=60.0
        )
    return _manager_singleton
