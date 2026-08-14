"""Classify free-text reports so greetings / chit-chat never trigger AWS investigation."""

from __future__ import annotations

import re

_OPS_KEYWORDS = (
    "down",
    "not working",
    "isn't working",
    "isnt working",
    "not running",
    "isn't running",
    "stopped",
    "error",
    "fail",
    "failed",
    "failure",
    "crash",
    "crashed",
    "slow",
    "timeout",
    "timed out",
    "unreachable",
    "offline",
    "unavailable",
    "502",
    "503",
    "500",
    "latency",
    "memory",
    "cpu",
    "disk",
    "alarm",
    "restart",
    "health",
    "unhealthy",
    "degraded",
    "outage",
    "incident",
    "broken",
    "blank",
    "white screen",
    "can't access",
    "cannot access",
    "unable to",
    "connection refused",
    "too many connections",
    "mysql",
    "database",
    "db ",
    " pm2",
    "pm2 ",
    "ec2",
    "cloudwatch",
    "staging",
    "production",
    "prod ",
    "api ",
    "server",
    "website",
    "site ",
    "signyn",
    "node-server",
    "signyards",
)

_GREETING_PREFIXES = (
    "hi",
    "hello",
    "hey",
    "hola",
    "namaste",
    "yo",
    "good morning",
    "good afternoon",
    "good evening",
    "good night",
    "thanks",
    "thank you",
    "thankyou",
    "bye",
    "goodbye",
    "see you",
    "how are you",
    "how's it going",
    "hows it going",
    "what's up",
    "whats up",
    "sup",
    "ok",
    "okay",
    "cool",
    "great",
    "nice",
    "test",
    "testing",
    "ping",
)

_INTRO_RE = re.compile(
    r"^(hi|hello|hey|hola|namaste)\b.{0,60}\b"
    r"(this is|i am|i'm|im|my name is|here is)\b",
    re.IGNORECASE,
)

_CHAT_ONLY_RE = re.compile(
    r"^(what can you do|who are you|help me|help|please help|"
    r"are you (there|ready|online)|can you hear me)\b",
    re.IGNORECASE,
)

_OUT_OF_SCOPE_MESSAGE = (
    "That looks like a greeting or chat message, not an ops issue. "
    "Describe a real problem (e.g. “signyn website is down”, “MySQL staging error”)."
)


def _normalize(message: str) -> str:
    text = (message or "").strip().lower()
    text = re.sub(r"[^\w\s'@./-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _starts_with_greeting(text: str) -> bool:
    return any(text == g or text.startswith(f"{g} ") for g in _GREETING_PREFIXES)


def _has_ops_signal(text: str) -> bool:
    padded = f" {text} "
    return any(k in padded or k in text for k in _OPS_KEYWORDS)


def out_of_scope_reason(message: str) -> str | None:
    """
    Return a user-facing rejection reason if we should NOT run investigation.
    Return None when the message looks like a real ops report.
    """
    text = _normalize(message)
    if not text or len(text) < 3:
        return "Please describe the issue (at least a few words)."

    if _INTRO_RE.match(text) and not _has_ops_signal(text):
        return _OUT_OF_SCOPE_MESSAGE

    if _CHAT_ONLY_RE.match(text) and not _has_ops_signal(text):
        return _OUT_OF_SCOPE_MESSAGE

    # Pure greeting / very short chit-chat with no ops signal
    if _starts_with_greeting(text) and not _has_ops_signal(text):
        words = text.split()
        if len(words) <= 10:
            return _OUT_OF_SCOPE_MESSAGE

    # Short messages with no ops / service signal at all
    if not _has_ops_signal(text) and len(text.split()) <= 6:
        return _OUT_OF_SCOPE_MESSAGE

    return None


def is_in_scope_issue(message: str) -> bool:
    return out_of_scope_reason(message) is None
