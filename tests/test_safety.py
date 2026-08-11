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


def test_allowlisted_websites_and_node_server():
    for name in ("websites", "node-server", "signyn", "signyardsnext"):
        decision = evaluate_action(
            "restart_pm2_process",
            {"process_name": name},
            actions_already_taken=0,
        )
        assert decision.allowed is True
        assert decision.risk.value == "LOW"


def test_low_risk_clear_temp_auto():
    decision = evaluate_action("clear_temp_files", {})
    assert decision.allowed is True
    assert decision.approval_required is False
    assert decision.risk.value == "LOW"


def test_medium_risk_mysql_requires_approval():
    decision = evaluate_action("restart_mysql", {})
    assert decision.allowed is False
    assert decision.approval_required is True
    assert decision.risk.value == "MEDIUM"


def test_medium_risk_mysql_allowed_after_approval():
    decision = evaluate_action("restart_mysql", {}, already_approved=True)
    assert decision.allowed is True
    assert decision.risk.value == "MEDIUM"


def test_critical_action_never_auto_even_if_approved():
    decision = evaluate_action(
        "drop_database", {}, already_approved=True
    )
    assert decision.allowed is False
    assert decision.risk.value == "CRITICAL"


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
