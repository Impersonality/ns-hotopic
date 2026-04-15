from __future__ import annotations

import math
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from typing import cast

from .models import HotTopicRanking, HotTopicRunResult, TopicObservation
from .storage import save_hot_topic_run_result
from .topic_filters import is_hot_excluded_title

WINDOW_HOURS = 6
COMMENT_WEIGHT = 12
VIEW_LOG_WEIGHT = 4
MAX_APPEARANCE_BONUS = 6
FRESHNESS_MAX_BOOST = 0.15
FRESHNESS_MAX_DECAY = 0.30
SINGLE_OBSERVATION_TOP_RATIO = 0.2
SINGLE_OBSERVATION_POSITION_THRESHOLD = 10
SINGLE_OBSERVATION_TOP_POSITION_BONUS_THRESHOLD = 10
SINGLE_OBSERVATION_MID_POSITION_BONUS_THRESHOLD = 20
SINGLE_OBSERVATION_TOP_POSITION_BONUS = 3
SINGLE_OBSERVATION_MID_POSITION_BONUS = 1
SINGLE_OBSERVATION_COMMENT_CAP = 80
SINGLE_OBSERVATION_VIEW_CAP = 1500
SINGLE_OBSERVATION_COMMENT_LOG_WEIGHT = 8
SINGLE_OBSERVATION_VIEW_LOG_WEIGHT = 2
TOPIC_URL_ID_PATTERN = re.compile(r"/post-(\d+)-")
ALGORITHM_VERSION = "v5_comment12_logview4_presence1_singlelatestmix_positionbucket_freshid15_window6h_exclude_pinned_giveaway"


def calculate_and_store_hot_topics(
    connection: sqlite3.Connection,
    *,
    source_crawl_run_id: int,
    computed_at: str,
) -> tuple[int, HotTopicRunResult]:
    window_end_dt = datetime.fromisoformat(computed_at)
    window_start = (window_end_dt - timedelta(hours=WINDOW_HOURS)).isoformat(timespec="seconds")
    observations = load_observations(
        connection,
        window_start=window_start,
        window_end=computed_at,
    )
    result = calculate_hot_topics(
        observations,
        source_crawl_run_id=source_crawl_run_id,
        window_start=window_start,
        window_end=computed_at,
    )
    hot_topic_run_id = save_hot_topic_run_result(connection, result)
    return hot_topic_run_id, result


