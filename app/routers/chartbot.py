"""
Chartbot API 라우터
종목 차트 정기 발송 관리 API
"""

import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, Optional, List

TZ = ZoneInfo("Asia/Seoul")


def _compute_next_chart_send_time(tickers: list) -> Optional[str]:
    """
    등록된 종목의 notification_time, notification_days를 기반으로
    실제 다음 차트 발송 예정 시각 계산
    """
    if not tickers:
        return None
    now = datetime.now(TZ)
    candidates = []
    for item in tickers:
        if not isinstance(item, dict):
            continue
        nt = item.get("notification_time", "09:00")
        nd = item.get("notification_days", [0, 1, 2, 3, 4])
        if not isinstance(nd, list):
            try:
                nd = [int(x.strip()) for x in str(nd).replace("[", "").replace("]", "").split(",") if x.strip().isdigit()]
            except (ValueError, TypeError):
                nd = []
        if not nd:
            continue
        try:
            h, m = map(int, nt.split(":"))
        except (ValueError, TypeError):
            continue
        for days_ahead in range(8):
            d = now.date() + timedelta(days=days_ahead)
            if d.weekday() not in nd:
                continue
            cand = datetime(d.year, d.month, d.day, h, m, 0, tzinfo=TZ)
            if cand > now:
                candidates.append(cand)
                break
    if not candidates:
        return None
    next_dt = min(candidates)
    return next_dt.isoformat()
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.crud import (
    get_or_create_user,
    get_setting_by_category,
    create_setting,
    update_setting,
    get_logs,
)
from app.services.bots.chart_bot import chart_bot
from app.services.bots.chart_analyzer import chart_analyzer, AiAnalysisConfig, DEFAULT_PROMPT
from app.services.bots.finance_bot import finance_bot
from app.services.scheduler import scheduler_service
from app.services.youtube.llm_client import get_litellm_client, LiteLLMError
from app.services.youtube.settings_manager import mask_secret


router = APIRouter(prefix="/api/chartbot", tags=["Chartbot"])


class ChartSymbolRequest(BaseModel):
    """차트 종목 등록 요청"""
    ticker: str
    market: str = "US"  # US / KR
    notification_time: str = "09:00"  # HH:MM 형식
    notification_days: List[int] = [0, 1, 2, 3, 4]  # 0=월~6=일 (Python weekday)


class AiAnalysisConfigRequest(BaseModel):
    """AI 기술분석 설정"""
    enabled: bool = False
    model: str = "gemini/gemini-2.5-flash"
    prompt: Optional[str] = None          # None이면 기본 프롬프트 유지
    include_weekly: bool = True
    max_output_tokens: int = 2000
    temperature: float = 0.4


class ChartbotConfigUpdateRequest(BaseModel):
    """Chartbot 설정 업데이트 요청"""
    notification_time: Optional[str] = None
    is_active: Optional[bool] = None
    tickers: Optional[List[dict]] = None
    ai_analysis: Optional[AiAnalysisConfigRequest] = None
    litellm_base_url: Optional[str] = None   # 차트봇 전용 LiteLLM Gateway URL
    litellm_api_key: Optional[str] = None    # 차트봇 전용 API Key (마스킹값이면 미저장)


class AnalyzePreviewRequest(BaseModel):
    """AI 기술분석 미리보기 요청 (텔레그램 미발송)"""
    ticker: str
    market: str = "US"
    daily_path: Optional[str] = None    # 클라이언트 캐시된 차트 경로 (있으면 재사용)
    weekly_path: Optional[str] = None


class TestChartsRequest(BaseModel):
    """테스트용 차트 생성 요청"""
    ticker: str
    market: str = "US"


