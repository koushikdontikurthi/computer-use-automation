from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn

from app.logging_utils import EvidenceLogger
from app.models import AgentAction, Locator
from app.surface.playwright_surface import PlaywrightSurface


class HandoffManager:
    """Minimal real same-session control transfer.

    Automation owns the Playwright page until request(). The operator API then acts on the
    exact same Page object. /resume returns ownership to automation.
    """

    def __init__(self, surface: PlaywrightSurface, logger: EvidenceLogger, port: int = 8765):
        self.surface = surface
        self.logger = logger
        self.port = port
        self.token = str(uuid.uuid4())
        self.operator_has_control = False
        self._resume = threading.Event()
        self._started = False
        self.resume_timeout_seconds = 120

    def _app(self) -> FastAPI:
        app = FastAPI(title="Computer-Use Human Handoff")

        @app.get("/operator", response_class=HTMLResponse)
        def operator_page():
            return HTMLResponse(
                """<!doctype html><html><body style='font-family:Arial;max-width:900px;margin:30px auto'>
                <h2>Live-session operator handoff</h2>
                <p>Use these endpoints while automation is paused:</p>
                <pre>GET /state\nPOST /click {"strategy":"text","value":"..."}\nPOST /type {"strategy":"label","value":"Member ID","text":"12345"}\nPOST /resume</pre>
                <p>The actions operate on the same Playwright page used by the automation process.</p>
                </body></html>"""
            )

        @app.get("/state")
        def state():
            if not self.operator_has_control:
                return {"control": "automation", "url": self.surface.page.url}
            screenshot = self.surface.screenshot("evidence/handoff-live.png")
            obs = self.surface.observe()
            return {
                "control": "human",
                "url": obs.url,
                "visible_text": obs.visible_text[:3000],
                "elements": [e.model_dump() for e in obs.elements[:30]],
                "screenshot": screenshot,
            }

        @app.post("/click")
        def click(payload: dict[str, Any]):
            if not self.operator_has_control:
                raise HTTPException(409, "operator does not own the session")
            loc = Locator(
                strategy=payload.get("strategy", "text"),
                value=payload["value"],
                role=payload.get("role"),
                exact=bool(payload.get("exact", False)),
            )
            self.surface.act(AgentAction(action="click", locator=loc, reason="human handoff"))
            self.logger.write("human_action", {"type": "click", "locator": loc.model_dump()})
            return {"ok": True, "url": self.surface.page.url}

        @app.post("/type")
        def type_text(payload: dict[str, Any]):
            if not self.operator_has_control:
                raise HTTPException(409, "operator does not own the session")
            loc = Locator(
                strategy=payload.get("strategy", "label"),
                value=payload["value"],
                role=payload.get("role"),
                exact=bool(payload.get("exact", False)),
            )
            self.surface.act(
                AgentAction(action="type", locator=loc, value=str(payload.get("text", "")), reason="human handoff")
            )
            self.logger.write("human_action", {"type": "type", "locator": loc.model_dump()})
            return {"ok": True}

        @app.post("/resume")
        def resume():
            self.operator_has_control = False
            self.logger.write("handoff_resumed", {"url": self.surface.page.url})
            self._resume.set()
            return {"ok": True, "control": "automation"}

        return app

    def _start_api(self) -> None:
        if self._started:
            return
        self._started = True
        app = self._app()
        thread = threading.Thread(
            target=lambda: uvicorn.run(app, host="127.0.0.1", port=self.port, log_level="warning"),
            daemon=True,
        )
        thread.start()
        time.sleep(0.4)

    def wait_for_resume(self) -> bool:
        return self._resume.wait(timeout=self.resume_timeout_seconds)

    def request(self, reason: str, goal: str, step: int, current_url: str) -> str:
        self._start_api()
        self.operator_has_control = True
        self._resume.clear()
        screenshot = self.surface.screenshot("evidence/handoff-request.png")
        payload = {
            "intervention_id": self.token,
            "goal": goal,
            "step": step,
            "url": current_url,
            "reason": reason,
            "screenshot": screenshot,
            "operator_url": f"http://127.0.0.1:{self.port}/operator",
        }
        Path("evidence/handoff_request.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.logger.write("handoff_requested", payload)
        return f"Human intervention required. Open {payload['operator_url']} (same live session)."
