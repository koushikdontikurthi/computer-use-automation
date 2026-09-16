from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    navigate = "navigate"
    click = "click"
    type = "type"
    read = "read"
    wait = "wait"
    done = "done"
    escalate = "escalate"


class Locator(BaseModel):
    strategy: Literal["role", "label", "text", "css"]
    value: str
    role: str | None = None
    exact: bool = False


class AgentAction(BaseModel):
    action: ActionType
    locator: Locator | None = None
    value: str | None = None
    output_name: str | None = None
    reason: str = ""
    risky: bool = False


class CapabilityInput(BaseModel):
    name: str
    type: Literal["string", "integer", "number", "boolean"] = "string"
    required: bool = True
    description: str = ""


class CapabilityOutput(BaseModel):
    name: str
    type: Literal["string", "integer", "number", "boolean"] = "string"
    description: str = ""


class CapabilityStep(BaseModel):
    id: str
    action: Literal["navigate", "click", "type", "read", "wait"]
    locator_candidates: list[Locator] = Field(default_factory=list)
    value: str | None = None
    output_name: str | None = None
    retry_count: int = 1
    timeout_ms: int = 10_000
    reversible: bool = True


class SuccessCondition(BaseModel):
    kind: Literal["url_contains", "text_visible", "output_present"]
    value: str


class CapabilityArtifact(BaseModel):
    schema_version: str = "1.0"
    capability_id: str
    name: str
    description: str
    app_family: str
    artifact_version: int = 1
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    target_entrypoint: str
    inputs: list[CapabilityInput]
    outputs: list[CapabilityOutput]
    steps: list[CapabilityStep]
    success_condition: SuccessCondition
    tenant_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    approved: bool = False


class ResultStatus(str, Enum):
    success = "success"
    business_outcome = "business_outcome"
    recoverable_exhausted = "recoverable_exhausted"
    hard_failure = "hard_failure"
    escalated = "escalated"


class RunResult(BaseModel):
    status: ResultStatus
    outputs: dict[str, Any] = Field(default_factory=dict)
    business_code: str | None = None
    step_id: str | None = None
    expected: str | None = None
    observed: str | None = None
    error: str | None = None
    evidence: list[str] = Field(default_factory=list)


class ElementSummary(BaseModel):
    role: str
    name: str
    tag: str
    value: str | None = None
    locator_candidates: list[Locator]


class Observation(BaseModel):
    url: str
    title: str
    visible_text: str
    elements: list[ElementSummary]
    screenshot_path: str | None = None
