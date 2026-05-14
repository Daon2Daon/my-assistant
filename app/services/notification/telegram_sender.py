"""
텔레그램 메시지 발송 모듈
Telegram Bot API를 사용한 메시지 발송
"""

import asyncio
import os
from typing import Dict, Optional

import httpx

from app.config import settings
from app.models import User


def _telegram_retry_after_sec(response: httpx.Response) -> Optional[float]:
    """Telegram 429 응답의 parameters.retry_after(초)를 추출. 없으면 None."""
    try:
        payload = response.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    params = payload.get("parameters")
    if isinstance(params, dict) and "retry_after" in params:
        try:
            return float(params["retry_after"])
        except (TypeError, ValueError):
            return None
    return None


class TelegramSender:
    """텔레그램 메시지 발송 전용 클래스"""

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_photo(
        self, user: User, photo_path: str, caption: str = ""
    ) -> bool:
        """
        텔레그램으로 이미지 발송

        Args:
            user: 사용자 객체 (telegram_chat_id 필요)
            photo_path: 이미지 파일 경로 (절대 경로)
            caption: 이미지 캡션 (선택)

        Returns:
            bool: 발송 성공 여부
        """
        try:
            if not user.telegram_chat_id:
                print("❌ 텔레그램 chat_id가 없습니다")
                return False

            url = f"{self.base_url}/sendPhoto"

            with open(photo_path, "rb") as photo_file:
                files = {
                    "photo": (
                        os.path.basename(photo_path),
                        photo_file,
                        "image/png",
                    )
                }
                data = {
                    "chat_id": user.telegram_chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                }

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        url, data=data, files=files
                    )

                    if response.status_code == 200:
                        print(
                            f"✅ 텔레그램 이미지 발송 성공 (user_id: {user.user_id})"
                        )
                        return True
                    else:
                        print(
                            f"❌ 텔레그램 이미지 발송 실패: "
                            f"{response.status_code} - {response.text}"
                        )
                        return False

        except FileNotFoundError:
            print(f"❌ 이미지 파일을 찾을 수 없습니다: {photo_path}")
            return False
        except Exception as e:
            print(f"❌ 텔레그램 이미지 발송 실패: {e}")
            return False

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

            # 긴 요약·네트워크 지연 대비 타임아웃 여유, 429/5xx·일시 오류 시 소수 재시도
            timeout = httpx.Timeout(60.0, connect=15.0)
            max_attempts = 4
            backoff_sec = (1.0, 3.0, 8.0)

            for attempt in range(max_attempts):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        response = await client.post(url, json=data)

                    if response.status_code == 200:
                        print(f"✅ 텔레그램 메시지 발송 성공 (user_id: {user.user_id})")
                        return True

                    retry_after = _telegram_retry_after_sec(response)
                    if response.status_code == 429 and attempt < max_attempts - 1:
                        wait = retry_after if retry_after is not None else backoff_sec[attempt]
                        print(
                            f"⚠️ 텔레그램 rate limit(429), {wait:.1f}s 후 재시도 "
                            f"({attempt + 1}/{max_attempts})"
                        )
                        await asyncio.sleep(wait)
                        continue

                    if response.status_code >= 500 and attempt < max_attempts - 1:
                        wait = backoff_sec[min(attempt, len(backoff_sec) - 1)]
                        print(
                            f"⚠️ 텔레그램 서버 오류({response.status_code}), {wait:.1f}s 후 재시도 "
                            f"({attempt + 1}/{max_attempts})"
                        )
                        await asyncio.sleep(wait)
                        continue

                    print(
                        f"❌ 텔레그램 메시지 발송 실패: {response.status_code} - {response.text}"
                    )
                    return False

                except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
                    if attempt < max_attempts - 1:
                        wait = backoff_sec[min(attempt, len(backoff_sec) - 1)]
                        print(
                            f"⚠️ 텔레그램 전송 일시 오류 ({type(e).__name__}), {wait:.1f}s 후 재시도 "
                            f"({attempt + 1}/{max_attempts})"
                        )
                        await asyncio.sleep(wait)
                        continue
                    print(f"❌ 텔레그램 메시지 발송 실패: {e}")
                    return False

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
