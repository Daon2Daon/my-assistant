"""
알림 발송 통합 서비스
텔레그램 채널로 메시지 발송
"""

from typing import List
from dataclasses import dataclass
from app.models import User
from app.services.notification.telegram_sender import telegram_sender


@dataclass
class NotificationResult:
    """알림 발송 결과"""

    success: bool  # 최소 하나 이상의 채널에서 성공했는지
    telegram_sent: bool  # 텔레그램 발송 성공 여부
    failed_channels: List[str]  # 실패한 채널 목록
    message: str  # 결과 메시지


class NotificationService:
    """
    알림 발송 통합 서비스

    사용자에게 연동된 텔레그램 채널로 메시지를 발송합니다.
    """

    def __init__(self):
        self.telegram_sender = telegram_sender

    async def send(self, user: User, message: str) -> NotificationResult:
        """
        텔레그램으로 메시지 발송

        Args:
            user: 사용자 객체
            message: 발송할 메시지 내용

        Returns:
            NotificationResult: 발송 결과
        """
        telegram_sent = False
        failed_channels = []

        # 텔레그램 발송
        if self.telegram_sender and self.telegram_sender.is_available(user):
            telegram_sent = await self.telegram_sender.send_message(user, message)
            if not telegram_sent:
                failed_channels.append("telegram")

        success = telegram_sent
        result_message = self._generate_result_message(
            telegram_sent, failed_channels
        )

        return NotificationResult(
            success=success,
            telegram_sent=telegram_sent,
            failed_channels=failed_channels,
            message=result_message,
        )

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
            List[str]: 연동된 채널 목록 ['telegram']
        """
        channels = []
        if self.telegram_sender and self.telegram_sender.is_available(user):
            channels.append("telegram")
        return channels

    def _generate_result_message(
        self, telegram_sent: bool, failed_channels: List[str]
    ) -> str:
        """
        발송 결과 메시지 생성

        Args:
            telegram_sent: 텔레그램 발송 성공 여부
            failed_channels: 실패한 채널 목록

        Returns:
            str: 결과 메시지
        """
        if not telegram_sent:
            return "알림 발송 실패: 텔레그램 연동이 필요합니다"

        result = "알림 발송 성공: 텔레그램"
        if failed_channels and "telegram" in failed_channels:
            result += " (실패: 텔레그램)"
        return result


# 싱글톤 인스턴스
notification_service = NotificationService()
