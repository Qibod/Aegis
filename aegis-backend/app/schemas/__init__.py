"""
app/schemas/__init__.py
───────────────────────
Pydantic v2 schemas for all API request/response bodies.
Separate from ORM models — keeps API contracts explicit.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, computed_field


# ── Base ──────────────────────────────────────────────────────────────────────

class AegisBase(BaseModel):
    model_config = {"from_attributes": True}


# ── AUTH ──────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int                    # seconds


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ── ORGANIZATIONS ─────────────────────────────────────────────────────────────

class OrgCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)


class OrgFingerprintRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=255)


class OrgFingerprintResponse(BaseModel):
    """Returned by the AI fingerprinting pipeline."""
    company_name: str
    industry_code: str | None
    industry_label: str | None
    jurisdiction: str | None
    regulator: str | None
    employee_range: str | None
    detected_processes: list[str]
    detected_regulations: list[str]
    risk_domains: list[dict[str, Any]]   # [{name, risk_count, severity}]
    suggested_frameworks: list[str]
    confidence_score: float              # 0.0 – 1.0
    risks: list[dict[str, Any]] = []     # [{name, domain, severity, description, likelihood, impact, framework_tags}]
    controls: list[dict[str, Any]] = []  # [{name, domain, type, description, framework_tags}]
    business_lines: list[str] = []
    business_summary: str = ""


class OrgResponse(AegisBase):
    id: UUID
    name: str
    slug: str
    industry_label: str | None
    jurisdiction: str | None
    regulator: str | None
    onboarding_complete: bool
    created_at: datetime


class OrgProfileResponse(AegisBase):
    id: UUID
    name: str
    slug: str
    industry_label: str | None
    jurisdiction: str | None
    regulator: str | None
    onboarding_complete: bool
    created_at: datetime
    fingerprint_data: dict[str, Any] = {}


class OrgCompleteOnboarding(BaseModel):
    """Final onboarding step — user confirms fingerprint and selects frameworks."""
    fingerprint_data: dict[str, Any]
    selected_frameworks: list[str]       # e.g. ["GDPR", "AML_AMLD6", "ISO_27001"]
    risk_domains: list[str]              # domains to seed risks from


# ── USERS ─────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=255)
    password: str = Field(..., min_length=8)
    role: str = "auditor"


class UserResponse(AegisBase):
    id: UUID
    email: str
    full_name: str
    initials: str | None
    avatar_color: str
    role: str
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = None
    avatar_color: str | None = None
    role: str | None = None


# ── RISKS ────────────────────────────────────────────────────────────────────

class RiskCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    domain: str | None = None
    inherent_severity: str = "medium"
    likelihood: int = Field(3, ge=1, le=5)
    impact: int = Field(3, ge=1, le=5)
    framework_tags: list[str] = []
    owner_id: UUID | None = None


class RiskUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    domain: str | None = None
    inherent_severity: str | None = None
    residual_severity: str | None = None
    likelihood: int | None = Field(None, ge=1, le=5)
    impact: int | None = Field(None, ge=1, le=5)
    framework_tags: list[str] | None = None
    owner_id: UUID | None = None


class RiskResponse(AegisBase):
    id: UUID
    org_id: UUID
    name: str
    description: str | None
    domain: str | None
    inherent_severity: str
    residual_severity: str
    likelihood: int
    impact: int
    control_coverage_pct: float
    framework_tags: list[str]
    ai_assessment: dict[str, Any]
    ai_seeded: bool
    owner: UserResponse | None
    created_at: datetime
    updated_at: datetime


class RiskListResponse(BaseModel):
    items: list[RiskResponse]
    total: int
    page: int
    page_size: int


# ── CONTROLS ──────────────────────────────────────────────────────────────────

class ControlCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    domain: str | None = None
    control_type: str = "manual"
    framework_tags: list[str] = []
    owner_id: UUID | None = None
    integration_source: str | None = None
    integration_config: dict[str, Any] = {}


class ControlUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    control_type: str | None = None
    framework_tags: list[str] | None = None
    owner_id: UUID | None = None
    last_tested_at: datetime | None = None
    test_frequency_days: int | None = None


class ControlResponse(AegisBase):
    id: UUID
    org_id: UUID
    name: str
    description: str | None
    domain: str | None
    control_type: str
    status: str
    last_tested_at: datetime | None
    next_test_due: datetime | None
    framework_tags: list[str]
    integration_source: str | None
    ai_seeded: bool
    owner: UserResponse | None
    created_at: datetime
    updated_at: datetime


# ── CANVAS ────────────────────────────────────────────────────────────────────

class CanvasNodeCreate(BaseModel):
    node_type: str
    pos_x: float = 0.0
    pos_y: float = 0.0
    risk_id: UUID | None = None
    control_id: UUID | None = None
    label: str | None = None
    node_metadata: dict[str, Any] = {}


class CanvasNodeUpdate(BaseModel):
    pos_x: float | None = None
    pos_y: float | None = None
    label: str | None = None
    node_metadata: dict[str, Any] | None = None


class CanvasNodeResponse(AegisBase):
    id: UUID
    org_id: UUID
    node_type: str
    pos_x: float
    pos_y: float
    risk_id: UUID | None
    control_id: UUID | None
    label: str | None
    node_metadata: dict[str, Any]
    is_orphan: bool
    ai_gap_flag: str | None
    risk: RiskResponse | None = None
    control: ControlResponse | None = None


class CanvasEdgeCreate(BaseModel):
    from_node_id: UUID
    to_node_id: UUID
    edge_type: str = "mitigates"


class CanvasEdgeResponse(AegisBase):
    id: UUID
    from_node_id: UUID
    to_node_id: UUID
    edge_type: str
    created_at: datetime


class CanvasResponse(BaseModel):
    """Full canvas state — nodes + edges."""
    nodes: list[CanvasNodeResponse]
    edges: list[CanvasEdgeResponse]


# ── EVIDENCE ──────────────────────────────────────────────────────────────────

class EvidenceCreate(BaseModel):
    control_id: UUID
    name: str
    description: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None


class EvidenceResponse(AegisBase):
    id: UUID
    control_id: UUID
    name: str
    description: str | None
    file_key: str | None
    file_size_bytes: int | None
    mime_type: str | None
    period_start: datetime | None
    period_end: datetime | None
    age_days: int | None
    created_at: datetime


# ── AUDIT PLANS ───────────────────────────────────────────────────────────────

class AuditPlanCreate(BaseModel):
    name: str
    description: str | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    scope_risk_ids: list[UUID] = []


class AuditTaskCreate(BaseModel):
    plan_id: UUID
    phase: int = Field(1, ge=1, le=3)
    phase_label: str | None = None
    label: str
    assignee_id: UUID | None = None
    due_date: datetime | None = None
    is_priority: bool = False
    sort_order: int = 0


class AuditTaskUpdate(BaseModel):
    status: str | None = None
    assignee_id: UUID | None = None
    due_date: datetime | None = None
    label: str | None = None


class AuditTaskResponse(AegisBase):
    id: UUID
    plan_id: UUID
    phase: int
    phase_label: str | None
    label: str
    status: str
    is_priority: bool
    sort_order: int
    due_date: datetime | None
    completed_at: datetime | None
    assignee: UserResponse | None


class AuditPlanResponse(AegisBase):
    id: UUID
    org_id: UUID
    name: str
    description: str | None
    status: str
    planned_start: datetime | None
    planned_end: datetime | None
    task_count: int
    done_count: int
    progress_pct: float
    tasks: list[AuditTaskResponse] = []
    created_at: datetime


# ── SIGNALS (RADAR) ───────────────────────────────────────────────────────────

class SignalResponse(AegisBase):
    id: UUID
    source: str
    category: str
    severity: str
    title: str
    body: str | None
    external_url: str | None
    tags: list[str]
    published_at: datetime | None
    relevance_score: float
    impacted_control_ids: list[str]
    impacted_risk_ids: list[str]
    ai_recommendation: str | None
    is_new: bool
    created_at: datetime


class SignalListResponse(BaseModel):
    items: list[SignalResponse]
    total: int
    counts: dict[str, int]    # {"critical": 3, "high": 5, "medium": 2, "info": 1, "new_today": 3}


# ── CONTROL PULSE ─────────────────────────────────────────────────────────────

class PulseControlResponse(BaseModel):
    control_id: UUID
    control_name: str
    integration_source: str | None
    current_status: str
    current_metrics: dict[str, Any]
    trend: list[dict[str, Any]]          # last 30 checks [{checked_at, status, metrics}]
    ai_alert: str | None                 # set when status is failing/degraded


class PulseSummaryResponse(BaseModel):
    passing_count: int
    failing_count: int
    degraded_count: int
    total_monitored: int
    controls: list[PulseControlResponse]


# ── AI COPILOT ────────────────────────────────────────────────────────────────

class CopilotRequest(BaseModel):
    message: str
    context_risk_id: UUID | None = None
    context_control_id: UUID | None = None
    context_plan_id: UUID | None = None
    conversation_history: list[dict[str, str]] = []


class CopilotResponse(BaseModel):
    response: str
    suggested_actions: list[dict[str, str]] = []  # [{label, action_type, payload}]
    referenced_risks: list[UUID] = []
    referenced_controls: list[UUID] = []


# ── DASHBOARD ─────────────────────────────────────────────────────────────────

class DashboardResponse(BaseModel):
    org: OrgResponse
    metrics: dict[str, Any]
    ai_insights: list[dict[str, str]]
    top_risks: list[RiskResponse]
    framework_coverage: list[dict[str, Any]]
    recent_signals: list[SignalResponse]
