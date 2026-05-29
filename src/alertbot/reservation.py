from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .config import Config
from .notifier import TelegramNotifier

LOGGER = logging.getLogger(__name__)

MONTH_LABEL_RE = re.compile(r"(?P<month>\d{1,2})월,\s*(?P<year>\d{4})")
TIMEOUT_SCALE = 1000


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


def _normalize_month_label(label: str) -> str:
    return re.sub(r"\s+", " ", label or "").strip()



def _build_driver(config: Config, profile_dir: str):
    options = ChromeOptions()
    if config.headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument(f"--user-agent={config.user_agent}")
    options.add_argument("--lang=ko-KR")
    
    # ⭐️ 라즈베리파이 크로미움 위치 강제 지정 
    browser_binary = shutil.which("chromium") or shutil.which("chromium-browser")
    if browser_binary:
        options.binary_location = browser_binary

    options.add_argument(f"--user-data-dir={profile_dir}")

    # ⭐️ 디버그 로그가 확실히 적용되도록 통합
    service_path = shutil.which("chromedriver")
    if service_path:
        service = ChromeService(executable_path=service_path, service_args=['--verbose', '--log-path=/home/pi/chromedriver_debug.log'])
    else:
        service = ChromeService(service_args=['--verbose', '--log-path=/home/pi/chromedriver_debug.log'])

    return webdriver.Chrome(service=service, options=options)


@contextmanager
def _driver_session(config: Config):
    # 세션 시작 시 임시 폴더 생성
    profile_dir = tempfile.mkdtemp(prefix="alertbot-chrome-")
    driver = _build_driver(config, profile_dir)
    try:
        driver.set_page_load_timeout(max(config.browser_timeout_ms / TIMEOUT_SCALE, 10))
        yield driver
    finally:
        driver.quit()
        # ⭐️ 세션 종료 시 임시 폴더 깔끔하게 삭제 (용량 폭발 방지)
        shutil.rmtree(profile_dir, ignore_errors=True)


def _wait(driver, timeout_ms: int) -> WebDriverWait:
    return WebDriverWait(driver, max(timeout_ms / TIMEOUT_SCALE, 1))


def _js_click(driver, element) -> None:
    driver.execute_script("arguments[0].click();", element)


def _select_month(driver, target_year: int, target_month: int, timeout_ms: int) -> str:
    target_label = f"{target_month}월, {target_year}"
    last_label = None

    for _ in range(24):
        current_label = _normalize_month_label(driver.find_element(By.CSS_SELECTOR, ".datepicker--nav-title").text or "")
        last_label = current_label
        LOGGER.info("Calendar month: %s -> target: %s", current_label, target_label)
        if current_label == target_label:
            return current_label

        current_year, current_month = _parse_month_label(current_label)
        nav_actions = driver.find_elements(By.CSS_SELECTOR, ".datepicker--nav-action")
        LOGGER.info(
            "Month navigation action: %s / %s",
            nav_actions[0].get_attribute("class") if nav_actions else "-",
            nav_actions[-1].get_attribute("class") if nav_actions else "-",
        )

        if (current_year, current_month) < (target_year, target_month):
            LOGGER.info("Clicking next month")
            _js_click(driver, nav_actions[-1])
        else:
            LOGGER.info("Clicking previous month")
            _js_click(driver, nav_actions[0])

        _wait(driver, timeout_ms).until(
            lambda current_driver: _normalize_month_label(current_driver.find_element(By.CSS_SELECTOR, ".datepicker--nav-title").text or "") != current_label
        )

    raise RuntimeError(f"Failed to navigate to target month: {target_label} (last seen: {last_label})")


def _select_date(driver, target_day: int, timeout_ms: int) -> None:
    LOGGER.info("Selecting day: %s", target_day)
    clicked = driver.execute_script(
        """
        const targetDay = String(arguments[0]);
        const cells = Array.from(document.querySelectorAll('.datepicker--cell-day'));
        const target = cells.find((cell) => {
            const text = String(cell.textContent || '').trim();
            const className = String(cell.className || '');
            return text === targetDay && !className.includes('-disabled-') && !className.includes('-other-month-');
        });

        if (!target) {
            return false;
        }

        target.click();
        return true;
        """,
        target_day,
    )

    if not clicked:
        raise RuntimeError(f"Could not find selectable date: {target_day}")

    _wait(driver, timeout_ms).until(
        lambda current_driver: current_driver.execute_script(
            """
            const targetDay = String(arguments[0]);
            return Array.from(document.querySelectorAll('.datepicker--cell-day')).some((cell) => {
                const text = String(cell.textContent || '').trim();
                const className = String(cell.className || '');
                return text === targetDay && className.includes('-selected-');
            });
            """,
            target_day,
        )
    )
    LOGGER.info("Day selected: %s", target_day)


