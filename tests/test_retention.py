from datetime import datetime, timedelta
from pathlib import Path

from ns_hotopic.config import AppPaths
from ns_hotopic.models import CrawlResult, HotTopicRanking, HotTopicRunResult, TopicSnapshot
from ns_hotopic.retention import cleanup_expired_data
from ns_hotopic.storage import connect, record_bot_delivery_log, save_crawl_result, save_hot_topic_run_result


def _make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        artifacts_dir=tmp_path / "artifacts",
        db_path=tmp_path / "data" / "ns_hotopic.db",
        storage_state_path=tmp_path / "state" / "storage_state.json",
    )


def test_cleanup_expired_data_respects_retention_windows(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    connection = connect(paths)
    reference = datetime.fromisoformat("2026-04-14T12:00:00+08:00")

    old_crawl_time = (reference - timedelta(days=61)).isoformat(timespec="seconds")
    new_crawl_time = (reference - timedelta(days=5)).isoformat(timespec="seconds")
    old_hot_time = (reference - timedelta(days=181)).isoformat(timespec="seconds")
    new_hot_time = (reference - timedelta(days=10)).isoformat(timespec="seconds")
    old_log_time = (reference - timedelta(days=31)).isoformat(timespec="seconds")
    new_log_time = (reference - timedelta(days=1)).isoformat(timespec="seconds")

    save_crawl_result(
        connection,
        CrawlResult(
            started_at=old_crawl_time,
            finished_at=old_crawl_time,
            status="success",
            page_url="https://www.nodeseek.com/",
            item_count=1,
            page_title="NodeSeek",
            snapshots=[
                TopicSnapshot(
                    position=1,
                    topic_id="old",
                    title="旧帖子",
                    url="https://www.nodeseek.com/post-old-1",
                )
            ],
        ),
    )
    save_crawl_result(
        connection,
        CrawlResult(
            started_at=new_crawl_time,
            finished_at=new_crawl_time,
            status="success",
            page_url="https://www.nodeseek.com/",
            item_count=1,
            page_title="NodeSeek",
            snapshots=[
                TopicSnapshot(
                    position=1,
                    topic_id="new",
                    title="新帖子",
                    url="https://www.nodeseek.com/post-new-1",
                )
            ],
        ),
    )
    save_hot_topic_run_result(
        connection,
        HotTopicRunResult(
            source_crawl_run_id=None,
            computed_at=old_hot_time,
            window_start=old_hot_time,
            window_end=old_hot_time,
            algorithm_version="old",
            candidate_count=1,
            ranking_count=1,
            rankings=[
                HotTopicRanking(
                    rank=1,
                    topic_id="old-hot",
                    title="旧热点",
                    url="https://www.nodeseek.com/post-oldhot-1",
                    score=10.0,
                    comment_delta=1,
                    view_delta=1,
                    position_gain=1,
                    appearance_count=2,
                    earliest_position=3,
                    latest_position=2,
                    latest_comment_count=3,
                    latest_view_count=10,
                )
            ],
        ),
    )
    save_hot_topic_run_result(
        connection,
        HotTopicRunResult(
            source_crawl_run_id=None,
            computed_at=new_hot_time,
            window_start=new_hot_time,
            window_end=new_hot_time,
            algorithm_version="new",
            candidate_count=1,
            ranking_count=1,
            rankings=[
                HotTopicRanking(
                    rank=1,
                    topic_id="new-hot",
                    title="新热点",
                    url="https://www.nodeseek.com/post-newhot-1",
                    score=20.0,
                    comment_delta=2,
                    view_delta=2,
                    position_gain=2,
                    appearance_count=3,
                    earliest_position=4,
                    latest_position=1,
                    latest_comment_count=5,
                    latest_view_count=20,
                )
            ],
        ),
    )
    record_bot_delivery_log(
        connection,
        chat_id=1,
        subscription_type="hot",
        scheduled_for=old_log_time,
        delivered_at=old_log_time,
        status="delivered",
    )
    record_bot_delivery_log(
        connection,
        chat_id=1,
        subscription_type="hot",
        scheduled_for=new_log_time,
        delivered_at=new_log_time,
        status="delivered",
    )

    old_artifact = paths.artifacts_dir / "old.html"
    old_artifact.parent.mkdir(parents=True, exist_ok=True)
    old_artifact.write_text("old", encoding="utf-8")
    old_timestamp = (reference - timedelta(days=8)).timestamp()
    old_artifact.chmod(0o644)
    import os
    os.utime(old_artifact, (old_timestamp, old_timestamp))

    new_artifact = paths.artifacts_dir / "new.html"
    new_artifact.write_text("new", encoding="utf-8")

    result = cleanup_expired_data(paths, now=reference, run_vacuum=False)

    assert result.deleted_topic_snapshots == 1
    assert result.deleted_crawl_runs == 1
    assert result.deleted_hot_topic_rankings == 1
    assert result.deleted_hot_topic_runs == 1
    assert result.deleted_bot_delivery_logs == 1
    assert result.deleted_artifacts == 1

    counts = {
        "crawl_runs": connection.execute("SELECT COUNT(*) FROM crawl_runs").fetchone()[0],
        "topic_snapshots": connection.execute("SELECT COUNT(*) FROM topic_snapshots").fetchone()[0],
        "hot_topic_runs": connection.execute("SELECT COUNT(*) FROM hot_topic_runs").fetchone()[0],
        "hot_topic_rankings": connection.execute("SELECT COUNT(*) FROM hot_topic_rankings").fetchone()[0],
        "bot_delivery_logs": connection.execute("SELECT COUNT(*) FROM bot_delivery_logs").fetchone()[0],
    }
    assert counts == {
        "crawl_runs": 1,
        "topic_snapshots": 1,
        "hot_topic_runs": 1,
        "hot_topic_rankings": 1,
        "bot_delivery_logs": 1,
    }
    assert old_artifact.exists() is False
    assert new_artifact.exists() is True
