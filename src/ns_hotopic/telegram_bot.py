from __future__ import annotations

import asyncio
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from telegram import Bot, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from .config import AppPaths, get_app_paths, get_settings
from .storage import (
    active_bot_subscriptions,
    all_snapshots_for_run,
    connect,
    count_hot_topic_rankings_for_run,
    crawl_run_by_id,
    deactivate_bot_subscription,
    hot_topic_rankings_for_run,
    hot_topic_run_by_id,
    latest_hot_topic_run,
    latest_successful_run,
    mark_bot_subscription_delivered,
    record_bot_delivery_log,
    upsert_bot_subscription,
)
from .topic_filters import is_lottery_title

PAGE_SIZE = 10
SUBSCRIPTION_TYPE_HOT = "hot"
SUBSCRIPTION_INTERVALS = (
    (30, "30 分钟"),
    (60, "1 小时"),
    (360, "6 小时"),
    (1440, "24 小时"),
)
BOT_COMMANDS = [
    BotCommand("hot", "热点"),
    BotCommand("lottery", "抽奖贴"),
    BotCommand("subscribe", "订阅热点推送"),
    BotCommand("unsubscribe", "取消热点推送"),
    BotCommand("help", "查看帮助"),
]


@dataclass(slots=True)
class PagePayload:
    source: str
    run_id: int
    page: int
    total_pages: int
    text: str


@dataclass(slots=True)
class DeliverySummary:
    checked: int
    delivered: int
    skipped: int
    failed: int


def run_bot(paths: AppPaths | None = None) -> None:
    app_paths = paths or get_app_paths()
    token = get_bot_token()
    application = (
        Application.builder()
        .token(token)
        .post_init(_post_init)
        .build()
    )
    application.bot_data["paths"] = app_paths
    application.add_handler(CommandHandler("start", _cmd_start))
    application.add_handler(CommandHandler("help", _cmd_help))
    application.add_handler(CommandHandler("hot", _cmd_hot))
    application.add_handler(CommandHandler("lottery", _cmd_lottery))
    application.add_handler(CommandHandler("subscribe", _cmd_subscribe))
    application.add_handler(CommandHandler("unsubscribe", _cmd_unsubscribe))
    application.add_handler(CallbackQueryHandler(_handle_page_callback, pattern=r"^pg\|"))
    application.add_handler(CallbackQueryHandler(_handle_subscription_callback, pattern=r"^sub\|"))
    application.run_polling(drop_pending_updates=False)


