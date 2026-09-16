from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse

from app.config import settings
from app.logging_utils import EvidenceLogger
from app.replay.executor import ReplayExecutor, load_artifact
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
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--evidence", default="evidence/replay_run.jsonl")
    args = parser.parse_args()

    surface = PlaywrightSurface(headless=settings.headless, timeout_ms=settings.timeout_ms)
    try:
        artifact = load_artifact(Path(args.artifact))
        executor = ReplayExecutor(
            surface,
            PolicyGuard(settings.allowed_hosts),
            EvidenceLogger(Path(args.evidence)),
        )
        result = executor.run(artifact, parse_inputs(args.input))
        print(result.model_dump_json(indent=2))
    finally:
        surface.close()


if __name__ == "__main__":
    main()
