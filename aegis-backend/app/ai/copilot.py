"""
app/ai/copilot.py
─────────────────
The Aegis AI co-pilot — a Claude-powered audit assistant.
Receives user messages with org context and returns sourced,
actionable responses. Uses RAG to ground responses in the
org's actual risk and control data.
"""
from typing import Any
from uuid import UUID

from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Control, Framework, Risk

settings = get_settings()
claude = AsyncAnthropic(api_key=settings.anthropic_api_key)


SYSTEM_PROMPT = """You are Aegis AI, an expert GRC (Governance, Risk and Compliance) co-pilot \
embedded in the Aegis platform. You assist internal auditors, compliance officers, and \
risk managers at financial services companies.

Your role:
- Answer questions about the organisation's specific risks, controls, and compliance posture
- Draft audit plans, workpapers, interview guides, and findings
- Explain regulatory requirements in plain language
- Suggest controls, evidence requirements, and testing procedures
- Escalate recommendations based on regulatory deadlines and examination risk

Tone: Expert but accessible. Direct. No filler phrases like "Great question!" or "Certainly!".
Always cite the source of your recommendations (regulation article, framework section, etc.).
Keep responses concise — prioritise bullets and structure over walls of text.
When you reference a risk or control from the context, name it exactly as it appears."""


