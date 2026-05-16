"""
seed_audit_plans.py
────────────────────
Seeds 3 realistic audit plans for Uber Technologies, Inc.:
  1. Gig Worker Classification Compliance Review  — 68% complete (fieldwork)
  2. CCPA / Data Privacy Controls Audit           — 35% complete (fieldwork)
  3. Platform Safety & Background Screening       — 100% complete (reporting)

Run inside container:
  docker compose cp seed_audit_plans.py api:/app/seed_audit_plans.py
  docker compose exec -T api python seed_audit_plans.py
"""

import asyncio
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import select, delete
from app.database import AsyncSessionLocal
from app.models import AuditPlan, AuditTask, AuditStatus, TaskStatus

ORG_ID  = UUID("ddda03b3-cd63-4d1c-a1a8-15871872876b")  # Uber Technologies, Inc.
LEAD_ID = UUID("059c5561-b841-41b2-b4d4-fd0519b6e6d4")  # Vijay Rao — head_of_audit

now = datetime.now(timezone.utc)


PLANS = [
    # ── Plan 1: Gig Worker Classification ────────────────────────────────────
    {
        "name": "Gig Worker Classification Compliance Review — Q1 2025",
        "description": "Risk-based review of Uber's independent contractor classification framework across key jurisdictions, including AB5 (California), the EU Platform Work Directive, and analogous legislation in the UK, Australia, and Brazil. Assesses legal exposure, litigation reserves, and contractual safeguards.",
        "status": AuditStatus.fieldwork,
        "planned_start": now - timedelta(days=55),
        "planned_end":   now + timedelta(days=18),
        "actual_start":  now - timedelta(days=52),
        "tasks": [
            # Phase 1 — Planning
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Map AB5 and EU Platform Work Directive requirements to Uber's contractor framework", "status": TaskStatus.done, "is_priority": True},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Identify top-10 jurisdictions by revenue at risk from reclassification", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Issue engagement letter to Legal, Policy, and People Operations", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Request litigation reserve data and outside counsel memos by jurisdiction", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Design interview guide for in-house employment counsel (CA, UK, EU, BR, AU)", "status": TaskStatus.done},
            # Phase 2 — Fieldwork
            {"phase": 2, "phase_label": "Fieldwork", "label": "Review Prop 22 implementation controls in California — ongoing compliance checks", "status": TaskStatus.done, "is_priority": True},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Assess EU Platform Work Directive transposition readiness across DE, FR, NL, ES", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Evaluate driver contract terms for behavioural control indicators (IRS 20-factor test)", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Interview employment counsel on UK Supreme Court ruling implications and current exposure", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Test algorithmic deactivation controls — assess whether deactivation metrics imply employment relationship", "status": TaskStatus.in_progress, "is_priority": True},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Review earnings guarantee and benefits programmes for classification impact (Uber Pro, Uber One)", "status": TaskStatus.in_progress},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Assess Board-level oversight of classification risk and escalation procedures", "status": TaskStatus.pending},
            # Phase 3 — Reporting
            {"phase": 3, "phase_label": "Reporting", "label": "Draft findings and validate facts with General Counsel and Chief People Officer", "status": TaskStatus.pending},
            {"phase": 3, "phase_label": "Reporting", "label": "Obtain management responses for each jurisdiction-level finding", "status": TaskStatus.pending},
            {"phase": 3, "phase_label": "Reporting", "label": "Issue draft report to Audit Committee for comment period (5 business days)", "status": TaskStatus.pending},
            {"phase": 3, "phase_label": "Reporting", "label": "Finalise and distribute report to Board Risk Committee", "status": TaskStatus.pending},
        ],
    },

    # ── Plan 2: CCPA / Data Privacy ───────────────────────────────────────────
    {
        "name": "CCPA / Data Privacy Controls Audit — FY2025",
        "description": "Pre-enforcement readiness assessment of Uber's data privacy programme against CCPA/CPRA and GDPR obligations. Covers data subject rights fulfilment, consent management, cross-border data transfer safeguards, and vendor DPA completeness across 200+ microservices.",
        "status": AuditStatus.fieldwork,
        "planned_start": now - timedelta(days=30),
        "planned_end":   now + timedelta(days=45),
        "actual_start":  now - timedelta(days=28),
        "tasks": [
            # Phase 1 — Planning
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Map CCPA/CPRA and GDPR requirements to Uber's privacy control framework", "status": TaskStatus.done, "is_priority": True},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Inventory all personal data categories handled across Mobility, Eats, and Freight", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Coordinate with Chief Privacy Officer and DPO for evidence availability timeline", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Design DSR fulfilment sampling methodology (stratified by request type and jurisdiction)", "status": TaskStatus.done},
            # Phase 2 — Fieldwork
            {"phase": 2, "phase_label": "Fieldwork", "label": "Test DSR fulfilment: end-to-end timing for 50 sampled requests (access, deletion, portability)", "status": TaskStatus.done, "is_priority": True},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Review consent capture and withdrawal mechanisms in Uber and Uber Eats apps", "status": TaskStatus.in_progress, "is_priority": True},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Assess Standard Contractual Clauses (SCCs) for EU–US data transfers (driver identity documents, trip data)", "status": TaskStatus.in_progress},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Evaluate DPA completeness for critical processors — Checkr, AWS, Google Maps, Twilio", "status": TaskStatus.pending},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Test data retention enforcement: automated deletion for deactivated accounts and expired trip data", "status": TaskStatus.pending},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Interview CPO on breach notification procedures and state AG reporting readiness", "status": TaskStatus.pending},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Assess sensitive data handling: precise geolocation, biometric liveness data, driver licence scans", "status": TaskStatus.pending},
            # Phase 3 — Reporting
            {"phase": 3, "phase_label": "Reporting", "label": "Compile privacy maturity scorecard across CCPA/CPRA and GDPR pillars", "status": TaskStatus.pending},
            {"phase": 3, "phase_label": "Reporting", "label": "Draft gap remediation roadmap with regulatory deadline mapping", "status": TaskStatus.pending},
            {"phase": 3, "phase_label": "Reporting", "label": "Present findings to CPO, Legal, and Audit Committee", "status": TaskStatus.pending},
        ],
    },

    # ── Plan 3: Platform Safety & Background Screening ─────────────────────────
    {
        "name": "Platform Safety & Background Screening Controls Review — FY2024",
        "description": "Annual review of Uber's driver and courier background screening programme, in-trip safety controls (RideCheck, Emergency SOS), and incident response procedures. Covers FCRA compliance, CPUC safety mandate adherence, and continuous monitoring effectiveness.",
        "status": AuditStatus.reporting,
        "planned_start": now - timedelta(days=90),
        "planned_end":   now - timedelta(days=5),
        "actual_start":  now - timedelta(days=88),
        "actual_end":    now - timedelta(days=6),
        "tasks": [
            # Phase 1 — Planning (all done)
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Define scope: driver onboarding screening, annual rechecks, and continuous monitoring across US, CA, AU, GB", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Review prior year safety audit findings and open management actions", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Obtain background check population data from Checkr for FY2024 (all US markets)", "status": TaskStatus.done},
            {"phase": 1, "phase_label": "Planning & Scoping", "label": "Issue audit engagement notice to Head of Safety and Trust & Safety VP", "status": TaskStatus.done},
            # Phase 2 — Fieldwork (all done)
            {"phase": 2, "phase_label": "Fieldwork", "label": "Test background check completeness — sample 100 active driver activations against FCRA-required disclosures", "status": TaskStatus.done, "is_priority": True},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Evaluate continuous monitoring hit-rate and auto-deactivation workflow (Checkr Continuous Check)", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Assess RideCheck anomaly detection coverage and escalation-to-911 response time SLAs", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Review CPUC Annual Safety Report data quality and completeness (CA requirement)", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Test FCRA adverse action notice procedures for deactivated drivers", "status": TaskStatus.done},
            {"phase": 2, "phase_label": "Fieldwork", "label": "Interview Trust & Safety VP on incident triage, law enforcement cooperation, and reporting procedures", "status": TaskStatus.done, "is_priority": True},
            # Phase 3 — Reporting
            {"phase": 3, "phase_label": "Reporting", "label": "Issue draft report to Head of Safety — 4 findings, 3 recommendations", "status": TaskStatus.done},
            {"phase": 3, "phase_label": "Reporting", "label": "Collect management responses (received within SLA)", "status": TaskStatus.done},
            {"phase": 3, "phase_label": "Reporting", "label": "Finalise audit report and distribute to Audit Committee and CPUC (public safety data only)", "status": TaskStatus.in_progress, "is_priority": True},
        ],
    },
]


