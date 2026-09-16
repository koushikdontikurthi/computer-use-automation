from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.models import AgentAction, ActionType


SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(password|token|secret|authorization)\s*[:=]\s*\S+"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b\d{13,19}\b"),
]


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    requires_human: bool = False


class PolicyGuard:
    def __init__(self, allowed_hosts: set[str]):
        self.allowed_hosts = allowed_hosts
        self.allowed_actions = {
            ActionType.navigate,
            ActionType.click,
            ActionType.type,
            ActionType.read,
            ActionType.wait,
            ActionType.done,
            ActionType.escalate,
        }
        self.risky_terms = {"delete", "transfer", "submit payment", "open account", "confirm open"}

    def check_url(self, url: str) -> PolicyDecision:
        parsed = urlparse(url)
        host = parsed.netloc
        if parsed.scheme not in {"http", "https"}:
            return PolicyDecision(False, f"scheme {parsed.scheme!r} is not allowed")
        if host not in self.allowed_hosts:
            return PolicyDecision(False, f"host {host!r} is outside the allowlist")
        return PolicyDecision(True, "target is allowlisted")

    def check_action(self, action: AgentAction) -> PolicyDecision:
        if action.action not in self.allowed_actions:
            return PolicyDecision(False, f"action {action.action} is not allowed")
        target = " ".join(
            part for part in [action.value, action.locator.value if action.locator else ""] if part
        ).lower()
        if action.risky or any(term in target for term in self.risky_terms):
            return PolicyDecision(False, "risky/irreversible action requires human approval", True)
        return PolicyDecision(True, "action permitted")


def redact(text: str) -> str:
    redacted = text
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted
