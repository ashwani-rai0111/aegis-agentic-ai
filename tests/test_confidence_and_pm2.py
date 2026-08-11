from app.agents.confidence import normalize_confidence
from app.agents.pm2_targets import pick_pm2_restart_target


def test_normalize_confidence_fraction_and_percent():
    assert normalize_confidence(0.9) == 0.9
    assert normalize_confidence(90) == 0.9
    assert normalize_confidence(9000) == 1.0  # 9000/100 then clamp
    assert normalize_confidence(None) == 0.5


def test_pick_pm2_does_not_force_restart_when_healthy():
    procs = [
        {"name": "websites", "status": "online", "unhealthy": False},
        {"name": "node-server", "status": "online", "unhealthy": False},
    ]
    target = pick_pm2_restart_target(
        procs,
        user_message="is my signyn website running?",
        allowlist={"websites", "node-server"},
        only_if_unhealthy=True,
    )
    assert target is None


def test_pick_pm2_selects_unhealthy_websites():
    procs = [
        {"name": "websites", "status": "errored", "unhealthy": True},
        {"name": "node-server", "status": "online", "unhealthy": False},
    ]
    target = pick_pm2_restart_target(
        procs,
        user_message="signyn website is down",
        allowlist={"websites", "node-server"},
    )
    assert target == "websites"


def test_pick_pm2_prefers_stopped_signyn():
    procs = [
        {"name": "signyardsnext", "status": "online", "unhealthy": False},
        {"name": "node-server", "status": "online", "unhealthy": False},
        {"name": "signyn", "status": "stopped", "unhealthy": True},
    ]
    target = pick_pm2_restart_target(
        procs,
        user_message="Is my signyn website is running?",
        allowlist={"signyn", "signyardsnext", "node-server", "websites"},
    )
    assert target == "signyn"
