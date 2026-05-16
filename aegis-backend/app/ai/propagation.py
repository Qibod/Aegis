"""app/ai/propagation.py — Profile change propagation engine"""
import json
import os
import anthropic

TRIGGER_MATRIX: dict[str, list[str]] = {
    "LineOfBusiness":       ["risk_register", "control_canvas", "risk_radar", "regulatory_agent"],
    "OrgGeography":         ["risk_register", "regulatory_agent"],
    "OrgIndustry":          ["risk_register", "regulatory_agent", "control_canvas"],
    "OrgProduct":           ["risk_register", "control_canvas", "risk_radar"],
    "CustomerSegment":      ["risk_register", "control_canvas"],
    "ThirdPartyDependency": ["risk_register", "control_canvas"],
    "DataTechProfile":      ["risk_register", "regulatory_agent", "control_canvas"],
    "OrgProfile":           [],
}

MODULE_LABELS = {
    "risk_register":    "Risk Register",
    "control_canvas":   "Control Canvas",
    "risk_radar":       "Risk Radar",
    "regulatory_agent": "Regulatory Change Agent",
}

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


async def compute_propagation(
    org_id: str,
    entity_type: str,
    change_data: dict,
    change_summary: str,
) -> dict:
    modules = TRIGGER_MATRIX.get(entity_type, [])
    if not modules:
        return {"affected_modules": []}

    modules_list = ", ".join(MODULE_LABELS[m] for m in modules)
    prompt = f"""You are a senior GRC consultant. A company profile change just occurred.

Change: {change_summary}
Changed data: {json.dumps(change_data, default=str)}

For each of the following GRC modules, list 2-3 specific, actionable updates that should follow from this change: {modules_list}

Return a JSON object with this exact structure:
{{
  "affected_modules": [
    {{
      "module": "<module_key>",
      "module_label": "<label>",
      "action_type": "add",
      "count": <number>,
      "preview": [
        {{"title": "<short title>", "severity": "high|medium|low", "rationale": "<1 sentence why>"}}
      ],
      "status": "pending"
    }}
  ]
}}

Module keys: {json.dumps(modules)}
Be specific — cite the exact change that motivated each suggestion. Return only valid JSON."""

    try:
        response = await _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception:
        return {
            "affected_modules": [
                {
                    "module": m,
                    "module_label": MODULE_LABELS[m],
                    "action_type": "add",
                    "count": 1,
                    "preview": [{"title": f"Review {MODULE_LABELS[m]} for impact", "severity": "medium", "rationale": change_summary}],
                    "status": "pending",
                }
                for m in modules
            ]
        }
