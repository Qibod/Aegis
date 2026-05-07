"""
One-shot seeding script for Meridian Financial Services.
Run inside the api container: docker compose exec api python seed_meridian.py
"""
import asyncio
import sys
sys.path.insert(0, '/app')

ORG_ID = 'ddda03b3-cd63-4d1c-a1a8-15871872876b'

RISKS = [
    {"name": "AML Transaction Monitoring Gaps", "domain": "Financial Crime & Fraud",
     "severity": "critical", "likelihood": 4, "impact": 5,
     "description": "Insufficient real-time transaction monitoring coverage leaves the firm exposed to money laundering typologies not captured by existing rule sets, with potential DNB enforcement action.",
     "framework_tags": ["AMLD6", "FATF", "ISO 31000"]},
    {"name": "GDPR Data Subject Access Request Backlogs", "domain": "Data Privacy & Protection",
     "severity": "high", "likelihood": 4, "impact": 4,
     "description": "DSARs are not consistently fulfilled within the 30-day statutory window due to fragmented data stores across legacy and cloud systems.",
     "framework_tags": ["GDPR", "AVG", "ISO 27701"]},
    {"name": "Third-Party Fintech API Dependency", "domain": "Third-Party & Vendor Risk",
     "severity": "high", "likelihood": 3, "impact": 5,
     "description": "Critical payment processing and KYC functions rely on a small number of API-connected fintechs; a single supplier outage could halt onboarding and transaction flows.",
     "framework_tags": ["DORA", "ISO 27001", "EBA Outsourcing Guidelines"]},
    {"name": "Ransomware Attack on Core Banking Infrastructure", "domain": "Cybersecurity & Information Security",
     "severity": "critical", "likelihood": 3, "impact": 5,
     "description": "A successful ransomware attack could encrypt core banking data, disrupt operations for days, and trigger mandatory regulatory notification under DORA and GDPR.",
     "framework_tags": ["DORA", "ISO 27001", "NIS2"]},
    {"name": "Sanctions Screening False Negatives", "domain": "Financial Crime & Fraud",
     "severity": "critical", "likelihood": 3, "impact": 5,
     "description": "Screening system may generate false negatives on SDN/EU sanctions lists due to transliteration variations and name-matching algorithm gaps, creating OFAC and EU sanctions exposure.",
     "framework_tags": ["EU Sanctions Regulation", "OFAC", "FATF"]},
    {"name": "Operational Resilience — Recovery Time Breach", "domain": "Business Continuity & Resilience",
     "severity": "high", "likelihood": 3, "impact": 4,
     "description": "Current RTO for the payment gateway exceeds DORA's tolerable disruption threshold for important business services, creating supervisory risk under the 2025 DORA deadline.",
     "framework_tags": ["DORA", "EBA Guidelines on ICT Risk", "ISO 22301"]},
    {"name": "Algorithmic Credit Scoring Bias", "domain": "Model & Algorithmic Risk",
     "severity": "high", "likelihood": 3, "impact": 4,
     "description": "ML-based credit decisioning model may exhibit demographic bias, creating exposure under EU AI Act prohibited practices provisions and consumer credit regulations.",
     "framework_tags": ["EU AI Act", "Consumer Credit Directive", "EBA ML Guidelines"]},
    {"name": "Privileged Access Management Weaknesses", "domain": "Cybersecurity & Information Security",
     "severity": "high", "likelihood": 4, "impact": 4,
     "description": "Excessive privileged accounts and insufficient PAM controls create insider threat risk and increase blast radius of compromised credentials.",
     "framework_tags": ["ISO 27001", "NIST CSF", "DORA"]},
    {"name": "Cross-Border Payment Regulatory Fragmentation", "domain": "Legal & Regulatory Compliance",
     "severity": "medium", "likelihood": 4, "impact": 3,
     "description": "Rapidly evolving PSR and cross-border payment regulations across operating jurisdictions create compliance gaps as local rules diverge from EU baseline.",
     "framework_tags": ["PSD2", "PSR", "FATF Recommendation 16"]},
    {"name": "Staff Fraud & Insider Dealing", "domain": "Conduct & Culture Risk",
     "severity": "medium", "likelihood": 2, "impact": 5,
     "description": "Access to customer accounts and transaction data creates opportunity for staff fraud or market manipulation; detection controls rely heavily on reactive alerting.",
     "framework_tags": ["MAR", "MiFID II", "FCA Conduct Rules"]},
    {"name": "Cloud Infrastructure Misconfiguration", "domain": "Technology & IT Risk",
     "severity": "high", "likelihood": 4, "impact": 4,
     "description": "Rapid cloud adoption without consistent IaC guardrails has resulted in misconfigured S3 buckets and IAM roles identified in the last penetration test.",
     "framework_tags": ["ISO 27001", "CIS Benchmarks", "DORA"]},
    {"name": "ESG Greenwashing Regulatory Risk", "domain": "Environmental, Social & Governance (ESG)",
     "severity": "medium", "likelihood": 3, "impact": 3,
     "description": "Forthcoming SFDR and CSRD requirements impose disclosure obligations; current ESG data quality and reporting processes are insufficient for institutional investor expectations.",
     "framework_tags": ["SFDR", "CSRD", "EU Taxonomy Regulation"]},
]

