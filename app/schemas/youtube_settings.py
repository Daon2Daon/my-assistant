"""
YouTube 모듈 설정 Pydantic 스키마.

민감 필드(password, api_key 등)는 응답 시 마스킹,
업데이트 시 빈 문자열이면 기존 값 유지.
"""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ── 데이터베이스 설정 ──────────────────────────────────────────────────────────

class DatabaseSettingsResponse(BaseModel):
    host: str
    port: int
    dbname: str
    username: str
    password_masked: str = Field(description="마지막 4자만 노출, 나머지 *** 처리")
    schema_name: str
    sslmode: str
    is_configured: bool


class DatabaseSettingsUpdate(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    dbname: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = Field(None, description="빈 문자열이면 기존 값 유지")
    schema_name: Optional[str] = None
    sslmode: Optional[str] = None


class ConnectionTestResponse(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[int] = None


class SchemaApplyResponse(BaseModel):
    success: bool
    message: str
    migration_version: Optional[str] = None


class DBHealthResponse(BaseModel):
    healthy: bool
    message: str
    latency_ms: Optional[int] = None


# ── AI Gateway 설정 ───────────────────────────────────────────────────────────

class AIGatewaySettingsResponse(BaseModel):
    base_url: str
    api_key_masked: str = Field(description="마지막 4자만 노출")
    primary_model: str
    fallback_model: str
    tagging_model: str
    temperature: float
    max_tokens: int
    daily_budget_usd: float


class AIGatewaySettingsUpdate(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = Field(None, description="빈 문자열이면 기존 값 유지")
    primary_model: Optional[str] = None
    fallback_model: Optional[str] = None
    tagging_model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=256)
    daily_budget_usd: Optional[float] = Field(None, ge=0.0)


class ModelInfo(BaseModel):
    model_id: str
    provider: Optional[str] = None


class ModelsResponse(BaseModel):
    models: List[ModelInfo]


class AIGatewayTestRequest(BaseModel):
    """
    연결 테스트/분석 테스트 시 저장하지 않고 폼 현재 값을 직접 넘길 때 사용.
    제공된 필드는 DB 저장값보다 우선 적용된다.
    """

    base_url: Optional[str] = None
    api_key: Optional[str] = Field(None, description="빈 문자열이면 DB 저장값 사용")
    primary_model: Optional[str] = None


class GatewayTestAnalyzeResponse(BaseModel):
    success: bool
    message: str
    model_used: Optional[str] = None
    latency_ms: Optional[int] = None


# ── 런타임 설정 (polling + notification 통합) ─────────────────────────────────

class RuntimeSettingsResponse(BaseModel):
    # polling
    master_interval_min: int
    pending_analysis_interval_min: int = Field(
        ge=1,
        le=10080,
        description="DB에 pending으로 쌓인 영상을 배치 분석하는 스케줄 잡 주기(분). 실행당 1건 처리.",
    )
    default_channel_interval_min: int
    youtube_api_key_masked: str
    youtube_daily_quota: int
    window_hours: int
    max_concurrent_channels: int
    max_concurrent_analyses: int
    analysis_interval_sec: int = Field(
        description="영상 간 AI 분석 대기 시간(초). 0이면 병렬 처리. Gemini 무료 티어 등 API 호출 제한 대응에 사용."
    )
    # notification
    telegram_enabled: bool
    wait_between_messages_sec: int
    low_confidence_threshold: float


# ── 프롬프트 설정 ─────────────────────────────────────────────────────────────

class PromptSettingsResponse(BaseModel):
    primary_prompt: str = Field(description="경로 A (Gemini native) 기본 프롬프트")
    fallback_prompt: str = Field(description="경로 B (OpenAI 호환) 폴백 프롬프트")
    prompt_version: str


class PromptSettingsUpdate(BaseModel):
    primary_prompt: Optional[str] = None
    fallback_prompt: Optional[str] = None


# ── 런타임 설정 (polling + notification 통합) ─────────────────────────────────

class RuntimeSettingsUpdate(BaseModel):
    # polling
    master_interval_min: Optional[int] = Field(None, ge=1, le=10080)
    pending_analysis_interval_min: Optional[int] = Field(None, ge=1, le=10080)
    default_channel_interval_min: Optional[int] = Field(None, ge=10)
    youtube_api_key: Optional[str] = Field(None, description="빈 문자열이면 기존 값 유지")
    youtube_daily_quota: Optional[int] = Field(None, ge=100)
    window_hours: Optional[int] = Field(None, ge=1)
    max_concurrent_channels: Optional[int] = Field(None, ge=1, le=20)
    max_concurrent_analyses: Optional[int] = Field(None, ge=1, le=20)
    analysis_interval_sec: Optional[int] = Field(
        None, ge=0, description="영상 간 AI 분석 대기 시간(초). 0이면 병렬 처리."
    )
    # notification
    telegram_enabled: Optional[bool] = None
    wait_between_messages_sec: Optional[int] = Field(None, ge=0)
    low_confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)


_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


# ── 알림 발송 설정 ─────────────────────────────────────────────────────────────

class NotificationSettingsResponse(BaseModel):
    telegram_enabled: bool
    send_mode: str = Field(description="'immediate' | 'scheduled'")
    scheduled_times: List[str] = Field(description="예약 발송 시각 목록 (HH:MM 24h, 최대 10개)")
    scheduled_max_per_run: int = Field(
        ge=1,
        le=50,
        description="예약발송 스케줄 한 번 실행당 최대 발송 건수. 잔여는 다음 회차에 순차 발송.",
    )
    wait_between_messages_sec: int = Field(description="발송 건 간 대기 시간 (초)")
    low_confidence_threshold: float = Field(description="저신뢰도 배지 임계값 (0.0 ~ 1.0)")


class NotificationSettingsUpdate(BaseModel):
    telegram_enabled: Optional[bool] = None
    send_mode: Optional[str] = Field(None, pattern="^(immediate|scheduled)$")
    scheduled_times: Optional[List[str]] = Field(None, max_length=10)
    scheduled_max_per_run: Optional[int] = Field(None, ge=1, le=50)
    wait_between_messages_sec: Optional[int] = Field(None, ge=0, le=600)
    low_confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)

    @field_validator("scheduled_times")
    @classmethod
    def validate_times(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        for t in v:
            if not _TIME_RE.match(t):
                raise ValueError(f"시각 형식이 올바르지 않습니다 (HH:MM): {t!r}")
        return v
