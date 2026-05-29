from __future__ import annotations

import hashlib
from urllib.parse import urljoin
from dataclasses import dataclass
from typing import List, Optional

from bs4 import BeautifulSoup

from .config import Config


@dataclass(frozen=True)
class ParsedItem:
    title: str
    link: Optional[str]
    content: str
    content_hash: str


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _select_text(element, selector: Optional[str]) -> str:
    if selector:
        found = element.select_one(selector)
        if found:
            return found.get_text(strip=True)
    return element.get_text(strip=True)


def _select_link(element, selector: Optional[str]) -> Optional[str]:
    if selector:
        found = element.select_one(selector)
        if found and found.get("href"):
            return found.get("href")
    anchor = element.find("a")
    if anchor and anchor.get("href"):
        return anchor.get("href")
    return None


def _normalize_link(link: Optional[str], config: Config) -> Optional[str]:
    if not link:
        return None
    return urljoin(config.target_url, link)


def parse_items(html: str, config: Config) -> List[ParsedItem]:
    soup = BeautifulSoup(html, "html.parser")

    if config.item_selector:
        elements = soup.select(config.item_selector)
    else:
        elements = []

    if not elements:
        text = soup.get_text(" ", strip=True)
        content_hash = _hash_text(text)
        return [ParsedItem(title="Page Update", link=config.target_url, content=text, content_hash=content_hash)]

    items: List[ParsedItem] = []
    for element in elements:
        title = _select_text(element, config.title_selector) or "(no title)"
        content = _select_text(element, config.content_selector) if config.content_selector else element.get_text(" ", strip=True)
        link = _normalize_link(_select_link(element, config.link_selector), config)
        content_hash = _hash_text(f"{title}|{link}|{content}")
        items.append(ParsedItem(title=title, link=link, content=content, content_hash=content_hash))

    return items
