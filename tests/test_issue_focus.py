from app.agents.issue_focus import (
    database_focus,
    mentions_database,
    summarize_mysql_for_question,
)


def test_mentions_database_for_staging_question():
    assert mentions_database("is my staging database running fine?")
    assert database_focus("is my staging database running fine?") == "staging"


def test_summarize_staging_healthy():
    summary = summarize_mysql_for_question(
        {
            "healthy": True,
            "severe": False,
            "current_connections": 10,
            "max_connections": 151,
            "threads_running": 2,
            "service": {"status": "active", "healthy": True},
            "production": {"database": "signyards", "healthy": True},
            "staging": {"database": "uatsignyards", "healthy": True},
        },
        "is my staging database running fine?",
    )
    assert summary["healthy"] is True
    assert summary["focus"] == "staging"
    assert "uatsignyards" in summary["root_cause"]
    assert "Website" not in summary["root_cause"]


def test_summarize_staging_unhealthy():
    summary = summarize_mysql_for_question(
        {
            "healthy": False,
            "severe": True,
            "service": {"status": "active", "healthy": True},
            "production": {"database": "signyards", "healthy": True},
            "staging": {
                "database": "uatsignyards",
                "healthy": False,
                "error": "Unknown database",
            },
        },
        "check staging mysql",
    )
    assert summary["healthy"] is False
    assert "NOT healthy" in summary["detail"]
