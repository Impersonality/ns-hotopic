from __future__ import annotations

import argparse
import sqlite3
import sys

from .config import get_app_paths, get_settings
from .crawler import run_fetch_once, run_trial_once
from .hot_topics import calculate_and_store_hot_topics
from .retention import cleanup_expired_data
from .service import run_service
from .storage import (
    connect,
    hot_topic_rankings_for_run,
    latest_hot_topic_run,
    latest_run,
    save_crawl_result,
    snapshots_for_run,
)
from .telegram_bot import run_bot, run_due_notifications


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="ns-hotopic")
    subparsers = parser.add_subparsers(dest="command")

    trial_parser = subparsers.add_parser("trial-once", help="Open a browser and fetch the homepage once.")
    trial_parser.add_argument("--url", default=settings.home_url, help="Homepage URL to fetch.")
    trial_parser.add_argument(
        "--wait-timeout",
        type=int,
        default=180,
        help="How many seconds to wait for manual verification to finish.",
    )
    trial_parser.add_argument("--keep-open", action="store_true", help="Keep the browser open until Enter is pressed.")
    trial_parser.add_argument("--headless", action="store_true", help="Run without a visible browser for debugging.")
    trial_parser.set_defaults(func=_cmd_trial_once)

    fetch_parser = subparsers.add_parser("fetch-once", help="Fetch the homepage once using saved browser state.")
    fetch_parser.add_argument("--url", default=settings.home_url, help="Homepage URL to fetch.")
    fetch_parser.add_argument("--no-headless", action="store_true", help="Run with a visible browser window.")
    fetch_parser.set_defaults(func=_cmd_fetch_once)

    last_parser = subparsers.add_parser("show-last-run", help="Print the latest crawl run and top items.")
    last_parser.add_argument("--limit", type=int, default=5, help="How many topic rows to print.")
    last_parser.set_defaults(func=_cmd_show_last_run)

    hot_parser = subparsers.add_parser("show-hot-topics", help="Print the latest hot topic ranking.")
    hot_parser.add_argument("--limit", type=int, default=10, help="How many ranking rows to print.")
    hot_parser.set_defaults(func=_cmd_show_hot_topics)

    bot_parser = subparsers.add_parser("bot-run", help="Run the Telegram bot in polling mode.")
    bot_parser.set_defaults(func=_cmd_bot_run)

    due_parser = subparsers.add_parser("bot-send-due", help="Send due hot topic subscription messages.")
    due_parser.set_defaults(func=_cmd_bot_send_due)

    service_parser = subparsers.add_parser("service-run", help="Run the bot and background scheduler in one process.")
    service_parser.set_defaults(func=_cmd_service_run)

    cleanup_parser = subparsers.add_parser("cleanup", help="Delete expired crawl, hot topic, and bot log data.")
    cleanup_parser.add_argument("--vacuum", action="store_true", help="Run VACUUM after cleanup.")
    cleanup_parser.set_defaults(func=_cmd_cleanup)
    return parser


def _cmd_trial_once(args: argparse.Namespace) -> None:
    paths = get_app_paths()
    result = run_trial_once(
        paths=paths,
        page_url=args.url,
        wait_timeout_seconds=args.wait_timeout,
        keep_open=args.keep_open,
        headless=args.headless,
    )
    _persist_and_print(paths, result)


