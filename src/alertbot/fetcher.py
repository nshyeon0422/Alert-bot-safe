from __future__ import annotations

import logging
from http.cookies import SimpleCookie
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import Config

LOGGER = logging.getLogger(__name__)


def _build_session(config: Config) -> requests.Session:
    session = requests.Session()

    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    headers = {
        "User-Agent": config.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": config.accept_language,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if config.referer:
        headers["Referer"] = config.referer
    session.headers.update(headers)

    if config.cookie:
        cookie = SimpleCookie()
        cookie.load(config.cookie)
        for key, morsel in cookie.items():
            session.cookies.set(key, morsel.value)

    return session


def _verify_setting(config: Config) -> Optional[bool | str]:
    if config.ca_bundle_path:
        return config.ca_bundle_path
    return config.verify_ssl


def fetch_html(config: Config) -> str:
    if not config.target_url:
        raise ValueError("TARGET_URL is required")

    session = _build_session(config)
    verify_setting = _verify_setting(config)

    response = session.get(
        config.target_url,
        timeout=15,
        verify=verify_setting,
        proxies=config.proxies() or None,
    )

    if response.status_code == 403:
        LOGGER.error("Received 403 Forbidden from target URL: %s", config.target_url)

    response.raise_for_status()
    return response.text
