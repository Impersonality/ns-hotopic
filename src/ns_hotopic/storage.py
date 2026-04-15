from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import AppPaths
from .models import CrawlResult, HotTopicRunResult


SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL,
    page_url TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0,
    page_title TEXT,
    error_message TEXT,
    html_artifact_path TEXT
);

CREATE TABLE IF NOT EXISTS topic_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    captured_at TEXT NOT NULL,
    position INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    author_name TEXT,
    node_name TEXT,
    view_count INTEGER,
    comment_count INTEGER,
    published_text TEXT,
    is_pinned INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(run_id) REFERENCES crawl_runs(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_topic_snapshots_run_position
    ON topic_snapshots(run_id, position);

CREATE INDEX IF NOT EXISTS idx_topic_snapshots_topic_captured
    ON topic_snapshots(topic_id, captured_at);

CREATE TABLE IF NOT EXISTS hot_topic_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_crawl_run_id INTEGER,
    computed_at TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    ranking_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(source_crawl_run_id) REFERENCES crawl_runs(id)
);

CREATE TABLE IF NOT EXISTS hot_topic_rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    rank INTEGER NOT NULL,
    topic_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    score REAL NOT NULL,
    comment_delta INTEGER NOT NULL DEFAULT 0,
    view_delta INTEGER NOT NULL DEFAULT 0,
    position_gain INTEGER NOT NULL DEFAULT 0,
    appearance_count INTEGER NOT NULL DEFAULT 0,
    earliest_position INTEGER NOT NULL,
    latest_position INTEGER NOT NULL,
    latest_comment_count INTEGER NOT NULL DEFAULT 0,
    latest_view_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(run_id) REFERENCES hot_topic_runs(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_hot_topic_rankings_run_rank
    ON hot_topic_rankings(run_id, rank);

CREATE INDEX IF NOT EXISTS idx_hot_topic_runs_source
    ON hot_topic_runs(source_crawl_run_id);

CREATE TABLE IF NOT EXISTS bot_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    subscription_type TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_delivered_at TEXT,
    UNIQUE(chat_id, subscription_type)
);

CREATE INDEX IF NOT EXISTS idx_bot_subscriptions_active
    ON bot_subscriptions(subscription_type, is_active);

CREATE TABLE IF NOT EXISTS bot_delivery_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    subscription_type TEXT NOT NULL,
    scheduled_for TEXT NOT NULL,
    delivered_at TEXT,
    status TEXT NOT NULL,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_bot_delivery_logs_scheduled
    ON bot_delivery_logs(subscription_type, scheduled_for);
