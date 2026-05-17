"""
app/workers/tasks.py
────────────────────
Celery background tasks:
  - Radar feed ingestion (regulatory, threat intel, vendor, macro)
  - Continuous control pulse monitoring (Okta, AWS, KYC provider)
  - AI fingerprint processing
  - Coverage score recomputation
"""
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID

import httpx
from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

settings = get_settings()

# ── Celery app ────────────────────────────────────────────────────────────────
celery_app = Celery(
    "aegis",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,          # re-queue on worker crash
    worker_prefetch_multiplier=1,  # one task at a time per worker
)

# ── Periodic schedule ────────────────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    # Radar feeds
    "ingest-nvd-cves": {
        "task": "app.workers.tasks.ingest_nvd_feed",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
    },
    "ingest-eur-lex": {
        "task": "app.workers.tasks.ingest_eur_lex_feed",
        "schedule": crontab(minute="*/15"),
    },
    "ingest-dnb-feed": {
        "task": "app.workers.tasks.ingest_dnb_feed",
        "schedule": crontab(minute="*/15"),
    },
    "ingest-mitre-feed": {
        "task": "app.workers.tasks.ingest_mitre_feed",
        "schedule": crontab(hour="*/2"),
    },
    # Pulse checks
    "pulse-okta": {
        "task": "app.workers.tasks.check_all_okta_controls",
        "schedule": crontab(minute=0, hour="*/24"),  # daily
    },
    "pulse-aws": {
        "task": "app.workers.tasks.check_all_aws_controls",
        "schedule": crontab(minute=0),  # hourly
    },
    # v2.1 — daily re-seed of unknown fields (02:00 UTC)
    "reseed-unknown-fields": {
        "task": "app.tasks.reseed_unknowns.reseed_all_orgs",
        "schedule": crontab(minute=0, hour=2),
    },
    # v2.1 — hard-delete synthetic tenants older than 90 days (03:00 UTC)
    "cleanup-synthetic-tenants": {
        "task": "app.tasks.cleanup_synthetic_tenants.cleanup_old_synthetic_tenants",
        "schedule": crontab(minute=0, hour=3),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# RADAR INGESTION TASKS
# ─────────────────────────────────────────────────────────────────────────────

def _run_async(coro):
    """Run an async coroutine from a Celery task (synchronous context)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.workers.tasks.ingest_nvd_feed", bind=True, max_retries=3)
def ingest_nvd_feed(self):
    """Fetch recent CVEs from the National Vulnerability Database."""
    try:
        _run_async(_ingest_nvd_async())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


async def _ingest_nvd_async():
    from app.database import get_db_context
    from app.models import Signal, SignalSeverity, SignalCategory
    from app.ai.relevance import score_signal_for_all_orgs

    pub_start = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%S.000"
    )

    params = {
        "pubStartDate": pub_start,
        "resultsPerPage": 50,
    }
    headers = {}
    if settings.anthropic_api_key:  # reuse env check
        pass
    # NVD_API_KEY would go here for higher rate limits

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                "https://services.nvd.nist.gov/rest/json/cves/2.0",
                params=params,
                headers=headers,
            )
            data = resp.json()
        except Exception:
            return

    async with get_db_context() as db:
        for vuln in data.get("vulnerabilities", []):
            cve = vuln.get("cve", {})
            cve_id = cve.get("id", "")
            metrics = cve.get("metrics", {})

            # Get CVSS score
            cvss_score = 0.0
            for key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
                metric_list = metrics.get(key, [])
                if metric_list:
                    cvss_score = metric_list[0].get("cvssData", {}).get("baseScore", 0.0)
                    break

            # Map CVSS to our severity
            if cvss_score >= 9.0:
                severity = SignalSeverity.critical
            elif cvss_score >= 7.0:
                severity = SignalSeverity.high
            elif cvss_score >= 4.0:
                severity = SignalSeverity.medium
            else:
                severity = SignalSeverity.info

            descriptions = cve.get("descriptions", [])
            desc_text = next(
                (d["value"] for d in descriptions if d.get("lang") == "en"), ""
            )

            # Score relevance against all orgs and create signals
            await score_signal_for_all_orgs(
                db=db,
                source="NVD",
                category=SignalCategory.threat,
                severity=severity,
                title=f"{cve_id} (CVSS {cvss_score}) — {desc_text[:120]}",
                body=desc_text,
                external_id=cve_id,
                tags=["CVE", f"CVSS {cvss_score:.1f}"],
                external_url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                published_at=datetime.now(timezone.utc),
            )


@celery_app.task(name="app.workers.tasks.ingest_eur_lex_feed", bind=True, max_retries=3)
def ingest_eur_lex_feed(self):
    """Fetch recent EU regulatory publications from EUR-Lex RSS."""
    try:
        _run_async(_ingest_rss_feed_async(
            url="https://eur-lex.europa.eu/rss/rss.xml",
            source="EUR-Lex",
            category="regulatory",
            default_severity="high",
            tags=["EU regulation"],
        ))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(name="app.workers.tasks.ingest_dnb_feed", bind=True, max_retries=3)
def ingest_dnb_feed(self):
    """Fetch recent DNB publications (Dutch Central Bank)."""
    try:
        _run_async(_ingest_rss_feed_async(
            url="https://www.dnb.nl/en/rss/",
            source="DNB",
            category="regulatory",
            default_severity="high",
            tags=["DNB", "Netherlands"],
        ))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(name="app.workers.tasks.ingest_mitre_feed")
def ingest_mitre_feed():
    """Fetch MITRE ATT&CK updates (simplified — full impl uses STIX API)."""
    _run_async(_ingest_rss_feed_async(
        url="https://medium.com/feed/mitre-attack",
        source="MITRE ATT&CK",
        category="threat",
        default_severity="high",
        tags=["Threat intel", "ATT&CK"],
    ))


async def _ingest_rss_feed_async(
    url: str,
    source: str,
    category: str,
    default_severity: str,
    tags: list[str],
):
    """Generic RSS ingestion — parses feed and calls relevance scoring."""
    import feedparser
    from app.database import get_db_context
    from app.models import SignalSeverity, SignalCategory
    from app.ai.relevance import score_signal_for_all_orgs

    cat_map = {
        "regulatory": SignalCategory.regulatory,
        "threat": SignalCategory.threat,
        "vendor": SignalCategory.vendor,
        "macro": SignalCategory.macro,
    }
    sev_map = {
        "critical": SignalSeverity.critical,
        "high": SignalSeverity.high,
        "medium": SignalSeverity.medium,
        "info": SignalSeverity.info,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            feed = feedparser.parse(resp.text)
    except Exception:
        return

    async with get_db_context() as db:
        for entry in feed.entries[:10]:  # Process latest 10 entries
            title = entry.get("title", "")[:500]
            body = entry.get("summary", "")[:2000]
            link = entry.get("link", "")
            entry_id = entry.get("id", link)

            await score_signal_for_all_orgs(
                db=db,
                source=source,
                category=cat_map.get(category, SignalCategory.regulatory),
                severity=sev_map.get(default_severity, SignalSeverity.high),
                title=title,
                body=body,
                external_id=entry_id,
                tags=tags,
                external_url=link,
                published_at=datetime.now(timezone.utc),
            )


# ─────────────────────────────────────────────────────────────────────────────
# CONTINUOUS CONTROL PULSE TASKS
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.workers.tasks.check_all_okta_controls")
def check_all_okta_controls():
    """Run Okta checks for all orgs that have Okta integrated."""
    _run_async(_check_all_controls_async(integration_source="okta"))


@celery_app.task(name="app.workers.tasks.check_all_aws_controls")
def check_all_aws_controls():
    """Run AWS Security Hub checks for all integrated orgs."""
    _run_async(_check_all_controls_async(integration_source="aws_security_hub"))


async def _check_all_controls_async(integration_source: str):
    from app.database import get_db_context
    from app.models import Control
    from sqlalchemy import select

    async with get_db_context() as db:
        controls = (await db.execute(
            select(Control).where(Control.integration_source == integration_source)
        )).scalars().all()

        for control in controls:
            if integration_source == "okta":
                await _check_okta_control(control, db)
            elif integration_source == "aws_security_hub":
                await _check_aws_control(control, db)


async def _check_okta_control(control, db):
    """
    Check an Okta-monitored control.
    Example: access review completeness.
    """
    from app.models import ControlCheck, PulseStatus
    from app.services.notification_service import notify_if_failing

    config = control.integration_config or {}
    okta_domain = config.get("domain", "")  # set per-control in integration_config

    # In production: call Okta API to get user review status
    # For now, simulate a check
    try:
        # Simulated metrics — replace with real Okta API call:
        # GET https://{domain}/api/v1/users?filter=status eq "ACTIVE"
        # Then check last_login / review timestamp
        metrics = {
            "completion_pct": 34.0,
            "overdue_count": 127,
            "total_users": 374,
        }
        status = PulseStatus.failing if metrics["completion_pct"] < 80 else PulseStatus.passing

    except Exception as e:
        metrics = {"error": str(e)}
        status = PulseStatus.unknown

    check = ControlCheck(
        control_id=control.id,
        org_id=control.org_id,
        status=status,
        metrics=metrics,
        checked_at=datetime.now(timezone.utc),
    )
    db.add(check)
    await db.flush()

    if status in (PulseStatus.failing, PulseStatus.degraded):
        await notify_if_failing(control, metrics, db)


async def _check_aws_control(control, db):
    """Check AWS Security Hub for critical unpatched vulnerabilities."""
    from app.models import ControlCheck, PulseStatus

    try:
        # Production: use boto3 to call SecurityHub.get_findings()
        # boto3.client('securityhub', region_name=settings.aws_region)
        # .get_findings(Filters={"SeverityLabel": [{"Value": "CRITICAL", "Comparison": "EQUALS"}]})
        metrics = {
            "critical_open": 3,
            "high_open": 7,
            "sla_breach_count": 3,
        }
        status = (
            PulseStatus.failing if metrics["critical_open"] > 0
            else PulseStatus.passing
        )
    except Exception as e:
        metrics = {"error": str(e)}
        status = PulseStatus.unknown

    check = ControlCheck(
        control_id=control.id,
        org_id=control.org_id,
        status=status,
        metrics=metrics,
        checked_at=datetime.now(timezone.utc),
    )
    db.add(check)


# ─────────────────────────────────────────────────────────────────────────────
# ONE-OFF TASKS (triggered by API endpoints)
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.workers.tasks.run_fingerprint")
def run_fingerprint(org_id: str, company_name: str):
    """Triggered during onboarding to fingerprint a company."""
    _run_async(_run_fingerprint_async(org_id, company_name))


async def _run_fingerprint_async(org_id: str, company_name: str):
    from app.ai.fingerprint import fingerprint_company, seed_org_from_fingerprint
    from app.database import get_db_context
    from app.models import Organization
    from sqlalchemy import select
    from datetime import datetime, timezone

    fingerprint = await fingerprint_company(company_name)

    async with get_db_context() as db:
        org = (await db.execute(
            select(Organization).where(Organization.id == org_id)
        )).scalar_one_or_none()

        if org:
            org.fingerprint_data = fingerprint
            org.industry_code = fingerprint.get("industry_code")
            org.industry_label = fingerprint.get("industry_label")
            org.jurisdiction = fingerprint.get("jurisdiction")
            org.regulator = fingerprint.get("regulator")
            org.fingerprinted_at = datetime.now(timezone.utc)

            await db.flush()
            await seed_org_from_fingerprint(org_id, fingerprint, db)


@celery_app.task(name="app.workers.tasks.recompute_coverage")
def recompute_coverage(risk_id: str, org_id: str):
    """Recompute control coverage for a risk after canvas changes."""
    _run_async(_recompute_coverage_async(risk_id, org_id))


async def _recompute_coverage_async(risk_id: str, org_id: str):
    from app.database import get_db_context
    from app.models import Risk, CanvasEdge, CanvasNode, Control, ControlStatus
    from sqlalchemy import select

    async with get_db_context() as db:
        # Find the risk's canvas node
        risk_node = (await db.execute(
            select(CanvasNode).where(
                CanvasNode.risk_id == risk_id,
                CanvasNode.org_id == org_id,
            )
        )).scalar_one_or_none()

        if not risk_node:
            return

        # Find all edges pointing from risk to controls
        edges = (await db.execute(
            select(CanvasEdge).where(CanvasEdge.from_node_id == risk_node.id)
        )).scalars().all()

        if not edges:
            coverage = 0.0
        else:
            control_node_ids = [e.to_node_id for e in edges]
            control_nodes = (await db.execute(
                select(CanvasNode).where(CanvasNode.id.in_(control_node_ids))
            )).scalars().all()

            control_ids = [n.control_id for n in control_nodes if n.control_id]
            controls = (await db.execute(
                select(Control).where(Control.id.in_(control_ids))
            )).scalars().all()

            effective = sum(1 for c in controls if c.status == ControlStatus.effective)
            partial = sum(1 for c in controls if c.status == ControlStatus.partial)
            coverage = min(
                100.0,
                (effective * 100 + partial * 50) / max(len(controls), 1)
            )

        # Update the risk
        risk = (await db.execute(
            select(Risk).where(Risk.id == risk_id)
        )).scalar_one_or_none()
        if risk:
            risk.control_coverage_pct = coverage
