from pathlib import Path

import pytest

from ns_hotopic.config import AppPaths
from ns_hotopic.service import (
    ScheduledTask,
    ServiceIntervals,
    execute_due_tasks,
    validate_service_prerequisites,
)


def _make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        artifacts_dir=tmp_path / "artifacts",
        db_path=tmp_path / "data" / "ns_hotopic.db",
        storage_state_path=tmp_path / "state" / "storage_state.json",
    )


def test_validate_service_prerequisites_requires_storage_state(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    paths.ensure_directories()

    with pytest.raises(RuntimeError, match="storage_state.json"):
        validate_service_prerequisites(paths)

    paths.storage_state_path.write_text("{}", encoding="utf-8")
    validate_service_prerequisites(paths)


def test_execute_due_tasks_runs_due_actions_and_updates_next_run() -> None:
    called: list[str] = []
    task_one = ScheduledTask(
        name="fetch",
        interval_seconds=60,
        action=lambda: called.append("fetch"),
    )
    task_two = ScheduledTask(
        name="deliver",
        interval_seconds=30,
        action=lambda: called.append("deliver"),
    )
    next_run_at = {"fetch": 0.0, "deliver": 100.0}

    execute_due_tasks([task_one, task_two], next_run_at, now=30.0)

    assert called == ["fetch"]
    assert next_run_at["fetch"] == 90.0
    assert next_run_at["deliver"] == 100.0


def test_service_intervals_are_plain_seconds() -> None:
    intervals = ServiceIntervals(
        fetch_seconds=1800,
        delivery_check_seconds=300,
        cleanup_seconds=86400,
    )

    assert intervals.fetch_seconds == 1800
    assert intervals.delivery_check_seconds == 300
    assert intervals.cleanup_seconds == 86400
