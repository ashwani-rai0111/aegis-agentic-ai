from app.agents.issue_focus import (
    build_focused_live_answer,
    classify_issue_focus,
    summarize_mysql_for_question,
)


def test_classify_website_vs_node_server():
    assert classify_issue_focus("is my signyn website running") == "website"
    assert classify_issue_focus("seems node server down") == "node_server"
    assert classify_issue_focus("node-server seems down") == "node_server"
    assert classify_issue_focus("staging database not reachable") == "database"


def test_node_server_answer_ignores_website_http():
    mysql = summarize_mysql_for_question(
        {
            "healthy": True,
            "service": {"healthy": True, "status": "active"},
            "production": {"healthy": True, "database": "signyards"},
            "staging": {"healthy": True, "database": "uatsignyards"},
            "current_connections": 10,
            "max_connections": 151,
            "threads_running": 2,
        },
        "node-server seems down",
    )
    answer = build_focused_live_answer(
        report="node-server seems down",
        health_block={
            "health": {
                "ok": True,
                "http_status": 200,
                "endpoint": "https://signyn.com",
            }
        },
        processes=[
            {
                "name": "signyn",
                "status": "online",
                "memory_mb": 100,
                "cpu": 1,
                "restarts": 0,
                "unhealthy": False,
            },
            {
                "name": "node-server",
                "status": "online",
                "memory_mb": 220,
                "cpu": 3,
                "restarts": 1,
                "unhealthy": False,
            },
        ],
        mysql_summary=mysql,
        allowlist={"signyn", "node-server", "api"},
    )
    assert answer["focus"] == "node_server"
    assert answer["healthy"] is True
    assert "node-server" in answer["root_cause"]
    assert "signyn.com" not in answer["root_cause"]
    assert "MySQL" not in answer["root_cause"]


def test_website_answer_mentions_http():
    mysql = summarize_mysql_for_question({"healthy": True}, "is signyn website running")
    answer = build_focused_live_answer(
        report="is my signyn website running",
        health_block={
            "health": {
                "ok": True,
                "http_status": 200,
                "endpoint": "https://signyn.com",
            }
        },
        processes=[
            {
                "name": "signyn",
                "status": "online",
                "memory_mb": 100,
                "cpu": 1,
                "restarts": 0,
                "unhealthy": False,
            }
        ],
        mysql_summary=mysql,
        allowlist={"signyn", "node-server"},
    )
    assert answer["focus"] == "website"
    assert "signyn.com" in answer["root_cause"] or "HTTP 200" in answer["root_cause"]
