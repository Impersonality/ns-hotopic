from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from shutil import which

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .config import AppPaths, DEFAULT_HOME_URL
from .models import CrawlResult
from .parser import looks_like_challenge_page, parse_homepage


READY_SELECTORS = (
    ".post-list-item",
    "a[href*='/post-']",
)


def run_trial_once(
    paths: AppPaths,
    page_url: str = DEFAULT_HOME_URL,
    wait_timeout_seconds: int = 180,
    keep_open: bool = False,
    headless: bool = False,
) -> CrawlResult:
    return _run_crawl(
        paths=paths,
        page_url=page_url,
        headless=headless,
        interactive=not headless,
        wait_timeout_seconds=wait_timeout_seconds,
        keep_open=keep_open,
    )


def run_fetch_once(
    paths: AppPaths,
    page_url: str = DEFAULT_HOME_URL,
    headless: bool = True,
) -> CrawlResult:
    if not paths.storage_state_path.exists():
        raise FileNotFoundError(
            f"Missing storage state file: {paths.storage_state_path}. "
            "Run `ns-hotopic trial-once` first."
        )

    return _run_crawl(
        paths=paths,
        page_url=page_url,
        headless=headless,
        interactive=False,
        wait_timeout_seconds=30,
        keep_open=False,
    )


def _run_crawl(
    *,
    paths: AppPaths,
    page_url: str,
    headless: bool,
    interactive: bool,
    wait_timeout_seconds: int,
    keep_open: bool,
) -> CrawlResult:
    started_at = _now()
    paths.ensure_directories()
    html_artifact_path: Path | None = None

    try:
        with sync_playwright() as playwright:
            launch_options = {
                "headless": headless,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            executable_path = _find_browser_executable()
            if executable_path is not None:
                launch_options["executable_path"] = executable_path
            browser = playwright.chromium.launch(**launch_options)

            context_options = {
                "viewport": {"width": 1440, "height": 1200},
                "locale": "zh-CN",
                "user_agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
                ),
            }
            if paths.storage_state_path.exists():
                context_options["storage_state"] = str(paths.storage_state_path)

            context = browser.new_context(**context_options)
            page = context.new_page()
            page.goto(page_url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(4_000)

            if interactive:
                print("A Chrome window has been opened for NodeSeek.")
                print("Complete the Cloudflare check in that window. Waiting for homepage content...")
                _wait_for_homepage(page, timeout_seconds=wait_timeout_seconds)
            else:
                page.wait_for_timeout(3_000)

            html = page.content()
            title = page.title()
            html_artifact_path = _write_html_artifact(paths, started_at, html)
            context.storage_state(path=str(paths.storage_state_path))
            snapshots = parse_homepage(html, page_url)

            if looks_like_challenge_page(title, html):
                status = "challenge"
                error_message = "Cloudflare challenge page detected."
            elif not snapshots:
                status = "parse_error"
                error_message = "No topic items were parsed from the homepage HTML."
            else:
                status = "success"
                error_message = None

            if keep_open and interactive:
                input("Press Enter to close the browser...")

            context.close()
            browser.close()

            return CrawlResult(
                started_at=started_at,
                finished_at=_now(),
                status=status,
                page_url=page_url,
                item_count=len(snapshots),
                page_title=title,
                error_message=error_message,
                html_artifact_path=html_artifact_path,
                snapshots=snapshots,
            )
    except (FileNotFoundError, PlaywrightError, PlaywrightTimeoutError) as exc:
        return CrawlResult(
            started_at=started_at,
            finished_at=_now(),
            status="network_error",
            page_url=page_url,
            item_count=0,
            page_title=None,
            error_message=str(exc),
            html_artifact_path=html_artifact_path,
            snapshots=[],
        )


def _wait_for_homepage(page: Page, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if _page_has_homepage_content(page):
            return
        page.wait_for_timeout(1_000)

    raise PlaywrightTimeoutError(
        f"Timed out after {timeout_seconds}s waiting for homepage content."
    )


def _page_has_homepage_content(page: Page) -> bool:
    for selector in READY_SELECTORS:
        if page.locator(selector).count() > 0:
            return True

    title = page.title()
    content = page.content()
    return not looks_like_challenge_page(title, content) and "/post-" in content


def _find_browser_executable() -> str | None:
    for candidate in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = which(candidate)
        if path:
            return path
    return None


def _write_html_artifact(paths: AppPaths, started_at: str, html: str) -> Path:
    timestamp = started_at.replace(":", "-").replace("+", "_")
    artifact_path = paths.artifacts_dir / f"homepage_{timestamp}.html"
    artifact_path.write_text(html, encoding="utf-8")

    latest_path = paths.artifacts_dir / "latest_homepage.html"
    latest_path.write_text(html, encoding="utf-8")

    metadata_path = paths.artifacts_dir / "latest_artifact.json"
    metadata_path.write_text(
        json.dumps({"started_at": started_at, "path": str(artifact_path)}, indent=2),
        encoding="utf-8",
    )
    return artifact_path


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
