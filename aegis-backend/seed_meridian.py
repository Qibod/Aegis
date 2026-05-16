"""
One-shot seeding script for Uber Technologies, Inc.
Run inside the api container: docker compose exec api python seed_meridian.py
"""
import asyncio
import sys
sys.path.insert(0, '/app')

ORG_ID = 'ddda03b3-cd63-4d1c-a1a8-15871872876b'

RISKS = [
    {
        "name": "Gig Worker Misclassification Liability",
        "domain": "Workforce & Labour Law",
        "severity": "critical", "likelihood": 5, "impact": 5,
        "description": "Ongoing legal exposure that drivers and couriers are employees rather than independent contractors across multiple jurisdictions. AB5 in California, the EU Platform Work Directive, and analogous laws in the UK and Australia impose back-pay, benefits, and penalty risk estimated in the billions.",
        "framework_tags": ["COSO ERM", "AB5", "EU Platform Work Directive", "UK Employment Rights Act"],
    },
    {
        "name": "Passenger / Diner Harm from Inadequate Background Screening",
        "domain": "Safety & Physical Security",
        "severity": "critical", "likelihood": 3, "impact": 5,
        "description": "Background check failures or gaps between annual rechecks allow individuals with disqualifying criminal histories onto the platform. Safety incidents generate civil liability, regulatory enforcement by the FTC/CPUC, and severe reputational harm.",
        "framework_tags": ["FCRA", "FTC Act", "CPUC Rideshare Safety Rules"],
    },
    {
        "name": "Large-Scale Customer Data Breach",
        "domain": "Data Privacy & Cybersecurity",
        "severity": "high", "likelihood": 3, "impact": 5,
        "description": "Breach of rider, diner, or driver PII — including real-time location history, payment data, and identity documents — triggers mandatory notification under CCPA/CPRA, GDPR, and breach-notification laws in 50+ US states, with class-action and regulatory fine exposure.",
        "framework_tags": ["CCPA/CPRA", "GDPR", "PCI DSS", "ISO 27001"],
    },
    {
        "name": "Regulatory Ban or Suspension in Key Market",
        "domain": "Regulatory & Compliance",
        "severity": "critical", "likelihood": 3, "impact": 5,
        "description": "Authorities (Transport for London, EU member states, US cities) can suspend or revoke operating licences over safety, labour, or data concerns — as seen historically in London and several EU cities. Loss of a top-5 market would materially impact revenue.",
        "framework_tags": ["TfL Private Hire Regulations", "EU Platform Work Directive", "CPUC"],
    },
    {
        "name": "Antitrust Enforcement on Surge Pricing or Market Dominance",
        "domain": "Marketplace & Antitrust",
        "severity": "high", "likelihood": 3, "impact": 4,
        "description": "DOJ, EU DG COMP, and state AGs are scrutinising dynamic pricing algorithms and exclusive agreements for potential per se antitrust violations. Algorithmic price coordination or market foreclosure claims carry treble-damages risk.",
        "framework_tags": ["Sherman Act", "EU Competition Law", "COSO ERM"],
    },
    {
        "name": "Platform Outage During Peak Demand",
        "domain": "Technology & Platform Resilience",
        "severity": "high", "likelihood": 3, "impact": 4,
        "description": "Failure of the dispatch, matching, or payments infrastructure during surge periods (New Year's Eve, major events) causes direct revenue loss and breaches SLAs with enterprise clients. A multi-hour outage may trigger regulatory inquiries in markets with essential-service obligations.",
        "framework_tags": ["SOC 2 Type II", "NIST CSF", "ISO 22301"],
    },
    {
        "name": "Payment Fraud and Chargeback Abuse",
        "domain": "Financial Crime & Payments",
        "severity": "high", "likelihood": 4, "impact": 3,
        "description": "Synthetic-identity fraud, stolen payment credentials, and promo-code abuse across Uber and Uber Eats generate chargeback losses and merchant disputes. At scale, fraud rates exceeding card-network thresholds risk merchant-account suspension.",
        "framework_tags": ["PCI DSS", "BSA/AML", "Nacha Rules"],
    },
    {
        "name": "Driver / Courier Algorithmic Earnings Bias",
        "domain": "Workforce & Labour Law",
        "severity": "high", "likelihood": 3, "impact": 4,
        "description": "AI-driven dispatch, acceptance-rate weighting, and deactivation algorithms may produce disparate earnings impacts across demographic groups, creating exposure under Title VII, ECOA, and emerging EU AI Act requirements for high-risk algorithmic decision-making.",
        "framework_tags": ["EU AI Act", "Title VII", "ECOA", "COSO ERM"],
    },
    {
        "name": "CCPA / GDPR Data Subject Rights Backlog",
        "domain": "Data Privacy & Cybersecurity",
        "severity": "medium", "likelihood": 4, "impact": 3,
        "description": "High volume of data subject access, deletion, and portability requests from riders and drivers may not be fulfilled within statutory windows (45 days CCPA, 30 days GDPR), particularly where data spans multiple microservices and international transfers.",
        "framework_tags": ["CCPA/CPRA", "GDPR Art. 15-22", "ISO 27701"],
    },
    {
        "name": "Uber Freight Carrier Compliance Failure",
        "domain": "Regulatory & Compliance",
        "severity": "high", "likelihood": 3, "impact": 4,
        "description": "Onboarding freight carriers without validating current FMCSA operating authority, safety ratings, and insurance certificates creates brokerage liability for cargo loss, injury, and environmental incidents under 49 CFR Part 371.",
        "framework_tags": ["DOT/FMCSA 49 CFR 371", "COSO ERM"],
    },
    {
        "name": "Cloud Infrastructure Misconfiguration",
        "domain": "Technology & Platform Resilience",
        "severity": "high", "likelihood": 4, "impact": 4,
        "description": "Misconfigurations in AWS S3, GCP Cloud Storage, or IAM policies — identified in prior penetration tests — could expose trip data, driver identity documents, or internal APIs. The attack surface spans hundreds of microservices across three cloud providers.",
        "framework_tags": ["ISO 27001", "CIS Benchmarks", "NIST CSF", "SOC 2 Type II"],
    },
    {
        "name": "Third-Party API Concentration Risk",
        "domain": "Technology & Platform Resilience",
        "severity": "medium", "likelihood": 3, "impact": 4,
        "description": "Critical real-time dependencies on Google Maps Platform (routing/ETA), Twilio (SMS/OTP), and Checkr (background checks) mean a single-supplier outage can degrade driver matching, rider authentication, or onboarding flows globally.",
        "framework_tags": ["NIST CSF", "ISO 27001", "SOC 2 Type II"],
    },
]

CONTROLS = [
    {
        "name": "Continuous Background Monitoring (Checkr)",
        "domain": "Safety & Physical Security",
        "type": "automated",
        "description": "Real-time criminal record monitoring via Checkr flags disqualifying incidents between annual full rechecks. Automated deactivation workflow triggers within 24 hours of a flagged hit across all markets.",
        "framework_tags": ["FCRA", "CPUC Rideshare Safety Rules"],
    },
    {
        "name": "Real-Time Safety Toolkit (RideCheck / Emergency SOS)",
        "domain": "Safety & Physical Security",
        "type": "automated",
        "description": "On-trip anomaly detection (unexpected stops, route deviations) triggers automatic RideCheck prompts. One-tap 911 SOS shares live GPS and trip details with emergency services. Share My Trip enables real-time location sharing with trusted contacts.",
        "framework_tags": ["CPUC", "FTC Act"],
    },
    {
        "name": "PCI DSS Payment Tokenisation",
        "domain": "Financial Crime & Payments",
        "type": "automated",
        "description": "All card data tokenised at point of capture via Braintree/PayPal. Raw PANs are never stored in Uber's application layer; tokens are mapped to cards in the payment processor's PCI-certified vault, eliminating cardholder data from Uber's scope.",
        "framework_tags": ["PCI DSS v4.0", "Nacha Rules"],
    },
    {
        "name": "Real-Time Fraud Detection ML Model",
        "domain": "Financial Crime & Payments",
        "type": "automated",
        "description": "Multi-model fraud stack (gradient boosting + neural network) scores every trip, promo redemption, and payout in real time. Signals include device fingerprint, velocity, geolocation, and synthetic-identity indicators. Fraudulent transactions blocked before completion.",
        "framework_tags": ["PCI DSS", "BSA/AML"],
    },
    {
        "name": "CCPA / GDPR Data Subject Request Workflow",
        "domain": "Data Privacy & Cybersecurity",
        "type": "manual",
        "description": "Centralised DSR portal for riders and drivers. Automated data discovery aggregates records across 200+ microservices. Legal review gate for ambiguous requests. 45-day CCPA / 30-day GDPR SLA enforced by workflow tooling with escalation reminders.",
        "framework_tags": ["CCPA/CPRA", "GDPR Art. 15-22"],
    },
    {
        "name": "Surge Pricing Audit & Cap Policy",
        "domain": "Marketplace & Antitrust",
        "type": "manual",
        "description": "Quarterly competition counsel review of surge algorithm design and market-share data. Hard caps enforced during declared emergencies (state law). Annual antitrust compliance training for pricing and data science teams.",
        "framework_tags": ["Sherman Act", "EU Competition Law"],
    },
    {
        "name": "Gig Worker Classification Legal Review Programme",
        "domain": "Workforce & Labour Law",
        "type": "manual",
        "description": "Quarterly jurisdiction-by-jurisdiction legal review of classification risk, with board escalation for material legislative changes (AB5 analogues, EU Platform Work Directive transposition). Dedicated policy team monitors 70+ regulatory developments simultaneously.",
        "framework_tags": ["AB5", "EU Platform Work Directive", "UK Employment Rights Act"],
    },
    {
        "name": "AI Fairness & Algorithmic Bias Testing",
        "domain": "Workforce & Labour Law",
        "type": "manual",
        "description": "Pre-deployment disparate-impact testing for dispatch, deactivation, and earnings algorithms. Ongoing drift monitoring with monthly fairness metrics reviewed by a dedicated Responsible AI committee. Model inventory maintained per EU AI Act Art. 9 requirements.",
        "framework_tags": ["EU AI Act", "Title VII", "ECOA"],
    },
    {
        "name": "FMCSA Carrier Verification Gate (Uber Freight)",
        "domain": "Regulatory & Compliance",
        "type": "automated",
        "description": "Automated FMCSA API lookup blocks carrier onboarding if operating authority is not active, safety rating is unsatisfactory, or insurance certificates are expired or below minimum thresholds. Re-verified at every load tender.",
        "framework_tags": ["DOT/FMCSA 49 CFR 371"],
    },
    {
        "name": "SOC 2 Type II & ISO 27001 Certification Programme",
        "domain": "Technology & Platform Resilience",
        "type": "manual",
        "description": "Annual SOC 2 Type II audit (Security, Availability, Confidentiality) and ISO 27001 surveillance audits. Continuous control monitoring via Drata feeds evidence into audit readiness dashboards. Customer-facing trust portal publishes reports.",
        "framework_tags": ["SOC 2 Type II", "ISO 27001"],
    },
    {
        "name": "Disaster Recovery & Multi-Region Failover",
        "domain": "Technology & Platform Resilience",
        "type": "automated",
        "description": "Active-active multi-region deployment across AWS us-east-1, us-west-2, and eu-west-1. Automated failover with RTO < 5 minutes and RPO < 1 minute for dispatch and payments. Quarterly chaos engineering exercises validate recovery runbooks.",
        "framework_tags": ["ISO 22301", "NIST CSF", "SOC 2 Type II"],
    },
    {
        "name": "Cloud Security Posture Management (CSPM)",
        "domain": "Technology & Platform Resilience",
        "type": "automated",
        "description": "Wiz CSPM continuously scans AWS, GCP, and Azure environments for misconfigurations, exposed credentials, and policy violations. P1 findings (publicly exposed buckets, admin key exposure) auto-remediated or paged to on-call within 15 minutes.",
        "framework_tags": ["ISO 27001", "CIS Benchmarks", "SOC 2 Type II"],
    },
    {
        "name": "Vulnerability Management & Patch SLAs",
        "domain": "Technology & Platform Resilience",
        "type": "automated",
        "description": "Tenable.io continuous scanning across 200+ microservices. P1 (CVSS 9+) patch SLA: 24 hours. P2 (CVSS 7-8.9): 7 days. Automated enforcement via GitHub Actions blocking merge until remediated. Bug bounty programme via HackerOne for external researchers.",
        "framework_tags": ["NIST CSF", "ISO 27001", "SOC 2 Type II"],
    },
    {
        "name": "Privileged Access Management & Just-in-Time Access",
        "domain": "Data Privacy & Cybersecurity",
        "type": "automated",
        "description": "HashiCorp Vault manages privileged credentials. JIT access grants time-limited, audited sessions for production environment access. All privileged sessions recorded. Quarterly access recertification by engineering managers with automated deprovisioning on rejection.",
        "framework_tags": ["ISO 27001 A.9", "NIST CSF PR.AC", "SOC 2 Type II"],
    },
    {
        "name": "Driver & Courier Onboarding Document Verification",
        "domain": "Safety & Physical Security",
        "type": "automated",
        "description": "AI-powered document verification (Onfido) validates driving licence, vehicle registration, and insurance at onboarding and renewal. Liveness detection prevents identity spoofing. Failed verification blocks activation; manual review queue for edge cases.",
        "framework_tags": ["FCRA", "CPUC", "GDPR Art. 9"],
    },
]

