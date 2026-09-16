# Computer-Use Automation System

A focused take-home implementation of **LLM discovery -> typed capability artifact -> deterministic replay** for legacy UI automation. The concrete target is a small local credit-union back-office app with intentionally old-style markup and no test IDs.

The implementation uses technologies aligned with the candidate's background: **Python, FastAPI, AWS Bedrock/Anthropic Claude, typed backend models, distributed-system style boundaries, Docker**, plus **Playwright** for browser computer use.

## What is implemented

- Goal-driven LLM observe -> decide -> act discovery loop using Claude through AWS Bedrock.
- Playwright surface adapter with role/name/text/CSS locator candidates.
- Typed, versioned Pydantic capability artifacts with inputs, outputs, checkpoints and tenant overrides.
- LLM-free deterministic replay with retries, business outcomes and debuggable hard failures.
- Explicit domain/action allowlist and conservative handling of risky/irreversible actions.
- Redacted JSONL evidence logging and screenshots on failure.
- Same-live-session human handoff API: automation pauses, an operator acts on the exact Playwright page, then resumes.
- Local legacy banking proxy with success, not-found, permission-denied and validation states.
- Tests for the artifact contract and policy rules.

## 1. Setup

### Local Python

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\\Scripts\\activate
python -m pip install -e ".[dev]"
python -m playwright install chromium
```

Copy `.env.example` to `.env` or export the required variables. The discovery loop supports two interchangeable LLM backends behind the same planner interface — pick whichever credentials you have:

**Option A — Anthropic API directly (simplest, no AWS account needed):**

```bash
export LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
export HEADLESS=false
```

**Option B — AWS Bedrock:**

```bash
export LLM_PROVIDER=bedrock
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
export HEADLESS=false
```

`BedrockPlanner` and `AnthropicPlanner` both implement the same `.decide(goal, observation) -> AgentAction` contract, so `DiscoveryRunner` doesn't care which one is wired in — this is the same surface-abstraction principle the artifact schema uses for target apps (see REPORT.md, Heterogeneity & multi-tenant).

No credentials are required to run deterministic replay against the checked-in example artifact.

## 2. Start the target application

In terminal 1:

```bash
python -m app.legacy_app.app
```

Open `http://127.0.0.1:8001` if you want to inspect the proxy UI. Demo members are `12345` and `24680`. `99999` returns a legitimate **MEMBER_NOT_FOUND** business outcome and `00000` returns **PERMISSION_DENIED**.

## 3. Demo path: LLM discovery

In terminal 2, with Bedrock credentials configured:

```bash
python scripts/run_discovery.py \
  --goal 'Look up member ${member_id} and read the current savings balance' \
  --target http://127.0.0.1:8001 \
  --input member_id=12345 \
  --artifact evidence/discovered_capability.json
```

The discovery loop observes the live browser, asks Claude for one structured next action, policy-checks it, executes it, and records the successful flow as a typed artifact. The run log is written to `evidence/discovery_live.jsonl`.

**Important:** the assignment requires evidence from a genuine LLM-driven run. This repository intentionally does not fabricate that evidence. Run the command above once with your own Bedrock access before submission and keep the generated log/artifact in `/evidence/`.

## 4. Demo path: deterministic replay

Replay requires no LLM:

```bash
python scripts/run_replay.py \
  --artifact evidence/example_capability.json \
  --input member_id=12345 \
  --evidence evidence/replay_success.jsonl
```

Expected structured result:

```json
{
  "status": "success",
  "outputs": {"savings_balance": "$6,430.21"}
}
```

Expected business outcome:

```bash
python scripts/run_replay.py \
  --artifact evidence/example_capability.json \
  --input member_id=99999 \
  --evidence evidence/replay_not_found.jsonl
```

The result is `business_outcome` with code `MEMBER_NOT_FOUND`, not a crash.

For a one-command local replay verification:

```bash
python scripts/run_offline_demo.py
```

## 5. Human-in-the-loop handoff

When discovery is blocked, ambiguous, fails a UI action, or requests a risky operation, `HandoffManager` transfers control to a local operator API while preserving the **same Playwright Page and browser context**.

The intervention payload is saved as `evidence/handoff_request.json` and includes the goal, step, URL, reason, screenshot and operator URL. The operator can use:

```text
GET  /state
POST /click
POST /type
POST /resume
```

Human actions are appended to the same evidence log. `/resume` returns control to automation. The deliberately minimal HTML page at `/operator` documents those controls; a full real-time co-browsing console is outside the scope.

## 6. Artifact example

`evidence/example_capability.json` is a reviewable capability contract. Important fields are:

- `schema_version` and `artifact_version`
- `app_family` for vendor/product-level reuse
- typed `inputs` and `outputs`
- ordered replay `steps`
- ordered `locator_candidates` per step
- `retry_count` and timeout behavior
- explicit `success_condition`
- `tenant_overrides` seam for institution-specific specialization
- `approved` gate for unattended use

Concrete runtime values are parameterized, e.g. `{{member_id}}`, instead of being persisted as member-specific data.

## 7. Safety and data handling

- Only configured hosts may be navigated.
- Only known action types may execute.
- Risky actions (delete, transfer, account opening confirmation, etc.) require human intervention rather than unattended execution.
- Logs are passed through redaction patterns for secrets, SSNs and long account/card-like numbers.
- The artifact stores parameter names, not credentials or full PII values.
- The local proxy uses synthetic data only.

## 8. Error model

Replay intentionally separates:

1. **Success** - checkpoint satisfied, outputs returned.
2. **Business outcome** - legitimate application result such as member not found or permission denied.
3. **Recoverable condition** - retryable Playwright timeout/transient load; exhausted retries become explicit failure.
4. **Hard failure** - locator/checkpoint/action error with step ID, observed state and screenshot evidence.
5. **Escalation** - discovery or a risky operation requires human control.

## 9. Tests

```bash
pytest -q
```

The most important tests protect the artifact schema, result taxonomy, host allowlist, risky-action policy and redaction behavior.

## 10. Docker

The included Dockerfile uses the Playwright Python base image. The local proxy can be run with:

```bash
docker compose up legacy-app
```

For an interactive discovery browser, local execution is generally easier than a container because the evaluator can see the UI.

## Repository map

```text
app/agent/          Bedrock planner and discovery loop
app/surface/        Surface abstraction + Playwright implementation
app/replay/         Deterministic executor and error taxonomy
app/handoff/        Same-session human control transfer
app/legacy_app/     Synthetic back-office proxy target
evidence/           Example capability and run evidence
scripts/            Discovery/replay/demo entry points
tests/              Contract and guardrail tests
REPORT.md           Design write-up
docs/               Technical documentation DOCX
```

## Submission note

The assignment brief requests a **public GitHub repository** and says to email only the repo URL rather than a ZIP. This ZIP is convenient for review/setup, but before final submission push the contents to a public GitHub repository, perform one real Bedrock discovery run, verify `/evidence/`, and email the repository link.
