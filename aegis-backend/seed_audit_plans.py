"""
seed_audit_plans.py
────────────────────
Seeds 3 realistic audit plans for Meridian Financial Services:
  1. AML & Financial Crime Audit          — 68% complete (fieldwork)
  2. DORA ICT Resilience Readiness Audit  — 35% complete (fieldwork)
  3. GDPR & Data Privacy Review           — 100% complete (reporting)

Run inside container:
  docker compose cp seed_audit_plans.py api:/app/seed_audit_plans.py
  docker compose exec -T api python seed_audit_plans.py
"""

import asyncio
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import select, text
from app.database import AsyncSessionLocal
from app.models import AuditPlan, AuditTask, AuditStatus, TaskStatus

ORG_ID  = UUID("ddda03b3-cd63-4d1c-a1a8-15871872876b")  # Meridian Financial Services
LEAD_ID = UUID("059c5561-b841-41b2-b4d4-fd0519b6e6d4")  # Vijay Rao — head_of_audit

now = datetime.now(timezone.utc)


PLANS = [
    # ── Plan 1: AML & Financial Crime ─────────────────────────────────────────
    {
        "name": "AML & Financial Crime Audit — Q1 2025",
        "description": "Risk-based review of Transaction Monitoring, Sanctions Screening, and KYC/CDD controls against AMLD6 and DNB regulatory expectations.",
        "status": AuditStatus.fieldwork,
        "planned_start": now - timedelta(days=55),
        "planned_end":   now + timedelta(days=18),
        "actual_start":  now - timedelta(days=52),
        "tasks": [
            # Phase 1 — Planning
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Define audit scope and objectives aligned to AMLD6 Articles 7-9", "status": TaskStatus.done, "is_priority": True},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Prepare risk assessment and materiality thresholds for TM testing", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Issue engagement letter to AML/MLRO function and schedule interviews", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Request population data: TM alerts Jan–Mar 2025 (Actimize export)", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Design sampling methodology — stratified by alert tier and amount", "status": TaskStatus.done},
            # Phase 2 — Fieldwork
            {"phase": 2, "phase_label": "Fieldwork", "label": "Test TM alert closure procedures — sample 75 closed alerts (25 per tier)", "status": TaskStatus.done, "is_priority": True},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Evaluate sanctions screening calibration — name-matching threshold analysis", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Review KYC/CDD completeness for 50 high-risk corporate customers", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Interview MLRO on escalation procedures and SAR filing backlog", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Test PEP screening refresh — verify re-screening at 12-month intervals", "status": TaskStatus.in_progress, "is_priority": True},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Assess TM model governance: documentation, validation, backtesting evidence", "status": TaskStatus.in_progress},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Review correspondent banking exposure and nested account controls", "status": TaskStatus.pending},
            # Phase 3 — Reporting
            {"phase": 3, "phase_label": "Reporting", "label": "Draft findings and validate facts with MLRO", "status": TaskStatus.pending},
            {"phase": 3, "phase_label": "Reporting", "label": "Obtain management responses for each finding", "status": TaskStatus.pending},
            {"phase": 3, "phase_label": "Reporting", "label": "Issue draft report to Head of Compliance for comment period (5 days)", "status": TaskStatus.pending},
            {"phase": 3, "phase_label": "Reporting", "label": "Finalise and distribute report to Audit Committee", "status": TaskStatus.pending},
        ],
    },

    # ── Plan 2: DORA ICT Resilience ───────────────────────────────────────────
    {
        "name": "DORA ICT Resilience Readiness — Gap Assessment",
        "description": "Pre-compliance gap assessment against DORA Articles 5-55 (effective Jan 2025). Covers ICT risk management framework, incident classification, third-party oversight, and TLPT readiness.",
        "status": AuditStatus.fieldwork,
        "planned_start": now - timedelta(days=30),
        "planned_end":   now + timedelta(days=45),
        "actual_start":  now - timedelta(days=28),
        "tasks": [
            # Phase 1 — Planning
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Map DORA regulatory text to Meridian's ICT risk management framework", "status": TaskStatus.done, "is_priority": True},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Identify ICT third-party providers in scope (critical vs non-critical)", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Coordinate with CTO and CISO for evidence availability timeline", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Design maturity scoring rubric (1-5 per DORA pillar)", "status": TaskStatus.done},
            # Phase 2 — Fieldwork
            {"phase": 2, "phase_label": "Fieldwork", "label": "Assess ICT risk management framework completeness vs Article 5-6 requirements", "status": TaskStatus.done, "is_priority": True},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Review ICT incident classification and reporting procedures (Articles 17-23)", "status": TaskStatus.in_progress, "is_priority": True},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Test Business Continuity and Disaster Recovery for core banking system", "status": TaskStatus.in_progress},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Evaluate third-party risk management: SLAs, exit strategies, sub-outsourcing", "status": TaskStatus.pending},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Assess TLPT (Threat-Led Penetration Testing) readiness and prior test results", "status": TaskStatus.pending},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Review ICT change management and patch governance procedures", "status": TaskStatus.pending},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Evaluate cryptographic key management and data integrity controls", "status": TaskStatus.pending},
            # Phase 3 — Reporting
            {"phase": 3, "phase_label": "Reporting", "label": "Compile DORA maturity scorecard across 5 pillars", "status": TaskStatus.pending},
            {"phase": 3, "phase_label": "Reporting", "label": "Draft gap remediation roadmap with regulatory deadline mapping", "status": TaskStatus.pending},
            {"phase": 3, "phase_label": "Reporting", "label": "Present findings to ExCo and issue final gap assessment report", "status": TaskStatus.pending},
        ],
    },

    # ── Plan 3: GDPR & Data Privacy ───────────────────────────────────────────
    {
        "name": "GDPR & Data Privacy Controls Review — FY2024",
        "description": "Annual review of data protection controls, DSAR workflow, consent management, and data retention in line with GDPR Articles 5, 12-22, and 30. Covers Meridian's retail and institutional data processing activities.",
        "status": AuditStatus.reporting,
        "planned_start": now - timedelta(days=90),
        "planned_end":   now - timedelta(days=5),
        "actual_start":  now - timedelta(days=88),
        "actual_end":    now - timedelta(days=6),
        "tasks": [
            # Phase 1 — Planning (all done)
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Define scope: retail deposits, payments, and institutional onboarding data flows", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Review prior year GDPR audit findings and open actions", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Obtain data inventory from DPO (Article 30 Records of Processing Activities)", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Issue audit engagement notice to DPO and Legal", "status": TaskStatus.done},
            # Phase 2 — Fieldwork (all done)
            {"phase": 2, "phase_label": "Fieldwork", "label": "Test DSAR fulfilment: end-to-end timing for 20 sampled requests (1-month period)", "status": TaskStatus.done, "is_priority": True},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Review consent records for marketing comms — completeness and withdrawal mechanisms", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Assess data retention enforcement: archival and deletion for legacy customer data", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Evaluate third-party data processor agreements (DPAs) — AWS, Temenos, Onfido", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Test pseudonymisation of analytical datasets in data warehouse", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Interview DPO on breach notification procedures and AP reporting readiness", "status": TaskStatus.done, "is_priority": True},
            # Phase 3 — Reporting
            {"phase": 3, "phase_label": "Reporting", "label": "Issue draft report to DPO — 3 findings, 2 recommendations", "status": TaskStatus.done},
            {"phase": 3, "phase_label": "Reporting", "label": "Collect management responses (received within SLA)", "status": TaskStatus.done},
            {"phase": 3, "phase_label": "Reporting", "label": "Finalise audit report and distribute to Audit Committee and AP", "status": TaskStatus.in_progress, "is_priority": True},
        ],
    },
]