PULSE_METRICS = {
    "Continuous Background Monitoring (Checkr)": {"checks_completed_today": 2847, "flags_raised_today": 12, "auto_deactivations_today": 3},
    "Real-Time Fraud Detection ML Model": {"transactions_scored_today": 892450, "fraud_blocked_today": 1284, "false_positive_rate_pct": 0.8},
    "CCPA / GDPR Data Subject Request Workflow": {"open_requests": 234, "avg_completion_days": 18, "overdue_pct": 4},
    "Surge Pricing Audit & Cap Policy": {"markets_above_4x_today": 7, "emergency_cap_activations_30d": 2, "legal_review_overdue": 0},
    "FMCSA Carrier Verification Gate (Uber Freight)": {"verifications_today": 1192, "blocked_carriers_today": 23, "insurance_lapses_flagged": 8},
    "Cloud Security Posture Management (CSPM)": {"critical_findings": 1, "high_findings": 9, "auto_remediated_today": 14},
    "Vulnerability Management & Patch SLAs": {"critical_unpatched": 0, "high_unpatched": 4, "p1_sla_met_pct": 100},
    "Privileged Access Management & Just-in-Time Access": {"active_sessions": 41, "sessions_recorded_today": 41, "overdue_recertifications": 9},
}

PULSE_ALERTS = {
    "CCPA / GDPR Data Subject Request Workflow": "4% of open DSRs are overdue beyond their statutory window. 11 requests have exceeded 45 days (CCPA). Legal team escalation recommended; potential AG inquiry risk.",
    "Cloud Security Posture Management (CSPM)": "1 critical finding in us-east-1: an internal S3 bucket storing driver identity documents is accessible via a misconfigured VPC endpoint policy. Auto-remediation failed — manual intervention required.",
    "Privileged Access Management & Just-in-Time Access": "9 privileged access recertifications are overdue. 3 accounts belong to employees who transferred teams 60+ days ago. Immediate access review required.",
}

