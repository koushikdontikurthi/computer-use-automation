from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from app.handoff.manager import HandoffManager
from app.logging_utils import EvidenceLogger
from app.models import (
    AgentAction,
    CapabilityArtifact,
    CapabilityInput,
    CapabilityOutput,
    CapabilityStep,
    ResultStatus,
    RunResult,
    SuccessCondition,
)
from app.security import PolicyGuard
from app.surface.playwright_surface import PlaywrightSurface


class DiscoveryRunner:
    def __init__(self, surface: PlaywrightSurface, planner, policy: PolicyGuard, logger: EvidenceLogger):
        self.surface = surface
        self.planner = planner
        self.policy = policy
        self.logger = logger
        self.handoff = HandoffManager(surface, logger)

    @staticmethod
    def _parameterize(value: str | None, inputs: dict[str, Any]) -> str | None:
        if value is None:
            return None
        result = value
        for name, raw in inputs.items():
            if str(raw) == result:
                return "{{" + name + "}}"
            result = result.replace(str(raw), "{{" + name + "}}")
        return result

    @staticmethod
    def _locator_candidates(action: AgentAction, observation) -> list:
        if not action.locator:
            return []
        requested = action.locator
        for element in observation.elements:
            role_match = not requested.role or requested.role == element.role
            name_match = requested.value.lower() in element.name.lower() or element.name.lower() in requested.value.lower()
            if role_match and name_match and element.name:
                ordered = [requested]
                ordered.extend(c for c in element.locator_candidates if c.model_dump() != requested.model_dump())
                return ordered[:4]
        return [requested]

    def run(
        self,
        goal: str,
        target: str,
        inputs: dict[str, Any],
        max_steps: int = 20,
    ) -> tuple[RunResult, CapabilityArtifact | None]:
        decision = self.policy.check_url(target)
        if not decision.allowed:
            return RunResult(status=ResultStatus.hard_failure, error=decision.reason), None
        self.surface.navigate(target)
        recorded: list[CapabilityStep] = []
        outputs: dict[str, Any] = {}
        history: list[dict[str, Any]] = []
        self.logger.write("discovery_started", {"goal": goal, "target": target, "inputs": inputs})

        for index in range(max_steps):
            observation = self.surface.observe()
            compact = {
                "url": observation.url,
                "title": observation.title,
                "visible_text": observation.visible_text[:5000],
                "elements": [e.model_dump() for e in observation.elements[:50]],
                "outputs_collected_so_far": outputs,
                "recent_actions": history[-6:],
            }
            action: AgentAction = self.planner.decide(goal, compact)
            self.logger.write(
                "agent_decision",
                {"step": index + 1, "action": action.model_dump(mode="json"), "url": observation.url},
            )

            policy = self.policy.check_action(action)
            if not policy.allowed:
                if policy.requires_human:
                    intervention = self.handoff.request(
                        reason=policy.reason,
                        goal=goal,
                        step=index + 1,
                        current_url=observation.url,
                    )
                    if self.handoff.wait_for_resume():
                        self.logger.write("automation_resumed", {"step": index + 1, "url": self.surface.page.url})
                        continue
                    return RunResult(
                        status=ResultStatus.escalated,
                        step_id=str(index + 1),
                        error=intervention,
                    ), None
                return RunResult(status=ResultStatus.hard_failure, error=policy.reason), None

            if action.action.value == "escalate":
                intervention = self.handoff.request(
                    reason=action.reason or "planner requested human intervention",
                    goal=goal,
                    step=index + 1,
                    current_url=observation.url,
                )
                if self.handoff.wait_for_resume():
                    continue
                return RunResult(status=ResultStatus.escalated, error=intervention), None

            if action.action.value == "done":
                artifact = self._build_artifact(goal, target, inputs, outputs, recorded, observation.url)
                self.logger.write("discovery_completed", {"artifact": artifact.model_dump(mode="json")})
                return RunResult(status=ResultStatus.success, outputs=outputs), artifact

            try:
                value = self.surface.act(action)
            except Exception as exc:
                failure = self.surface.observe(capture_failure_evidence=True)
                self.logger.write(
                    "discovery_action_failed",
                    {"step": index + 1, "error": str(exc), "url": failure.url, "text": failure.visible_text[:1000]},
                )
                intervention = self.handoff.request(
                    reason=f"action failed: {exc}",
                    goal=goal,
                    step=index + 1,
                    current_url=failure.url,
                )
                if self.handoff.wait_for_resume():
                    continue
                return RunResult(status=ResultStatus.escalated, error=intervention), None

            if action.action.value == "read" and action.output_name:
                outputs[action.output_name] = value

            history.append(
                {
                    "step": index + 1,
                    "action": action.action.value,
                    "target": action.locator.value if action.locator else None,
                    "value_typed": action.value if action.action.value == "type" else None,
                    "value_read": value if action.action.value == "read" else None,
                    "output_name": action.output_name,
                }
            )

            if action.action.value in {"click", "type", "read", "wait", "navigate"}:
                locators = self._locator_candidates(action, observation)
                recorded.append(
                    CapabilityStep(
                        id=f"step-{len(recorded)+1:02d}",
                        action=action.action.value,
                        locator_candidates=locators,
                        value=self._parameterize(action.value, inputs),
                        output_name=action.output_name,
                        reversible=not action.risky,
                    )
                )

        self.logger.write("discovery_stopped", {"reason": "max_steps", "max_steps": max_steps})
        return RunResult(status=ResultStatus.hard_failure, error="maximum discovery steps reached"), None

    def _build_artifact(
        self,
        goal: str,
        target: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        steps: list[CapabilityStep],
        final_url: str,
    ) -> CapabilityArtifact:
        input_defs = [
            CapabilityInput(name=k, type="string", description=f"Runtime parameter: {k}") for k in inputs
        ]
        output_defs = [
            CapabilityOutput(name=k, type="string", description=f"Extracted value: {k}") for k in outputs
        ]
        safe_name = re.sub(r"[^a-z0-9]+", "-", goal.lower()).strip("-")[:48] or "capability"
        return CapabilityArtifact(
            capability_id=str(uuid.uuid4()),
            name=safe_name,
            description=goal,
            app_family="legacy-bank-demo",
            target_entrypoint=target,
            inputs=input_defs,
            outputs=output_defs,
            steps=steps,
            success_condition=SuccessCondition(kind="url_contains", value=final_url),
        )


def save_artifact(artifact: CapabilityArtifact, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")
