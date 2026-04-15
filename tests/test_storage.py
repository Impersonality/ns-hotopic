from pathlib import Path

from ns_hotopic.config import AppPaths
from ns_hotopic.hot_topics import calculate_and_store_hot_topics
from ns_hotopic.models import CrawlResult, TopicSnapshot
from ns_hotopic.storage import (
    connect,
    hot_topic_rankings_for_run,
    latest_hot_topic_run,
    latest_run,
    save_crawl_result,
    snapshots_for_run,
)


def test_save_crawl_result_persists_rows(tmp_path: Path) -> None:
    paths = AppPaths(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        artifacts_dir=tmp_path / "artifacts",
        db_path=tmp_path / "data" / "ns_hotopic.db",
        storage_state_path=tmp_path / "state" / "storage_state.json",
    )
    connection = connect(paths)

    result = CrawlResult(
        started_at="2026-04-14T16:00:00+08:00",
        finished_at="2026-04-14T16:00:05+08:00",
        status="success",
        page_url="https://www.nodeseek.com/",
        item_count=1,
        page_title="NodeSeek",
        snapshots=[
            TopicSnapshot(
                position=1,
                topic_id="12345",
                title="第一条帖子",
                url="https://www.nodeseek.com/post-12345-1",
                view_count=10,
                comment_count=2,
            )
        ],
    )

    run_id = save_crawl_result(connection, result)
    run = latest_run(connection)
    snapshots = snapshots_for_run(connection, run_id, limit=10)

    assert run is not None
    assert run["id"] == run_id
    assert run["status"] == "success"
    assert len(snapshots) == 1
    assert snapshots[0]["topic_id"] == "12345"


def test_hot_topic_results_are_persisted(tmp_path: Path) -> None:
    paths = AppPaths(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        state_dir=tmp_path / "state",
        artifacts_dir=tmp_path / "artifacts",
        db_path=tmp_path / "data" / "ns_hotopic.db",
        storage_state_path=tmp_path / "state" / "storage_state.json",
    )
    connection = connect(paths)

    first_run_id = save_crawl_result(
        connection,
        CrawlResult(
            started_at="2026-04-14T10:00:00+08:00",
            finished_at="2026-04-14T10:00:05+08:00",
            status="success",
            page_url="https://www.nodeseek.com/",
            item_count=2,
            page_title="NodeSeek",
            snapshots=[
                TopicSnapshot(
                    position=8,
                    topic_id="12345",
                    title="第一条帖子",
                    url="https://www.nodeseek.com/post-12345-1",
                    view_count=100,
                    comment_count=2,
                ),
                TopicSnapshot(
                    position=2,
                    topic_id="22222",
                    title="第二条帖子",
                    url="https://www.nodeseek.com/post-22222-1",
                    view_count=300,
                    comment_count=1,
                ),
            ],
        ),
    )
    second_run_id = save_crawl_result(
        connection,
        CrawlResult(
            started_at="2026-04-14T12:00:00+08:00",
            finished_at="2026-04-14T12:00:05+08:00",
            status="success",
            page_url="https://www.nodeseek.com/",
            item_count=2,
            page_title="NodeSeek",
            snapshots=[
                TopicSnapshot(
                    position=1,
                    topic_id="12345",
                    title="第一条帖子",
                    url="https://www.nodeseek.com/post-12345-1",
                    view_count=180,
                    comment_count=6,
                ),
                TopicSnapshot(
                    position=2,
                    topic_id="22222",
                    title="第二条帖子",
                    url="https://www.nodeseek.com/post-22222-1",
                    view_count=320,
                    comment_count=2,
                ),
            ],
        ),
    )

    hot_run_id, hot_result = calculate_and_store_hot_topics(
        connection,
        source_crawl_run_id=second_run_id,
        computed_at="2026-04-14T12:00:00+08:00",
    )
    run = latest_hot_topic_run(connection)
    rankings = hot_topic_rankings_for_run(connection, hot_run_id, limit=10)

    assert first_run_id > 0
    assert run is not None
    assert run["source_crawl_run_id"] == second_run_id
    assert hot_result.ranking_count == 2
    assert len(rankings) == 2
    assert rankings[0]["topic_id"] == "12345"
    assert rankings[0]["rank"] == 1
    assert rankings[0]["comment_delta"] == 4
