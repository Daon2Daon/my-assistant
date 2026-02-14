"""
Chartbot API 라우터
종목 차트 정기 발송 관리 API
"""

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, List

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
from app.services.bots.finance_bot import finance_bot
from app.services.scheduler import scheduler_service


router = APIRouter(prefix="/api/chartbot", tags=["Chartbot"])


class ChartSymbolRequest(BaseModel):
    """차트 종목 등록 요청"""
    ticker: str
    market: str = "US"  # US / KR
    notification_time: str = "09:00"  # HH:MM 형식
    notification_days: List[int] = [0, 1, 2, 3, 4]  # 0=월~6=일 (Python weekday)


class ChartbotConfigUpdateRequest(BaseModel):
    """Chartbot 설정 업데이트 요청"""
    notification_time: Optional[str] = None
    is_active: Optional[bool] = None
    tickers: Optional[List[dict]] = None  # [{"ticker": "AAPL", "market": "US"}, ...]


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
        for t in tickers:
            if isinstance(t, dict):
                if "notification_time" not in t:
                    t["notification_time"] = "09:00"
                if "notification_days" not in t:
                    t["notification_days"] = [0, 1, 2, 3, 4]
                if "name" not in t:
                    try:
                        t["name"] = chart_bot._get_name(
                            t.get("ticker", ""), t.get("market", "US")
                        )
                    except Exception:
                        t["name"] = t.get("ticker", "")

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


@router.get("/settings")
async def get_chartbot_settings(db: Session = Depends(get_db)):
    """Chartbot 설정 조회 (설정 페이지용)"""
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
                }
            )

        return JSONResponse(
            content={
                "category": "chartbot",
                "notification_time": setting.notification_time,
                "is_active": setting.is_active,
                "config_json": setting.config_json or "{}",
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

        config_json = None
        if request.tickers is not None:
            existing_config = {}
            if setting and setting.config_json:
                try:
                    existing_config = json.loads(setting.config_json)
                except Exception:
                    pass
            existing_config["tickers"] = request.tickers
            config_json = json.dumps(existing_config)

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

        tickers.append({
            "ticker": request.ticker,
            "market": request.market,
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


@router.post("/test")
async def test_chartbot_notification():
    """Chartbot 즉시 테스트 발송"""
    try:
        result = await chart_bot.send_all_charts()

        return JSONResponse(
            content={
                "message": "Chartbot 테스트 발송 완료",
                "success": result["success"],
                "fail": result["fail"],
            }
        )

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
async def preview_chart(ticker: str, market: str = "US"):
    """차트 미리보기 - 이미지 경로 반환"""
    try:
        chart_path = chart_bot.generate_chart(ticker, market)
        if not chart_path:
            raise HTTPException(
                status_code=500, detail=f"차트 생성 실패: {ticker}"
            )

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
