"""
My Assistant 메인 애플리케이션
FastAPI 기반 개인용 비서 앱
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.database import init_db, run_migrations
from app.middleware import AuthMiddleware
from app.routers import auth, scheduler, reminders, pages, settings as settings_router, logs, weather, finance, calendar, chartbot, youtube as youtube_router
from app.services.scheduler import scheduler_service
from app.services.bots.memo_bot import memo_bot

# FastAPI 앱 생성
app = FastAPI(
    title="My Assistant",
    description="개인용 비서 앱 - 날씨, 금융, 일정 알림 서비스 (텔레그램)",
    version="0.1.0",
    debug=settings.DEBUG,
)

# 미들웨어 등록 (주의: 나중에 등록된 것이 먼저 실행됨)
# 따라서 AuthMiddleware를 먼저 등록하고, SessionMiddleware를 나중에 등록해야 함

# 1. 인증 미들웨어 등록 (먼저 등록, 나중에 실행)
app.add_middleware(AuthMiddleware)

# 2. 세션 미들웨어 등록 (나중에 등록, 먼저 실행)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    max_age=settings.SESSION_MAX_AGE,
    same_site="lax",
    https_only=not settings.DEBUG,  # 프로덕션에서는 HTTPS 강제
)

# Static 파일 서빙
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# API 라우터 등록
app.include_router(auth.router)
app.include_router(scheduler.router)
app.include_router(reminders.router)
app.include_router(settings_router.router)
app.include_router(logs.router)
app.include_router(weather.router)
app.include_router(finance.router)
app.include_router(calendar.router)
app.include_router(chartbot.router)
app.include_router(youtube_router.router)

# Pages 라우터 (페이지 렌더링) - 마지막에 등록
app.include_router(pages.router)


@app.get("/health")
async def health_check():
    """
    헬스 체크 엔드포인트
    서버 정상 동작 확인
    """
    return JSONResponse(content={"status": "healthy"})


# 애플리케이션 시작 이벤트
@app.on_event("startup")
async def startup_event():
    """
    애플리케이션 시작 시 실행되는 이벤트
    데이터베이스 초기화 및 스케줄러 시작
    """
    print("🚀 My Assistant 시작")
    print(f"🔧 DEBUG 모드: {settings.DEBUG}")

    # 데이터베이스 초기화
    init_db()

    # 데이터베이스 마이그레이션 자동 실행
    run_migrations()

    # 스케줄러 시작
    scheduler_service.start()

    # YouTube 모니터 Job 등록
    try:
        scheduler_service.setup_youtube_jobs()
    except Exception as e:
        print(f"⚠️  YouTube Job 등록 실패: {e}")

    # YouTube 가상 채널(추가 영상 분석 전용) 초기화
    try:
        from app.services.youtube.db_engine import db_engine_manager, DBNotConfiguredError
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from app.routers.youtube import ensure_instant_channel

        engine = await db_engine_manager.get_engine()
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as sess:
            async with sess.begin():
                await ensure_instant_channel(sess)
        print("✅ YouTube 가상 채널 초기화 완료")
    except DBNotConfiguredError:
        pass  # DB 미설정 상태 — 첫 분석 요청 시 자동 생성
    except Exception as e:
        print(f"⚠️  YouTube 가상 채널 초기화 실패: {e}")

    # Weather 알림 Job 등록
    try:
        scheduler_service.setup_weather_job()
    except Exception as e:
        print(f"⚠️  Weather Job 등록 실패: {e}")

    # Calendar 알림 Job 등록
    try:
        scheduler_service.setup_calendar_job()
    except Exception as e:
        print(f"⚠️  Calendar Job 등록 실패: {e}")

    # Finance 알림 Job 등록
    try:
        scheduler_service.setup_finance_jobs()
    except Exception as e:
        print(f"⚠️  Finance Job 등록 실패: {e}")

    # Chartbot Job 등록
    try:
        scheduler_service.setup_chartbot_job()
    except Exception as e:
        print(f"⚠️  Chartbot Job 등록 실패: {e}")

    # 미발송 메모 Job 복원
    restored_count = memo_bot.restore_pending_reminders()
    if restored_count > 0:
        print(f"📝 미발송 메모 {restored_count}개 Job 복원 완료")

    # 복원된 Job 목록 출력
    jobs = scheduler_service.get_all_jobs()
    if jobs:
        print(f"📋 등록된 Job 목록 ({len(jobs)}개):")
        for job in jobs:
            print(f"   - {job['id']}: 다음 실행 {job['next_run_time']}")
    else:
        print("📋 등록된 Job이 없습니다")


# 애플리케이션 종료 이벤트
@app.on_event("shutdown")
async def shutdown_event():
    """
    애플리케이션 종료 시 실행되는 이벤트
    스케줄러 종료 및 리소스 정리
    """
    print("👋 My Assistant 종료")

    # 스케줄러 종료
    scheduler_service.shutdown()
