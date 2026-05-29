from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from alertbot.config import Config
from alertbot.notifier import TelegramNotifier
from alertbot.reservation import StateStore, run_once


def main() -> None:
    load_dotenv()
    config = Config.from_env()

    logging.basicConfig(level=config.log_level)

    if not config.target_url:
        raise ValueError("TARGET_URL is required")

    notifier = TelegramNotifier(
        config.telegram_bot_token,
        config.telegram_chat_id,
        config.telegram_send_delay_seconds,
    )
    state_store = StateStore(config.state_db_path)

    if config.log_item_decisions:
        logging.info("State file: %s", config.state_db_path)
        logging.info(
            "Reservation target: %04d-%02d-%02d / %s",
            config.reservation_year,
            config.reservation_month,
            config.reservation_day,
            config.reservation_theme,
        )

    while True:
        try:
            run_once(config, notifier, state_store)
        except Exception as exc:  # noqa: BLE001
            logging.exception("Polling error: %s", exc)

        time.sleep(max(config.poll_interval_seconds, 5))


if __name__ == "__main__":
    main()