async def seed():
    async with AsyncSessionLocal() as db:
        # Check if already seeded
        existing = (await db.execute(
            select(AuditPlan).where(AuditPlan.org_id == ORG_ID).limit(1)
        )).scalar_one_or_none()

        if existing:
            print(f"✓ Audit plans already seeded for Meridian (found: {existing.name})")
            return

        for plan_data in PLANS:
            tasks_data = plan_data.pop("tasks")
            actual_end = plan_data.pop("actual_end", None)

            plan = AuditPlan(
                org_id=ORG_ID,
                lead_id=LEAD_ID,
                **plan_data,
            )
            if actual_end:
                plan.actual_end = actual_end

            db.add(plan)
            await db.flush()  # get plan.id

            tasks = []
            for i, t in enumerate(tasks_data):
                task = AuditTask(
                    plan_id=plan.id,
                    sort_order=i,
                    **t,
                )
                tasks.append(task)
                db.add(task)

            await db.flush()

            # Compute progress
            done  = sum(1 for t in tasks_data if t["status"] == TaskStatus.done)
            total = len(tasks_data)
            plan.task_count  = total
            plan.done_count  = done
            plan.progress_pct = (done / total * 100) if total else 0.0

            print(f"  ✓ {plan.name}  [{done}/{total} tasks · {plan.progress_pct:.0f}%]")

        await db.commit()
        print("\n✅ Audit plans seeded successfully for Meridian Financial Services")


if __name__ == "__main__":
    asyncio.run(seed())