CONTROLS = [
    {"name": "Transaction Monitoring Rule Engine", "domain": "Financial Crime & Fraud",
     "type": "automated", "description": "Real-time rule-based transaction monitoring covering 47 AML typologies including structuring, rapid movement, and high-risk jurisdiction routing.",
     "framework_tags": ["AMLD6", "FATF", "DNB AML Guidelines"]},
    {"name": "DSAR Intake & Fulfilment Workflow", "domain": "Data Privacy & Protection",
     "type": "manual", "description": "Structured intake process with 25-day SLA, legal review gate, and cross-system data retrieval checklist to ensure GDPR-compliant response.",
     "framework_tags": ["GDPR Art. 15", "AVG"]},
    {"name": "Third-Party Risk Assessment Programme", "domain": "Third-Party & Vendor Risk",
     "type": "manual", "description": "Annual vendor risk assessments for critical suppliers including security questionnaires, SOC 2 review, and sub-processor mapping.",
     "framework_tags": ["DORA", "EBA Outsourcing Guidelines"]},
    {"name": "Endpoint Detection & Response (EDR)", "domain": "Cybersecurity & Information Security",
     "type": "automated", "description": "CrowdStrike Falcon deployed across 98% of endpoints with 24/7 SOC monitoring and automated quarantine for suspected ransomware activity.",
     "framework_tags": ["DORA", "ISO 27001 A.12", "NIST CSF"]},
    {"name": "Sanctions Screening — Real-Time API", "domain": "Financial Crime & Fraud",
     "type": "automated", "description": "Dow Jones Risk & Compliance API screens all onboarding and transaction counterparties against OFAC SDN, EU Consolidated List, and UN sanctions lists with 300ms SLA.",
     "framework_tags": ["EU Sanctions Regulation", "OFAC", "FATF Recommendation 6"]},
    {"name": "Business Continuity & DR Testing", "domain": "Business Continuity & Resilience",
     "type": "manual", "description": "Semi-annual tabletop exercises and annual full DR failover tests for payment gateway and core banking, with RTO/RPO validation against DORA thresholds.",
     "framework_tags": ["DORA Art. 25", "ISO 22301"]},
    {"name": "AI Model Risk Governance Framework", "domain": "Model & Algorithmic Risk",
     "type": "manual", "description": "Pre-deployment bias testing, ongoing drift monitoring, and model inventory management for all credit and fraud ML models per EBA ML guidelines.",
     "framework_tags": ["EU AI Act", "EBA ML Guidelines", "SS1/23"]},
    {"name": "Privileged Access Management (CyberArk)", "domain": "Cybersecurity & Information Security",
     "type": "automated", "description": "CyberArk PAM vaults all privileged credentials with just-in-time access, session recording, and quarterly access reviews. Covers 94% of privileged accounts.",
     "framework_tags": ["ISO 27001 A.9", "NIST CSF PR.AC", "DORA"]},
    {"name": "Regulatory Change Management Process", "domain": "Legal & Regulatory Compliance",
     "type": "manual", "description": "Monthly horizon-scanning review by Legal & Compliance, with impact assessments for material changes and tracked remediation plans in the GRC register.",
     "framework_tags": ["PSD2", "MiFID II", "PSR"]},
    {"name": "Whistleblower & Speak-Up Programme", "domain": "Conduct & Culture Risk",
     "type": "manual", "description": "Anonymous whistleblower channel, mandatory annual conduct training, and quarterly tone-from-the-top communications from ExCo.",
     "framework_tags": ["EU Whistleblower Directive", "MAR", "FCA Conduct Rules"]},
    {"name": "Cloud Security Posture Management (CSPM)", "domain": "Technology & IT Risk",
     "type": "automated", "description": "Wiz CSPM continuously scans AWS and Azure environments for misconfigurations, exposed credentials, and policy violations with P1 auto-remediation.",
     "framework_tags": ["ISO 27001", "CIS Benchmarks", "DORA"]},
    {"name": "ESG Reporting & Disclosure Framework", "domain": "Environmental, Social & Governance (ESG)",
     "type": "manual", "description": "Annual SFDR entity-level disclosure, CSRD readiness gap assessment, and board-approved ESG KPI dashboard for investor reporting.",
     "framework_tags": ["SFDR", "CSRD", "EU Taxonomy Regulation"]},
    {"name": "Access Review & Recertification", "domain": "Cybersecurity & Information Security",
     "type": "manual", "description": "Quarterly access recertification for all production systems; line managers attest to necessity of each user's entitlements with automated deprovisioning on rejection.",
     "framework_tags": ["ISO 27001 A.9.2", "DORA", "NIST CSF"]},
    {"name": "KYC / Customer Due Diligence Engine", "domain": "Financial Crime & Fraud",
     "type": "automated", "description": "Onfido-powered identity verification with liveness detection, PEP/adverse media screening, and risk-tiered EDD workflow for high-risk customers.",
     "framework_tags": ["AMLD6", "FATF Rec 10", "DNB CDD Guidelines"]},
    {"name": "Vulnerability Management & Patch SLAs", "domain": "Cybersecurity & Information Security",
     "type": "automated", "description": "Tenable.io continuous scanning with P1 patch SLA of 24h, P2 of 7 days, automated enforcement via AWS Security Hub and Jira ticketing integration.",
     "framework_tags": ["DORA", "ISO 27001 A.12.6", "CIS Control 7"]},
]