def _cmd_fetch_once(args: argparse.Namespace) -> None:
    paths = get_app_paths()
    try:
        result = run_fetch_once(
            paths=paths,
            page_url=args.url,
            headless=not args.no_headless,
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    _persist_and_print(paths, result)


def _cmd_show_last_run(args: argparse.Namespace) -> None:
    paths = get_app_paths()
    try:
        connection = connect(paths)
    except sqlite3.Error as exc:
        print(f"Failed to open database: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    run = latest_run(connection)
    if run is None:
        print("No crawl runs found.")
        return

    print(
        f"Run #{run['id']} | status={run['status']} | "
        f"started_at={run['started_at']} | items={run['item_count']}"
    )
    if run["page_title"]:
        print(f"Page title: {run['page_title']}")
    if run["html_artifact_path"]:
        print(f"Artifact: {run['html_artifact_path']}")
    if run["error_message"]:
        print(f"Error: {run['error_message']}")

    snapshots = snapshots_for_run(connection, int(run["id"]), args.limit)
    for snapshot in snapshots:
        views = snapshot["view_count"] if snapshot["view_count"] is not None else "-"
        comments = snapshot["comment_count"] if snapshot["comment_count"] is not None else "-"
        print(
            f"{snapshot['position']:>2}. {snapshot['title']} "
            f"(views={views}, comments={comments})"
        )


def _cmd_show_hot_topics(args: argparse.Namespace) -> None:
    paths = get_app_paths()
    try:
        connection = connect(paths)
    except sqlite3.Error as exc:
        print(f"Failed to open database: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    hot_run = latest_hot_topic_run(connection)
    if hot_run is None:
        print("No hot topic runs found.")
        return

    print(
        f"Hot topic run #{hot_run['id']} | computed_at={hot_run['computed_at']} | "
        f"window={hot_run['window_start']} -> {hot_run['window_end']}"
    )
    print(
        f"Algorithm={hot_run['algorithm_version']} | "
        f"candidates={hot_run['candidate_count']} | ranked={hot_run['ranking_count']}"
    )

    rankings = hot_topic_rankings_for_run(connection, int(hot_run["id"]), args.limit)
    if not rankings:
        print("No ranked topics for this window yet.")
        return

    for ranking in rankings:
        print(
            f"{ranking['rank']:>2}. {ranking['title']} "
            f"({_format_cli_hot_metrics(ranking)})"
        )


def _cmd_bot_run(args: argparse.Namespace) -> None:
    paths = get_app_paths()
    try:
        run_bot(paths)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


def _cmd_bot_send_due(args: argparse.Namespace) -> None:
    paths = get_app_paths()
    try:
        summary = run_due_notifications(paths)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(
        f"Checked {summary.checked} subscriptions | "
        f"delivered={summary.delivered} skipped={summary.skipped} failed={summary.failed}"
    )


def _cmd_service_run(args: argparse.Namespace) -> None:
    paths = get_app_paths()
    try:
        run_service(paths)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


def _cmd_cleanup(args: argparse.Namespace) -> None:
    paths = get_app_paths()
    result = cleanup_expired_data(paths, run_vacuum=args.vacuum)
    print(f"Deleted topic_snapshots: {result.deleted_topic_snapshots}")
    print(f"Deleted crawl_runs: {result.deleted_crawl_runs}")
    print(f"Deleted hot_topic_rankings: {result.deleted_hot_topic_rankings}")
    print(f"Deleted hot_topic_runs: {result.deleted_hot_topic_runs}")
    print(f"Deleted bot_delivery_logs: {result.deleted_bot_delivery_logs}")
    print(f"Deleted artifacts: {result.deleted_artifacts}")
    print(f"Vacuumed: {result.vacuumed}")


def _persist_and_print(paths, result) -> None:
    connection = connect(paths)
    run_id = save_crawl_result(connection, result)
    print(
        f"Saved run #{run_id} | status={result.status} | "
        f"items={result.item_count} | started_at={result.started_at}"
    )
    if result.page_title:
        print(f"Page title: {result.page_title}")
    if result.html_artifact_path:
        print(f"HTML artifact: {result.html_artifact_path}")
    if result.error_message:
        print(f"Error: {result.error_message}")

    for snapshot in result.snapshots[:5]:
        views = snapshot.view_count if snapshot.view_count is not None else "-"
        comments = snapshot.comment_count if snapshot.comment_count is not None else "-"
        print(f"{snapshot.position:>2}. {snapshot.title} (views={views}, comments={comments})")

    if result.status == "success":
        hot_topic_run_id, hot_result = calculate_and_store_hot_topics(
            connection,
            source_crawl_run_id=run_id,
            computed_at=result.started_at,
        )
        print(
            f"Hot topic run #{hot_topic_run_id} | "
            f"candidates={hot_result.candidate_count} | ranked={hot_result.ranking_count}"
        )
        for ranking in hot_result.rankings[:3]:
            print(
                f"#{ranking.rank} {ranking.title} "
                f"({_format_model_hot_metrics(ranking)})"
            )

    if result.status != "success":
        raise SystemExit(1)


def _format_cli_hot_metrics(ranking: sqlite3.Row) -> str:
    if int(ranking["appearance_count"]) == 1:
        return (
            f"score={ranking['score']:.2f}, comments={ranking['latest_comment_count']}, "
            f"views={ranking['latest_view_count']}, new-entry"
        )
    return (
        f"score={ranking['score']:.2f}, +comments={ranking['comment_delta']}, "
        f"+views={ranking['view_delta']}, seen={ranking['appearance_count']}"
    )


def _format_model_hot_metrics(ranking) -> str:
    if ranking.appearance_count == 1:
        return (
            f"score={ranking.score:.2f}, comments={ranking.latest_comment_count}, "
            f"views={ranking.latest_view_count}, new-entry"
        )
    return (
        f"score={ranking.score:.2f}, +comments={ranking.comment_delta}, "
        f"+views={ranking.view_delta}, seen={ranking.appearance_count}"
    )
