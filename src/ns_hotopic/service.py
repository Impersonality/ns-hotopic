from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass
from typing import Callable

from .config import AppPaths, get_app_paths, get_settings
from .crawler import run_fetch_once
from .hot_topics import calculate_and_store_hot_topics
from .retention import cleanup_expired_data
from .storage import connect, save_crawl_result
from .telegram_bot import run_bot, run_due_notifications


@dataclass(frozen=True, slots=True)
class ServiceIntervals:
    fetch_seconds: int
    delivery_check_seconds: int
    cleanup_seconds: int


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    name: str
    interval_seconds: int
    action: Callable[[], None]


def run_service(paths: AppPaths | None = None) -> None:
    app_paths = paths or get_app_paths()
    validate_service_prerequisites(app_paths)
    intervals = get_service_intervals()

    stop_event = threading.Event()
    scheduler = threading.Thread(
        target=run_scheduler_loop,
        kwargs={
            "paths": app_paths,
            "intervals": intervals,
            "stop_event": stop_event,
        },
        name="ns-hotopic-scheduler",
        daemon=True,
    )
    scheduler.start()
    log_service_event(
        "info",
        (
            "service started "
            f"(fetch={intervals.fetch_seconds}s, "
            f"delivery={intervals.delivery_check_seconds}s, "
            f"cleanup={intervals.cleanup_seconds}s)"
        ),
    )

    try:
        run_bot(app_paths)
    finally:
        stop_event.set()
        scheduler.join(timeout=10)
        log_service_event("info", "service stopped")


def validate_service_prerequisites(paths: AppPaths) -> None:
    if paths.storage_state_path.exists():
        return
    raise RuntimeError(
        "Missing state/storage_state.json. "
        "Run `ns-hotopic trial-once` in a visible browser first, "
        "then upload the generated file before starting `service-run`."
    )


def get_service_intervals() -> ServiceIntervals:
    settings = get_settings()
    return ServiceIntervals(
        fetch_seconds=settings.fetch_interval_minutes * 60,
        delivery_check_seconds=settings.delivery_check_interval_minutes * 60,
        cleanup_seconds=settings.cleanup_interval_minutes * 60,
    )


def build_service_tasks(paths: AppPaths, intervals: ServiceIntervals) -> list[ScheduledTask]:
    return [
        ScheduledTask(
            name="fetch",
            interval_seconds=intervals.fetch_seconds,
            action=lambda: run_fetch_cycle(paths),
        ),
        ScheduledTask(
            name="deliver",
            interval_seconds=intervals.delivery_check_seconds,
            action=lambda: run_delivery_cycle(paths),
        ),
        ScheduledTask(
            name="cleanup",
            interval_seconds=intervals.cleanup_seconds,
            action=lambda: run_cleanup_cycle(paths),
        ),
    ]


def run_scheduler_loop(
    *,
    paths: AppPaths,
    intervals: ServiceIntervals,
    stop_event: threading.Event,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    tasks = build_service_tasks(paths, intervals)
    next_run_at = {task.name: 0.0 for task in tasks}

    while not stop_event.is_set():
        now = monotonic()
        execute_due_tasks(tasks, next_run_at, now=now)
        next_due = min(next_run_at.values(), default=now + 1)
        timeout = max(next_due - monotonic(), 0.5)
        stop_event.wait(timeout=timeout)


def execute_due_tasks(
    tasks: list[ScheduledTask],
    next_run_at: dict[str, float],
    *,
    now: float,
) -> None:
    for task in tasks:
        if now < next_run_at.get(task.name, 0.0):
            continue
        log_service_event("info", f"task start: {task.name}")
        try:
            task.action()
        except Exception as exc:  # noqa: BLE001
            log_service_event("error", f"task failed: {task.name}: {exc}")
            traceback.print_exc()
        else:
            log_service_event("info", f"task done: {task.name}")
        next_run_at[task.name] = now + task.interval_seconds


def run_fetch_cycle(paths: AppPaths) -> None:
    settings = get_settings()
    result = run_fetch_once(
        paths=paths,
        page_url=settings.home_url,
        headless=True,
    )

    connection = connect(paths)
    run_id = save_crawl_result(connection, result)
    log_service_event(
        "info",
        f"saved crawl run #{run_id} status={result.status} items={result.item_count}",
    )

    if result.status != "success":
        if result.error_message:
            log_service_event("warn", result.error_message)
        return

    hot_topic_run_id, hot_result = calculate_and_store_hot_topics(
        connection,
        source_crawl_run_id=run_id,
        computed_at=result.started_at,
    )
    log_service_event(
        "info",
        f"saved hot run #{hot_topic_run_id} candidates={hot_result.candidate_count} ranked={hot_result.ranking_count}",
    )


def run_delivery_cycle(paths: AppPaths) -> None:
    summary = run_due_notifications(paths)
    log_service_event(
        "info",
        (
            "delivery checked="
            f"{summary.checked} delivered={summary.delivered} "
            f"skipped={summary.skipped} failed={summary.failed}"
        ),
    )


def run_cleanup_cycle(paths: AppPaths) -> None:
    result = cleanup_expired_data(paths, run_vacuum=False)
    log_service_event(
        "info",
        (
            "cleanup "
            f"topic_snapshots={result.deleted_topic_snapshots} "
            f"crawl_runs={result.deleted_crawl_runs} "
            f"hot_topic_rankings={result.deleted_hot_topic_rankings} "
            f"hot_topic_runs={result.deleted_hot_topic_runs} "
            f"bot_delivery_logs={result.deleted_bot_delivery_logs} "
            f"artifacts={result.deleted_artifacts}"
        ),
    )


def log_service_event(level: str, message: str) -> None:
    print(f"[service][{level}] {message}", flush=True)