async def send_due_notifications(paths: AppPaths | None = None) -> DeliverySummary:
    app_paths = paths or get_app_paths()
    token = get_bot_token()
    connection = connect(app_paths)
    now = datetime.now().astimezone()
    subscriptions = active_bot_subscriptions(connection, subscription_type=SUBSCRIPTION_TYPE_HOT)
    if not subscriptions:
        return DeliverySummary(checked=0, delivered=0, skipped=0, failed=0)

    bot = Bot(token=token)
    checked = len(subscriptions)
    delivered = 0
    skipped = 0
    failed = 0

    await bot.initialize()
    try:
        for subscription in subscriptions:
            if not _is_subscription_due(subscription, now=now):
                skipped += 1
                continue

            scheduled_for = now.isoformat(timespec="seconds")
            message = build_hot_push_text(connection, limit=10)
            if message is None:
                record_bot_delivery_log(
                    connection,
                    chat_id=int(subscription["chat_id"]),
                    subscription_type=SUBSCRIPTION_TYPE_HOT,
                    scheduled_for=scheduled_for,
                    status="skipped",
                    error_message="No hot topic run available.",
                )
                skipped += 1
                continue

            message_signature = _message_signature(message)
            if _is_duplicate_push(subscription, message_signature):
                mark_bot_subscription_delivered(
                    connection,
                    subscription_id=int(subscription["id"]),
                    delivered_at=scheduled_for,
                    message_signature=message_signature,
                )
                record_bot_delivery_log(
                    connection,
                    chat_id=int(subscription["chat_id"]),
                    subscription_type=SUBSCRIPTION_TYPE_HOT,
                    scheduled_for=scheduled_for,
                    status="skipped",
                    error_message="Hot topic push content unchanged.",
                )
                skipped += 1
                continue

            try:
                await bot.send_message(
                    chat_id=int(subscription["chat_id"]),
                    text=message,
                    disable_web_page_preview=True,
                )
            except TelegramError as exc:
                record_bot_delivery_log(
                    connection,
                    chat_id=int(subscription["chat_id"]),
                    subscription_type=SUBSCRIPTION_TYPE_HOT,
                    scheduled_for=scheduled_for,
                    status="failed",
                    error_message=str(exc),
                )
                failed += 1
                continue

            delivered_at = datetime.now().astimezone().isoformat(timespec="seconds")
            mark_bot_subscription_delivered(
                connection,
                subscription_id=int(subscription["id"]),
                delivered_at=delivered_at,
                message_signature=message_signature,
            )
            record_bot_delivery_log(
                connection,
                chat_id=int(subscription["chat_id"]),
                subscription_type=SUBSCRIPTION_TYPE_HOT,
                scheduled_for=scheduled_for,
                delivered_at=delivered_at,
                status="delivered",
            )
            delivered += 1
    finally:
        await bot.shutdown()

    return DeliverySummary(
        checked=checked,
        delivered=delivered,
        skipped=skipped,
        failed=failed,
    )


async def _post_init(application: Application) -> None:
    await application.bot.set_my_commands(BOT_COMMANDS)


async def _cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_text(update, _help_text())


async def _cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _send_text(update, _help_text())


async def _cmd_hot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    paths = _get_paths_from_context(context)
    connection = connect(paths)
    payload = build_hot_page_payload(connection, page=0)
    if payload is None:
        await _send_text(update, "当前还没有可用的热点数据。")
        return
    await _send_text(
        update,
        payload.text,
        reply_markup=_pagination_markup(payload),
        disable_web_page_preview=True,
    )


async def _cmd_lottery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    paths = _get_paths_from_context(context)
    connection = connect(paths)
    payload = build_lottery_page_payload(connection, page=0)
    if payload is None:
        await _send_text(update, "当前最近一轮抓取中没有抽奖贴。")
        return
    await _send_text(
        update,
        payload.text,
        reply_markup=_pagination_markup(payload),
        disable_web_page_preview=True,
    )


