"""
YouTube 모니터 모듈용 PostgreSQL 전용 Declarative Base.

중요: 기존 `app/database.py::Base`는 SQLite(assistant.db) 테이블을 모두 생성하기 위해
`init_db()`에서 `Base.metadata.create_all()`을 호출한다.

YouTube 영상 데이터(7개 테이블)는 PostgreSQL에만 있어야 하므로,
PG 모델은 별도의 Base를 사용해 SQLite 자동 생성 영향에서 분리한다.
"""

from sqlalchemy.orm import declarative_base

YoutubePGBase = declarative_base()