async def seed():
    async with AsyncSessionLocal() as db:
        # Clear existing audit plans for this org
        existing_plans = (await db.execute(
            select(AuditPlan).where(AuditPlan.org_id == ORG_ID)
        )).scalars().all()

        if existing_plans:
            print(f"Clearing {len(existing_plans)} existing audit plan(s)...")
            for plan in existing_plans:
                await db.execute(delete(AuditTask).where(AuditTask.plan_id == plan.id))
            await db.execute(delete(AuditPlan).where(AuditPlan.org_id == ORG_ID))
            await db.commit()

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
            await db.flush()

            tasks = []
            for i, t in enumerate(tasks_data):
                task = AuditTask(plan_id=plan.id, sort_order=i, **t)
                tasks.append(task)
                db.add(task)

            await db.flush()

            done  = sum(1 for t in tasks_data if t["status"] == TaskStatus.done)
            total = len(tasks_data)
            plan.task_count   = total
            plan.done_count   = done
            plan.progress_pct = (done / total * 100) if total else 0.0

            print(f"  ✓ {plan.name}  [{done}/{total} tasks · {plan.progress_pct:.0f}%]")

        await db.commit()
        print("\n✅ Audit plans seeded successfully for Uber Technologies, Inc.")


if __name__ == "__main__":
    asyncio.run(seed())