def _select_theme(driver, theme_name: str, timeout_ms: int) -> None:
    LOGGER.info("Selecting theme: %s", theme_name)
    inputs = driver.find_elements(By.CSS_SELECTOR, 'input[name="themePK"]')
    target = None
    for input_element in inputs:
        label = input_element.find_element(By.XPATH, "./following-sibling::*[1]")
        label_text = (label.text or "").replace(" ", "")
        if label_text == theme_name.replace(" ", ""):
            target = input_element
            break

    if target is None:
        raise RuntimeError(f"Could not find theme: {theme_name}")

    try:
        target.find_element(By.XPATH, "./following-sibling::*[1]").click()
    except (NoSuchElementException, WebDriverException):
        target.click()

    _wait(driver, timeout_ms).until(lambda _: target.is_selected())
    LOGGER.info("Theme selected: %s", theme_name)


def _collect_time_slots(driver) -> list[dict[str, object]]:
    LOGGER.info("Collecting reservation time slots")
    slots = []
    inputs = driver.find_elements(By.CSS_SELECTOR, 'input[name="reservationTime"]')
    for input_element in inputs:
        label = input_element.find_element(By.XPATH, "./parent::label")
        label_text = (label.text or input_element.get_attribute("aria-label") or "").strip()
        label_class = label.get_attribute("class") or ""
        enabled = input_element.is_enabled()
        available = enabled and "hover2" in label_class and "active" not in label_class
        slots.append(
            {
                "label": label_text,
                "value": input_element.get_attribute("value") or "",
                "disabled": not enabled,
                "checked": input_element.is_selected(),
                "labelClass": label_class,
                "enabled": enabled,
                "available": available,
            }
        )
        LOGGER.info(
            "Slot inspect: label=%s value=%s enabled=%s class=%s -> %s",
            label_text,
            input_element.get_attribute("value") or "",
            enabled,
            label_class or "-",
            "open" if available else "closed",
        )

    if not slots:
        raise RuntimeError("No reservation time slots were found")

    LOGGER.info(
        "Time slots: %s",
        ", ".join(
            f"{slot['label']}[{('open' if slot['available'] else 'closed')}]"
            for slot in slots
            if slot["label"]
        ),
    )
    return slots


def inspect_reservation(config: Config) -> ReservationSnapshot:
    if not config.target_url:
        raise ValueError("TARGET_URL is required")
    if not config.reservation_theme:
        raise ValueError("RESERVATION_THEME is required")

    reservation_date = f"{config.reservation_year:04d}-{config.reservation_month:02d}-{config.reservation_day:02d}"

    with _driver_session(config) as driver:
        LOGGER.info(
            "Starting inspection for %04d-%02d-%02d / %s",
            config.reservation_year,
            config.reservation_month,
            config.reservation_day,
            config.reservation_theme,
        )
        driver.get(config.target_url)
        _wait(driver, config.browser_timeout_ms).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".datepicker--nav-title")))
        _wait(driver, config.browser_timeout_ms).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="themePK"]')))
        _wait(driver, config.browser_timeout_ms).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="reservationTime"]')))

        month_label = _select_month(
            driver,
            config.reservation_year,
            config.reservation_month,
            config.browser_timeout_ms,
        )
        _select_date(driver, config.reservation_day, config.browser_timeout_ms)
        _select_theme(driver, config.reservation_theme, config.browser_timeout_ms)

        slots = _collect_time_slots(driver)
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
    previous_state = state_store.load() # 이전 상태 불러오기
    snapshot = inspect_reservation(config)
    current_status = "open" if snapshot.is_open else "closed"

    if snapshot.is_open:
        # 이전에 닫혀 있었거나 기록이 없을 때만 알림 전송
        if previous_state.last_status != "open":
            notifier.send_message(build_alert_message(config, snapshot))
            LOGGER.warning("Reservation opened! Alert sent.")
        else:
            LOGGER.info("Reservation is still open. Skipped duplicate alert.")
    else:
        LOGGER.info("Reservation is closed.")

    # 현재 상태 저장
    state_store.save(ReservationState(last_status=current_status))