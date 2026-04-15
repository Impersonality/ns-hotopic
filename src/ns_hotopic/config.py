from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_HOME_URL = "https://www.nodeseek.com/"
CHALLENGE_MARKERS = (
    "Just a moment...",
    "Performing security verification",
    "Enable JavaScript and cookies to continue",
    "This website uses a security service to protect against malicious bots.",
)


@dataclass(frozen=True, slots=True)
class Settings:
    root_dir: Path
    home_url: str
    telegram_bot_token: str | None
    crawl_retention_days: int
    hot_topic_retention_days: int
    bot_delivery_log_retention_days: int
    artifact_retention_days: int
    fetch_interval_minutes: int
    delivery_check_interval_minutes: int
    cleanup_interval_minutes: int


@dataclass(frozen=True, slots=True)
class AppPaths:
    root_dir: Path
    data_dir: Path
    state_dir: Path
    artifacts_dir: Path
    db_path: Path
    storage_state_path: Path

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)


def discover_root_dir() -> Path:
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate

    return Path(__file__).resolve().parents[2]


def load_project_dotenv(root_dir: Path | None = None) -> Path | None:
    candidate_root = root_dir or discover_root_dir()
    dotenv_path = candidate_root / ".env"
    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=False)
        return dotenv_path
    return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    discovered_root = discover_root_dir()
    load_project_dotenv(discovered_root)

    root_override = os.getenv("NS_HOTOPIC_HOME")
    root_dir = (
        Path(root_override).expanduser().resolve()
        if root_override
        else discovered_root
    )

    return Settings(
        root_dir=root_dir,
        home_url=os.getenv("NODESEEK_HOME_URL", DEFAULT_HOME_URL),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        crawl_retention_days=_get_int_env("NS_HOTOPIC_CRAWL_RETENTION_DAYS", 60),
        hot_topic_retention_days=_get_int_env("NS_HOTOPIC_HOT_RETENTION_DAYS", 180),
        bot_delivery_log_retention_days=_get_int_env("NS_HOTOPIC_BOT_LOG_RETENTION_DAYS", 30),
        artifact_retention_days=_get_int_env("NS_HOTOPIC_ARTIFACT_RETENTION_DAYS", 7),
        fetch_interval_minutes=_get_int_env("NS_HOTOPIC_FETCH_INTERVAL_MINUTES", 30),
        delivery_check_interval_minutes=_get_int_env("NS_HOTOPIC_DELIVERY_CHECK_INTERVAL_MINUTES", 5),
        cleanup_interval_minutes=_get_int_env("NS_HOTOPIC_CLEANUP_INTERVAL_MINUTES", 1440),
    )


def get_app_paths() -> AppPaths:
    settings = get_settings()
    root_dir = settings.root_dir
    data_dir = root_dir / "data"
    state_dir = root_dir / "state"
    artifacts_dir = root_dir / "artifacts"
    return AppPaths(
        root_dir=root_dir,
        data_dir=data_dir,
        state_dir=state_dir,
        artifacts_dir=artifacts_dir,
        db_path=data_dir / "ns_hotopic.db",
        storage_state_path=state_dir / "storage_state.json",
    )


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer.") from exc
