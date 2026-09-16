# 1. Architecture

The system is split into four load-bearing seams: **surface**, **discovery**, **artifact**, and **replay**. The target proxy is a local FastAPI application that imitates a stable but unfriendly back-office bank UI. A `PlaywrightSurface` owns the live browser session and exposes `observe`, `act`, `screenshot`, and navigation operations. Discovery receives a goal and runtime parameters, observes the UI, asks Claude for exactly one structured next action, policy-checks that action, executes it, and records only the reusable semantics of successful steps. The raw model conversation is not the production artifact.

I used a simple state-machine loop instead of adding a large agent framework. Playwright is the one new specialized tool because browser computer-use is the concrete target. The architecture keeps the browser-specific implementation behind `Surface`, so the artifact and replay contract do not depend on Playwright. The planner is also behind an interface: `AnthropicPlanner` calls the Anthropic API directly, and a `BedrockPlanner` calling the same model through AWS Bedrock implements the identical `.decide(goal, observation) -> AgentAction` contract. `DiscoveryRunner` is unaware which one is wired in. I used the direct Anthropic API for the submitted discovery run since it removes AWS account/IAM/model-access setup from the critical path with no change to prompting or decision quality; a deployment already standardized on AWS would swap in `BedrockPlanner` as a config change.

The local demo focuses on “look up a member and return savings balance.” The proxy also exposes not-found, permission-denied, validation, and a review-only account-opening path so the executor can demonstrate meaningful runtime states without real credentials or PII.

# 2. Artifact schema

The artifact is a versioned Pydantic model, serialized as JSON. It is designed as an **agent-invocable capability contract**, not a transcript. It includes identity and version fields, `app_family`, a target entrypoint, typed runtime inputs, typed outputs, ordered steps, per-step locator candidates, retry/timeout policy, reversibility metadata, a success checkpoint, optional tenant overrides, and an approval state.

Each control has multiple ordered locators when possible. The priority is semantic role/name or label, then visible text, then a narrow CSS fallback. The example deliberately has no test IDs. This is more robust than persisting a generated XPath and gives replay a deterministic fallback order. Runtime values such as the member number are stored as `{{member_id}}`; the concrete value used during discovery is not written into the capability.

`app_family` is the reuse key for institutions running the same vendor product. `tenant_overrides` is intentionally a sparse overlay rather than a full cloned artifact. This keeps one base capability reviewable while allowing known route/locator differences for a specific institution or version.

# 3. Determinism & error handling

Replay never asks the model what to do. It validates required inputs, navigates to the saved allowlisted entrypoint, renders parameters, executes the saved step sequence, tries locator candidates in a fixed order, retries only bounded transient Playwright timeouts, extracts declared outputs, and verifies the explicit success condition.

The result contract separates **business outcomes** from automation failures. “Member not found,” “permission denied,” and target validation errors are legitimate outcomes the caller may need to branch on. Transient loads/timeouts are retryable. Exhausted retries, locator failures, or unmet checkpoints are hard failures containing the failing step, expected locator/checkpoint, observed page text, error detail, and screenshot path. This makes failure behavior inspectable instead of blindly continuing.

The checked-in example capability is intentionally small, but its replay path handles both success and not-found. A production extension would move runtime-state detectors into app-family adapters so each vendor product can define known dialogs, session expiry markers, recoveries, and business outcome codes without putting those details into the generic executor.

Two runtime bugs surfaced during the actual discovery/replay runs and are worth recording here because they shaped the final design more than anything planned upfront. First, the initial observation gave the planner no memory of its own prior actions or already-collected outputs, and no visibility into a form field's current value versus its label — so on a stateless per-step call, the model would repeat the same `type` or `read` action indefinitely, unable to tell it had already made progress. The fix was to include `outputs_collected_so_far` and a short `recent_actions` history in each observation, plus surface each element's live `value` alongside its name, and to make that distinction explicit in the system prompt. Second, `_detect_business_outcome` originally substring-matched the *entire page body text* for phrases like "permission denied" — which meant a completely unrelated help caption ("Use 00000 for permission denied") on the demo app's home page tripped a false business outcome on every replay before any real action occurred. The fix scopes detection to the actual `.error` container element instead of the whole page. Both are the kind of naive-detection failure mode the brief calls out directly (Section 1: "the interesting failures aren't layout drift"): the underlying UI never changed, but incomplete state and free-text matching produced wrong behavior anyway. A production version would want structured, app-family-scoped error/state detectors rather than either of these shortcuts.

