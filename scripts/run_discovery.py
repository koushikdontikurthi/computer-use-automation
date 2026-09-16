from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse

from app.agent.discovery import DiscoveryRunner, save_artifact
from app.config import settings
from app.logging_utils import EvidenceLogger
from app.security import PolicyGuard
from app.surface.playwright_surface import PlaywrightSurface


def parse_inputs(items: list[str]) -> dict[str, str]:
    result = {}
    for item in items:
        key, value = item.split("=", 1)
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--artifact", default="artifacts/discovered_capability.json")
    args = parser.parse_args()

    inputs = parse_inputs(args.input)
    surface = PlaywrightSurface(headless=settings.headless, timeout_ms=settings.timeout_ms)
    try:
        if settings.llm_provider == "anthropic":
            from app.agent.anthropic_llm import AnthropicPlanner

            planner = AnthropicPlanner(model=settings.anthropic_model)
        else:
            from app.agent.bedrock_llm import BedrockPlanner

            planner = BedrockPlanner(settings.aws_region, settings.bedrock_model_id)
        logger = EvidenceLogger(Path("evidence/discovery_live.jsonl"))
        runner = DiscoveryRunner(surface, planner, PolicyGuard(settings.allowed_hosts), logger)
        result, artifact = runner.run(args.goal, args.target, inputs, settings.max_steps)
        print(result.model_dump_json(indent=2))
        if artifact:
            path = Path(args.artifact)
            save_artifact(artifact, path)
            print(f"Saved artifact to {path}")
    finally:
        surface.close()


if __name__ == "__main__":
    main()
