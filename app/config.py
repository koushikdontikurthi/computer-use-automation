from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "bedrock")  # "bedrock" or "anthropic"
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    bedrock_model_id: str = os.getenv(
        "BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0"
    )
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
    headless: bool = os.getenv("HEADLESS", "false").lower() == "true"
    artifact_dir: Path = Path(os.getenv("ARTIFACT_DIR", "artifacts"))
    evidence_dir: Path = Path(os.getenv("EVIDENCE_DIR", "evidence"))
    operator_port: int = int(os.getenv("OPERATOR_PORT", "8765"))
    max_steps: int = 20
    timeout_ms: int = 10_000
    allowed_hosts: set[str] = field(
        default_factory=lambda: {"127.0.0.1:8001", "localhost:8001"}
    )


settings = Settings()