@router.get("/status")
async def get_chartbot_status(db: Session = Depends(get_db)):
    """
    Chartbot 모듈 상태 조회
    활성화 상태, 알림 시간, 다음 실행 시간, 등록된 종목
    """
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "chartbot")

        if not setting:
            return JSONResponse(
                content={
                    "is_active": False,
                    "next_run_time": None,
                    "tickers": [],
                    "last_run_time": None,
                    "last_status": None,
                }
            )

        # config에서 tickers 파싱
        tickers = []
        if setting.config_json:
            try:
                config = json.loads(setting.config_json)
                tickers = config.get("tickers", [])
            except Exception:
                pass

        # 실제 다음 차트 발송 예정 시각 계산 (종목별 notification_time, notification_days 기반)
        next_run_time = _compute_next_chart_send_time(tickers)
        if not next_run_time:
            jobs = scheduler_service.get_all_jobs()
            chartbot_job = next(
                (job for job in jobs if job["id"] == "chartbot_dispatcher"), None
            )
            next_run_time = chartbot_job["next_run_time"] if chartbot_job else None

        # 마지막 로그
        logs = get_logs(db, category="chartbot", limit=1)
        last_log = logs[0] if logs else None

        # 기존 ticker에 notification_time, notification_days, name 없으면 기본값 추가
        name_updated = False
        for t in tickers:
            if isinstance(t, dict):
                if "notification_time" not in t:
                    t["notification_time"] = "09:00"
                if "notification_days" not in t:
                    t["notification_days"] = [0, 1, 2, 3, 4]
                if not t.get("name"):
                    try:
                        resolved = chart_bot._get_name(
                            t.get("ticker", ""), t.get("market", "US")
                        )
                        if resolved and resolved != t.get("ticker", ""):
                            t["name"] = resolved
                            name_updated = True
                        else:
                            t["name"] = ""
                    except Exception:
                        t["name"] = ""

        # 종목명이 새로 조회된 경우 DB에 반영
        if name_updated and setting and setting.config_json:
            try:
                save_config = json.loads(setting.config_json)
                save_config["tickers"] = tickers
                update_setting(db, setting.setting_id, config_json=json.dumps(save_config))
            except Exception:
                pass

        return JSONResponse(
            content={
                "is_active": setting.is_active,
                "next_run_time": next_run_time,
                "tickers": tickers,
                "last_run_time": (
                    last_log.created_at.isoformat() if last_log else None
                ),
                "last_status": last_log.status if last_log else None,
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _default_ai_analysis_dict() -> Dict[str, Any]:
    """ai_analysis 기본값 딕셔너리"""
    return {
        "enabled": False,
        "model": "gemini/gemini-2.5-flash",
        "prompt": DEFAULT_PROMPT,
        "include_weekly": True,
        "max_output_tokens": 2000,
        "temperature": 0.4,
    }


@router.get("/settings")
async def get_chartbot_settings(db: Session = Depends(get_db)):
    """Chartbot 설정 조회 (설정 페이지용) - ai_analysis 포함"""
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "chartbot")

        if not setting:
            return JSONResponse(
                content={
                    "category": "chartbot",
                    "notification_time": "09:00",
                    "is_active": False,
                    "config_json": json.dumps({"tickers": []}),
                    "ai_analysis": _default_ai_analysis_dict(),
                    "default_prompt": DEFAULT_PROMPT,
                    "litellm_base_url": "",
                    "litellm_api_key_masked": "",
                }
            )

        config = {}
        if setting.config_json:
            try:
                config = json.loads(setting.config_json)
            except Exception:
                pass

        # ai_analysis 없으면 기본값 제공 (기존 설정과 병합)
        ai_analysis = _default_ai_analysis_dict()
        ai_analysis.update(config.get("ai_analysis") or {})

        litellm_base_url = config.get("litellm_base_url", "")
        litellm_api_key_masked = mask_secret(config.get("litellm_api_key", ""))

        return JSONResponse(
            content={
                "category": "chartbot",
                "notification_time": setting.notification_time,
                "is_active": setting.is_active,
                "config_json": setting.config_json or "{}",
                "ai_analysis": ai_analysis,
                "default_prompt": DEFAULT_PROMPT,
                "litellm_base_url": litellm_base_url,
                "litellm_api_key_masked": litellm_api_key_masked,
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings")
async def update_chartbot_settings(
    request: ChartbotConfigUpdateRequest, db: Session = Depends(get_db)
):
    """Chartbot 설정 저장"""
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "chartbot")

        # 기존 config 로드
        existing_config: Dict[str, Any] = {}
        if setting and setting.config_json:
            try:
                existing_config = json.loads(setting.config_json)
            except Exception:
                pass

        config_changed = False

        if request.tickers is not None:
            existing_config["tickers"] = request.tickers
            config_changed = True

        if request.litellm_base_url is not None:
            existing_config["litellm_base_url"] = request.litellm_base_url.strip()
            config_changed = True

        if request.litellm_api_key is not None:
            # 마스킹된 값(*로 시작)이면 기존 키 유지, 새 값이면 저장
            if not request.litellm_api_key.startswith("*"):
                existing_config["litellm_api_key"] = request.litellm_api_key.strip()
                config_changed = True

        if request.ai_analysis is not None:
            ai_dict = request.ai_analysis.model_dump()
            # prompt가 None이면 기존 값 또는 기본 프롬프트 유지
            if ai_dict.get("prompt") is None:
                ai_dict["prompt"] = (
                    existing_config.get("ai_analysis", {}).get("prompt") or DEFAULT_PROMPT
                )
            existing_config["ai_analysis"] = ai_dict
            config_changed = True

        config_json = json.dumps(existing_config) if config_changed else None

        if not setting:
            create_setting(
                db,
                user_id=user.user_id,
                category="chartbot",
                notification_time="09:00",  # 기본값 (종목별 시간 사용)
                config_json=config_json,
            )
        else:
            update_setting(
                db,
                setting.setting_id,
                config_json=config_json,
                is_active=request.is_active,
            )

        db.commit()

        # 스케줄러 Job 업데이트
        try:
            scheduler_service.update_chartbot_job()
        except Exception as e:
            print(f"⚠️ Chartbot Job 업데이트 실패: {e}")

        return JSONResponse(content={"message": "설정이 저장되었습니다"})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tickers")
async def add_chartbot_ticker(
    request: ChartSymbolRequest, db: Session = Depends(get_db)
):
    """차트 발송 종목 추가"""
    try:
        user = get_or_create_user(db)

        # 티커 유효성 검증
        if not finance_bot.validate_ticker(request.ticker, request.market):
            detail = f"유효하지 않은 티커입니다: {request.ticker}"
            if (
                request.ticker
                and request.ticker.strip().isdigit()
                and len(request.ticker.strip()) == 6
                and request.market == "US"
            ):
                detail += " (한국 종목은 시장을 KR로 선택하세요)"
            raise HTTPException(status_code=400, detail=detail)

        setting = get_setting_by_category(db, user.user_id, "chartbot")
        tickers = []

        if setting and setting.config_json:
            try:
                config = json.loads(setting.config_json)
                tickers = config.get("tickers", [])
            except Exception:
                pass

        # 중복 확인
        for t in tickers:
            t_ticker = t.get("ticker") if isinstance(t, dict) else t
            if t_ticker == request.ticker:
                raise HTTPException(
                    status_code=400, detail="이미 등록된 종목입니다"
                )

        # 종목명 조회하여 DB에 함께 저장 (pykrx 장애 시에도 이름 표시 가능)
        ticker_name = ""
        try:
            ticker_name = chart_bot._get_name(request.ticker, request.market)
            if ticker_name == request.ticker:
                ticker_name = ""  # 조회 실패 시 빈 문자열
        except Exception:
            pass

        tickers.append({
            "ticker": request.ticker,
            "market": request.market,
            "name": ticker_name,
            "notification_time": request.notification_time or "09:00",
            "notification_days": request.notification_days if request.notification_days else [],
        })

        if not setting:
            create_setting(
                db,
                user_id=user.user_id,
                category="chartbot",
                notification_time="09:00",
                config_json=json.dumps({"tickers": tickers}),
            )
        else:
            config = json.loads(setting.config_json or "{}")
            config["tickers"] = tickers
            update_setting(db, setting.setting_id, config_json=json.dumps(config))

        # Job 업데이트
        try:
            scheduler_service.update_chartbot_job()
        except Exception:
            pass

        return JSONResponse(
            content={
                "message": "종목이 추가되었습니다",
                "ticker": request.ticker,
                "market": request.market,
            },
            status_code=201,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ChartTickerUpdateRequest(BaseModel):
    """차트 종목 발송 설정 업데이트 요청"""
    notification_time: Optional[str] = None  # HH:MM
    notification_days: Optional[List[int]] = None  # 0=월~6=일


@router.patch("/tickers/{ticker}")
async def update_chartbot_ticker_time(
    ticker: str,
    request: ChartTickerUpdateRequest,
    market: str = "US",
    db: Session = Depends(get_db),
):
    """차트 종목 발송 시간 수정"""
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "chartbot")

        if not setting or not setting.config_json:
            raise HTTPException(status_code=404, detail="등록된 종목이 없습니다")

        config = json.loads(setting.config_json)
        tickers = config.get("tickers", [])
        updated = False

        for t in tickers:
            t_ticker = t.get("ticker") if isinstance(t, dict) else t
            t_market = t.get("market", "US") if isinstance(t, dict) else "US"
            if t_ticker == ticker and t_market == market:
                if isinstance(t, dict):
                    if request.notification_time is not None:
                        t["notification_time"] = request.notification_time
                    if request.notification_days is not None:
                        t["notification_days"] = request.notification_days
                updated = True
                break

        if not updated:
            raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

        config["tickers"] = tickers
        update_setting(db, setting.setting_id, config_json=json.dumps(config))

        try:
            scheduler_service.update_chartbot_job()
        except Exception:
            pass

        return JSONResponse(
            content={
                "message": "발송 설정이 수정되었습니다",
                "ticker": ticker,
                "market": market,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tickers/{ticker}")
async def remove_chartbot_ticker(
    ticker: str, market: str = "US", db: Session = Depends(get_db)
):
    """차트 발송 종목 제거"""
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "chartbot")

        if not setting or not setting.config_json:
            raise HTTPException(status_code=404, detail="등록된 종목이 없습니다")

        config = json.loads(setting.config_json)
        tickers = config.get("tickers", [])

        new_tickers = [
            t for t in tickers
            if (t.get("ticker") if isinstance(t, dict) else t) != ticker
            or (t.get("market") if isinstance(t, dict) else "US") != market
        ]

        if len(new_tickers) == len(tickers):
            raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

        config["tickers"] = new_tickers
        update_setting(db, setting.setting_id, config_json=json.dumps(config))

        try:
            scheduler_service.update_chartbot_job()
        except Exception:
            pass

        return JSONResponse(content={"message": "종목이 제거되었습니다"})

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ChartTestRequest(BaseModel):
    """차트 테스트 발송 요청 (미리보기에서 선택한 종목)"""
    ticker: str
    market: str = "US"


@router.post("/test")
async def test_chartbot_notification(request: ChartTestRequest):
    """차트 미리보기에서 선택한 종목의 차트를 텔레그램으로 테스트 발송"""
    try:
        ticker = request.ticker.strip().upper()
        if not ticker:
            raise HTTPException(status_code=400, detail="티커를 입력해주세요")

        market = request.market or "US"
        name = chart_bot._get_name(ticker, market)
        sent = await chart_bot.send_ta_charts(ticker, market, name)

        success = 1 if sent > 0 else 0
        fail = 1 if sent == 0 else 0

        return JSONResponse(
            content={
                "message": "Chartbot 테스트 발송 완료",
                "success": success,
                "fail": fail,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Chartbot 테스트 발송 실패: {str(e)}"
        )


@router.get("/ticker-name")
async def get_ticker_name(ticker: str, market: str = "US"):
    """티커에 해당하는 종목명 조회 (추가 폼 미리보기용)"""
    try:
        if not ticker or len(ticker.strip()) < 1:
            return JSONResponse(content={"name": ""})
        name = chart_bot._get_name(ticker.strip().upper(), market)
        return JSONResponse(content={"ticker": ticker, "market": market, "name": name})
    except Exception:
        return JSONResponse(content={"name": ""})


@router.get("/preview/{ticker}")
async def preview_chart(ticker: str, market: str = "US", days: int = 30):
    """차트 미리보기 - 이미지 경로 반환"""
    try:
        if days not in (30, 90, 180, 365, 1825):
            days = 30
        chart_path = chart_bot.generate_chart(ticker, market, days=days)
        if not chart_path:
            detail = f"차트 생성 실패: {ticker}"
            if market == "KR":
                detail += " (KRX 데이터 조회 실패 - pykrx 연결 상태 확인 필요)"
            raise HTTPException(status_code=500, detail=detail)

        # 상대 URL 반환 (프론트에서 /static/charts/xxx 로 표시)
        return JSONResponse(
            content={
                "chart_path": f"/static/{chart_path}",
                "ticker": ticker,
                "market": market,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/llm/models")
async def get_llm_models():
    """LiteLLM Gateway의 사용 가능한 모델 목록 조회 (AI 분석 모델 드롭다운용)"""
    try:
        client = get_litellm_client()
        models_resp = await client.get_models()
        model_ids = [m.id for m in models_resp.models]
        return JSONResponse(content={"models": model_ids, "count": len(model_ids)})
    except LiteLLMError as e:
        # Gateway 미연결 등 → 빈 목록으로 graceful 처리
        return JSONResponse(content={"models": [], "count": 0, "error": str(e)})
    except Exception as e:
        return JSONResponse(content={"models": [], "count": 0, "error": str(e)})


def _path_to_url(abs_path: Optional[str]) -> Optional[str]:
    """차트 절대 경로 → 정적 URL 변환"""
    if not abs_path:
        return None
    import os
    return f"/static/charts/{os.path.basename(abs_path)}"


@router.post("/test-charts")
async def generate_test_charts(request: TestChartsRequest):
    """
    테스트용 ta-charts (일봉+주봉) 생성.
    - 같은 ticker+market의 이전 테스트 파일 자동 삭제
    - 파일은 분석 재사용을 위해 디스크에 유지 (실발송과 달리 즉시 삭제 안 함)
    """
    try:
        ticker = request.ticker.strip().upper()
        if not ticker:
            raise HTTPException(status_code=400, detail="티커를 입력해주세요")
        market = request.market or "US"
        name = chart_bot._get_name(ticker, market)

        charts = chart_bot.generate_test_charts(ticker, market, name)
        if not charts:
            raise HTTPException(status_code=500, detail=f"차트 생성 실패: {ticker}")

        return JSONResponse(content={
            "ticker": ticker,
            "market": market,
            "name": name,
            "charts": [
                {"path": abs_path, "url": f"/static/{rel_url}", "label": label}
                for abs_path, rel_url, label in charts
            ],
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-preview")
async def analyze_chart_preview(request: AnalyzePreviewRequest):
    """
    AI 기술분석 미리보기 - 분석 텍스트 + 차트 URL 반환 (텔레그램 미발송).
    클라이언트가 daily_path/weekly_path를 전달하면 캐시 차트를 재사용.
    없거나 무효하면 새 차트 생성.
    """
    import os
    try:
        ticker = request.ticker.strip().upper()
        if not ticker:
            raise HTTPException(status_code=400, detail="티커를 입력해주세요")
        market = request.market or "US"
        name = chart_bot._get_name(ticker, market)

        # 1. 캐시 차트 검증 (경로 안전성 + 파일 존재)
        daily_path: Optional[str] = None
        weekly_path: Optional[str] = None
        cached_used = False

        if request.daily_path and request.weekly_path:
            if (chart_bot.is_safe_chart_path(request.daily_path)
                and os.path.exists(request.daily_path)
                and chart_bot.is_safe_chart_path(request.weekly_path)
                and os.path.exists(request.weekly_path)):
                daily_path = request.daily_path
                weekly_path = request.weekly_path
                cached_used = True

        # 2. 캐시 미스 → 새 차트 생성
        if not cached_used:
            charts = chart_bot.generate_test_charts(ticker, market, name)
            if not charts:
                raise HTTPException(status_code=500, detail=f"차트 생성 실패: {ticker}")
            daily_path = charts[0][0] if len(charts) > 0 else None
            weekly_path = charts[1][0] if len(charts) > 1 else None

        # 3. AI 분석 (파일은 분석 후에도 유지 → 캐시 재사용 가능)
        t0 = time.monotonic()
        analysis_html = await chart_analyzer.analyze(
            daily_path=daily_path,
            weekly_path=weekly_path,
            ticker=ticker,
            name=name,
            market=market,
        )
        elapsed = round(time.monotonic() - t0, 1)

        if not analysis_html:
            raise HTTPException(
                status_code=503,
                detail="AI 분석 실패: LLM 설정을 확인하거나 AI 기술분석이 활성화되어 있는지 확인하세요",
            )

        # 4. 차트 메타 (항상 반환 → 클라이언트가 화면 갱신 가능)
        charts_meta = []
        if daily_path:
            charts_meta.append({
                "path": daily_path,
                "url": _path_to_url(daily_path),
                "label": "일봉 (1년)",
            })
        if weekly_path:
            charts_meta.append({
                "path": weekly_path,
                "url": _path_to_url(weekly_path),
                "label": "주봉 (5년)",
            })

        return JSONResponse(content={
            "ticker": ticker,
            "market": market,
            "name": name,
            "analysis_html": analysis_html,
            "elapsed_sec": elapsed,
            "cached_charts_used": cached_used,
            "charts": charts_meta,
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_chartbot_logs(limit: int = 20, db: Session = Depends(get_db)):
    """Chartbot 관련 로그 조회"""
    try:
        logs = get_logs(db, category="chartbot", limit=limit)

        return JSONResponse(
            content={
                "logs": [
                    {
                        "log_id": log.log_id,
                        "category": log.category,
                        "status": log.status,
                        "message": log.message,
                        "created_at": log.created_at.isoformat(),
                    }
                    for log in logs
                ],
                "count": len(logs),
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_stocks(q: str, market: str = "US"):
    """종목 검색 (Finance API 재사용)"""
    try:
        if not q or len(q) < 1:
            raise HTTPException(status_code=400, detail="검색어를 입력해주세요")

        results = finance_bot.search_ticker(q, market)

        return JSONResponse(
            content={
                "results": results if results else [],
                "count": len(results) if results else 0,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
