import os
from pathlib import Path

from ns_hotopic import config


def test_get_settings_loads_dotenv_and_parses_ints(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.1.0'\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TELEGRAM_BOT_TOKEN=test-token",
                "NODESEEK_HOME_URL=https://example.com/",
                "NS_HOTOPIC_CRAWL_RETENTION_DAYS=61",
                "NS_HOTOPIC_HOT_RETENTION_DAYS=181",
                "NS_HOTOPIC_BOT_LOG_RETENTION_DAYS=31",
                "NS_HOTOPIC_ARTIFACT_RETENTION_DAYS=8",
                "NS_HOTOPIC_FETCH_INTERVAL_MINUTES=29",
                "NS_HOTOPIC_DELIVERY_CHECK_INTERVAL_MINUTES=4",
                "NS_HOTOPIC_CLEANUP_INTERVAL_MINUTES=1439",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("NODESEEK_HOME_URL", raising=False)
    monkeypatch.delenv("NS_HOTOPIC_CRAWL_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("NS_HOTOPIC_HOT_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("NS_HOTOPIC_BOT_LOG_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("NS_HOTOPIC_ARTIFACT_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("NS_HOTOPIC_FETCH_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("NS_HOTOPIC_DELIVERY_CHECK_INTERVAL_MINUTES", raising=False)
    monkeypatch.delenv("NS_HOTOPIC_CLEANUP_INTERVAL_MINUTES", raising=False)
    config.get_settings.cache_clear()

    settings = config.get_settings()

    assert settings.root_dir == tmp_path
    assert settings.telegram_bot_token == "test-token"
    assert settings.home_url == "https://example.com/"
    assert settings.crawl_retention_days == 61
    assert settings.hot_topic_retention_days == 181
    assert settings.bot_delivery_log_retention_days == 31
    assert settings.artifact_retention_days == 8
    assert settings.fetch_interval_minutes == 29
    assert settings.delivery_check_interval_minutes == 4
    assert settings.cleanup_interval_minutes == 1439
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "NODESEEK_HOME_URL",
        "NS_HOTOPIC_CRAWL_RETENTION_DAYS",
        "NS_HOTOPIC_HOT_RETENTION_DAYS",
        "NS_HOTOPIC_BOT_LOG_RETENTION_DAYS",
        "NS_HOTOPIC_ARTIFACT_RETENTION_DAYS",
        "NS_HOTOPIC_FETCH_INTERVAL_MINUTES",
        "NS_HOTOPIC_DELIVERY_CHECK_INTERVAL_MINUTES",
        "NS_HOTOPIC_CLEANUP_INTERVAL_MINUTES",
    ):
        os.environ.pop(name, None)
    config.get_settings.cache_clear()
