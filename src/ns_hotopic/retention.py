from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .config import AppPaths, get_settings
from .storage import (
    connect,
    delete_expired_bot_delivery_logs,
    delete_expired_crawl_runs,
    delete_expired_hot_topic_rankings,
    delete_expired_hot_topic_runs,
    delete_expired_topic_snapshots,
    vacuum,
)

@dataclass(slots=True)
class CleanupResult:
    deleted_topic_snapshots: int
    deleted_crawl_runs: int
    deleted_hot_topic_rankings: int
    deleted_hot_topic_runs: int
    deleted_bot_delivery_logs: int
    deleted_artifacts: int
    vacuumed: bool


def cleanup_expired_data(
    paths: AppPaths,
    *,
    now: datetime | None = None,
    run_vacuum: bool = False,
) -> CleanupResult:
    reference = now or datetime.now().astimezone()
    settings = get_settings()
    crawl_cutoff = (reference - timedelta(days=settings.crawl_retention_days)).isoformat(timespec="seconds")
    hot_cutoff = (reference - timedelta(days=settings.hot_topic_retention_days)).isoformat(timespec="seconds")
    delivery_cutoff = (
        reference - timedelta(days=settings.bot_delivery_log_retention_days)
    ).isoformat(timespec="seconds")
    artifact_cutoff = reference - timedelta(days=settings.artifact_retention_days)

    connection = connect(paths)
    deleted_topic_snapshots = delete_expired_topic_snapshots(connection, crawl_cutoff)
    deleted_crawl_runs = delete_expired_crawl_runs(connection, crawl_cutoff)
    deleted_hot_topic_rankings = delete_expired_hot_topic_rankings(connection, hot_cutoff)
    deleted_hot_topic_runs = delete_expired_hot_topic_runs(connection, hot_cutoff)
    deleted_bot_delivery_logs = delete_expired_bot_delivery_logs(connection, delivery_cutoff)
    deleted_artifacts = _delete_expired_artifacts(paths.artifacts_dir, cutoff=artifact_cutoff)

    if run_vacuum:
        vacuum(connection)

    return CleanupResult(
        deleted_topic_snapshots=deleted_topic_snapshots,
        deleted_crawl_runs=deleted_crawl_runs,
        deleted_hot_topic_rankings=deleted_hot_topic_rankings,
        deleted_hot_topic_runs=deleted_hot_topic_runs,
        deleted_bot_delivery_logs=deleted_bot_delivery_logs,
        deleted_artifacts=deleted_artifacts,
        vacuumed=run_vacuum,
    )


def _delete_expired_artifacts(artifacts_dir: Path, *, cutoff: datetime) -> int:
    if not artifacts_dir.exists():
        return 0

    deleted = 0
    for artifact in artifacts_dir.iterdir():
        if not artifact.is_file():
            continue
        modified_at = datetime.fromtimestamp(artifact.stat().st_mtime, tz=cutoff.tzinfo)
        if modified_at < cutoff:
            artifact.unlink(missing_ok=True)
            deleted += 1
    return deleted
