from app.services.issue_scope import is_in_scope_issue, out_of_scope_reason


def test_greetings_are_out_of_scope():
    for msg in (
        "hi",
        "hello",
        "hi this is ashwani",
        "hey I am Ashwani",
        "good morning",
        "thanks",
        "what can you do",
        "ok",
    ):
        assert out_of_scope_reason(msg), msg
        assert not is_in_scope_issue(msg)


def test_ops_reports_are_in_scope():
    for msg in (
        "my signyn website is not working",
        "hi, signyn website is down",
        "MySQL staging error",
        "node-server seems down",
        "website is slow / not loading",
        "pm2 process crashed",
        "check production database connections",
    ):
        assert out_of_scope_reason(msg) is None, msg
        assert is_in_scope_issue(msg)