def calculate_hot_topics(
    observations: list[TopicObservation],
    *,
    source_crawl_run_id: int | None,
    window_start: str,
    window_end: str,
) -> HotTopicRunResult:
    grouped: dict[str, list[TopicObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.topic_id].append(observation)

    for points in grouped.values():
        points.sort(key=lambda point: (point.captured_at, point.position))

    topic_numeric_ids = {
        topic_id: _topic_numeric_id(points[-1])
        for topic_id, points in grouped.items()
    }
    newest_topic_numeric_id = max(
        (numeric_id for numeric_id in topic_numeric_ids.values() if numeric_id is not None),
        default=None,
    )
    latest_points = [
        points[-1]
        for points in grouped.values()
        if points[-1].captured_at == window_end
        and not points[-1].is_pinned
        and not is_hot_excluded_title(points[-1].title)
    ]
    latest_comment_threshold = _top_ratio_threshold(
        [_safe_count(point.comment_count) for point in latest_points],
        top_ratio=SINGLE_OBSERVATION_TOP_RATIO,
    )
    latest_view_threshold = _top_ratio_threshold(
        [_safe_count(point.view_count) for point in latest_points],
        top_ratio=SINGLE_OBSERVATION_TOP_RATIO,
    )

    rankings: list[HotTopicRanking] = []
    candidate_count = 0

    for topic_id, points in grouped.items():
        latest = points[-1]
        if any(point.is_pinned for point in points):
            continue
        if is_hot_excluded_title(latest.title):
            continue

        if len(points) == 1:
            if not _is_single_observation_candidate(
                latest,
                window_end=window_end,
                comment_threshold=latest_comment_threshold,
                view_threshold=latest_view_threshold,
            ):
                continue

            latest_comment_count = _safe_count(latest.comment_count)
            latest_view_count = _safe_count(latest.view_count)
            appearance_count = 1
            freshness_multiplier = _freshness_multiplier(
                topic_numeric_ids.get(topic_id),
                newest_topic_numeric_id,
            )
            score = round(
                _single_observation_score(
                    comment_count=latest_comment_count,
                    view_count=latest_view_count,
                    position=latest.position,
                )
                * freshness_multiplier,
                6,
            )

            candidate_count += 1
            rankings.append(
                HotTopicRanking(
                    rank=0,
                    topic_id=topic_id,
                    title=latest.title,
                    url=latest.url,
                    score=score,
                    comment_delta=latest_comment_count,
                    view_delta=latest_view_count,
                    position_gain=0,
                    appearance_count=appearance_count,
                    earliest_position=latest.position,
                    latest_position=latest.position,
                    latest_comment_count=latest_comment_count,
                    latest_view_count=latest_view_count,
                )
            )
            continue

        candidate_count += 1

        earliest = points[0]
        earliest_comment_count = _safe_count(earliest.comment_count)
        latest_comment_count = _safe_count(latest.comment_count)
        earliest_view_count = _safe_count(earliest.view_count)
        latest_view_count = _safe_count(latest.view_count)

        comment_delta = max(latest_comment_count - earliest_comment_count, 0)
        view_delta = max(latest_view_count - earliest_view_count, 0)
        if comment_delta == 0 and view_delta == 0:
            continue

        appearance_count = len(points)
        freshness_multiplier = _freshness_multiplier(
            topic_numeric_ids.get(topic_id),
            newest_topic_numeric_id,
        )
        engagement_score = (
            comment_delta * COMMENT_WEIGHT
            + math.log1p(view_delta) * VIEW_LOG_WEIGHT
            + min(appearance_count, MAX_APPEARANCE_BONUS)
        )
        score = round(
            engagement_score * freshness_multiplier,
            6,
        )

        rankings.append(
            HotTopicRanking(
                rank=0,
                topic_id=topic_id,
                title=latest.title,
                url=latest.url,
                score=score,
                comment_delta=comment_delta,
                view_delta=view_delta,
                position_gain=0,
                appearance_count=appearance_count,
                earliest_position=earliest.position,
                latest_position=latest.position,
                latest_comment_count=latest_comment_count,
                latest_view_count=latest_view_count,
            )
        )

    rankings.sort(
        key=lambda ranking: (
            -ranking.score,
            -ranking.comment_delta,
            -ranking.view_delta,
            -ranking.appearance_count,
            -(topic_numeric_ids.get(ranking.topic_id) or 0),
            ranking.topic_id,
        )
    )
    for index, ranking in enumerate(rankings, start=1):
        ranking.rank = index

    return HotTopicRunResult(
        source_crawl_run_id=source_crawl_run_id,
        computed_at=window_end,
        window_start=window_start,
        window_end=window_end,
        algorithm_version=ALGORITHM_VERSION,
        candidate_count=candidate_count,
        ranking_count=len(rankings),
        rankings=rankings,
    )


def load_observations(
    connection: sqlite3.Connection,
    *,
    window_start: str,
    window_end: str,
) -> list[TopicObservation]:
    rows = connection.execute(
        """
        SELECT
            topic_id,
            title,
            url,
            captured_at,
            position,
            view_count,
            comment_count,
            is_pinned
        FROM topic_snapshots
        WHERE captured_at >= ? AND captured_at <= ?
        ORDER BY topic_id ASC, captured_at ASC, position ASC
        """,
        (window_start, window_end),
    ).fetchall()
    return [
        TopicObservation(
            topic_id=cast(str, row["topic_id"]),
            title=cast(str, row["title"]),
            url=cast(str, row["url"]),
            captured_at=cast(str, row["captured_at"]),
            position=int(row["position"]),
            view_count=_optional_int(row["view_count"]),
            comment_count=_optional_int(row["comment_count"]),
            is_pinned=bool(row["is_pinned"]),
        )
        for row in rows
    ]


def _safe_count(value: int | None) -> int:
    return value if value is not None else 0


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _topic_numeric_id(observation: TopicObservation) -> int | None:
    if observation.topic_id.isdigit():
        return int(observation.topic_id)
    match = TOPIC_URL_ID_PATTERN.search(observation.url)
    if match is None:
        return None
    return int(match.group(1))


def _freshness_multiplier(
    topic_numeric_id: int | None,
    newest_topic_numeric_id: int | None,
) -> float:
    if topic_numeric_id is None or newest_topic_numeric_id is None:
        return 1.0

    gap = max(newest_topic_numeric_id - topic_numeric_id, 0)
    decay = min(math.sqrt(gap) / 1000, FRESHNESS_MAX_DECAY)
    return round(1.0 + FRESHNESS_MAX_BOOST - decay, 6)


def _top_ratio_threshold(values: list[int], *, top_ratio: float) -> int:
    if not values:
        return 0

    sorted_values = sorted(values, reverse=True)
    top_count = max(1, math.ceil(len(sorted_values) * top_ratio))
    return sorted_values[top_count - 1]


def _is_single_observation_candidate(
    latest: TopicObservation,
    *,
    window_end: str,
    comment_threshold: int,
    view_threshold: int,
) -> bool:
    comment_count = _safe_count(latest.comment_count)
    view_count = _safe_count(latest.view_count)
    if comment_count == 0 and view_count == 0:
        return False
    if latest.captured_at != window_end:
        return False
    return (
        latest.position <= SINGLE_OBSERVATION_POSITION_THRESHOLD
        or comment_count >= comment_threshold
        or view_count >= view_threshold
    )


def _single_observation_score(*, comment_count: int, view_count: int, position: int) -> float:
    capped_comment_count = min(comment_count, SINGLE_OBSERVATION_COMMENT_CAP)
    capped_view_count = min(view_count, SINGLE_OBSERVATION_VIEW_CAP)
    return (
        math.log1p(capped_comment_count) * SINGLE_OBSERVATION_COMMENT_LOG_WEIGHT
        + math.log1p(capped_view_count) * SINGLE_OBSERVATION_VIEW_LOG_WEIGHT
        + _single_observation_position_bonus(position)
        + 1
    )


def _single_observation_position_bonus(position: int) -> int:
    if position <= SINGLE_OBSERVATION_TOP_POSITION_BONUS_THRESHOLD:
        return SINGLE_OBSERVATION_TOP_POSITION_BONUS
    if position <= SINGLE_OBSERVATION_MID_POSITION_BONUS_THRESHOLD:
        return SINGLE_OBSERVATION_MID_POSITION_BONUS
    return 0
