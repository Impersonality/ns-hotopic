import sqlite3
from pathlib import Path

from ns_hotopic.config import AppPaths
from ns_hotopic.storage import (
    connect,
    save_crawl_result,
    save_hot_topic_run_result,
    upsert_bot_subscription,
)
from ns_hotopic.models import CrawlResult, HotTopicRanking, HotTopicRunResult, TopicSnapshot
from ns_hotopic.telegram_bot import (
    build_hot_page_payload,
    build_hot_push_text,
    build_lottery_page_payload,
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


def test_build_lottery_page_payload_filters_for_titles_with_choujiang(tmp_path: Path) -> None:
    connection = connect(_make_paths(tmp_path))
    run_id = save_crawl_result(
        connection,
        CrawlResult(
            started_at="2026-04-14T10:00:00+08:00",
            finished_at="2026-04-14T10:00:05+08:00",
            status="success",
            page_url="https://www.nodeseek.com/",
            item_count=3,
            page_title="NodeSeek",
            snapshots=[
                TopicSnapshot(
                    position=1,
                    topic_id="1",
                    title="【抽奖】第一条",
                    url="https://www.nodeseek.com/post-1-1",
                    node_name="福利羊毛",
                    published_text="刚刚",
                ),
                TopicSnapshot(
                    position=2,
                    topic_id="2",
                    title="【评论送鸡腿】第二条",
                    url="https://www.nodeseek.com/post-2-1",
                    node_name="福利羊毛",
                    published_text="1 分钟前",
                ),
                TopicSnapshot(
                    position=3,
                    topic_id="3",
                    title="普通帖子",
                    url="https://www.nodeseek.com/post-3-1",
                    node_name="服务器",
                    published_text="2 分钟前",
                ),
            ],
        ),
    )

    payload = build_lottery_page_payload(connection, page=0, run_id=run_id)

    assert payload is not None
    assert payload.run_id == run_id
    assert "【抽奖】第一条" in payload.text
    assert "评论送鸡腿" not in payload.text
    assert "普通帖子" not in payload.text


def test_build_hot_payload_and_push_text_paginate_and_render(tmp_path: Path) -> None:
    connection = connect(_make_paths(tmp_path))
    save_hot_topic_run_result(
        connection,
        HotTopicRunResult(
            source_crawl_run_id=1,
            computed_at="2026-04-14T12:00:00+08:00",
            window_start="2026-04-14T06:00:00+08:00",
            window_end="2026-04-14T12:00:00+08:00",
            algorithm_version="v-test",
            candidate_count=12,
            ranking_count=12,
            rankings=[
                *[
                    HotTopicRanking(
                        rank=1,
                        topic_id="single",
                        title="新进高热帖",
                        url="https://www.nodeseek.com/post-single-1",
                        score=99.0,
                        comment_delta=35,
                        view_delta=635,
                        position_gain=0,
                        appearance_count=1,
                        earliest_position=2,
                        latest_position=2,
                        latest_comment_count=35,
                        latest_view_count=635,
                    )
                ],
                *[
                    HotTopicRanking(
                        rank=index,
                        topic_id=str(index),
                        title=f"标题 {index}",
                        url=f"https://www.nodeseek.com/post-{index}-1",
                        score=float(index),
                        comment_delta=index,
                        view_delta=index * 2,
                        position_gain=index,
                        appearance_count=2,
                        earliest_position=index + 5,
                        latest_position=index,
                        latest_comment_count=index,
                        latest_view_count=index * 3,
                    )
                    for index in range(2, 13)
                ],
            ],
        ),
    )

    page_one = build_hot_page_payload(connection, page=0)
    page_two = build_hot_page_payload(connection, page=1)
    push_text = build_hot_push_text(connection, limit=3)

    assert page_one is not None
    assert page_two is not None
    assert "热点 第 1/2 页" in page_one.text
    assert "1. 新进高热帖" in page_one.text
    assert "10. 标题 10" in page_one.text
    assert "评论 35 | 浏览 635 | 新进候选" in page_one.text
    assert "出现 2 次" in page_one.text
    assert "上升" not in page_one.text
    assert "11. 标题 11" in page_two.text
    assert push_text is not None
    assert "热点推送" in push_text
    assert "1. 新进高热帖" in push_text
    assert "评论 35 | 浏览 635 | 新进候选" in push_text
    assert "上升" not in push_text


def test_upsert_bot_subscription_reactivates_and_updates_interval(tmp_path: Path) -> None:
    connection = connect(_make_paths(tmp_path))
    subscription_id = upsert_bot_subscription(
        connection,
        chat_id=123,
        subscription_type="hot",
        interval_minutes=30,
        timestamp="2026-04-14T10:00:00+08:00",
    )
    same_subscription_id = upsert_bot_subscription(
        connection,
        chat_id=123,
        subscription_type="hot",
        interval_minutes=60,
        timestamp="2026-04-14T11:00:00+08:00",
    )
    row = connection.execute("SELECT * FROM bot_subscriptions WHERE id = ?", (subscription_id,)).fetchone()

    assert subscription_id == same_subscription_id
    assert row is not None
    assert row["interval_minutes"] == 60
    assert row["is_active"] == 1
