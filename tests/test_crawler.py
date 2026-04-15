from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ns_hotopic.config import AppPaths
from ns_hotopic.crawler import run_fetch_once, run_trial_once
from ns_hotopic.models import TopicSnapshot


class FakePage:
    def __init__(self, *, title: str, html: str) -> None:
        self._title = title
        self._html = html

    def goto(self, page_url: str, wait_until: str, timeout: int) -> None:
        self.page_url = page_url
        self.wait_until = wait_until
        self.timeout = timeout

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.waited_for = milliseconds

    def title(self) -> str:
        return self._title

    def content(self) -> str:
        return self._html


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.storage_state_calls: list[str] = []

    def new_page(self) -> FakePage:
        return self.page

    def storage_state(self, path: str) -> None:
        self.storage_state_calls.append(path)

    def close(self) -> None:
        return None


class FakeBrowser:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.context_options: dict[str, object] | None = None

    def new_context(self, **kwargs: object) -> FakeContext:
        self.context_options = kwargs
        return self.context

    def close(self) -> None:
        return None


class FakeChromium:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.launch_options: dict[str, object] | None = None

    def launch(self, **kwargs: object) -> FakeBrowser:
        self.launch_options = kwargs
        return self.browser


class FakePlaywrightManager:
    def __init__(self, chromium: FakeChromium) -> None:
        self._chromium = chromium

    def __enter__(self) -> SimpleNamespace:
        return SimpleNamespace(chromium=self._chromium)

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        artifacts_dir=tmp_path / "artifacts",
        db_path=tmp_path / "data" / "ns_hotopic.db",
        storage_state_path=tmp_path / "state" / "storage_state.json",
    )


def install_fake_browser(monkeypatch, *, title: str, html: str):
    page = FakePage(title=title, html=html)
    context = FakeContext(page)
    browser = FakeBrowser(context)
    chromium = FakeChromium(browser)
    manager = FakePlaywrightManager(chromium)

    monkeypatch.setattr("ns_hotopic.crawler.sync_playwright", lambda: manager)
    monkeypatch.setattr("ns_hotopic.crawler._find_browser_executable", lambda: None)
    monkeypatch.setattr(
        "ns_hotopic.crawler._write_html_artifact",
        lambda paths, started_at, html: paths.artifacts_dir / "latest.html",
    )
    monkeypatch.setattr(
        "ns_hotopic.crawler._now",
        lambda: "2026-04-15T12:00:00+08:00",
    )
    return browser, context


def test_run_fetch_once_uses_storage_state_without_overwriting_it(tmp_path: Path, monkeypatch) -> None:
    paths = make_paths(tmp_path)
    paths.ensure_directories()
    paths.storage_state_path.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
    browser, context = install_fake_browser(
        monkeypatch,
        title="NodeSeek",
        html="<html><body><a href='/post-12345-1'>topic</a></body></html>",
    )
    monkeypatch.setattr(
        "ns_hotopic.crawler.parse_homepage",
        lambda html, base_url: [
            TopicSnapshot(
                position=1,
                topic_id="12345",
                title="topic",
                url="https://www.nodeseek.com/post-12345-1",
            )
        ],
    )

    result = run_fetch_once(paths=paths)

    assert result.status == "success"
    assert browser.context_options is not None
    assert browser.context_options["storage_state"] == str(paths.storage_state_path)
    assert context.storage_state_calls == []


def test_run_trial_once_persists_storage_state_after_success(tmp_path: Path, monkeypatch) -> None:
    paths = make_paths(tmp_path)
    browser, context = install_fake_browser(
        monkeypatch,
        title="NodeSeek",
        html="<html><body><a href='/post-12345-1'>topic</a></body></html>",
    )
    monkeypatch.setattr(
        "ns_hotopic.crawler.parse_homepage",
        lambda html, base_url: [
            TopicSnapshot(
                position=1,
                topic_id="12345",
                title="topic",
                url="https://www.nodeseek.com/post-12345-1",
            )
        ],
    )

    result = run_trial_once(paths=paths, headless=True)

    assert result.status == "success"
    assert browser.context_options is not None
    assert "storage_state" not in browser.context_options
    assert context.storage_state_calls == [str(paths.storage_state_path)]


def test_run_trial_once_does_not_persist_challenge_state(tmp_path: Path, monkeypatch) -> None:
    paths = make_paths(tmp_path)
    _, context = install_fake_browser(
        monkeypatch,
        title="Just a moment...",
        html="<html><body>Performing security verification</body></html>",
    )
    monkeypatch.setattr("ns_hotopic.crawler.parse_homepage", lambda html, base_url: [])

    result = run_trial_once(paths=paths, headless=True)

    assert result.status == "challenge"
    assert context.storage_state_calls == []