"""


def connect(paths: AppPaths) -> sqlite3.Connection:
    paths.ensure_directories()
    connection = sqlite3.connect(paths.db_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    connection.commit()
    return connection


def save_crawl_result(connection: sqlite3.Connection, result: CrawlResult) -> int:
    cursor = connection.execute(
        """
        INSERT INTO crawl_runs (
            started_at,
            finished_at,
            status,
            page_url,
            item_count,
            page_title,
            error_message,
            html_artifact_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.started_at,
            result.finished_at,
            result.status,
            result.page_url,
            result.item_count,
            result.page_title,
            result.error_message,
            str(result.html_artifact_path) if result.html_artifact_path else None,
        ),
    )
    run_id = int(cursor.lastrowid)

    if result.snapshots:
        connection.executemany(
            """
            INSERT INTO topic_snapshots (
                run_id,
                captured_at,
                position,
                topic_id,
                title,
                url,
                author_name,
                node_name,
                view_count,
                comment_count,
                published_text,
                is_pinned
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    result.started_at,
                    snapshot.position,
                    snapshot.topic_id,
                    snapshot.title,
                    snapshot.url,
                    snapshot.author_name,
                    snapshot.node_name,
                    snapshot.view_count,
                    snapshot.comment_count,
                    snapshot.published_text,
                    int(snapshot.is_pinned),
                )
                for snapshot in result.snapshots
            ],
        )

    connection.commit()
    return run_id


def save_hot_topic_run_result(connection: sqlite3.Connection, result: HotTopicRunResult) -> int:
    cursor = connection.execute(
        """
        INSERT INTO hot_topic_runs (
            source_crawl_run_id,
            computed_at,
            window_start,
            window_end,
            algorithm_version,
            candidate_count,
            ranking_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result.source_crawl_run_id,
            result.computed_at,
            result.window_start,
            result.window_end,
            result.algorithm_version,
            result.candidate_count,
            result.ranking_count,
        ),
    )
    run_id = int(cursor.lastrowid)

    if result.rankings:
        connection.executemany(
            """
            INSERT INTO hot_topic_rankings (
                run_id,
                rank,
                topic_id,
                title,
                url,
                score,
                comment_delta,
                view_delta,
                position_gain,
                appearance_count,
                earliest_position,
                latest_position,
                latest_comment_count,
                latest_view_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    ranking.rank,
                    ranking.topic_id,
                    ranking.title,
                    ranking.url,
                    ranking.score,
                    ranking.comment_delta,
                    ranking.view_delta,
                    ranking.position_gain,
                    ranking.appearance_count,
                    ranking.earliest_position,
                    ranking.latest_position,
                    ranking.latest_comment_count,
                    ranking.latest_view_count,
                )
                for ranking in result.rankings
            ],
        )

    connection.commit()
    return run_id


def latest_run(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM crawl_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def latest_successful_run(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM crawl_runs
        WHERE status = 'success'
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def crawl_run_by_id(connection: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM crawl_runs
        WHERE id = ?
        LIMIT 1
        """,
        (run_id,),
    ).fetchone()


def snapshots_for_run(
    connection: sqlite3.Connection,
    run_id: int,
    limit: int,
    offset: int = 0,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM topic_snapshots
        WHERE run_id = ?
        ORDER BY position ASC
        LIMIT ? OFFSET ?
        """,
        (run_id, limit, offset),
    ).fetchall()


def all_snapshots_for_run(connection: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM topic_snapshots
        WHERE run_id = ?
        ORDER BY position ASC
        """,
        (run_id,),
    ).fetchall()


