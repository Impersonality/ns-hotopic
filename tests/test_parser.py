from pathlib import Path

from ns_hotopic.parser import looks_like_challenge_page, parse_homepage


def test_parse_homepage_extracts_topics() -> None:
    html = Path("tests/fixtures/homepage.html").read_text(encoding="utf-8")

    topics = parse_homepage(html, "https://www.nodeseek.com/")

    assert len(topics) == 2
    assert topics[0].topic_id == "12345"
    assert topics[0].title == "[置顶] 第一条帖子"
    assert topics[0].author_name == "alice"
    assert topics[0].node_name == "福利羊毛"
    assert topics[0].view_count == 128
    assert topics[0].comment_count == 7
    assert topics[0].published_text == "3 小时前"
    assert topics[0].is_pinned is True

    assert topics[1].topic_id == "67890"
    assert topics[1].url == "https://www.nodeseek.com/post-67890-1"
    assert topics[1].view_count == 2560
    assert topics[1].comment_count == 42


def test_challenge_detection_matches_cloudflare_marker() -> None:
    html = "<html><body><h2>Performing security verification</h2></body></html>"
    assert looks_like_challenge_page("Just a moment...", html) is True
