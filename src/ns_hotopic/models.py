from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class TopicSnapshot:
    position: int
    topic_id: str
    title: str
    url: str
    author_name: str | None = None
    node_name: str | None = None
    view_count: int | None = None
    comment_count: int | None = None
    published_text: str | None = None
    is_pinned: bool = False


@dataclass(slots=True)
class CrawlResult:
    started_at: str
    finished_at: str
    status: str
    page_url: str
    item_count: int
    page_title: str | None
    error_message: str | None = None
    html_artifact_path: Path | None = None
    snapshots: list[TopicSnapshot] = field(default_factory=list)


@dataclass(slots=True)
class TopicObservation:
    topic_id: str
    title: str
    url: str
    captured_at: str
    position: int
    view_count: int | None = None
    comment_count: int | None = None
    is_pinned: bool = False


@dataclass(slots=True)
class HotTopicRanking:
    rank: int
    topic_id: str
    title: str
    url: str
    score: float
    comment_delta: int
    view_delta: int
    position_gain: int
    appearance_count: int
    earliest_position: int
    latest_position: int
    latest_comment_count: int
    latest_view_count: int


@dataclass(slots=True)
class HotTopicRunResult:
    source_crawl_run_id: int | None
    computed_at: str
    window_start: str
    window_end: str
    algorithm_version: str
    candidate_count: int
    ranking_count: int
    rankings: list[HotTopicRanking] = field(default_factory=list)