async def run_copilot(
    message: str,
    org_id: UUID,
    db: AsyncSession,
    context_risk_id: UUID | None = None,
    context_control_id: UUID | None = None,
    context_plan_id: UUID | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Main copilot entry point.
    Builds context from the org's data, then calls Claude.
    """
    # Build RAG context from database
    context_sections = await _build_context(
        org_id=org_id,
        db=db,
        focus_risk_id=context_risk_id,
        focus_control_id=context_control_id,
    )

    system = SYSTEM_PROMPT + "\n\n" + context_sections

    # Build message history
    messages = list(conversation_history or [])
    messages.append({"role": "user", "content": message})

    response = await claude.messages.create(
        model=settings.claude_model,
        max_tokens=1500,
        system=system,
        messages=messages,
    )

    response_text = response.content[0].text

    # Extract suggested actions from response (simple heuristic)
    actions = _extract_suggested_actions(response_text)

    return {
        "response": response_text,
        "suggested_actions": actions,
        "referenced_risks": [],
        "referenced_controls": [],
    }


async def generate_interview_guide(
    risk_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> str:
    """Generate a structured interview guide for auditing a specific risk."""
    risk = (await db.execute(
        select(Risk).where(Risk.id == risk_id, Risk.org_id == org_id)
    )).scalar_one_or_none()

    if not risk:
        return "Risk not found."

    prompt = f"""Generate a structured audit interview guide for the following risk:

Risk: {risk.name}
Domain: {risk.domain}
Description: {risk.description or 'N/A'}
Framework obligations: {', '.join(risk.framework_tags or [])}
Inherent severity: {risk.inherent_severity}

Structure the guide with 2-3 stakeholder groups, 4-5 specific questions each.
Format as markdown. Each question should target evidence that would confirm
or deny the effectiveness of controls over this risk."""

    msg = await claude.messages.create(
        model=settings.claude_model,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


async def generate_audit_plan_tasks(
    plan_name: str,
    risk_names: list[str],
    org_context: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Generate structured audit plan tasks from a list of in-scope risks.
    Returns a list of task dicts ready to be inserted as AuditTask rows.
    """
    import json, re

    prompt = f"""You are building an audit plan for: {plan_name}

Organisation context:
- Industry: {org_context.get('industry_label', 'Financial services')}
- Jurisdiction: {org_context.get('jurisdiction', 'Netherlands')}
- Regulator: {org_context.get('regulator', 'DNB')}

In-scope risks:
{chr(10).join(f"- {r}" for r in risk_names)}

Generate a structured 3-phase audit plan with specific tasks.
Return ONLY valid JSON — no preamble, no markdown fences:
{{
  "tasks": [
    {{
      "phase": 1,
      "phase_label": "Planning & scoping",
      "label": "Review prior year findings and regulatory correspondence",
      "is_priority": false
    }},
    {{
      "phase": 2,
      "phase_label": "Fieldwork & testing",
      "label": "Test transaction monitoring rule engine — sample 150 alerts",
      "is_priority": true
    }},
    {{
      "phase": 3,
      "phase_label": "Reporting & closure",
      "label": "Draft findings report — AI will auto-assemble from workpapers",
      "is_priority": false
    }}
  ],
  "ai_guidance": "Key insight about this audit's timing or risk profile."
}}

Generate 8-12 realistic tasks total across the 3 phases."""

    msg = await claude.messages.create(
        model=settings.claude_model,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = msg.content[0].text.strip()
    text = re.sub(r"^```(?:json)?\n?", "", text)
    text = re.sub(r"\n?```$", "", text)

    try:
        data = json.loads(text)
        tasks = data.get("tasks", [])
        # Add sort_order
        for i, task in enumerate(tasks):
            task["sort_order"] = i
        return tasks
    except Exception:
        return []


# ── Context building ──────────────────────────────────────────────────────────

async def _build_context(
    org_id: UUID,
    db: AsyncSession,
    focus_risk_id: UUID | None,
    focus_control_id: UUID | None,
) -> str:
    """
    Builds a RAG context string from the org's live data.
    Injected into the system prompt so Claude has specific knowledge.
    """
    sections = []

    # Top risks
    risks = (await db.execute(
        select(Risk)
        .where(Risk.org_id == org_id)
        .order_by(Risk.inherent_severity.desc())
        .limit(10)
    )).scalars().all()

    if risks:
        risk_lines = [
            f"- {r.name} ({r.inherent_severity} / {r.domain or 'general'}) "
            f"— coverage {r.control_coverage_pct:.0f}%"
            + (f" [FOCUS RISK]" if str(r.id) == str(focus_risk_id) else "")
            for r in risks
        ]
        sections.append("## Organisation risk register (top 10)\n" + "\n".join(risk_lines))

    # Active frameworks
    frameworks = (await db.execute(
        select(Framework).where(Framework.org_id == org_id, Framework.is_active == True)
    )).scalars().all()

    if frameworks:
        fw_lines = [f"- {f.label}: {f.coverage_pct:.0f}% coverage" for f in frameworks]
        sections.append("## Active compliance frameworks\n" + "\n".join(fw_lines))

    # Focus risk detail
    if focus_risk_id:
        risk = (await db.execute(
            select(Risk).where(Risk.id == focus_risk_id, Risk.org_id == org_id)
        )).scalar_one_or_none()
        if risk:
            sections.append(
                f"## Focused risk context\n"
                f"**{risk.name}**\n"
                f"Domain: {risk.domain}\n"
                f"Description: {risk.description or 'Not documented'}\n"
                f"Inherent severity: {risk.inherent_severity} | "
                f"Residual: {risk.residual_severity}\n"
                f"Framework obligations: {', '.join(risk.framework_tags or [])}\n"
                f"Control coverage: {risk.control_coverage_pct:.0f}%"
            )

    return "\n\n".join(sections)


def _extract_suggested_actions(text: str) -> list[dict[str, str]]:
    """
    Heuristically extract suggested actions from a copilot response.
    Looks for imperative sentences that suggest a concrete next step.
    """
    actions = []
    action_phrases = [
        "update the risk register",
        "assign an owner",
        "schedule a review",
        "rotate the api key",
        "escalate to",
        "draft a",
        "create a",
        "add to the audit plan",
    ]
    lines = text.lower().split("\n")
    for line in lines:
        for phrase in action_phrases:
            if phrase in line:
                actions.append({
                    "label": line.strip().lstrip("- •*").strip()[:80],
                    "action_type": "note",
                })
                break
    return actions[:3]  # Max 3 suggested actions