async def _cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton(label, callback_data=f"sub|{minutes}")
            for minutes, label in SUBSCRIPTION_INTERVALS[:2]
        ],
        [
            InlineKeyboardButton(label, callback_data=f"sub|{minutes}")
            for minutes, label in SUBSCRIPTION_INTERVALS[2:]
        ],
    ]
    await _send_text(
        update,
        "请选择热点推送间隔：",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def _cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return
    paths = _get_paths_from_context(context)
    connection = connect(paths)
    changed = deactivate_bot_subscription(
        connection,
        chat_id=int(chat.id),
        subscription_type=SUBSCRIPTION_TYPE_HOT,
        timestamp=_now(),
    )
    if changed:
        await _send_text(update, "已取消热点推送订阅。")
    else:
        await _send_text(update, "你当前没有激活的热点订阅。")


async def _handle_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    _, source, run_id_text, page_text = query.data.split("|", maxsplit=3)
    run_id = int(run_id_text)
    page = int(page_text)
    paths = _get_paths_from_context(context)
    connection = connect(paths)

    if source == "hot":
        payload = build_hot_page_payload(connection, page=page, run_id=run_id)
        if payload is None:
            await query.edit_message_text("这条热点榜已经不可用了。")
            return
    elif source == "lottery":
        payload = build_lottery_page_payload(connection, page=page, run_id=run_id)
        if payload is None:
            await query.edit_message_text("这轮抽奖贴数据已经不可用了。")
            return
    else:
        await query.edit_message_text("未知分页类型。")
        return

    await query.edit_message_text(
        payload.text,
        reply_markup=_pagination_markup(payload),
        disable_web_page_preview=True,
    )


async def _handle_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    _, minutes_text = query.data.split("|", maxsplit=1)
    minutes = int(minutes_text)
    chat = query.message.chat if query.message else None
    if chat is None:
        await query.edit_message_text("无法识别当前聊天。")
        return

    paths = _get_paths_from_context(context)
    connection = connect(paths)
    upsert_bot_subscription(
        connection,
        chat_id=int(chat.id),
        subscription_type=SUBSCRIPTION_TYPE_HOT,
        interval_minutes=minutes,
        timestamp=_now(),
    )
    await query.edit_message_text(f"已订阅热点推送，间隔为 {format_interval(minutes)}。")


def build_hot_page_payload(
    connection: sqlite3.Connection,
    *,
    page: int,
    run_id: int | None = None,
) -> PagePayload | None:
    run = hot_topic_run_by_id(connection, run_id) if run_id is not None else latest_hot_topic_run(connection)
    if run is None:
        return None

    total_items = count_hot_topic_rankings_for_run(connection, int(run["id"]))
    if total_items == 0:
        return None

    page = max(page, 0)
    total_pages = max((total_items - 1) // PAGE_SIZE + 1, 1)
    page = min(page, total_pages - 1)
    rows = hot_topic_rankings_for_run(
        connection,
        int(run["id"]),
        PAGE_SIZE,
        offset=page * PAGE_SIZE,
    )
    lines = [
        f"热点 第 {page + 1}/{total_pages} 页",
        f"更新时间：{run['computed_at']}",
        f"窗口：{run['window_start']} -> {run['window_end']}",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"{row['rank']}. {truncate_text(str(row['title']))}",
                _format_hot_metrics_line(row),
                str(row["url"]),
                "",
            ]
        )

    return PagePayload(
        source="hot",
        run_id=int(run["id"]),
        page=page,
        total_pages=total_pages,
        text="\n".join(lines).rstrip(),
    )


def build_lottery_page_payload(
    connection: sqlite3.Connection,
    *,
    page: int,
    run_id: int | None = None,
) -> PagePayload | None:
    run = crawl_run_by_id(connection, run_id) if run_id is not None else latest_successful_run(connection)
    if run is None:
        return None

    snapshots = [row for row in all_snapshots_for_run(connection, int(run["id"])) if is_lottery_title(str(row["title"]))]
    if not snapshots:
        return None

    total_items = len(snapshots)
    page = max(page, 0)
    total_pages = max((total_items - 1) // PAGE_SIZE + 1, 1)
    page = min(page, total_pages - 1)
    page_rows = snapshots[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    lines = [
        f"抽奖贴 第 {page + 1}/{total_pages} 页",
        f"抓取时间：{run['started_at']}",
        "",
    ]
    start_number = page * PAGE_SIZE + 1
    for index, row in enumerate(page_rows, start=start_number):
        node_name = row["node_name"] or "-"
        published_text = row["published_text"] or "-"
        lines.extend(
            [
                f"{index}. {truncate_text(str(row['title']))}",
                f"节点：{node_name} | 时间：{published_text}",
                str(row["url"]),
                "",
            ]
        )

    return PagePayload(
        source="lottery",
        run_id=int(run["id"]),
        page=page,
        total_pages=total_pages,
        text="\n".join(lines).rstrip(),
    )


def build_hot_push_text(connection: sqlite3.Connection, *, limit: int = 10) -> str | None:
    run = latest_hot_topic_run(connection)
    if run is None:
        return None
    rows = hot_topic_rankings_for_run(connection, int(run["id"]), limit, offset=0)
    if not rows:
        return None

    lines = [
        "热点推送",
        f"更新时间：{run['computed_at']}",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"{row['rank']}. {truncate_text(str(row['title']))}",
                _format_hot_metrics_line(row, include_score=False),
                str(row["url"]),
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def format_interval(minutes: int) -> str:
    for value, label in SUBSCRIPTION_INTERVALS:
        if value == minutes:
            return label
    return f"{minutes} 分钟"


def get_bot_token() -> str:
    token = get_settings().telegram_bot_token
    if not token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN.")
    return token


def truncate_text(text: str, limit: int = 72) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"


def _format_hot_metrics_line(row: sqlite3.Row, *, include_score: bool = True) -> str:
    if int(row["appearance_count"]) == 1:
        parts = [
            f"评论 {row['latest_comment_count']}",
            f"浏览 {row['latest_view_count']}",
            "新进候选",
        ]
    else:
        parts = [
            f"评论 +{row['comment_delta']}",
            f"浏览 +{row['view_delta']}",
            f"出现 {row['appearance_count']} 次",
        ]

    if include_score:
        return f"分数 {row['score']:.2f} | " + " | ".join(parts)
    return " | ".join(parts)


def _pagination_markup(payload: PagePayload) -> InlineKeyboardMarkup | None:
    buttons: list[InlineKeyboardButton] = []
    if payload.page > 0:
        buttons.append(
            InlineKeyboardButton(
                "上一页",
                callback_data=f"pg|{payload.source}|{payload.run_id}|{payload.page - 1}",
            )
        )
    if payload.page + 1 < payload.total_pages:
        buttons.append(
            InlineKeyboardButton(
                "下一页",
                callback_data=f"pg|{payload.source}|{payload.run_id}|{payload.page + 1}",
            )
        )
    if not buttons:
        return None
    return InlineKeyboardMarkup([buttons])


async def _send_text(
    update: Update,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    disable_web_page_preview: bool = False,
) -> None:
    target = update.effective_message
    if target is None:
        return
    await target.reply_text(
        text,
        reply_markup=reply_markup,
        disable_web_page_preview=disable_web_page_preview,
    )


def _help_text() -> str:
    return (
        "可用命令：\n"
        "/hot 当前热点榜\n"
        "/lottery 抽奖贴\n"
        "/subscribe 订阅热点推送\n"
        "/unsubscribe 取消热点推送\n"
        "/help 查看帮助\n\n"
        "说明：\n"
        "- /hot 和 /lottery 支持分页，每页 10 条\n"
        "- 热点订阅支持 30m / 1h / 6h / 24h\n"
        "- 抽奖贴当前只识别标题里明确包含“抽奖”的帖子"
    )


def _get_paths_from_context(context: ContextTypes.DEFAULT_TYPE) -> AppPaths:
    stored = context.application.bot_data.get("paths")
    if isinstance(stored, AppPaths):
        return stored
    paths = get_app_paths()
    context.application.bot_data["paths"] = paths
    return paths


def _is_subscription_due(subscription: sqlite3.Row, *, now: datetime) -> bool:
    last_delivered_at = subscription["last_delivered_at"]
    if last_delivered_at is None:
        return True
    last_delivered = datetime.fromisoformat(str(last_delivered_at))
    next_due = last_delivered + timedelta(minutes=int(subscription["interval_minutes"]))
    return now >= next_due


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_due_notifications(paths: AppPaths | None = None) -> DeliverySummary:
    return asyncio.run(send_due_notifications(paths))


def _message_signature(message: str) -> str:
    return hashlib.sha256(message.encode("utf-8")).hexdigest()


def _is_duplicate_push(subscription: sqlite3.Row, message_signature: str) -> bool:
    previous_signature = subscription["last_delivered_signature"]
    if previous_signature is None:
        return False
    return str(previous_signature) == message_signature
