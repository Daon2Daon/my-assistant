# My Assistant Dockerfile
# Stage 1: Node.js 20 - YouTube Monitor UI 빌드
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

# package.json 먼저 복사해서 캐시 활용
COPY frontend/youtube/package*.json ./
RUN npm ci --ignore-scripts

# 소스 복사 후 빌드
COPY frontend/youtube/ ./
RUN npm run build

# Stage 2: Python 3.10 slim - 메인 애플리케이션
FROM python:3.10-slim

# 환경변수 설정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# Stage 1에서 빌드된 React 정적 파일 복사
# vite.config.ts의 outDir: path.resolve(__dirname, '../../app/static/youtube') 기준
COPY --from=frontend-builder /app/static/youtube/ ./app/static/youtube/

# 데이터 디렉토리 생성
RUN mkdir -p /app/data

# 비root 사용자 생성 및 권한 설정
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# 포트 노출 (기본값: 8000)
EXPOSE 8000

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 애플리케이션 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
