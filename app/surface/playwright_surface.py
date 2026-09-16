from __future__ import annotations

from pathlib import Path
import os
import shutil

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, TimeoutError, sync_playwright

from app.models import AgentAction, ElementSummary, Locator, Observation
from app.surface.base import Surface


class PlaywrightSurface(Surface):
    def __init__(self, headless: bool = True, timeout_ms: int = 10_000):
        self._pw: Playwright = sync_playwright().start()
        executable = os.getenv("CHROMIUM_EXECUTABLE") or shutil.which("chromium") or shutil.which("google-chrome")
        launch_kwargs = {"headless": headless}
        if executable:
            launch_kwargs["executable_path"] = executable
        self._browser: Browser = self._pw.chromium.launch(**launch_kwargs)
        self.context: BrowserContext = self._browser.new_context(viewport={"width": 1365, "height": 900})
        self.page: Page = self.context.new_page()
        self.page.set_default_timeout(timeout_ms)
        self.timeout_ms = timeout_ms

    def navigate(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded")

    def _element_summaries(self) -> list[ElementSummary]:
        raw = self.page.evaluate(
            """
            () => {
              const selectors = 'button,a,input,select,textarea,[role="button"],[role="link"]';
              const nodes = [...document.querySelectorAll(selectors)].filter(el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
              });
              return nodes.slice(0, 80).map(el => {
                const tag = el.tagName.toLowerCase();
                const explicitRole = el.getAttribute('role');
                const role = explicitRole || ({BUTTON:'button',A:'link',INPUT:'textbox',SELECT:'combobox',TEXTAREA:'textbox'}[el.tagName] || 'control');
                const labelEl = el.labels && el.labels.length ? el.labels[0] : null;
                const name = (el.getAttribute('aria-label') || (labelEl && labelEl.innerText) || el.innerText || el.value || el.name || el.placeholder || '').trim();
                const css = el.id ? `#${CSS.escape(el.id)}` : (el.name ? `${tag}[name="${CSS.escape(el.name)}"]` : tag);
                const currentValue = (tag === 'input' || tag === 'select' || tag === 'textarea') ? (el.value || '') : '';
                return {role, name: name.slice(0,120), tag, css, value: currentValue.slice(0,120)};
              });
            }
            """
        )
        items: list[ElementSummary] = []
        for item in raw:
            name = item["name"]
            role = item["role"]
            candidates: list[Locator] = []
            if name:
                candidates.append(Locator(strategy="role", role=role, value=name))
                candidates.append(Locator(strategy="text", value=name, exact=False))
            candidates.append(Locator(strategy="css", value=item["css"]))
            items.append(
                ElementSummary(role=role, name=name, tag=item["tag"], value=item.get("value") or None, locator_candidates=candidates)
            )
        return items

    def observe(self, capture_failure_evidence: bool = False) -> Observation:
        screenshot_path = None
        if capture_failure_evidence:
            Path("evidence").mkdir(exist_ok=True)
            screenshot_path = str(Path("evidence") / "last_failure.png")
            self.page.screenshot(path=screenshot_path, full_page=True)
        text = self.page.locator("body").inner_text(timeout=self.timeout_ms)
        return Observation(
            url=self.page.url,
            title=self.page.title(),
            visible_text=text[:12_000],
            elements=self._element_summaries(),
            screenshot_path=screenshot_path,
        )

    def _resolve(self, locator: Locator):
        if locator.strategy == "role":
            return self.page.get_by_role(locator.role or "", name=locator.value, exact=locator.exact)
        if locator.strategy == "label":
            return self.page.get_by_label(locator.value, exact=locator.exact)
        if locator.strategy == "text":
            return self.page.get_by_text(locator.value, exact=locator.exact)
        return self.page.locator(locator.value)

    def act(self, action: AgentAction) -> str | None:
        if action.action.value == "navigate":
            self.navigate(action.value or "")
            return None
        if action.action.value == "wait":
            self.page.wait_for_timeout(int(action.value or "500"))
            return None
        if action.action.value in {"done", "escalate"}:
            return None
        if not action.locator:
            raise ValueError(f"{action.action.value} requires a locator")
        target = self._resolve(action.locator)
        if action.action.value == "click":
            target.first.click()
            return None
        if action.action.value == "type":
            target.first.fill(action.value or "")
            return None
        if action.action.value == "read":
            return target.first.inner_text()
        raise ValueError(f"unsupported action {action.action}")

    def act_with_candidates(self, action: AgentAction, candidates: list[Locator]) -> str | None:
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                return self.act(action.model_copy(update={"locator": candidate}))
            except (TimeoutError, Exception) as exc:
                last_error = exc
        if last_error:
            raise last_error
        raise RuntimeError("no locator candidates supplied")

    def screenshot(self, path: str) -> str:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=path, full_page=True)
        return path

    def close(self) -> None:
        self.context.close()
        self._browser.close()
        self._pw.stop()
