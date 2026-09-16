from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.logging_utils import EvidenceLogger
from app.replay.executor import ReplayExecutor, load_artifact
from app.security import PolicyGuard
from app.surface.playwright_surface import PlaywrightSurface

BASE_URL = "http://127.0.0.1:8001"


def port_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", 8001)) == 0


def server_healthy() -> bool:
    try:
        with urlopen(BASE_URL, timeout=2) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return response.status == 200 and "Member Lookup" in body
    except Exception:
        return False


def wait_for_server(timeout_seconds: float = 10.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if server_healthy():
            return True
        time.sleep(0.25)
    return False


def run_case(member_id: str, log_name: str):
    surface = PlaywrightSurface(headless=True)
    try:
        artifact = load_artifact(Path("evidence/example_capability.json"))
        result = ReplayExecutor(
            surface,
            PolicyGuard({"127.0.0.1:8001", "localhost:8001"}),
            EvidenceLogger(Path("evidence") / log_name),
        ).run(artifact, {"member_id": member_id})
        print(member_id, result.model_dump_json(indent=2))
    finally:
        surface.close()


def main():
    server = None
    if port_in_use():
        if not server_healthy():
            print("ERROR: Port 8001 is already in use, but the app on that port is not healthy.")
            print("Stop the old server with Ctrl+C, then run this command again.")
            raise SystemExit(1)
        print("Reusing healthy app already running on http://127.0.0.1:8001")
    else:
        server = subprocess.Popen([sys.executable, "-m", "app.legacy_app.app"])
        if not wait_for_server():
            server.terminate()
            raise SystemExit("ERROR: Demo app did not become healthy on port 8001.")
        print("Started demo app on http://127.0.0.1:8001")

    try:
        run_case("12345", "replay_success.jsonl")
        run_case("99999", "replay_not_found.jsonl")
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
