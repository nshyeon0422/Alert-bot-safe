from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional


def _parse_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_int(value: Optional[str], default: int) -> int:
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    target_url: str
    reservation_year: int
    reservation_month: int
    reservation_day: int
    reservation_theme: str
    keywords: List[str]
    use_keywords: bool
    poll_interval_seconds: int
    seed_existing: bool
    item_selector: Optional[str]
    title_selector: Optional[str]
    link_selector: Optional[str]
    content_selector: Optional[str]

    user_agent: str
    accept_language: str
    referer: Optional[str]
    cookie: Optional[str]
    retry_on_403: bool

    headless: bool
    browser_timeout_ms: int
    interaction_wait_ms: int

    verify_ssl: bool
    ca_bundle_path: Optional[str]

    http_proxy: Optional[str]
    https_proxy: Optional[str]

    telegram_bot_token: str
    telegram_chat_id: str
    telegram_send_delay_seconds: int
    alert_on_start: bool

    state_db_path: str
    max_items: int
    log_item_decisions: bool
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        keywords = [k.strip() for k in os.getenv("KEYWORDS", "").split(",") if k.strip()]
        return cls(
            target_url=os.getenv("TARGET_URL", "").strip(),
            reservation_year=_parse_int(os.getenv("RESERVATION_YEAR"), 2026),
            reservation_month=_parse_int(os.getenv("RESERVATION_MONTH"), 6),
            reservation_day=_parse_int(os.getenv("RESERVATION_DAY"), 3),
            reservation_theme=os.getenv("RESERVATION_THEME", "[홍대] 층간소음").strip(),
            keywords=keywords,
            use_keywords=_parse_bool(os.getenv("USE_KEYWORDS"), False),
            poll_interval_seconds=_parse_int(os.getenv("POLL_INTERVAL_SECONDS"), 60),
            seed_existing=_parse_bool(os.getenv("SEED_EXISTING"), True),
            item_selector=os.getenv("ITEM_SELECTOR") or None,
            title_selector=os.getenv("TITLE_SELECTOR") or None,
            link_selector=os.getenv("LINK_SELECTOR") or None,
            content_selector=os.getenv("CONTENT_SELECTOR") or None,
            user_agent=os.getenv(
                "USER_AGENT",
                "Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ),
            accept_language=os.getenv("ACCEPT_LANGUAGE", "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"),
            referer=os.getenv("REFERER") or None,
            cookie=os.getenv("COOKIE") or None,
            retry_on_403=_parse_bool(os.getenv("RETRY_ON_403"), False),

            headless=_parse_bool(os.getenv("HEADLESS"), True),
            browser_timeout_ms=_parse_int(os.getenv("BROWSER_TIMEOUT_MS"), 30000),
            interaction_wait_ms=_parse_int(os.getenv("INTERACTION_WAIT_MS"), 500),

            verify_ssl=_parse_bool(os.getenv("VERIFY_SSL"), True),
            ca_bundle_path=os.getenv("CA_BUNDLE_PATH") or None,
            http_proxy=os.getenv("HTTP_PROXY") or None,
            https_proxy=os.getenv("HTTPS_PROXY") or None,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
            telegram_send_delay_seconds=_parse_int(os.getenv("TELEGRAM_SEND_DELAY_SECONDS"), 1),
            alert_on_start=_parse_bool(os.getenv("ALERT_ON_START"), True),
            state_db_path=os.getenv("STATE_DB_PATH", "state.db"),
            max_items=_parse_int(os.getenv("MAX_ITEMS"), 30),
            log_item_decisions=_parse_bool(os.getenv("LOG_ITEM_DECISIONS"), False),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

    def proxies(self) -> Dict[str, str]:
        proxies: Dict[str, str] = {}
        if self.http_proxy:
            proxies["http"] = self.http_proxy
        if self.https_proxy:
            proxies["https"] = self.https_proxy
        return proxies
