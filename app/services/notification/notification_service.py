"""
알림 발송 통합 서비스
연동된 모든 채널로 메시지를 자동 발송
"""

from typing import Dict, List
from dataclasses import dataclass
from app.models import User
from app.services.notification.kakao_sender import kakao_sender
from app.services.notification.telegram_sender import telegram_sender


@dataclass
class NotificationResult:
    """알림 발송 결과"""

    success: bool  # 최소 하나 이상의 채널에서 성공했는지
    kakao_sent: bool  # 카카오톡 발송 성공 여부
    telegram_sent: bool  # 텔레그램 발송 성공 여부
    failed_channels: List[str]  # 실패한 채널 목록
    message: str  # 결과 메시지


class NotificationService:
    """
    알림 발송 통합 서비스

    사용자에게 연동된 모든 채널(카카오톡, 텔레그램)로 메시지를 발송합니다.
    """

    def __init__(self):
        self.kakao_sender = kakao_sender
        self.telegram_sender = telegram_sender

    async def send(self, user: User, message: str) -> NotificationResult:
        """
        연동된 모든 채널로 메시지 발송

        Args:
            user: 사용자 객체
            message: 발송할 메시지 내용

        Returns:
            NotificationResult: 발송 결과
        """
        kakao_sent = False
        telegram_sent = False
        failed_channels = []

        # 카카오톡 발송
        if self.kakao_sender.is_available(user):
            kakao_sent = await self.kakao_sender.send_message(user, message)
            if not kakao_sent:
                failed_channels.append("kakao")

        # 텔레그램 발송
        if self.telegram_sender and self.telegram_sender.is_available(user):
            telegram_sent = await self.telegram_sender.send_message(user, message)
            if not telegram_sent:
                failed_channels.append("telegram")

        # 결과 생성
        success = kakao_sent or telegram_sent
        result_message = self._generate_result_message(
            kakao_sent, telegram_sent, failed_channels
        )

        return NotificationResult(
            success=success,
            kakao_sent=kakao_sent,
            telegram_sent=telegram_sent,
            failed_channels=failed_channels,
            message=result_message,
        )

    async def send_to_kakao(self, user: User, message: str) -> bool:
        """
        카카오톡으로만 메시지 발송

        Args:
            user: 사용자 객체
            message: 발송할 메시지

        Returns:
            bool: 발송 성공 여부
        """
        if not self.kakao_sender.is_available(user):
            return False
        return await self.kakao_sender.send_message(user, message)

    async def send_to_telegram(self, user: User, message: str) -> bool:
        """
        텔레그램으로만 메시지 발송

        Args:
            user: 사용자 객체
            message: 발송할 메시지

        Returns:
            bool: 발송 성공 여부
        """
        if not self.telegram_sender or not self.telegram_sender.is_available(user):
            return False
        return await self.telegram_sender.send_message(user, message)

    def get_available_channels(self, user: User) -> List[str]:
        """
        사용자에게 연동된 채널 목록 조회

        Args:
            user: 사용자 객체

        Returns:
            List[str]: 연동된 채널 목록 ['kakao', 'telegram']
        """
        channels = []

        if self.kakao_sender.is_available(user):
            channels.append("kakao")

        if self.telegram_sender and self.telegram_sender.is_available(user):
            channels.append("telegram")

        return channels

    def _generate_result_message(
        self, kakao_sent: bool, telegram_sent: bool, failed_channels: List[str]
    ) -> str:
        """
        발송 결과 메시지 생성

        Args:
            kakao_sent: 카카오톡 발송 성공 여부
            telegram_sent: 텔레그램 발송 성공 여부
            failed_channels: 실패한 채널 목록

        Returns:
            str: 결과 메시지
        """
        sent_channels = []
        if kakao_sent:
            sent_channels.append("카카오톡")
        if telegram_sent:
            sent_channels.append("텔레그램")

        if not sent_channels:
            return "알림 발송 실패: 연동된 채널이 없거나 모두 실패했습니다"

        result = f"알림 발송 성공: {', '.join(sent_channels)}"

        if failed_channels:
            failed_names = []
            if "kakao" in failed_channels:
                failed_names.append("카카오톡")
            if "telegram" in failed_channels:
                failed_names.append("텔레그램")
            result += f" (실패: {', '.join(failed_names)})"

        return result


# 싱글톤 인스턴스
notification_service = NotificationService()
