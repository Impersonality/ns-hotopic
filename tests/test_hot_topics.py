from ns_hotopic.hot_topics import ALGORITHM_VERSION, calculate_hot_topics
from ns_hotopic.models import TopicObservation


def test_calculate_hot_topics_prefers_comment_growth_even_without_position_signal() -> None:
    observations = [
        TopicObservation(
            topic_id="a",
            title="A",
            url="https://www.nodeseek.com/post-1-1",
            captured_at="2026-04-14T10:00:00+08:00",
            position=10,
            view_count=10,
            comment_count=1,
        ),
        TopicObservation(
            topic_id="a",
            title="A",
            url="https://www.nodeseek.com/post-1-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=2,
            view_count=40,
            comment_count=5,
        ),
        TopicObservation(
            topic_id="b",
            title="B",
            url="https://www.nodeseek.com/post-2-1",
            captured_at="2026-04-14T10:00:00+08:00",
            position=1,
            view_count=100,
            comment_count=0,
        ),
        TopicObservation(
            topic_id="b",
            title="B",
            url="https://www.nodeseek.com/post-2-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=1,
            view_count=400,
            comment_count=2,
        ),
        TopicObservation(
            topic_id="pinned",
            title="Pinned",
            url="https://www.nodeseek.com/post-3-1",
            captured_at="2026-04-14T10:00:00+08:00",
            position=1,
            view_count=1000,
            comment_count=10,
            is_pinned=True,
        ),
        TopicObservation(
            topic_id="pinned",
            title="Pinned",
            url="https://www.nodeseek.com/post-3-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=1,
            view_count=1100,
            comment_count=30,
            is_pinned=True,
        ),
        TopicObservation(
            topic_id="single",
            title="Single",
            url="https://www.nodeseek.com/post-4-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=6,
            view_count=10,
            comment_count=1,
        ),
        TopicObservation(
            topic_id="giveaway",
            title="【抽奖】plus 直冲卡密低至7.5",
            url="https://www.nodeseek.com/post-7-1",
            captured_at="2026-04-14T10:00:00+08:00",
            position=20,
            view_count=10,
            comment_count=1,
        ),
        TopicObservation(
            topic_id="giveaway",
            title="【抽奖】plus 直冲卡密低至7.5",
            url="https://www.nodeseek.com/post-7-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=2,
            view_count=200,
            comment_count=15,
        ),
    ]

    result = calculate_hot_topics(
        observations,
        source_crawl_run_id=2,
        window_start="2026-04-14T06:00:00+08:00",
        window_end="2026-04-14T12:00:00+08:00",
    )

    assert result.algorithm_version == ALGORITHM_VERSION
    assert result.candidate_count == 3
    assert result.ranking_count == 3
    assert [ranking.topic_id for ranking in result.rankings] == ["a", "b", "single"]
    assert result.rankings[0].comment_delta == 4
    assert result.rankings[0].position_gain == 0
    assert result.rankings[0].rank == 1
    assert result.rankings[1].rank == 2


def test_calculate_hot_topics_filters_topics_with_only_position_change() -> None:
    observations = [
        TopicObservation(
            topic_id="position-only",
            title="Position",
            url="https://www.nodeseek.com/post-5-1",
            captured_at="2026-04-14T10:00:00+08:00",
            position=8,
            view_count=100,
            comment_count=5,
        ),
        TopicObservation(
            topic_id="position-only",
            title="Position",
            url="https://www.nodeseek.com/post-5-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=3,
            view_count=90,
            comment_count=4,
        ),
        TopicObservation(
            topic_id="flat",
            title="Flat",
            url="https://www.nodeseek.com/post-6-1",
            captured_at="2026-04-14T10:00:00+08:00",
            position=4,
            view_count=50,
            comment_count=1,
        ),
        TopicObservation(
            topic_id="flat",
            title="Flat",
            url="https://www.nodeseek.com/post-6-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=4,
            view_count=50,
            comment_count=1,
        ),
    ]

    result = calculate_hot_topics(
        observations,
        source_crawl_run_id=2,
        window_start="2026-04-14T06:00:00+08:00",
        window_end="2026-04-14T12:00:00+08:00",
    )

    assert result.candidate_count == 2
    assert result.ranking_count == 0


def test_calculate_hot_topics_softly_prefers_newer_topics_with_same_engagement() -> None:
    observations = [
        TopicObservation(
            topic_id="100000",
            title="旧帖",
            url="https://www.nodeseek.com/post-100000-1",
            captured_at="2026-04-14T10:00:00+08:00",
            position=5,
            view_count=100,
            comment_count=1,
        ),
        TopicObservation(
            topic_id="100000",
            title="旧帖",
            url="https://www.nodeseek.com/post-100000-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=4,
            view_count=160,
            comment_count=4,
        ),
        TopicObservation(
            topic_id="190000",
            title="新帖",
            url="https://www.nodeseek.com/post-190000-1",
            captured_at="2026-04-14T10:00:00+08:00",
            position=8,
            view_count=100,
            comment_count=1,
        ),
        TopicObservation(
            topic_id="190000",
            title="新帖",
            url="https://www.nodeseek.com/post-190000-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=7,
            view_count=160,
            comment_count=4,
        ),
    ]

    result = calculate_hot_topics(
        observations,
        source_crawl_run_id=2,
        window_start="2026-04-14T06:00:00+08:00",
        window_end="2026-04-14T12:00:00+08:00",
    )

    assert [ranking.topic_id for ranking in result.rankings] == ["190000", "100000"]
    assert result.rankings[0].score > result.rankings[1].score


