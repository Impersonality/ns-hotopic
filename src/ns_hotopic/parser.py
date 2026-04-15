from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .config import CHALLENGE_MARKERS
from .models import TopicSnapshot


ITEM_SELECTORS = (
    ".post-list-item",
    "article.post-list-item",
    ".post-list > li",
    ".post-list > div",
)
TITLE_SELECTORS = (
    ".post-title a[href]",
    "a.post-title[href]",
    "h1 a[href]",
    "h2 a[href]",
    "h3 a[href]",
    "a[href*='/post-']",
)
AUTHOR_SELECTORS = (
    ".info-author > a[href]",
    ".author-info a[href]",
    ".post-author a[href]",
    ".Username",
)
NODE_SELECTORS = (
    "a.post-category[href]",
    ".post-category a[href]",
    ".node-name a[href]",
    "a[href*='/forum-']",
)
TIME_SELECTORS = (
    "time",
    ".post-time",
    ".info-time",
    ".content-time",
)
META_SELECTORS = (
    ".content-info span",
    ".post-info span",
    ".post-meta-info span",
    ".nsk-content-meta-info span",
    ".info-item",
    ".meta-item",
)

TOPIC_ID_PATTERNS = (
    re.compile(r"/post-(\d+)(?:-|$)"),
    re.compile(r"[?&](?:tid|topic_id)=(\d+)"),
)
NUMBER_PATTERN = re.compile(r"(\d[\d,]*)")
PUBLISHED_PATTERN = re.compile(
    r"(\d+\s*(?:秒|分钟|小時|小时|天|月|年)前|\d+\s*(?:seconds?|minutes?|hours?|days?|months?|years?)\s+ago|\d{4}[-/]\d{1,2}[-/]\d{1,2}(?:\s+\d{1,2}:\d{2})?)",
    re.IGNORECASE,
)
VIEW_HINTS = ("eye", "view", "views", "浏览", "查看")
COMMENT_HINTS = ("message", "comment", "comments", "reply", "replies", "回复", "评论")
PINNED_HINTS = ("置顶", "top", "pinned")


def parse_homepage(html: str, base_url: str) -> list[TopicSnapshot]:
    soup = BeautifulSoup(html, "html.parser")
    candidate_items = _find_candidate_items(soup)
    snapshots: list[TopicSnapshot] = []
    seen_urls: set[str] = set()

    for position, item in enumerate(candidate_items, start=1):
        title_link = _select_first(item, TITLE_SELECTORS)
        if title_link is None:
            continue

        href = title_link.get("href")
        title = clean_text(title_link.get_text(" ", strip=True))
        if not href or not title:
            continue

        url = urljoin(base_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        view_count, comment_count = _extract_counts(item)
        snapshots.append(
            TopicSnapshot(
                position=position,
                topic_id=extract_topic_id(url),
                title=title,
                url=url,
                author_name=_extract_text(item, AUTHOR_SELECTORS),
                node_name=_extract_text(item, NODE_SELECTORS),
                view_count=view_count,
                comment_count=comment_count,
                published_text=_extract_published_text(item),
                is_pinned=_detect_pinned(item),
            )
        )

    return snapshots


def looks_like_challenge_page(title: str | None, html: str) -> bool:
    haystack = f"{title or ''}\n{html}".lower()
    return any(marker.lower() in haystack for marker in CHALLENGE_MARKERS)


def extract_topic_id(url: str) -> str:
    for pattern in TOPIC_ID_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return url


def clean_text(value: str) -> str:
    return " ".join(value.split())


def _find_candidate_items(soup: BeautifulSoup) -> list[Tag]:
    for selector in ITEM_SELECTORS:
        items = soup.select(selector)
        if items:
            return list(items)

    items: list[Tag] = []
    for link in soup.select("a[href*='/post-']"):
        parent = _first_structural_parent(link)
        if parent is not None:
            items.append(parent)
    return items


def _first_structural_parent(tag: Tag) -> Tag | None:
    for parent in tag.parents:
        if not isinstance(parent, Tag):
            continue
        if parent.name in {"li", "article"}:
            return parent
        class_names = set(parent.get("class", []))
        if {"post-list-item", "post-item"} & class_names:
            return parent
    return None


def _select_first(tag: Tag, selectors: Iterable[str]) -> Tag | None:
    for selector in selectors:
        match = tag.select_one(selector)
        if isinstance(match, Tag):
            return match
    return None


def _extract_text(tag: Tag, selectors: Iterable[str]) -> str | None:
    node = _select_first(tag, selectors)
    if node is None:
        return None
    text = clean_text(node.get_text(" ", strip=True))
    return text or None


def _extract_counts(tag: Tag) -> tuple[int | None, int | None]:
    view_count: int | None = None
    comment_count: int | None = None

    for meta in _iter_meta_nodes(tag):
        text = clean_text(meta.get_text(" ", strip=True))
        if not text:
            continue
        value = _parse_number(text)
        if value is None:
            continue

        icon_refs = " ".join(
            part
            for use in meta.select("use")
            for part in (use.get("href"), use.get("xlink:href"))
            if part
        )
        classification = f"{icon_refs} {text}".lower()
        if any(hint in classification for hint in COMMENT_HINTS) and comment_count is None:
            comment_count = value
        elif any(hint in classification for hint in VIEW_HINTS) and view_count is None:
            view_count = value

    if view_count is not None or comment_count is not None:
        return view_count, comment_count

    body_text = clean_text(tag.get_text(" ", strip=True))
    if view_count is None:
        match = re.search(r"(?:浏览|查看|views?)\D*(\d[\d,]*)", body_text, re.IGNORECASE)
        if match:
            view_count = _parse_number(match.group(1))
    if comment_count is None:
        match = re.search(r"(?:回复|评论|repl(?:y|ies)|comments?)\D*(\d[\d,]*)", body_text, re.IGNORECASE)
        if match:
            comment_count = _parse_number(match.group(1))

    return view_count, comment_count


def _iter_meta_nodes(tag: Tag) -> Iterable[Tag]:
    seen: set[int] = set()
    for selector in META_SELECTORS:
        for node in tag.select(selector):
            if id(node) in seen:
                continue
            seen.add(id(node))
            if isinstance(node, Tag):
                yield node


def _parse_number(text: str) -> int | None:
    match = NUMBER_PATTERN.search(text)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _extract_published_text(tag: Tag) -> str | None:
    for selector in TIME_SELECTORS:
        node = tag.select_one(selector)
        if isinstance(node, Tag):
            text = clean_text(node.get_text(" ", strip=True))
            if text:
                return text

    body_text = clean_text(tag.get_text(" ", strip=True))
    match = PUBLISHED_PATTERN.search(body_text)
    if match:
        return match.group(1)
    return None


def _detect_pinned(tag: Tag) -> bool:
    classes = {class_name.lower() for class_name in tag.get("class", [])}
    if {"top", "pinned", "sticky"} & classes:
        return True

    title = _extract_text(tag, TITLE_SELECTORS) or ""
    full_text = f"{title} {clean_text(tag.get_text(' ', strip=True))}".lower()
    return any(hint in full_text for hint in PINNED_HINTS)
