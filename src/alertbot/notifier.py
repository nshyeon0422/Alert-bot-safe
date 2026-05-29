from __future__ import annotations

import logging
import time

import requests

LOGGER = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, delay_seconds: int = 0) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.delay_seconds = delay_seconds
        self.session = requests.Session()

    def send_message(self, text: str) -> None:
        if not self.bot_token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

        response = self.session.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        response.raise_for_status()
        LOGGER.info("Sent Telegram message")
        time.sleep(max(self.delay_seconds, 0))