PULSE_METRICS = {
    "Transaction Monitoring Rule Engine": {"alerts_fired_today": 47, "false_positive_rate_pct": 12, "sla_met_pct": 98},
    "Endpoint Detection & Response (EDR)": {"coverage_pct": 98, "incidents_last_30d": 3, "mean_time_to_detect_min": 4},
    "Sanctions Screening — Real-Time API": {"screens_today": 1284, "avg_latency_ms": 187, "matches_flagged": 2},
    "Privileged Access Management (CyberArk)": {"accounts_vaulted": 847, "sessions_recorded_today": 23, "overdue_reviews": 12},
    "Cloud Security Posture Management (CSPM)": {"critical_findings": 2, "high_findings": 11, "auto_remediated_today": 8},
    "Access Review & Recertification": {"completion_pct": 34, "overdue_users": 127, "days_until_deadline": 14},
    "KYC / Customer Due Diligence Engine": {"onboardings_today": 312, "pass_rate_pct": 91, "edd_triggered": 18},
    "Vulnerability Management & Patch SLAs": {"critical_unpatched": 0, "high_unpatched": 7, "p1_sla_met_pct": 100},
}

PULSE_ALERTS = {
    "Access Review & Recertification": "Completion dropped from 71% to 34% over 14 days. At current velocity the quarterly deadline will be missed. Recommend escalating to IT owner to issue automated reminders.",
    "Cloud Security Posture Management (CSPM)": "2 critical findings in eu-west-1 relate to publicly exposed S3 buckets containing transaction logs. Auto-remediation has been attempted but requires manual review.",
    "Privileged Access Management (CyberArk)": "12 privileged accounts have overdue quarterly reviews. Two accounts belong to former contractors — immediate revocation recommended.",
}

