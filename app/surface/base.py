from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import AgentAction, Observation


class Surface(ABC):
    @abstractmethod
    def navigate(self, url: str) -> None: ...

    @abstractmethod
    def observe(self, capture_failure_evidence: bool = False) -> Observation: ...

    @abstractmethod
    def act(self, action: AgentAction) -> str | None: ...

    @abstractmethod
    def screenshot(self, path: str) -> str: ...

    @abstractmethod
    def close(self) -> None: ...
