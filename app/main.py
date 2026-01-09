"""
My-Kakao-Assistant 메인 애플리케이션
FastAPI 기반 개인용 카카오톡 비서 앱
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.config import settings
from app.routers import auth, scheduler
from app.services.scheduler import scheduler_service

# FastAPI 앱 생성
app = FastAPI(
    title="My-Kakao-Assistant",
    description="개인용 카카오톡 비서 앱 - 날씨, 금융, 일정 알림 서비스",
    version="0.1.0",
    debug=settings.DEBUG,
)

# 라우터 등록
app.include_router(auth.router)
app.include_router(scheduler.router)


@app.get("/")
async def root():
    """
    루트 엔드포인트
    서버 상태 확인용
    """
    return JSONResponse(
        content={
            "message": "Hello World",
            "app": "My-Kakao-Assistant",
            "version": "0.1.0",
            "status": "running",
        }
    )


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

    # 스케줄러 시작
    scheduler_service.start()


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