async def seed():
    import os
    os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://aegis:aegis@db:5432/aegis')

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select, delete
    from app.models import (
        Risk, Control, CanvasNode, CanvasEdge, Framework,
        RiskSeverity, ControlType, ControlStatus, NodeType, EdgeType
    )
    from uuid import UUID
    from datetime import datetime, timezone, timedelta
    import random

    org_uuid = UUID(ORG_ID)
    engine = create_async_engine(os.environ['DATABASE_URL'], echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Clear existing (empty) data
        await db.execute(delete(CanvasEdge).where(CanvasEdge.org_id == org_uuid))
        await db.execute(delete(CanvasNode).where(CanvasNode.org_id == org_uuid))
        await db.execute(delete(Control).where(Control.org_id == org_uuid))
        await db.execute(delete(Risk).where(Risk.org_id == org_uuid))
        await db.commit()

        SEV_MAP = {"critical": RiskSeverity.critical, "high": RiskSeverity.high,
                   "medium": RiskSeverity.medium, "low": RiskSeverity.low}
        TYPE_MAP = {"automated": ControlType.automated, "manual": ControlType.manual,
                    "compensating": ControlType.compensating}
        STATUS_LIST = [ControlStatus.effective, ControlStatus.effective, ControlStatus.effective,
                       ControlStatus.partial, ControlStatus.ineffective, ControlStatus.not_tested]

        # ── Risks ──────────────────────────────────────────────────────────────
        risk_rows = []
        for r in RISKS:
            row = Risk(
                org_id=org_uuid,
                name=r["name"],
                description=r["description"],
                domain=r["domain"],
                inherent_severity=SEV_MAP[r["severity"]],
                residual_severity=SEV_MAP[r["severity"]],
                likelihood=r["likelihood"],
                impact=r["impact"],
                framework_tags=r["framework_tags"],
                ai_assessment={"source": "fingerprint", "rationale": r["description"]},
                ai_seeded=True,
            )
            db.add(row)
            risk_rows.append(row)
        await db.flush()
        print(f"Seeded {len(risk_rows)} risks")

        # ── Controls ───────────────────────────────────────────────────────────
        control_rows = []
        for c in CONTROLS:
            status = random.choice(STATUS_LIST)
            last_tested = (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 90))) if status != ControlStatus.not_tested else None
            metrics = PULSE_METRICS.get(c["name"], {})
            alert = PULSE_ALERTS.get(c["name"])

            row = Control(
                org_id=org_uuid,
                name=c["name"],
                description=c["description"],
                domain=c["domain"],
                control_type=TYPE_MAP.get(c["type"], ControlType.manual),
                status=status,
                framework_tags=c["framework_tags"],
                last_tested_at=last_tested,
                test_frequency_days=90,
                integration_source=None,
                integration_config=metrics if metrics else None,
                ai_seeded=True,
            )
            db.add(row)
            control_rows.append((row, alert))
        await db.flush()
        print(f"Seeded {len(control_rows)} controls")

        # ── Canvas nodes + edges ───────────────────────────────────────────────
        COLS = 4
        risk_nodes = []
        for i, risk in enumerate(risk_rows):
            node = CanvasNode(
                org_id=org_uuid,
                node_type=NodeType.risk,
                risk_id=risk.id,
                label=risk.name,
                pos_x=float((i % COLS) * 320 + 80),
                pos_y=float((i // COLS) * 200 + 80),
            )
            db.add(node)
            risk_nodes.append((node, risk))

        control_nodes = []
        risk_row_count = (len(risk_rows) // COLS) + 2
        for i, (control, _) in enumerate(control_rows):
            node = CanvasNode(
                org_id=org_uuid,
                node_type=NodeType.control,
                control_id=control.id,
                label=control.name,
                pos_x=float((i % COLS) * 320 + 80),
                pos_y=float((i // COLS) * 200 + risk_row_count * 200 + 80),
            )
            db.add(node)
            control_nodes.append((node, control))
        await db.flush()

        # Edges: connect controls to risks by domain
        edge_count = 0
        for c_node, control in control_nodes:
            for r_node, risk in risk_nodes:
                if control.domain and risk.domain and (
                    control.domain.lower() == risk.domain.lower() or
                    control.domain.lower() in risk.domain.lower() or
                    risk.domain.lower() in control.domain.lower()
                ):
                    db.add(CanvasEdge(
                        org_id=org_uuid,
                        from_node_id=c_node.id,
                        to_node_id=r_node.id,
                        edge_type=EdgeType.mitigates,
                    ))
                    edge_count += 1
        await db.flush()
        print(f"Seeded {len(risk_nodes)} risk nodes, {len(control_nodes)} control nodes, {edge_count} edges")

        await db.commit()
        print("✅ Seeding complete!")

    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(seed())
