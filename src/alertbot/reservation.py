from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

from .config import Config
from .notifier import TelegramNotifier

LOGGER = logging.getLogger(__name__)

MONTH_LABEL_RE = re.compile(r"(?P<month>\d{1,2})월,\s*(?P<year>\d{4})")


@dataclass(frozen=True)
class ReservationSnapshot:
    reservation_date: str
    theme_name: str
    month_label: str
    available_times: tuple[str, ...]
    is_open: bool


@dataclass(frozen=True)
class ReservationState:
    last_status: Optional[str] = None


class StateStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> ReservationState:
        if not self.path.exists():
            return ReservationState()

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("Failed to load state file: %s", self.path)
            return ReservationState()

        return ReservationState(last_status=data.get("last_status"))

    def save(self, state: ReservationState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"last_status": state.last_status}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _parse_month_label(label: str) -> tuple[int, int]:
    match = MONTH_LABEL_RE.search(label or "")
    if not match:
        raise ValueError(f"Could not parse month label: {label!r}")
    return int(match.group("year")), int(match.group("month"))


def _select_month(page, target_year: int, target_month: int, timeout_ms: int) -> str:
    target_label = f"{target_month}월, {target_year}"

    for _ in range(24):
        current_label = (page.locator(".datepicker--nav-title").text_content() or "").strip()
        if current_label == target_label:
            return current_label

        current_year, current_month = _parse_month_label(current_label)
        nav_actions = page.locator(".datepicker--nav-action")

        if (current_year, current_month) < (target_year, target_month):
            nav_actions.last.click(timeout=timeout_ms)
        else:
            nav_actions.first.click(timeout=timeout_ms)

        page.wait_for_timeout(200)

    raise RuntimeError(f"Failed to navigate to target month: {target_label}")


def _select_date(page, target_day: int, timeout_ms: int) -> None:
    success = page.locator(".datepicker--cell-day").evaluate_all(
        """
        (cells, day) => {
            const targetDay = String(day);
            const target = cells.find((cell) => {
                const text = (cell.textContent || '').trim();
                const className = String(cell.className || '');
                return text === targetDay && !className.includes('-disabled-') && !className.includes('-other-month-');
            });

            if (!target) {
                return false;
            }

            target.click();
            return true;
        }
        """,
        target_day,
    )

    if not success:
        raise RuntimeError(f"Could not find selectable date: {target_day}")

    page.wait_for_timeout(timeout_ms // 10 if timeout_ms >= 10 else 10)


def _select_theme(page, theme_name: str, timeout_ms: int) -> None:
    success = page.locator('input[name="themePK"]').evaluate_all(
        """
        (inputs, theme) => {
            const normalize = (text) => String(text || '').replace(/\\s+/g, '');
            const wanted = normalize(theme);
            const target = inputs.find((input) => {
                const label = input.nextElementSibling?.textContent || input.parentElement?.textContent || '';
                return normalize(label) === wanted;
            });

            if (!target) {
                return false;
            }

            const label = target.closest('label') || target.parentElement;
            if (label) {
                label.click();
            } else {
                target.click();
            }

            return target.checked;
        }
        """,
        theme_name,
    )

    if not success:
        raise RuntimeError(f"Could not find theme: {theme_name}")

    page.wait_for_timeout(timeout_ms // 10 if timeout_ms >= 10 else 10)


def _collect_time_slots(page) -> list[dict[str, object]]:
    slots = page.locator('input[name="reservationTime"]').evaluate_all(
        """
        (inputs) => inputs.map((input) => {
            const label = (input.nextElementSibling?.textContent || input.parentElement?.textContent || input.getAttribute('aria-label') || '').trim();
            const labelClass = String(input.nextElementSibling?.className || input.parentElement?.className || '');
            return {
                label,
                value: input.value || '',
                disabled: Boolean(input.disabled),
                checked: Boolean(input.checked),
                labelClass,
                available: labelClass.includes('hover2') && !labelClass.includes('active'),
            };
        })
        """
    )

    if not slots:
        raise RuntimeError("No reservation time slots were found")

    return slots


def inspect_reservation(config: Config) -> ReservationSnapshot:
    if not config.target_url:
        raise ValueError("TARGET_URL is required")
    if not config.reservation_theme:
        raise ValueError("RESERVATION_THEME is required")

    reservation_date = f"{config.reservation_year:04d}-{config.reservation_month:02d}-{config.reservation_day:02d}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=config.headless)
        context = browser.new_context(
            user_agent=config.user_agent,
            locale="ko-KR",
            ignore_https_errors=not config.verify_ssl,
        )
        page = context.new_page()

        try:
            page.goto(config.target_url, wait_until="domcontentloaded", timeout=config.browser_timeout_ms)
            page.wait_for_selector(".datepicker--nav-title", timeout=config.browser_timeout_ms)
            page.wait_for_selector('input[name="themePK"]', timeout=config.browser_timeout_ms)
            page.wait_for_selector('input[name="reservationTime"]', timeout=config.browser_timeout_ms)

            month_label = _select_month(
                page,
                config.reservation_year,
                config.reservation_month,
                config.browser_timeout_ms,
            )
            _select_date(page, config.reservation_day, config.browser_timeout_ms)
            _select_theme(page, config.reservation_theme, config.browser_timeout_ms)
            page.wait_for_timeout(config.interaction_wait_ms)

            slots = _collect_time_slots(page)
            available_times = tuple(
                slot["label"]
                for slot in slots
                if slot["label"] and slot["available"]
            )

            if config.log_item_decisions:
                LOGGER.info(
                    "Reservation inspected: date=%s theme=%s month=%s open=%s available_times=%s",
                    reservation_date,
                    config.reservation_theme,
                    month_label,
                    bool(available_times),
                    ", ".join(available_times) or "-",
                )

            return ReservationSnapshot(
                reservation_date=reservation_date,
                theme_name=config.reservation_theme,
                month_label=month_label,
                available_times=available_times,
                is_open=bool(available_times),
            )
        finally:
            context.close()
            browser.close()


def build_alert_message(config: Config, snapshot: ReservationSnapshot) -> str:
    available_times = ", ".join(snapshot.available_times) if snapshot.available_times else "없음"
    return (
        "제로월드 홍대점 예약 알림\n"
        f"날짜: {snapshot.reservation_date}\n"
        f"테마: {snapshot.theme_name}\n"
        f"열린 시간: {available_times}\n"
        f"상태: {'오픈' if snapshot.is_open else '미오픈'}\n"
        f"페이지: {config.target_url}"
    )


def run_once(config: Config, notifier: TelegramNotifier, state_store: StateStore) -> None:
    snapshot = inspect_reservation(config)
    state = state_store.load()
    current_status = "open" if snapshot.is_open else "closed"

    if current_status == state.last_status:
        return

    if not snapshot.is_open:
        state_store.save(ReservationState(last_status=current_status))
        return

    if state.last_status is None and not config.alert_on_start:
        LOGGER.info("Reservation is open on first check, alert suppressed by ALERT_ON_START=false")
        state_store.save(ReservationState(last_status=current_status))
        return

    notifier.send_message(build_alert_message(config, snapshot))
    state_store.save(ReservationState(last_status=current_status))
    LOGGER.warning("Reservation is open; alert sent")