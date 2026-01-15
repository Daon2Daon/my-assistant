"""
Finance API 라우터
금융 알림 전용 API 엔드포인트
"""

from typing import Optional, Any, Dict
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import math

from app.database import get_db
from app.crud import (
    get_or_create_user,
    get_setting_by_category,
    get_logs,
    get_watchlists,
    get_watchlist,
    get_watchlist_by_ticker,
    create_watchlist,
    update_watchlist,
    delete_watchlist,
    get_price_alerts,
    get_price_alert,
    create_price_alert,
    update_alert_triggered,
    delete_price_alert,
)
from app.services.bots.finance_bot import finance_bot
from app.services.scheduler import scheduler_service


router = APIRouter(prefix="/api/finance", tags=["Finance"])


def sanitize_for_json(data: Any) -> Any:
    """
    JSON 직렬화를 위해 데이터 정제
    - NaN, Infinity를 None으로 변환
    - NumPy 타입을 Python native 타입으로 변환
    """
    if data is None:
        return None

    if isinstance(data, dict):
        return {k: sanitize_for_json(v) for k, v in data.items()}

    if isinstance(data, list):
        return [sanitize_for_json(item) for item in data]

    # NumPy int/float를 Python 타입으로 변환
    if hasattr(data, 'item'):
        data = data.item()

    # float 타입 처리 (NaN, Infinity 체크)
    if isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None
        return data

    return data


class FinanceStatusResponse(BaseModel):
    """금융 모듈 상태 응답"""

    is_active: bool
    notification_time: str
    us_next_run_time: Optional[str] = None
    kr_next_run_time: Optional[str] = None
    last_run_time: Optional[str] = None
    last_status: Optional[str] = None


class WatchlistCreateRequest(BaseModel):
    """관심 종목 등록 요청"""

    ticker: str
    market: str  # US / KR


class WatchlistUpdateRequest(BaseModel):
    """관심 종목 수정 요청"""

    name: Optional[str] = None
    is_active: Optional[bool] = None


class PriceAlertCreateRequest(BaseModel):
    """가격 알림 등록 요청"""

    watchlist_id: int
    alert_type: str  # TARGET_HIGH / TARGET_LOW / PERCENT_CHANGE
    target_price: Optional[float] = None
    target_percent: Optional[float] = None


class PriceAlertResponse(BaseModel):
    """가격 알림 응답"""

    alert_id: int
    user_id: int
    watchlist_id: int
    ticker: str
    market: str
    alert_type: str
    target_price: Optional[float] = None
    target_percent: Optional[float] = None
    is_triggered: bool
    triggered_at: Optional[str] = None
    is_active: bool
    created_at: str