def latest_hot_topic_run(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM hot_topic_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def hot_topic_run_by_id(connection: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM hot_topic_runs
        WHERE id = ?
        LIMIT 1
        """,
        (run_id,),
    ).fetchone()


def count_hot_topic_rankings_for_run(connection: sqlite3.Connection, run_id: int) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM hot_topic_rankings
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    return int(row["count"]) if row is not None else 0


def hot_topic_rankings_for_run(
    connection: sqlite3.Connection,
    run_id: int,
    limit: int,
    offset: int = 0,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM hot_topic_rankings
        WHERE run_id = ?
        ORDER BY rank ASC
        LIMIT ? OFFSET ?
        """,
        (run_id, limit, offset),
    ).fetchall()


def upsert_bot_subscription(
    connection: sqlite3.Connection,
    *,
    chat_id: int,
    subscription_type: str,
    interval_minutes: int,
    timestamp: str,
) -> int:
    connection.execute(
        """
        INSERT INTO bot_subscriptions (
            chat_id,
            subscription_type,
            interval_minutes,
            is_active,
            created_at,
            updated_at,
            last_delivered_at
        ) VALUES (?, ?, ?, 1, ?, ?, NULL)
        ON CONFLICT(chat_id, subscription_type)
        DO UPDATE SET
            interval_minutes = excluded.interval_minutes,
            is_active = 1,
            updated_at = excluded.updated_at
        """,
        (chat_id, subscription_type, interval_minutes, timestamp, timestamp),
    )
    connection.commit()
    row = connection.execute(
        """
        SELECT id
        FROM bot_subscriptions
        WHERE chat_id = ? AND subscription_type = ?
        """,
        (chat_id, subscription_type),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to load bot subscription after upsert")
    return int(row["id"])


def active_bot_subscription_for_chat(
    connection: sqlite3.Connection,
    *,
    chat_id: int,
    subscription_type: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM bot_subscriptions
        WHERE chat_id = ? AND subscription_type = ? AND is_active = 1
        LIMIT 1
        """,
        (chat_id, subscription_type),
    ).fetchone()


def deactivate_bot_subscription(
    connection: sqlite3.Connection,
    *,
    chat_id: int,
    subscription_type: str,
    timestamp: str,
) -> int:
    cursor = connection.execute(
        """
        UPDATE bot_subscriptions
        SET is_active = 0, updated_at = ?
        WHERE chat_id = ? AND subscription_type = ? AND is_active = 1
        """,
        (timestamp, chat_id, subscription_type),
    )
    connection.commit()
    return int(cursor.rowcount)


def active_bot_subscriptions(
    connection: sqlite3.Connection,
    *,
    subscription_type: str,
) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM bot_subscriptions
        WHERE subscription_type = ? AND is_active = 1
        ORDER BY id ASC
        """,
        (subscription_type,),
    ).fetchall()


def mark_bot_subscription_delivered(
    connection: sqlite3.Connection,
    *,
    subscription_id: int,
    delivered_at: str,
) -> None:
    connection.execute(
        """
        UPDATE bot_subscriptions
        SET last_delivered_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (delivered_at, delivered_at, subscription_id),
    )
    connection.commit()


def record_bot_delivery_log(
    connection: sqlite3.Connection,
    *,
    chat_id: int,
    subscription_type: str,
    scheduled_for: str,
    status: str,
    delivered_at: str | None = None,
    error_message: str | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO bot_delivery_logs (
            chat_id,
            subscription_type,
            scheduled_for,
            delivered_at,
            status,
            error_message
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (chat_id, subscription_type, scheduled_for, delivered_at, status, error_message),
    )
    connection.commit()
    return int(cursor.lastrowid)


def bot_delivery_logs(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM bot_delivery_logs
        ORDER BY id ASC
        """
    ).fetchall()


def delete_expired_topic_snapshots(connection: sqlite3.Connection, cutoff_iso: str) -> int:
    cursor = connection.execute(
        """
        DELETE FROM topic_snapshots
        WHERE captured_at < ?
        """,
        (cutoff_iso,),
    )
    connection.commit()
    return int(cursor.rowcount)


def delete_expired_crawl_runs(connection: sqlite3.Connection, cutoff_iso: str) -> int:
    cursor = connection.execute(
        """
        DELETE FROM crawl_runs
        WHERE started_at < ? AND finished_at < ?
        """,
        (cutoff_iso, cutoff_iso),
    )
    connection.commit()
    return int(cursor.rowcount)


def delete_expired_hot_topic_rankings(connection: sqlite3.Connection, cutoff_iso: str) -> int:
    cursor = connection.execute(
        """
        DELETE FROM hot_topic_rankings
        WHERE run_id IN (
            SELECT id
            FROM hot_topic_runs
            WHERE computed_at < ?
        )
        """,
        (cutoff_iso,),
    )
    connection.commit()
    return int(cursor.rowcount)


def delete_expired_hot_topic_runs(connection: sqlite3.Connection, cutoff_iso: str) -> int:
    cursor = connection.execute(
        """
        DELETE FROM hot_topic_runs
        WHERE computed_at < ?
        """,
        (cutoff_iso,),
    )
    connection.commit()
    return int(cursor.rowcount)


def delete_expired_bot_delivery_logs(connection: sqlite3.Connection, cutoff_iso: str) -> int:
    cursor = connection.execute(
        """
        DELETE FROM bot_delivery_logs
        WHERE scheduled_for < ?
        """,
        (cutoff_iso,),
    )
    connection.commit()
    return int(cursor.rowcount)


def vacuum(connection: sqlite3.Connection) -> None:
    connection.execute("VACUUM")
    connection.commit()


def resolve_db_path(root_dir: Path) -> Path:
    return root_dir / "data" / "ns_hotopic.db"
