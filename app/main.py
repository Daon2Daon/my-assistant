"""
My-Kakao-Assistant 메인 애플리케이션
FastAPI 기반 개인용 카카오톡 비서 앱
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database import init_db
from app.routers import auth, scheduler, reminders, pages, settings as settings_router, logs, weather, finance, calendar
from app.services.scheduler import scheduler_service
from app.services.bots.memo_bot import memo_bot

# FastAPI 앱 생성
app = FastAPI(
    title="My-Kakao-Assistant",
    description="개인용 카카오톡 비서 앱 - 날씨, 금융, 일정 알림 서비스",
    version="0.1.0",
    debug=settings.DEBUG,
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
    print("🚀 My-Kakao-Assistant 시작")
    print(f"🔧 DEBUG 모드: {settings.DEBUG}")

    # 데이터베이스 초기화
    init_db()

    # 스케줄러 시작
    scheduler_service.start()

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
    print("👋 My-Kakao-Assistant 종료")

    # 스케줄러 종료
    scheduler_service.shutdown()