async def seed():
    import os
    os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://aegis:aegis@db:5432/aegis')

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select as sel, delete
    from app.models import (
        Risk, Control, CanvasNode, CanvasEdge, Framework,
        RiskSeverity, ControlType, ControlStatus, NodeType, EdgeType,
        OrgProfile, LineOfBusiness, OrgGeography, OrgIndustry,
        OrgProduct, CustomerSegment, ThirdPartyDependency, DataTechProfile,
        ProfileChangeLog, Organization, User,
    )
    from uuid import UUID
    from datetime import datetime, timezone, timedelta
    import random

    org_uuid = UUID(ORG_ID)
    engine = create_async_engine(os.environ['DATABASE_URL'], echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # ── Clear canvas / risk / control data ────────────────────────────
        await db.execute(delete(CanvasEdge).where(CanvasEdge.org_id == org_uuid))
        await db.execute(delete(CanvasNode).where(CanvasNode.org_id == org_uuid))
        await db.execute(delete(Control).where(Control.org_id == org_uuid))
        await db.execute(delete(Risk).where(Risk.org_id == org_uuid))
        await db.commit()

        # ── Clear company profile data ─────────────────────────────────────
        await db.execute(delete(DataTechProfile).where(DataTechProfile.org_id == org_uuid))
        await db.execute(delete(ThirdPartyDependency).where(ThirdPartyDependency.org_id == org_uuid))
        await db.execute(delete(CustomerSegment).where(CustomerSegment.org_id == org_uuid))
        await db.execute(delete(OrgProduct).where(OrgProduct.org_id == org_uuid))
        await db.execute(delete(OrgIndustry).where(OrgIndustry.org_id == org_uuid))
        await db.execute(delete(OrgGeography).where(OrgGeography.org_id == org_uuid))
        await db.execute(delete(LineOfBusiness).where(LineOfBusiness.org_id == org_uuid))
        await db.execute(delete(ProfileChangeLog).where(ProfileChangeLog.org_id == org_uuid))
        await db.execute(delete(OrgProfile).where(OrgProfile.org_id == org_uuid))
        await db.commit()

        SEV_MAP = {"critical": RiskSeverity.critical, "high": RiskSeverity.high,
                   "medium": RiskSeverity.medium, "low": RiskSeverity.low}
        TYPE_MAP = {"automated": ControlType.automated, "manual": ControlType.manual,
                    "compensating": ControlType.compensating}
        STATUS_LIST = [ControlStatus.effective, ControlStatus.effective, ControlStatus.effective,
                       ControlStatus.partial, ControlStatus.ineffective, ControlStatus.not_tested]

        # ── Risks ──────────────────────────────────────────────────────────
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

        # ── Controls ───────────────────────────────────────────────────────
        control_rows = []
        for c in CONTROLS:
            status = random.choice(STATUS_LIST)
            last_tested = (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 90))) if status != ControlStatus.not_tested else None
            metrics = PULSE_METRICS.get(c["name"], {})

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
            control_rows.append(row)
        await db.flush()
        print(f"Seeded {len(control_rows)} controls")

        # ── Canvas nodes + edges ───────────────────────────────────────────
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
        for i, control in enumerate(control_rows):
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

        # ── Company Profile ────────────────────────────────────────────────
        user = (await db.execute(sel(User).where(User.org_id == org_uuid).limit(1))).scalar_one_or_none()
        user_id = user.id if user else org_uuid

        db.add(OrgProfile(
            org_id=org_uuid,
            legal_name="Uber Technologies, Inc.",
            trading_name="Uber",
            year_founded=2009,
            employee_range=">20000",
            annual_revenue_range=">$1B",
            hq_country="US",
            hq_city="San Francisco",
            stock_ticker="UBER",
            website="https://www.uber.com",
            description="Uber is a global technology platform that connects riders with drivers, diners with restaurants, shippers with carriers, and businesses with logistics solutions across 70+ countries. Operates Mobility (ride-hailing), Delivery (Uber Eats), and Freight segments.",
            updated_by=user_id,
        ))
        await db.flush()
        print("Seeded company identity")

        for lob in [
            {"name": "Mobility", "description": "Ride-hailing platform connecting riders with drivers globally.", "status": "active", "is_primary": True, "revenue_contribution_pct": 58},
            {"name": "Delivery (Uber Eats)", "description": "Food, grocery, and convenience delivery marketplace.", "status": "active", "is_primary": False, "revenue_contribution_pct": 37},
            {"name": "Freight", "description": "Digital freight brokerage connecting shippers with carriers.", "status": "active", "is_primary": False, "revenue_contribution_pct": 5},
        ]:
            db.add(LineOfBusiness(org_id=org_uuid, **lob))
        await db.flush()
        print("Seeded lines of business")

        GEO_MAP = {
            "US": (["CCPA/CPRA", "SOX", "FCRA", "BSA/AML", "FTC Act"], "headquarters"),
            "CA": (["PIPEDA", "CASL"], "operational"),
            "GB": (["UK GDPR", "FCA", "TfL Regulations"], "operational"),
            "AU": (["Privacy Act 1988", "APRA"], "operational"),
            "BR": (["LGPD"], "operational"),
            "MX": (["LFPDPPP"], "operational"),
            "IN": (["PDPB", "IT Act 2000"], "operational"),
            "DE": (["GDPR", "BDSG"], "operational"),
            "FR": (["GDPR"], "operational"),
            "NL": (["GDPR"], "operational"),
            "SG": (["PDPA", "MAS Guidelines"], "operational"),
            "JP": (["APPI"], "operational"),
        }
        for country, (flags, presence) in GEO_MAP.items():
            db.add(OrgGeography(org_id=org_uuid, country=country, presence_type=presence, regulatory_flags=flags))
        await db.flush()
        print(f"Seeded {len(GEO_MAP)} geographies")

        for ind in [
            {"code": "7372", "name": "Technology Platform / Software", "classification": "primary"},
            {"code": "4121", "name": "Taxicab & Ridesharing Services", "classification": "secondary"},
            {"code": "5812", "name": "Food Delivery Services", "classification": "secondary"},
            {"code": "7389", "name": "Freight Brokerage", "classification": "secondary"},
        ]:
            db.add(OrgIndustry(org_id=org_uuid, **ind))
        await db.flush()
        print("Seeded industries")

        for prod in [
            {"name": "Uber (Ride-Hailing App)", "product_type": "platform", "status": "live", "data_sensitivity": "critical"},
            {"name": "Uber Eats", "product_type": "platform", "status": "live", "data_sensitivity": "high"},
            {"name": "Uber Freight", "product_type": "platform", "status": "live", "data_sensitivity": "medium"},
            {"name": "Uber for Business", "product_type": "service", "status": "live", "data_sensitivity": "high"},
            {"name": "Uber One (Subscription)", "product_type": "product", "status": "live", "data_sensitivity": "medium"},
            {"name": "Uber Advertising", "product_type": "platform", "status": "live", "data_sensitivity": "medium"},
        ]:
            db.add(OrgProduct(org_id=org_uuid, **prod))
        await db.flush()
        print("Seeded products")

        for seg in [
            {"name": "Riders & Consumers", "segment_type": "b2c", "estimated_size": "~137M monthly active", "includes_minors": False, "includes_healthcare": False, "includes_financial": True},
            {"name": "Drivers & Couriers (Earners)", "segment_type": "b2c", "estimated_size": "~5.4M active earners", "includes_minors": False, "includes_healthcare": False, "includes_financial": True},
            {"name": "Restaurants & Merchants", "segment_type": "b2b", "estimated_size": "~700K+ merchants", "includes_minors": False, "includes_healthcare": False, "includes_financial": False},
            {"name": "Enterprise & Corporate (Uber for Business)", "segment_type": "b2b", "estimated_size": "175K+ business accounts", "includes_minors": False, "includes_healthcare": False, "includes_financial": False},
            {"name": "Shippers & Carriers (Freight)", "segment_type": "b2b", "estimated_size": "~150K+ carriers", "includes_minors": False, "includes_healthcare": False, "includes_financial": False},
        ]:
            db.add(CustomerSegment(org_id=org_uuid, **seg))
        await db.flush()
        print("Seeded customer segments")

        for tp in [
            {"name": "Amazon Web Services (AWS)", "category": "cloud_infrastructure", "tier": "tier_1", "assessment_status": "passed"},
            {"name": "Google Cloud Platform / Maps", "category": "data_processor", "tier": "tier_1", "assessment_status": "passed"},
            {"name": "Checkr", "category": "data_processor", "tier": "tier_1", "assessment_status": "passed"},
            {"name": "Braintree / PayPal", "category": "payment_processor", "tier": "tier_1", "assessment_status": "passed"},
            {"name": "Twilio", "category": "saas_vendor", "tier": "tier_2", "assessment_status": "passed"},
            {"name": "Microsoft Azure", "category": "cloud_infrastructure", "tier": "tier_2", "assessment_status": "passed"},
            {"name": "Onfido", "category": "data_processor", "tier": "tier_2", "assessment_status": "in_progress"},
            {"name": "Drata", "category": "saas_vendor", "tier": "tier_3", "assessment_status": "passed"},
        ]:
            db.add(ThirdPartyDependency(org_id=org_uuid, **tp))
        await db.flush()
        print("Seeded third parties")

        db.add(DataTechProfile(
            org_id=org_uuid,
            uses_ai_ml=True,
            handles_personal_data=True,
            handles_sensitive_personal_data=True,
            handles_payment_data=True,
            handles_health_data=False,
            handles_classified_data=False,
            cloud_providers=["AWS", "GCP", "Azure"],
            ai_use_cases=[
                "Dynamic surge pricing",
                "Driver / rider matching & dispatch",
                "Real-time fraud detection",
                "ETA prediction & route optimisation",
                "Background check anomaly scoring",
                "Driver deactivation risk scoring",
            ],
            core_tech_stack=["Go", "Python", "Node.js", "Kafka", "PostgreSQL", "Redis", "Kubernetes", "React Native"],
        ))
        await db.flush()
        print("Seeded data & tech profile")

        org = (await db.execute(sel(Organization).where(Organization.id == org_uuid))).scalar_one_or_none()
        if org:
            org.name = "Uber Technologies, Inc."
            await db.flush()
            print("Updated organization name → Uber Technologies, Inc.")

        await db.commit()
        print("✅ Seeding complete — Uber Technologies, Inc.")

    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(seed())