@router.get("/status")
async def get_finance_status(db: Session = Depends(get_db)):
    """
    금융 모듈 상태 조회

    Returns:
        활성화 상태, 알림 시간, 다음 실행 시간, 마지막 실행 결과
    """
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "finance")

        if not setting:
            return JSONResponse(
                content={
                    "is_active": False,
                    "notification_time": "22:00",
                    "us_next_run_time": None,
                    "kr_next_run_time": None,
                    "last_run_time": None,
                    "last_status": None,
                }
            )

        # 스케줄러에서 다음 실행 시간 조회
        jobs = scheduler_service.get_all_jobs()
        us_job = next((job for job in jobs if job["id"] == "finance_us_daily"), None)
        kr_job = next((job for job in jobs if job["id"] == "finance_kr_daily"), None)

        us_next_run_time = us_job["next_run_time"] if us_job else None
        kr_next_run_time = kr_job["next_run_time"] if kr_job else None

        # 마지막 로그 조회
        logs = get_logs(db, category="finance", limit=1)
        last_log = logs[0] if logs else None

        return JSONResponse(
            content={
                "is_active": setting.is_active,
                "notification_time": setting.notification_time,
                "us_next_run_time": us_next_run_time,
                "kr_next_run_time": kr_next_run_time,
                "last_run_time": last_log.created_at.isoformat() if last_log else None,
                "last_status": last_log.status if last_log else None,
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview/us")
async def get_us_market_preview():
    """
    미국 시장 메시지 미리보기

    Returns:
        포맷팅된 미국 증시 메시지
    """
    try:
        # 증시 데이터 조회
        market_data = finance_bot.get_us_market_data()

        if not market_data:
            raise HTTPException(
                status_code=500,
                detail="미국 증시 데이터를 가져올 수 없습니다"
            )

        # 메시지 포맷팅
        message = finance_bot.format_us_market_message(market_data)

        return JSONResponse(
            content={
                "market": "US",
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ US 마켓 미리보기 에러: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview/kr")
async def get_kr_market_preview():
    """
    한국 시장 메시지 미리보기

    Returns:
        포맷팅된 한국 증시 메시지
    """
    try:
        # 증시 데이터 조회
        market_data = finance_bot.get_kr_market_data()

        if not market_data:
            raise HTTPException(
                status_code=500,
                detail="한국 증시 데이터를 가져올 수 없습니다"
            )

        # 메시지 포맷팅
        message = finance_bot.format_kr_market_message(market_data)

        return JSONResponse(
            content={
                "market": "KR",
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ KR 마켓 미리보기 에러: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/us")
async def test_us_market_notification():
    """
    미국 증시 알림 테스트 발송

    Returns:
        발송 결과
    """
    try:
        # 미국 증시 알림 즉시 발송
        await finance_bot.send_us_market_notification()

        return JSONResponse(
            content={
                "message": "미국 증시 알림 테스트 발송 완료",
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"미국 증시 알림 발송 실패: {str(e)}"
        )


@router.post("/test/kr")
async def test_kr_market_notification():
    """
    한국 증시 알림 테스트 발송

    Returns:
        발송 결과
    """
    try:
        # 한국 증시 알림 즉시 발송
        await finance_bot.send_kr_market_notification()

        return JSONResponse(
            content={
                "message": "한국 증시 알림 테스트 발송 완료",
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"한국 증시 알림 발송 실패: {str(e)}"
        )


@router.get("/logs")
async def get_finance_logs(limit: int = 20, db: Session = Depends(get_db)):
    """
    금융 관련 로그 조회

    Args:
        limit: 조회할 로그 개수 (기본값: 20)

    Returns:
        금융 카테고리 로그 목록
    """
    try:
        logs = get_logs(db, category="finance", limit=limit)

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


# ============================================================
# 관심 종목 관리 API
# ============================================================


@router.get("/watchlist")
async def get_user_watchlist(db: Session = Depends(get_db)):
    """
    등록된 관심 종목 목록 조회

    Returns:
        관심 종목 목록
    """
    try:
        user = get_or_create_user(db)
        watchlists = get_watchlists(db, user.user_id, is_active=True)

        return JSONResponse(
            content={
                "watchlists": [
                    {
                        "watchlist_id": w.watchlist_id,
                        "ticker": w.ticker,
                        "name": w.name,
                        "market": w.market,
                        "created_at": w.created_at.isoformat(),
                    }
                    for w in watchlists
                ],
                "count": len(watchlists),
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/watchlist")
async def add_watchlist(
    request: WatchlistCreateRequest, db: Session = Depends(get_db)
):
    """
    관심 종목 등록

    Args:
        request: 종목 등록 정보

    Returns:
        등록된 종목 정보
    """
    try:
        user = get_or_create_user(db)

        # 티커 유효성 검증
        if not finance_bot.validate_ticker(request.ticker, request.market):
            raise HTTPException(
                status_code=400, detail=f"유효하지 않은 티커입니다: {request.ticker}"
            )

        # 중복 확인
        existing = get_watchlist_by_ticker(db, user.user_id, request.ticker)
        if existing and existing.is_active:
            raise HTTPException(status_code=400, detail="이미 등록된 종목입니다")

        # 종목 정보 조회
        stock_info = finance_bot.get_stock_quote(request.ticker, request.market)
        if not stock_info:
            raise HTTPException(
                status_code=500, detail="종목 정보를 가져올 수 없습니다"
            )

        # 관심 종목 등록
        watchlist = create_watchlist(
            db,
            user_id=user.user_id,
            ticker=request.ticker,
            name=stock_info.get("name"),
            market=request.market,
        )

        return JSONResponse(
            content={
                "message": "관심 종목이 등록되었습니다",
                "watchlist": {
                    "watchlist_id": watchlist.watchlist_id,
                    "ticker": watchlist.ticker,
                    "name": watchlist.name,
                    "market": watchlist.market,
                },
            },
            status_code=201,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/watchlist/{watchlist_id}")
async def update_user_watchlist(
    watchlist_id: int, request: WatchlistUpdateRequest, db: Session = Depends(get_db)
):
    """
    관심 종목 정보 수정

    Args:
        watchlist_id: 관심 종목 ID
        request: 수정 정보

    Returns:
        수정된 종목 정보
    """
    try:
        user = get_or_create_user(db)

        # 종목 존재 확인
        watchlist = get_watchlist(db, watchlist_id)
        if not watchlist or watchlist.user_id != user.user_id:
            raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

        # 종목 정보 수정
        updated = update_watchlist(
            db,
            watchlist_id,
            name=request.name,
            is_active=request.is_active,
        )

        return JSONResponse(
            content={
                "message": "종목 정보가 수정되었습니다",
                "watchlist": {
                    "watchlist_id": updated.watchlist_id,
                    "ticker": updated.ticker,
                    "name": updated.name,
                    "market": updated.market,
                    "is_active": updated.is_active,
                },
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/watchlist/{watchlist_id}")
async def delete_user_watchlist(watchlist_id: int, db: Session = Depends(get_db)):
    """
    관심 종목 삭제

    Args:
        watchlist_id: 관심 종목 ID

    Returns:
        삭제 결과
    """
    try:
        user = get_or_create_user(db)

        # 종목 존재 확인
        watchlist = get_watchlist(db, watchlist_id)
        if not watchlist or watchlist.user_id != user.user_id:
            raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

        # 종목 삭제
        success = delete_watchlist(db, watchlist_id)

        if success:
            return JSONResponse(
                content={"message": "관심 종목이 삭제되었습니다"},
                status_code=200,
            )
        else:
            raise HTTPException(status_code=500, detail="종목 삭제에 실패했습니다")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_stocks(q: str, market: str = "US"):
    """
    종목 검색

    Args:
        q: 검색 키워드 (티커 또는 종목명)
        market: 시장 (US / KR)

    Returns:
        검색 결과 목록
    """
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


@router.get("/quote/{ticker}")
async def get_stock_quote_api(ticker: str, market: str = "US"):
    """
    종목 시세 조회

    Args:
        ticker: 종목 티커
        market: 시장 (US / KR)

    Returns:
        종목 시세 정보 (실시간 가격, 변동률, 52주 범위 등)
    """
    try:
        # 기본 시세 조회
        quote = finance_bot.get_stock_quote(ticker, market)
        if not quote:
            raise HTTPException(
                status_code=404, detail=f"종목을 찾을 수 없습니다: {ticker}"
            )

        # 기간별 변동률 조회
        period_changes = finance_bot.calculate_period_changes(ticker, market)

        # 52주 범위 조회
        week_52_range = finance_bot.get_52week_range(ticker, market)

        # JSON 직렬화 가능하도록 데이터 정제
        sanitized_data = sanitize_for_json({
            "quote": quote,
            "period_changes": period_changes,
            "week_52_range": week_52_range,
            "timestamp": datetime.now().isoformat(),
        })

        return JSONResponse(content=sanitized_data)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ 종목 시세 조회 에러 ({ticker}, {market}): {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# 가격 알림 API
# ========================================


@router.get("/alerts")
async def get_alerts_api(db: Session = Depends(get_db)):
    """
    가격 알림 목록 조회

    Returns:
        사용자의 등록된 가격 알림 목록
    """
    try:
        user = get_or_create_user(db)
        alerts = get_price_alerts(db, user.user_id)

        # 응답 데이터 구성
        alert_list = []
        for alert in alerts:
            # watchlist 정보 가져오기
            watchlist = get_watchlist(db, alert.watchlist_id)
            if not watchlist:
                continue

            alert_list.append(
                {
                    "alert_id": alert.alert_id,
                    "user_id": alert.user_id,
                    "watchlist_id": alert.watchlist_id,
                    "ticker": watchlist.ticker,
                    "market": watchlist.market,
                    "alert_type": alert.alert_type,
                    "target_price": alert.target_price,
                    "target_percent": alert.target_percent,
                    "is_triggered": alert.is_triggered,
                    "triggered_at": (
                        alert.triggered_at.isoformat() if alert.triggered_at else None
                    ),
                    "is_active": alert.is_active,
                    "created_at": alert.created_at.isoformat(),
                }
            )

        return JSONResponse(content={"alerts": alert_list, "count": len(alert_list)})

    except Exception as e:
        import traceback

        print(f"❌ 가격 알림 목록 조회 에러: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts")
async def create_alert_api(
    request: PriceAlertCreateRequest, db: Session = Depends(get_db)
):
    """
    가격 알림 등록

    Args:
        request: 가격 알림 등록 요청 (watchlist_id, alert_type, target_price, target_percent)

    Returns:
        생성된 가격 알림 정보
    """
    try:
        user = get_or_create_user(db)

        # watchlist 존재 확인
        watchlist = get_watchlist(db, request.watchlist_id)
        if not watchlist:
            raise HTTPException(
                status_code=404, detail=f"관심 종목을 찾을 수 없습니다: {request.watchlist_id}"
            )

        # watchlist가 현재 사용자의 것인지 확인
        if watchlist.user_id != user.user_id:
            raise HTTPException(status_code=403, detail="권한이 없습니다")

        # 알림 타입 검증
        valid_alert_types = ["TARGET_HIGH", "TARGET_LOW", "PERCENT_CHANGE"]
        if request.alert_type not in valid_alert_types:
            raise HTTPException(
                status_code=400,
                detail=f"잘못된 알림 타입입니다. 사용 가능한 타입: {', '.join(valid_alert_types)}",
            )

        # 목표가/변동률 검증
        if request.alert_type in ["TARGET_HIGH", "TARGET_LOW"]:
            if request.target_price is None or request.target_price <= 0:
                raise HTTPException(
                    status_code=400, detail="목표가는 0보다 커야 합니다"
                )
        elif request.alert_type == "PERCENT_CHANGE":
            if request.target_percent is None:
                raise HTTPException(status_code=400, detail="목표 변동률을 입력해주세요")

        # 가격 알림 생성
        alert = create_price_alert(
            db=db,
            user_id=user.user_id,
            watchlist_id=request.watchlist_id,
            alert_type=request.alert_type,
            target_price=request.target_price,
            target_percent=request.target_percent,
        )

        return JSONResponse(
            content={
                "alert_id": alert.alert_id,
                "user_id": alert.user_id,
                "watchlist_id": alert.watchlist_id,
                "ticker": watchlist.ticker,
                "market": watchlist.market,
                "alert_type": alert.alert_type,
                "target_price": alert.target_price,
                "target_percent": alert.target_percent,
                "is_triggered": alert.is_triggered,
                "triggered_at": (
                    alert.triggered_at.isoformat() if alert.triggered_at else None
                ),
                "is_active": alert.is_active,
                "created_at": alert.created_at.isoformat(),
            },
            status_code=201,
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        print(f"❌ 가격 알림 등록 에러: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/alerts/{alert_id}")
async def delete_alert_api(alert_id: int, db: Session = Depends(get_db)):
    """
    가격 알림 삭제

    Args:
        alert_id: 삭제할 알림 ID

    Returns:
        삭제 성공 메시지
    """
    try:
        user = get_or_create_user(db)

        # 알림 존재 확인
        alert = get_price_alert(db, alert_id)
        if not alert:
            raise HTTPException(
                status_code=404, detail=f"가격 알림을 찾을 수 없습니다: {alert_id}"
            )

        # 알림이 현재 사용자의 것인지 확인
        if alert.user_id != user.user_id:
            raise HTTPException(status_code=403, detail="권한이 없습니다")

        # 알림 삭제
        success = delete_price_alert(db, alert_id)
        if not success:
            raise HTTPException(status_code=500, detail="가격 알림 삭제에 실패했습니다")

        return JSONResponse(
            content={"message": "가격 알림이 삭제되었습니다", "alert_id": alert_id}
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        print(f"❌ 가격 알림 삭제 에러 ({alert_id}): {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
