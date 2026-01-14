"""
Telegram Chat ID 컬럼 추가 마이그레이션 스크립트
"""
import sqlite3
from pathlib import Path


def migrate():
    """telegram_chat_id 컬럼을 users 테이블에 추가"""

    db_path = Path("data/assistant.db")

    if not db_path.exists():
        print(f"❌ 데이터베이스 파일을 찾을 수 없습니다: {db_path}")
        return

    print(f"📂 데이터베이스 경로: {db_path.absolute()}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 현재 테이블 스키마 확인
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()

        print("\n📋 현재 users 테이블 컬럼:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")

        # telegram_chat_id 컬럼이 이미 존재하는지 확인
        column_names = [col[1] for col in columns]

        if "telegram_chat_id" in column_names:
            print("\n✅ telegram_chat_id 컬럼이 이미 존재합니다.")
        else:
            print("\n🔧 telegram_chat_id 컬럼을 추가합니다...")
            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN telegram_chat_id TEXT
            """)
            conn.commit()
            print("✅ telegram_chat_id 컬럼이 성공적으로 추가되었습니다!")

        # 변경 후 스키마 확인
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()

        print("\n📋 업데이트된 users 테이블 컬럼:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")

    except sqlite3.Error as e:
        print(f"❌ 에러 발생: {e}")
        conn.rollback()
    finally:
        conn.close()

    print("\n✅ 마이그레이션 완료!")


if __name__ == "__main__":
    migrate()
