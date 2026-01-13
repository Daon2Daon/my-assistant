"""
카카오톡 메시지 발송 모듈
KakaoAuthService를 활용한 메시지 발송 전용 클래스
"""

from typing import Optional
from app.models import User
from app.services.auth.kakao_auth import kakao_auth_service


class KakaoSender:
    """카카오톡 메시지 발송 전용 클래스"""

    def __init__(self):
        self.kakao_auth = kakao_auth_service

    async def send_message(self, user: User, message: str) -> bool:
        """
        카카오톡으로 메시지 발송

        Args:
            user: 사용자 객체 (kakao_access_token 필요)
            message: 발송할 메시지 내용

        Returns:
            bool: 발송 성공 여부
        """
        try:
            # 토큰이 없으면 발송 불가
            if not user.kakao_access_token:
                print("❌ 카카오톡 토큰이 없습니다")
                return False

            # 카카오톡 메시지 발송
            await self.kakao_auth.send_message_to_me(
                user.kakao_access_token, message
            )

            print(f"✅ 카카오톡 메시지 발송 성공 (user_id: {user.user_id})")
            return True

        except Exception as e:
            print(f"❌ 카카오톡 메시지 발송 실패: {e}")
            return False

    def is_available(self, user: User) -> bool:
        """
        카카오톡 발송 가능 여부 확인

        Args:
            user: 사용자 객체

        Returns:
            bool: 발송 가능 여부 (토큰 존재 여부)
        """
        return user.kakao_access_token is not None and user.kakao_access_token != ""


# 싱글톤 인스턴스
kakao_sender = KakaoSender()
