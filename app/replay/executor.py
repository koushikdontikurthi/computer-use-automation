from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from app.logging_utils import EvidenceLogger
from app.models import AgentAction, CapabilityArtifact, Locator, ResultStatus, RunResult
from app.security import PolicyGuard
from app.surface.playwright_surface import PlaywrightSurface


class BusinessOutcome(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ReplayExecutor:
    def __init__(self, surface: PlaywrightSurface, policy: PolicyGuard, logger: EvidenceLogger):
        self.surface = surface
        self.policy = policy
        self.logger = logger

    @staticmethod
    def _render_value(value: str | None, inputs: dict[str, Any]) -> str | None:
        if value is None:
            return None
        rendered = value
        for key, raw in inputs.items():
            rendered = rendered.replace("{{" + key + "}}", str(raw))
        unresolved = re.findall(r"\{\{([^}]+)\}\}", rendered)
        if unresolved:
            raise ValueError(f"missing inputs: {', '.join(unresolved)}")
        return rendered

    def _detect_business_outcome(self) -> None:
        error_box = self.surface.page.locator(".error")
        if error_box.count() == 0:
            return
        text = error_box.first.inner_text().lower()
        if "member not found" in text or "not found" in text:
            raise BusinessOutcome("MEMBER_NOT_FOUND", "The requested member does not exist")
        if "permission denied" in text:
            raise BusinessOutcome("PERMISSION_DENIED", "The current operator is not permitted")
        if "validation error" in text:
            raise BusinessOutcome("VALIDATION_ERROR", "The target application rejected the input")

    def _verify_success(self, artifact: CapabilityArtifact, outputs: dict[str, Any]) -> bool:
        condition = artifact.success_condition
        if condition.kind == "url_contains":
            return condition.value in self.surface.page.url
        if condition.kind == "text_visible":
            return self.surface.page.get_by_text(condition.value, exact=False).count() > 0
        if condition.kind == "output_present":
            return condition.value in outputs and outputs[condition.value] not in {None, ""}
        return False

    def run(self, artifact: CapabilityArtifact, inputs: dict[str, Any]) -> RunResult:
        url_check = self.policy.check_url(artifact.target_entrypoint)
        if not url_check.allowed:
            return RunResult(status=ResultStatus.hard_failure, error=url_check.reason)
        declared = {item.name for item in artifact.inputs if item.required}
        missing = sorted(declared - set(inputs))
        if missing:
            return RunResult(status=ResultStatus.hard_failure, error=f"missing inputs: {missing}")

        outputs: dict[str, Any] = {}
        self.surface.navigate(artifact.target_entrypoint)
        self.logger.write(
            "replay_started",
            {"capability_id": artifact.capability_id, "version": artifact.artifact_version, "inputs": inputs},
        )

        for step in artifact.steps:
            try:
                self._detect_business_outcome()
                value = self._render_value(step.value, inputs)
                action = AgentAction(
                    action=step.action,
                    locator=step.locator_candidates[0] if step.locator_candidates else None,
                    value=value,
                    output_name=step.output_name,
                )
                last_error: Exception | None = None
                for attempt in range(step.retry_count + 1):
                    try:
                        if step.locator_candidates:
                            result = self.surface.act_with_candidates(action, step.locator_candidates)
                        else:
                            result = self.surface.act(action)
                        if step.action == "read" and step.output_name:
                            outputs[step.output_name] = result
                        self.logger.write(
                            "replay_step_ok",
                            {"step_id": step.id, "action": step.action, "attempt": attempt + 1},
                        )
                        last_error = None
                        break
                    except PlaywrightTimeout as exc:
                        last_error = exc
                        if attempt < step.retry_count:
                            self.surface.page.wait_for_timeout(500)
                if last_error:
                    raise last_error
                self._detect_business_outcome()
            except BusinessOutcome as outcome:
                self.logger.write(
                    "replay_business_outcome",
                    {"step_id": step.id, "code": outcome.code, "message": outcome.message},
                )
                return RunResult(
                    status=ResultStatus.business_outcome,
                    business_code=outcome.code,
                    step_id=step.id,
                    observed=outcome.message,
                )
            except Exception as exc:
                screenshot = self.surface.screenshot(f"evidence/failure-{step.id}.png")
                observed = self.surface.page.locator("body").inner_text()[:1000]
                self.logger.write(
                    "replay_hard_failure",
                    {"step_id": step.id, "error": str(exc), "observed": observed, "screenshot": screenshot},
                )
                return RunResult(
                    status=ResultStatus.hard_failure,
                    step_id=step.id,
                    expected=str(step.locator_candidates),
                    observed=observed,
                    error=str(exc),
                    evidence=[screenshot],
                )

        if not self._verify_success(artifact, outputs):
            screenshot = self.surface.screenshot("evidence/failure-checkpoint.png")
            return RunResult(
                status=ResultStatus.hard_failure,
                expected=artifact.success_condition.model_dump_json(),
                observed=self.surface.page.url,
                error="success checkpoint was not satisfied",
                evidence=[screenshot],
            )

        self.logger.write("replay_completed", {"outputs": outputs})
        return RunResult(status=ResultStatus.success, outputs=outputs)


def load_artifact(path: Path) -> CapabilityArtifact:
    return CapabilityArtifact.model_validate_json(path.read_text(encoding="utf-8"))
