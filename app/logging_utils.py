from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.security import redact


class EvidenceLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, payload: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        safe = redact(json.dumps(record, default=str, ensure_ascii=True))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(safe + "\n")
