"""Fetch a page with headless Chromium and pull out the watched text."""

from __future__ import annotations

import re
from dataclasses import dataclass

from playwright.sync_api import Browser, Page
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .config import Watch

# Longest wait for network activity to stop after the load event.
NETWORK_IDLE_CAP_SECONDS = 10.0
# Screenshots stop at this height. Chromium cannot capture much taller pages
# in one image; the text of the whole page is still compared.
MAX_SCREENSHOT_HEIGHT = 20000


class FetchError(Exception):
    """A check that could not produce trustworthy text."""


@dataclass(frozen=True)
class Capture:
    text: str
    screenshot: bytes


def normalise(text: str, ignore: tuple[str, ...]) -> str:
    """Remove ignored patterns, trim each line and drop blank lines."""
    for pattern in ignore:
        text = re.sub(pattern, "", text)
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _first_line(exc: PlaywrightError) -> str:
    return (exc.message or str(exc)).splitlines()[0]


def _read(page: Page, watch: Watch, timeout_seconds: float) -> Capture:
    timeout_ms = timeout_seconds * 1000
    try:
        response = page.goto(watch.url, timeout=timeout_ms, wait_until="load")
    except PlaywrightTimeout as exc:
        raise FetchError(f"timed out after {timeout_seconds:g}s") from exc
    except PlaywrightError as exc:
        raise FetchError(f"could not load page: {_first_line(exc)}") from exc
    if response is None:
        raise FetchError("no response from server")
    if response.status >= 400:
        raise FetchError(f"HTTP {response.status}")

    # Give scripts that fetch data after the load event time to finish.
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_seconds, NETWORK_IDLE_CAP_SECONDS) * 1000)
    except PlaywrightTimeout:
        pass  # pages that poll forever never go idle; read what is there
    if watch.wait_for:
        try:
            page.wait_for_selector(watch.wait_for, timeout=timeout_ms)
        except PlaywrightTimeout as exc:
            raise FetchError(f"wait_for element did not appear: {watch.wait_for}") from exc
    if watch.settle_seconds:
        page.wait_for_timeout(watch.settle_seconds * 1000)

    if watch.selector:
        target = page.locator(watch.selector)
        if target.count() == 0:
            raise FetchError(f"selector not found: {watch.selector}")
        raw = "\n".join(target.all_inner_texts())
    else:
        raw = page.inner_text("body")

    try:
        height = page.evaluate("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
        if height > MAX_SCREENSHOT_HEIGHT:
            clip = {"x": 0, "y": 0, "width": 1280, "height": MAX_SCREENSHOT_HEIGHT}
            shot = page.screenshot(full_page=True, clip=clip)
        else:
            shot = page.screenshot(full_page=True)
    except PlaywrightError as exc:
        raise FetchError(f"screenshot failed: {_first_line(exc)}") from exc
    return Capture(text=normalise(raw, watch.ignore), screenshot=shot)


def capture(browser: Browser, watch: Watch, timeout_seconds: float) -> Capture:
    """Load the page and return its watched text and a full-page screenshot.

    Any browser error becomes a FetchError. On Ctrl+C the page is left open on
    purpose: closing it after an interrupt can hang, and the process is exiting.
    """
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    try:
        result = _read(page, watch, timeout_seconds)
    except PlaywrightError as exc:
        _close(page)
        raise FetchError(_first_line(exc)) from exc
    except Exception:
        _close(page)
        raise
    _close(page)
    return result


def _close(page: Page) -> None:
    try:
        page.close()
    except PlaywrightError:
        pass
