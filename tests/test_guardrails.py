from app.models import AgentAction, Locator
from app.security import PolicyGuard, redact


def test_domain_allowlist():
    guard = PolicyGuard({"127.0.0.1:8001"})
    assert guard.check_url("http://127.0.0.1:8001").allowed
    assert not guard.check_url("https://example.com").allowed


def test_risky_action_requires_human():
    guard = PolicyGuard({"127.0.0.1:8001"})
    decision = guard.check_action(
        AgentAction(action="click", locator=Locator(strategy="text", value="Confirm Open Account"))
    )
    assert not decision.allowed
    assert decision.requires_human


def test_redaction():
    assert "[REDACTED]" in redact("password=abc123")
