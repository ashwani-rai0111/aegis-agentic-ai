from app.policies.safety import evaluate_action


def test_read_only_tool_allowed():
    decision = evaluate_action("get_system_metrics", {})
    assert decision.allowed is True
    assert decision.approval_required is False


def test_allowlisted_pm2_restart_auto_approved():
    decision = evaluate_action(
        "restart_pm2_process",
        {"process_name": "api"},
        actions_already_taken=0,
    )
    assert decision.allowed is True
    assert decision.approval_required is False
    assert decision.risk.value == "LOW"


def test_unknown_action_blocked():
    decision = evaluate_action("rm_rf_production", {})
    assert decision.allowed is False


def test_non_allowlisted_process_blocked():
    decision = evaluate_action(
        "restart_pm2_process",
        {"process_name": "payments-critical"},
    )
    assert decision.allowed is False


def test_action_limit():
    decision = evaluate_action(
        "restart_pm2_process",
        {"process_name": "api"},
        actions_already_taken=1,
    )
    assert decision.allowed is False