def test_calculate_hot_topics_allows_latest_single_observation_high_signal_topic() -> None:
    observations = [
        TopicObservation(
            topic_id="300000",
            title="增量帖子",
            url="https://www.nodeseek.com/post-300000-1",
            captured_at="2026-04-14T10:00:00+08:00",
            position=8,
            view_count=20,
            comment_count=1,
        ),
        TopicObservation(
            topic_id="300000",
            title="增量帖子",
            url="https://www.nodeseek.com/post-300000-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=3,
            view_count=80,
            comment_count=3,
        ),
        TopicObservation(
            topic_id="400000",
            title="新进高热帖子",
            url="https://www.nodeseek.com/post-400000-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=2,
            view_count=635,
            comment_count=35,
        ),
        TopicObservation(
            topic_id="200000",
            title="旧窗口单次帖子",
            url="https://www.nodeseek.com/post-200000-1",
            captured_at="2026-04-14T11:00:00+08:00",
            position=1,
            view_count=900,
            comment_count=100,
        ),
        TopicObservation(
            topic_id="500000",
            title="低信号单次帖子",
            url="https://www.nodeseek.com/post-500000-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=28,
            view_count=5,
            comment_count=0,
        ),
    ]

    result = calculate_hot_topics(
        observations,
        source_crawl_run_id=2,
        window_start="2026-04-14T06:00:00+08:00",
        window_end="2026-04-14T12:00:00+08:00",
    )

    assert [ranking.topic_id for ranking in result.rankings] == ["400000", "300000"]
    assert result.rankings[0].appearance_count == 1
    assert result.rankings[0].comment_delta == 35
    assert result.rankings[0].view_delta == 635
    assert result.rankings[1].appearance_count == 2


def test_calculate_hot_topics_uses_bucketed_position_bonus_for_single_observation_topics() -> None:
    observations = [
        TopicObservation(
            topic_id="top-2",
            title="前排第2",
            url="https://www.nodeseek.com/post-500000-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=2,
            view_count=300,
            comment_count=20,
        ),
        TopicObservation(
            topic_id="top-9",
            title="前排第9",
            url="https://www.nodeseek.com/post-500000-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=9,
            view_count=300,
            comment_count=20,
        ),
        TopicObservation(
            topic_id="mid-15",
            title="中段第15",
            url="https://www.nodeseek.com/post-500000-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=15,
            view_count=300,
            comment_count=20,
        ),
    ]

    result = calculate_hot_topics(
        observations,
        source_crawl_run_id=2,
        window_start="2026-04-14T06:00:00+08:00",
        window_end="2026-04-14T12:00:00+08:00",
    )

    rankings = {ranking.topic_id: ranking for ranking in result.rankings}
    assert rankings["top-2"].score == rankings["top-9"].score
    assert rankings["top-2"].score > rankings["mid-15"].score


def test_calculate_hot_topics_excludes_comment_giveaway_titles() -> None:
    observations = [
        TopicObservation(
            topic_id="giveaway",
            title="【评论送鸡腿】溢价60包push收个Vmiss 美西US.LA.TRI.Basic 月付4CAD",
            url="https://www.nodeseek.com/post-8-1",
            captured_at="2026-04-14T10:00:00+08:00",
            position=15,
            view_count=20,
            comment_count=1,
        ),
        TopicObservation(
            topic_id="giveaway",
            title="【评论送鸡腿】溢价60包push收个Vmiss 美西US.LA.TRI.Basic 月付4CAD",
            url="https://www.nodeseek.com/post-8-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=3,
            view_count=140,
            comment_count=7,
        ),
        TopicObservation(
            topic_id="normal",
            title="正常帖子",
            url="https://www.nodeseek.com/post-9-1",
            captured_at="2026-04-14T10:00:00+08:00",
            position=5,
            view_count=10,
            comment_count=1,
        ),
        TopicObservation(
            topic_id="normal",
            title="正常帖子",
            url="https://www.nodeseek.com/post-9-1",
            captured_at="2026-04-14T12:00:00+08:00",
            position=2,
            view_count=20,
            comment_count=2,
        ),
    ]

    result = calculate_hot_topics(
        observations,
        source_crawl_run_id=2,
        window_start="2026-04-14T06:00:00+08:00",
        window_end="2026-04-14T12:00:00+08:00",
    )

    assert result.candidate_count == 1
    assert result.ranking_count == 1
    assert result.rankings[0].topic_id == "normal"
