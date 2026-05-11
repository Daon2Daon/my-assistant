"""
YouTube 모듈 설정 Pydantic 스키마.

민감 필드(password, api_key 등)는 응답 시 마스킹,
업데이트 시 빈 문자열이면 기존 값 유지.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


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


class GatewayTestAnalyzeResponse(BaseModel):
    success: bool
    message: str
    model_used: Optional[str] = None
    latency_ms: Optional[int] = None


# ── 런타임 설정 (polling + notification 통합) ─────────────────────────────────

class RuntimeSettingsResponse(BaseModel):
    # polling
    master_interval_min: int
    default_channel_interval_min: int
    youtube_api_key_masked: str
    youtube_daily_quota: int
    window_hours: int
    max_concurrent_channels: int
    max_concurrent_analyses: int
    # notification
    telegram_enabled: bool
    wait_between_messages_sec: int
    low_confidence_threshold: float


class RuntimeSettingsUpdate(BaseModel):
    # polling
    master_interval_min: Optional[int] = Field(None, ge=1)
    default_channel_interval_min: Optional[int] = Field(None, ge=10)
    youtube_api_key: Optional[str] = Field(None, description="빈 문자열이면 기존 값 유지")
    youtube_daily_quota: Optional[int] = Field(None, ge=100)
    window_hours: Optional[int] = Field(None, ge=1)
    max_concurrent_channels: Optional[int] = Field(None, ge=1, le=20)
    max_concurrent_analyses: Optional[int] = Field(None, ge=1, le=20)
    # notification
    telegram_enabled: Optional[bool] = None
    wait_between_messages_sec: Optional[int] = Field(None, ge=0)
    low_confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
