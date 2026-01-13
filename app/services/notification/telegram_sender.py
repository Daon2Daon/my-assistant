"""
텔레그램 메시지 발송 모듈
Telegram Bot API를 사용한 메시지 발송
"""

import httpx
from typing import Optional, Dict
from app.models import User
from app.config import settings


class TelegramSender:
    """텔레그램 메시지 발송 전용 클래스"""

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_message(self, user: User, message: str) -> bool:
        """
        텔레그램으로 메시지 발송

        Args:
            user: 사용자 객체 (telegram_chat_id 필요)
            message: 발송할 메시지 내용

        Returns:
            bool: 발송 성공 여부
        """
        try:
            # chat_id가 없으면 발송 불가
            if not user.telegram_chat_id:
                print("❌ 텔레그램 chat_id가 없습니다")
                return False

            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": user.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",  # HTML 포맷 지원
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=data)

                if response.status_code == 200:
                    print(f"✅ 텔레그램 메시지 발송 성공 (user_id: {user.user_id})")
                    return True
                else:
                    print(f"❌ 텔레그램 메시지 발송 실패: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            print(f"❌ 텔레그램 메시지 발송 실패: {e}")
            return False

    async def get_bot_info(self) -> Optional[Dict]:
        """
        봇 정보 조회 (연결 테스트용)

        Returns:
            Dict: 봇 정보 또는 None
        """
        try:
            url = f"{self.base_url}/getMe"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)

                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"❌ 텔레그램 봇 정보 조회 실패: {response.status_code}")
                    return None

        except Exception as e:
            print(f"❌ 텔레그램 봇 정보 조회 실패: {e}")
            return None

    def is_available(self, user: User) -> bool:
        """
        텔레그램 발송 가능 여부 확인

        Args:
            user: 사용자 객체

        Returns:
            bool: 발송 가능 여부 (chat_id 존재 여부)
        """
        return user.telegram_chat_id is not None and user.telegram_chat_id != ""


# 싱글톤 인스턴스
telegram_sender = TelegramSender()
