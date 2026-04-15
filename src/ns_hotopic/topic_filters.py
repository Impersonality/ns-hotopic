from __future__ import annotations

HOT_EXCLUSION_KEYWORDS = (
    "抽奖",
    "评论送",
    "送鸡腿",
)
LOTTERY_KEYWORDS = ("抽奖",)


def normalize_title(title: str) -> str:
    return "".join(title.lower().split())


def is_hot_excluded_title(title: str) -> bool:
    normalized = normalize_title(title)
    return any(keyword in normalized for keyword in HOT_EXCLUSION_KEYWORDS)


def is_lottery_title(title: str) -> bool:
    normalized = normalize_title(title)
    return any(keyword in normalized for keyword in LOTTERY_KEYWORDS)
