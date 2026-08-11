from app.tools.mysql_health import evaluate_instance_health, merge_mysql_report


def test_healthy_instance():
    scored = evaluate_instance_health(
        reachable=True,
        service_active=True,
        current_connections=10,
        max_connections=151,
        threads_running=2,
    )
    assert scored["healthy"] is True
    assert scored["severe"] is False
    assert scored["status"] == "online"


def test_saturated_connections_are_severe():
    scored = evaluate_instance_health(
        reachable=True,
        service_active=True,
        current_connections=140,
        max_connections=151,
        threads_running=3,
        conn_saturation_pct=90.0,
    )
    assert scored["healthy"] is False
    assert scored["severe"] is True


def test_merge_includes_prod_and_staging():
    report = merge_mysql_report(
        service={"name": "mysql", "status": "active", "healthy": True},
        globals_={
            "reachable": True,
            "current_connections": 10,
            "max_connections": 151,
            "threads_running": 2,
            "version": "8.0",
        },
        environments={
            "production": {"database": "signyards", "healthy": True},
            "staging": {"database": "uatsignyards", "healthy": True},
        },
    )
    assert report["healthy"] is True
    assert report["production"]["database"] == "signyards"
    assert report["staging"]["database"] == "uatsignyards"
    assert report["current_connections"] == 10


def test_merge_marks_unhealthy_when_staging_probe_fails():
    report = merge_mysql_report(
        service={"name": "mysql", "status": "active", "healthy": True},
        globals_={
            "reachable": True,
            "current_connections": 5,
            "max_connections": 151,
            "threads_running": 1,
        },
        environments={
            "production": {"database": "signyards", "healthy": True},
            "staging": {
                "database": "uatsignyards",
                "healthy": False,
                "error": "Unknown database",
            },
        },
    )
    assert report["healthy"] is False
    assert report["staging"]["healthy"] is False