# 4. Heterogeneity & multi-tenant

The key seam is `Surface`. The artifact records **intentional control targeting**, not Playwright method calls. A future `AccessibilitySurface` could resolve role/name locators using a desktop accessibility tree; a screenshot/vision surface could resolve the same logical locator against OCR/vision anchors and coordinates; and a native Windows adapter could use UI Automation. The replay engine would still consume the same capability steps and result contract.

For legacy web pages, locator candidates are important because semantic markup may be weak. The implementation already supports CSS as a last resort and could add frame-path, table-anchor, accessibility, image-anchor, or coordinate strategies without changing the high-level artifact structure.

For hundreds of tenants, I would store a base capability per `app_family` and vendor version, then attach small tenant/version overlays. Each replay would record locator/checkpoint health. Repeated fallback use or checkpoint failure would lower confidence and flag drift. A capability should be promoted through a draft/approved lifecycle only after successful replay against the relevant app-family/version. This avoids re-recording every institution while preserving a safe specialization path.

# 5. Escalation & handoff

The handoff mechanism preserves the same live Playwright `Page` and browser context. When discovery cannot proceed safely, the manager pauses automation ownership, captures a screenshot and context payload, starts a local operator API, and marks the operator as the current controller. The payload includes the capability/goal, current step, URL, reason, evidence path, and operator URL.

While human control is active, `/state`, `/click`, and `/type` operate directly on the same `Page` object; human actions are written to the same evidence log. `/resume` flips ownership back to automation. This is intentionally minimal: it proves the control-transfer seam and same-session behavior without building a production co-browsing product. In a deployed system, the same control model would sit behind authenticated WebSocket streaming, operator identity, authorization, auditing, and lease/lock semantics.

Risky or irreversible actions are one trigger for escalation. For example, the proxy allows navigation to an “account opening review” screen, but final creation would not be executed unattended under the default policy.

# 6. Safety

The policy layer has an explicit host allowlist and a known action allowlist. Discovery actions are checked before execution. Risky/irreversible actions are denied to unattended automation and routed to human approval. The proxy contains synthetic data, and the repository contains no credentials.

Evidence logging uses redaction before persistence for password/token/secret patterns, SSN-like values, and long account/card-like digit sequences. Artifacts store parameter names rather than concrete secret/PII values. A production version would use structured field-level classification instead of regex alone, encrypt evidence at rest, apply retention limits, isolate tenants, and obtain secrets from a dedicated secret manager only at execution time.

The main policy limitation is that intent classification for risk is still partly term-based. A real banking integration should use app-specific action metadata and server-side policy rules so “what is irreversible” is not inferred from button text.

# 7. Cuts

I deliberately did not build queues, Kubernetes deployment, a multi-tenant database, a rich operator console, or a desktop adapter. The brief values the complete vertical slice and the quality of the core abstractions over infrastructure breadth. The human UI is a minimal same-session operator API, and multi-tenant/desktop support is represented at the seam rather than prematurely implemented.

The one item that must be completed with the submitter's credentials is the **genuine LLM discovery evidence**. This has been done: `evidence/discovery_live.jsonl` and `evidence/discovered_capability.json` are from a real run against the local live UI using the Anthropic API, and `evidence/replay_success.jsonl` / `evidence/replay_not_found.jsonl` are from real deterministic replays of that artifact, including one that correctly resolves to a business outcome rather than a crash.

With more time, the next improvements would be: app-family runtime-state detectors/recoveries, stronger accessibility-tree observation, explicit risk metadata per capability step, authenticated operator streaming, stability scoring across repeated replays, and a small capability catalog endpoint.
