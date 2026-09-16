from __future__ import annotations

import json
import os

import anthropic

from app.models import AgentAction

SYSTEM_PROMPT = """You are a computer-use planner. You never call APIs for the target app.
You receive a goal and a compact observation of a UI. Choose exactly one next action.
Return JSON only and match this shape:
{"action":"click|type|read|wait|done|escalate","locator":{"strategy":"role|label|text|css","role":"button|link|textbox|combobox|null","value":"...","exact":false},"value":"... or null","output_name":"... or null","reason":"short reason","risky":false}
Use robust human-like targeting: role/name first, then visible text. Do not invent controls.
Each element in the observation includes its current "value" if it has one. Before typing into a
field, check whether it already holds the value you intend to enter — if so, do not retype it;
instead move on to the next action needed to make progress (e.g. click the search/submit button).
The observation also includes "outputs_collected_so_far" (data you have already extracted) and
"recent_actions" (your last few steps and their results). Check these before acting: if the data
the goal asks for is already present in outputs_collected_so_far, do not read it again — call done
immediately instead. When using read, target the smallest unique piece of text that contains just
the value itself (e.g. "$6,430.21"), not a longer string spanning multiple labels or table cells,
since exact multi-part text is fragile to locate.
Use done only after the goal is satisfied.
Use escalate when blocked, permission denied, ambiguous, or when a risky/irreversible action is required."""


class AnthropicPlanner:
    """Same planner contract as BedrockPlanner, calling the Anthropic API directly.

    Drop-in alternative for environments without AWS Bedrock access: same
    prompt, same output contract, same .decide(goal, observation) interface
    that DiscoveryRunner expects.
    """

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

    def decide(self, goal: str, observation: dict) -> AgentAction:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=600,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({"goal": goal, "observation": observation}),
                        }
                    ],
                }
            ],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        return AgentAction.model_validate_json(text)
