"""
app/models/__init__.py
──────────────────────
SQLAlchemy ORM models — the complete Aegis database schema.

Table overview:
  organizations     — multi-tenant root entity
  users             — team members, scoped to org
  risks             — the risk register
  controls          — the control library
  canvas_nodes      — positioned nodes on the living canvas
  canvas_edges      — typed connections between nodes
  evidence          — files / records linked to controls
  audit_plans       — structured audit engagements
  audit_tasks       — checklist items within a plan
  signals           — incoming radar signals
  control_checks    — continuous pulse monitoring results
  frameworks        — active compliance frameworks per org
"""

import enum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, JSON, UniqueConstraint, Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(AsyncAttrs, DeclarativeBase):
    __allow_unmapped__ = True

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# ── ENUMERATIONS ──────────────────────────────────────────────────────────────

class RiskSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ControlStatus(str, enum.Enum):
    effective = "effective"
    partial = "partial"
    ineffective = "ineffective"
    not_tested = "not_tested"


class ControlType(str, enum.Enum):
    automated = "automated"
    manual = "manual"
    compensating = "compensating"


class NodeType(str, enum.Enum):
    risk = "risk"
    control = "control"
    process = "process"
    evidence = "evidence"


class EdgeType(str, enum.Enum):
    mitigates = "mitigates"
    partially_mitigates = "partially_mitigates"
    evidences = "evidences"
    generates = "generates"          # process generates risk


class AuditStatus(str, enum.Enum):
    planning = "planning"
    fieldwork = "fieldwork"
    reporting = "reporting"
    closed = "closed"


class TaskStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    blocked = "blocked"


class SignalSeverity(str, enum.Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    info = "info"


class SignalCategory(str, enum.Enum):
    regulatory = "regulatory"
    threat = "threat"
    vendor = "vendor"
    macro = "macro"


class PulseStatus(str, enum.Enum):
    passing = "passing"
    failing = "failing"
    degraded = "degraded"
    unknown = "unknown"


class UserRole(str, enum.Enum):
    org_admin = "org_admin"
    head_of_audit = "head_of_audit"
    auditor = "auditor"
    control_owner = "control_owner"


# ── ORGANIZATIONS ─────────────────────────────────────────────────────────────

class Organization(Base):
    """Root multi-tenant entity. All data is scoped to an org."""
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)

    # Fingerprinting results stored as JSONB
    industry_code = Column(String(20))          # SIC / NAICS code
    industry_label = Column(String(255))
    jurisdiction = Column(String(100))          # e.g. "Netherlands"
    regulator = Column(String(100))             # e.g. "DNB / AFM"
    employee_range = Column(String(50))         # e.g. "120-500"
    fingerprint_data = Column(JSONB, default=dict)  # raw fingerprint output

    # Onboarding state
    onboarding_complete = Column(Boolean, default=False)
    fingerprinted_at = Column(DateTime(timezone=True))

    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    risks = relationship("Risk", back_populates="organization", cascade="all, delete-orphan")
    controls = relationship("Control", back_populates="organization", cascade="all, delete-orphan")
    canvas_nodes = relationship("CanvasNode", back_populates="organization", cascade="all, delete-orphan")
    audit_plans = relationship("AuditPlan", back_populates="organization", cascade="all, delete-orphan")
    signals = relationship("Signal", back_populates="organization", cascade="all, delete-orphan")
    frameworks = relationship("Framework", back_populates="organization", cascade="all, delete-orphan")


# ── USERS ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    initials = Column(String(4))                # e.g. "VR"
    avatar_color = Column(String(7), default="#6c63ff")
    role = Column(Enum(UserRole), nullable=False, default=UserRole.auditor)
    hashed_password = Column(String(255))
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_user_org_email"),
    )

    organization = relationship("Organization", back_populates="users")
    owned_controls = relationship("Control", foreign_keys="Control.owner_id", back_populates="owner")
    owned_risks = relationship("Risk", foreign_keys="Risk.owner_id", back_populates="owner")
    assigned_tasks = relationship("AuditTask", back_populates="assignee")


# ── RISKS ────────────────────────────────────────────────────────────────────

class Risk(Base):
    __tablename__ = "risks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(Text)
    domain = Column(String(100))                # e.g. "Financial crime"

    # Ratings
    inherent_severity = Column(Enum(RiskSeverity), nullable=False, default=RiskSeverity.medium)
    residual_severity = Column(Enum(RiskSeverity), nullable=False, default=RiskSeverity.medium)
    likelihood = Column(Integer, default=3)     # 1-5 scale
    impact = Column(Integer, default=3)         # 1-5 scale
    velocity = Column(String(50))               # slow / medium / fast

    # Coverage (computed and cached)
    control_coverage_pct = Column(Float, default=0.0)

    # AI-generated metadata
    ai_assessment = Column(JSONB, default=dict)
    framework_tags = Column(JSONB, default=list)   # e.g. ["AML/AMLD6", "GDPR"]
    ai_seeded = Column(Boolean, default=False)     # true if created by fingerprinting

    # Embedding for semantic search (stored as array via pgvector)
    embedding = Column(JSONB)                       # [float, ...] — swap for Vector(1536) with pgvector

    # Risk Universe linkage
    lob_id = Column(UUID(as_uuid=True), ForeignKey("lines_of_business.id", ondelete="SET NULL"), nullable=True)
    geography_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}")
    product_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}")
    segment_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}")

    __table_args__ = (
        Index("ix_risks_org_severity", "org_id", "inherent_severity"),
        Index("ix_risks_lob_id", "lob_id"),
    )

    organization = relationship("Organization", back_populates="risks")
    owner = relationship("User", foreign_keys=[owner_id], back_populates="owned_risks")
    canvas_node = relationship("CanvasNode", back_populates="risk", uselist=False)
    lob = relationship("LineOfBusiness", foreign_keys=[lob_id], lazy="joined")


# ── CONTROLS ──────────────────────────────────────────────────────────────────

class Control(Base):
    __tablename__ = "controls"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(Text)
    domain = Column(String(100))

    control_type = Column(Enum(ControlType), default=ControlType.manual)
    status = Column(Enum(ControlStatus), default=ControlStatus.not_tested)

    # Testing metadata
    last_tested_at = Column(DateTime(timezone=True))
    test_frequency_days = Column(Integer, default=90)
    next_test_due = Column(DateTime(timezone=True))

    # Integration for continuous monitoring
    integration_source = Column(String(100))    # e.g. "okta", "aws_security_hub"
    integration_config = Column(JSONB, default=dict)

    framework_tags = Column(JSONB, default=list)
    ai_seeded = Column(Boolean, default=False)
    embedding = Column(JSONB)

    __table_args__ = (
        Index("ix_controls_org_status", "org_id", "status"),
    )

    organization = relationship("Organization", back_populates="controls")
    owner = relationship("User", foreign_keys=[owner_id], back_populates="owned_controls")
    evidence = relationship("Evidence", back_populates="control", cascade="all, delete-orphan")
    pulse_checks = relationship("ControlCheck", back_populates="control", cascade="all, delete-orphan")
    canvas_node = relationship("CanvasNode", back_populates="control", uselist=False)


# ── CANVAS NODES ──────────────────────────────────────────────────────────────

class CanvasNode(Base):
    """
    Every node on the living canvas. Stores position alongside
    a reference to the underlying entity (risk, control, etc.).
    """
    __tablename__ = "canvas_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    node_type = Column(Enum(NodeType), nullable=False)

    # Foreign keys to underlying entities (only one is set per node)
    risk_id = Column(UUID(as_uuid=True), ForeignKey("risks.id", ondelete="CASCADE"), nullable=True)
    control_id = Column(UUID(as_uuid=True), ForeignKey("controls.id", ondelete="CASCADE"), nullable=True)

    # Canvas position
    pos_x = Column(Float, nullable=False, default=0.0)
    pos_y = Column(Float, nullable=False, default=0.0)

    # For process / evidence nodes (no separate table — stored inline)
    label = Column(String(255))
    node_metadata = Column(JSONB, default=dict)

    # AI flags
    is_orphan = Column(Boolean, default=False)      # no connected edges
    ai_gap_flag = Column(String(255))               # AI-detected issue description

    organization = relationship("Organization", back_populates="canvas_nodes")
    risk = relationship("Risk", back_populates="canvas_node")
    control = relationship("Control", back_populates="canvas_node")
    outgoing_edges = relationship("CanvasEdge", foreign_keys="CanvasEdge.from_node_id",
                                  back_populates="from_node", cascade="all, delete-orphan")
    incoming_edges = relationship("CanvasEdge", foreign_keys="CanvasEdge.to_node_id",
                                  back_populates="to_node", cascade="all, delete-orphan")


class CanvasEdge(Base):
    """Typed connection between two canvas nodes."""
    __tablename__ = "canvas_edges"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    from_node_id = Column(UUID(as_uuid=True), ForeignKey("canvas_nodes.id", ondelete="CASCADE"), nullable=False)
    to_node_id = Column(UUID(as_uuid=True), ForeignKey("canvas_nodes.id", ondelete="CASCADE"), nullable=False)
    edge_type = Column(Enum(EdgeType), nullable=False, default=EdgeType.mitigates)

    __table_args__ = (
        UniqueConstraint("from_node_id", "to_node_id", "edge_type", name="uq_canvas_edge"),
    )

    from_node = relationship("CanvasNode", foreign_keys=[from_node_id], back_populates="outgoing_edges")
    to_node = relationship("CanvasNode", foreign_keys=[to_node_id], back_populates="incoming_edges")


# ── EVIDENCE ──────────────────────────────────────────────────────────────────

class Evidence(Base):
    """Files and records that evidence a control is operating."""
    __tablename__ = "evidence"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    control_id = Column(UUID(as_uuid=True), ForeignKey("controls.id", ondelete="CASCADE"), nullable=False, index=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(Text)
    file_key = Column(String(500))              # S3 object key
    file_size_bytes = Column(Integer)
    mime_type = Column(String(100))
    period_start = Column(DateTime(timezone=True))
    period_end = Column(DateTime(timezone=True))
    age_days = Column(Integer)                  # computed on read

    control = relationship("Control", back_populates="evidence")


# ── AUDIT PLANS ───────────────────────────────────────────────────────────────

class AuditPlan(Base):
    __tablename__ = "audit_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    name = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(Enum(AuditStatus), default=AuditStatus.planning)

    planned_start = Column(DateTime(timezone=True))
    planned_end = Column(DateTime(timezone=True))
    actual_start = Column(DateTime(timezone=True))
    actual_end = Column(DateTime(timezone=True))

    # AI-generated planning data
    ai_plan_data = Column(JSONB, default=dict)   # sampling guidance, interview guide etc.
    scope_risk_ids = Column(JSONB, default=list) # list of risk UUIDs in scope

    # Progress (cached)
    task_count = Column(Integer, default=0)
    done_count = Column(Integer, default=0)
    progress_pct = Column(Float, default=0.0)

    organization = relationship("Organization", back_populates="audit_plans")
    tasks = relationship("AuditTask", back_populates="plan", cascade="all, delete-orphan",
                         order_by="AuditTask.sort_order")


class AuditTask(Base):
    __tablename__ = "audit_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    plan_id = Column(UUID(as_uuid=True), ForeignKey("audit_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    phase = Column(Integer, nullable=False, default=1)   # 1=Planning, 2=Fieldwork, 3=Reporting
    phase_label = Column(String(100))
    label = Column(String(500), nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.pending)
    sort_order = Column(Integer, default=0)
    is_priority = Column(Boolean, default=False)

    due_date = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    plan = relationship("AuditPlan", back_populates="tasks")
    assignee = relationship("User", back_populates="assigned_tasks")


# ── SIGNALS (RADAR) ───────────────────────────────────────────────────────────

class Signal(Base):
    """An incoming risk signal from any external feed."""
    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    source = Column(String(100), nullable=False)   # e.g. "DNB", "NVD", "MITRE"
    category = Column(Enum(SignalCategory), nullable=False)
    severity = Column(Enum(SignalSeverity), nullable=False)

    title = Column(String(500), nullable=False)
    body = Column(Text)
    external_url = Column(String(1000))
    external_id = Column(String(255))              # source's own ID for deduplication

    tags = Column(JSONB, default=list)
    published_at = Column(DateTime(timezone=True))

    # Relevance scoring (0.0 – 1.0)
    relevance_score = Column(Float, default=0.0)
    is_surfaced = Column(Boolean, default=False)   # above relevance threshold

    # Impact mapping (AI-generated)
    impacted_control_ids = Column(JSONB, default=list)
    impacted_risk_ids = Column(JSONB, default=list)
    ai_recommendation = Column(Text)

    is_new = Column(Boolean, default=True)
    dismissed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("org_id", "source", "external_id", name="uq_signal_source_external"),
        Index("ix_signals_org_surfaced", "org_id", "is_surfaced", "severity"),
    )

    organization = relationship("Organization", back_populates="signals")


# ── CONTROL CHECKS (PULSE) ────────────────────────────────────────────────────

class ControlCheck(Base):
    """
    One data point in the continuous control pulse.
    Written by background workers every N hours per control.
    """
    __tablename__ = "control_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    control_id = Column(UUID(as_uuid=True), ForeignKey("controls.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(Enum(PulseStatus), nullable=False)
    metrics = Column(JSONB, default=dict)          # e.g. {"completion_pct": 34, "overdue_count": 127}
    raw_response = Column(JSONB)                   # full API response for debugging
    checked_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_control_checks_control_time", "control_id", "checked_at"),
    )

    control = relationship("Control", back_populates="pulse_checks")


# ── FRAMEWORKS ────────────────────────────────────────────────────────────────

class Framework(Base):
    """Active compliance frameworks for an org, with coverage percentage."""
    __tablename__ = "frameworks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    code = Column(String(50), nullable=False)    # e.g. "GDPR", "ISO_27001"
    label = Column(String(255), nullable=False)
    category = Column(String(100))               # e.g. "Data protection"
    coverage_pct = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    ai_seeded = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("org_id", "code", name="uq_framework_org_code"),
    )

    organization = relationship("Organization", back_populates="frameworks")


# ── GRC TIME MACHINE ──────────────────────────────────────────────────────────

class GRCEventType(str, enum.Enum):
    risk_created       = "risk_created"
    risk_updated       = "risk_updated"
    risk_deleted       = "risk_deleted"
    control_created    = "control_created"
    control_updated    = "control_updated"
    control_deleted    = "control_deleted"
    control_tested     = "control_tested"
    framework_added    = "framework_added"
    audit_opened       = "audit_opened"
    audit_closed       = "audit_closed"
    signal_critical    = "signal_critical"
    coverage_changed   = "coverage_changed"
    certification      = "certification"
    regulatory_inquiry = "regulatory_inquiry"
    milestone          = "milestone"


class GRCEventSentiment(str, enum.Enum):
    positive = "positive"   # improvement
    negative = "negative"   # adverse event
    neutral  = "neutral"    # informational


class GRCEvent(Base):
    """
    Immutable event log — every material GRC change is written here.
    This is the source of truth for the time machine history view.
    """
    __tablename__ = "grc_events"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                    nullable=False, index=True)

    event_type  = Column(Enum(GRCEventType), nullable=False)
    sentiment   = Column(Enum(GRCEventSentiment), nullable=False, default=GRCEventSentiment.neutral)

    entity_type = Column(String(50))   # "risk" | "control" | "framework" | "audit"
    entity_id   = Column(UUID(as_uuid=True), nullable=True)
    entity_name = Column(String(255))  # snapshot of name at time of event

    title       = Column(String(500), nullable=False)
    description = Column(Text)

    before_state = Column(JSONB)       # snapshot of entity before change
    after_state  = Column(JSONB)       # snapshot of entity after change
    delta        = Column(JSONB)       # computed diff {field: {from, to}}

    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_grc_events_org_time", "org_id", "occurred_at"),
    )


class TimeMachineSnapshot(Base):
    """
    Monthly aggregate snapshot — pre-computed for fast scrubber queries.
    One row per org per calendar month.
    """
    __tablename__ = "time_machine_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                    nullable=False, index=True)

    snapshot_month = Column(String(7), nullable=False)  # "YYYY-MM"

    # Aggregated metrics at end of month
    total_risks          = Column(Integer, default=0)
    critical_risks       = Column(Integer, default=0)
    high_risks           = Column(Integer, default=0)
    total_controls       = Column(Integer, default=0)
    effective_controls   = Column(Integer, default=0)
    coverage_pct         = Column(Float, default=0.0)
    frameworks_active    = Column(Integer, default=0)
    open_audit_plans     = Column(Integer, default=0)

    # Month-over-month deltas (vs prior snapshot)
    delta_risks        = Column(Integer, default=0)
    delta_coverage_pct = Column(Float, default=0.0)
    delta_controls     = Column(Integer, default=0)

    # Notable events this month (for AI banner)
    notable_events = Column(JSONB, default=list)  # [{type, title, sentiment}]

    # Diff vs prior month
    risk_diff    = Column(JSONB, default=dict)    # {added:[...], removed:[...], changed:[...]}
    control_diff = Column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("org_id", "snapshot_month", name="uq_snapshot_org_month"),
    )


class SimulationRun(Base):
    """Stores each scenario simulation run for audit trail and replay."""
    __tablename__ = "simulation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                    nullable=False, index=True)

    scenario_key   = Column(String(100), nullable=False)  # e.g. "data_breach"
    scenario_label = Column(String(255))

    # Input parameters
    parameters = Column(JSONB, nullable=False)  # {affected_records, control_effectiveness, ...}

    # Computed outputs
    residual_risk_score     = Column(Float)        # 0.0 – 100.0
    controls_failing_count  = Column(Integer)
    regulatory_exposure_usd = Column(Float)
    domain_exposure         = Column(JSONB)        # [{domain, exposure_pct}]
    ai_recommendation       = Column(Text)
    findings                = Column(JSONB)        # [{severity, title, description}]

    run_at = Column(DateTime(timezone=True), server_default=func.now())


# ── REGULATORY CHANGE AGENT ───────────────────────────────────────────────────

class RegChangeSeverity(str, enum.Enum):
    critical = "critical"
    high     = "high"
    medium   = "medium"
    low      = "low"


class RegChangePipelineStage(str, enum.Enum):
    ingested   = "ingested"
    filtered   = "filtered"
    mapped     = "mapped"
    assessed   = "assessed"
    actioned   = "actioned"


class RegChangeTaskStatus(str, enum.Enum):
    pending     = "pending"
    in_progress = "in_progress"
    done        = "done"


class RegulatoryChange(Base):
    """
    A single detected regulatory change event — the unit of work for the
    regulatory change agent. One row per change across all feed sources.
    """
    __tablename__ = "regulatory_changes"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                    nullable=False, index=True)

    # Source metadata
    source         = Column(String(50), nullable=False)   # "EBA", "DNB", "AP", "EC", "ISO"
    source_url     = Column(String(1000))
    regulation_family = Column(String(100))               # "DORA", "GDPR", "AML/AMLD6", "PSD3"
    jurisdiction   = Column(String(100))                  # "EU", "NL", "Global"

    # Content
    title          = Column(String(500), nullable=False)
    summary        = Column(Text)
    full_text      = Column(Text)

    # Classification
    severity       = Column(Enum(RegChangeSeverity), nullable=False, default=RegChangeSeverity.medium)
    relevance_score = Column(Float, default=0.0)          # 0.0 – 1.0
    pipeline_stage = Column(Enum(RegChangePipelineStage), default=RegChangePipelineStage.ingested)

    # Deadline
    deadline_at    = Column(DateTime(timezone=True))
    deadline_label = Column(String(100))                  # "60 days", "Jan 2027"

    # AI-generated content (set after assessed stage)
    impact_assessment = Column(Text)                      # Plain-English AI assessment
    matched_controls  = Column(JSONB, default=list)       # [{control_name, gap_type, severity}]
    tags              = Column(JSONB, default=list)        # ["DORA", "ICT", "third-party"]

    # Status
    is_new         = Column(Boolean, default=True)
    is_dismissed   = Column(Boolean, default=False)
    published_at   = Column(DateTime(timezone=True), server_default=func.now())

    # External dedup
    external_id    = Column(String(255))

    __table_args__ = (
        Index("ix_reg_changes_org_stage", "org_id", "pipeline_stage", "severity"),
        UniqueConstraint("org_id", "external_id", name="uq_reg_change_external"),
    )

    tasks = relationship("RegChangeTask", back_populates="change",
                         cascade="all, delete-orphan", order_by="RegChangeTask.sort_order")


class RegChangeTask(Base):
    """Phased action plan task for a regulatory change."""
    __tablename__ = "reg_change_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    change_id = Column(UUID(as_uuid=True), ForeignKey("regulatory_changes.id", ondelete="CASCADE"),
                       nullable=False, index=True)

    phase        = Column(Integer, nullable=False, default=1)
    phase_label  = Column(String(100))                    # "Urgent response", "Implementation", "Evidence"
    label        = Column(String(500), nullable=False)
    role         = Column(String(50))                     # "MLRO", "Legal", "IT", "Compliance", "Audit"
    status       = Column(Enum(RegChangeTaskStatus), default=RegChangeTaskStatus.pending)
    is_priority  = Column(Boolean, default=False)
    sort_order   = Column(Integer, default=0)
    due_week     = Column(Integer)                        # week number within deadline window

    change = relationship("RegulatoryChange", back_populates="tasks")


# ── AUDIT REPORT GENERATOR ────────────────────────────────────────────────────

class AuditReportStatus(str, enum.Enum):
    assembling = "assembling"   # 4-stage Claude pipeline running
    draft      = "draft"        # AI assembly complete, editable
    review     = "review"       # submitted for management review
    published  = "published"    # finalised and distributed


class AuditReport(Base):
    """
    AI-generated audit report. Associated with an org (and optionally a plan).
    Created by the 4-stage Claude assembly pipeline.
    """
    __tablename__ = "audit_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id  = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("audit_plans.id", ondelete="SET NULL"),
                     nullable=True)

    title           = Column(String(500), nullable=False)
    status          = Column(Enum(AuditReportStatus), default=AuditReportStatus.assembling)
    overall_rating  = Column(String(50))          # "Satisfactory" | "Needs Improvement" | "Unsatisfactory"
    rating_score    = Column(Float, default=0.0)  # 0-100

    # Period covered
    period_start    = Column(String(20))          # "Q1 2025"
    period_end      = Column(String(20))

    # 4-stage AI output stored as JSONB
    exec_summary    = Column(JSONB, default=dict)   # {headline, body, key_metrics:[...], period}
    findings        = Column(JSONB, default=list)   # [{id,title,severity,criteria,condition,cause,effect,observation}]
    recommendations = Column(JSONB, default=list)   # [{finding_id,text,priority,target_date_label}]
    doc_structure   = Column(JSONB, default=dict)   # {scope_statement, methodology, appendix_a, appendix_b}

    # Assembly metadata
    assembly_log    = Column(JSONB, default=list)   # [{stage, status, duration_ms}]
    assembled_at    = Column(DateTime(timezone=True))
    published_at    = Column(DateTime(timezone=True))

    # Distribution
    distribution    = Column(JSONB, default=dict)   # {audit_committee, board, control_owners, regulator}

    # Relationships
    finding_responses = relationship("FindingResponse", back_populates="report",
                                     cascade="all, delete-orphan",
                                     order_by="FindingResponse.finding_index")
    comments = relationship("ReportComment", back_populates="report",
                            cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_audit_reports_org_status", "org_id", "status"),
    )


class FindingResponse(Base):
    """Management response to an individual audit finding."""
    __tablename__ = "finding_responses"

    id            = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    report_id     = Column(UUID(as_uuid=True), ForeignKey("audit_reports.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    finding_index = Column(Integer, nullable=False)  # index into report.findings array

    response_text   = Column(Text, nullable=False)
    responder_name  = Column(String(255))
    responder_role  = Column(String(100))
    target_date     = Column(String(100))   # free-text target e.g. "Q3 2025"
    agreed          = Column(Boolean, default=True)

    report = relationship("AuditReport", back_populates="finding_responses")

    __table_args__ = (
        UniqueConstraint("report_id", "finding_index", name="uq_finding_response"),
    )


class ReportComment(Base):
    """Inline comment on any section of an audit report."""
    __tablename__ = "report_comments"

    id          = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    report_id   = Column(UUID(as_uuid=True), ForeignKey("audit_reports.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    section     = Column(String(100), nullable=False)  # "exec_summary" | "finding_0" | "appendix_a"
    comment_text = Column(Text, nullable=False)
    author_name = Column(String(255))
    resolved    = Column(Boolean, default=False)

    report = relationship("AuditReport", back_populates="comments")


# ── AI CO-AUDITOR ─────────────────────────────────────────────────────────────

class EngagementStatus(str, enum.Enum):
    active   = "active"
    complete = "complete"
    archived = "archived"


class WorkPaperStatus(str, enum.Enum):
    draft     = "draft"
    in_review = "in_review"
    approved  = "approved"


class WPSectionStatus(str, enum.Enum):
    empty       = "empty"
    ai_drafting = "ai_drafting"
    drafted     = "drafted"
    approved    = "approved"


class AnomalySeverity(str, enum.Enum):
    high   = "high"
    medium = "medium"
    low    = "low"


class CopilotMode(str, enum.Enum):
    anomaly_review  = "anomaly_review"
    draft_workpaper = "draft_workpaper"
    interview_prep  = "interview_prep"
    free_query      = "free_query"


class AuditEngagement(Base):
    """Top-level AI co-auditor engagement. Scoped to one audit project."""
    __tablename__ = "audit_engagements"

    id      = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id  = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    name         = Column(String(255), nullable=False)  # "Meridian Group · FY2024 Revenue Audit"
    phase        = Column(String(100))                  # "Phase 2"
    client_name  = Column(String(255))
    period       = Column(String(50))                   # "FY2024"
    status       = Column(Enum(EngagementStatus), default=EngagementStatus.active)

    work_papers  = relationship("CopilotWorkPaper", back_populates="engagement",
                                cascade="all, delete-orphan", order_by="CopilotWorkPaper.sort_order")
    anomalies    = relationship("EngagementAnomaly",   back_populates="engagement",
                                cascade="all, delete-orphan")


class CopilotWorkPaper(Base):
    """Structured work paper with AI-fillable sections."""
    __tablename__ = "copilot_work_papers"

    id            = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    engagement_id = Column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)

    code       = Column(String(20), nullable=False)    # "WP-REV-04"
    title      = Column(String(255), nullable=False)
    area       = Column(String(100))                   # "Revenue", "Controls", "AML"
    status     = Column(Enum(WorkPaperStatus), default=WorkPaperStatus.draft)
    sort_order = Column(Integer, default=0)
    is_active  = Column(Boolean, default=False)        # currently open in editor

    engagement = relationship("AuditEngagement", back_populates="work_papers")
    sections   = relationship("WPSection", back_populates="work_paper",
                              cascade="all, delete-orphan", order_by="WPSection.sort_order")
    questions  = relationship("InterviewQuestion", back_populates="work_paper",
                              cascade="all, delete-orphan")


class WPSection(Base):
    """One section of a work paper — AI drafts content via co-auditor chat."""
    __tablename__ = "wp_sections"

    id             = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    work_paper_id  = Column(UUID(as_uuid=True), ForeignKey("copilot_work_papers.id", ondelete="CASCADE"), nullable=False, index=True)

    title      = Column(String(255), nullable=False)
    content    = Column(Text)
    status     = Column(Enum(WPSectionStatus), default=WPSectionStatus.empty)
    sort_order = Column(Integer, default=0)

    work_paper = relationship("CopilotWorkPaper", back_populates="sections")


class EngagementAnomaly(Base):
    """A statistical or pattern anomaly detected in uploaded engagement data."""
    __tablename__ = "engagement_anomalies"

    id            = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    engagement_id = Column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)

    title        = Column(String(500), nullable=False)
    description  = Column(Text)
    severity     = Column(Enum(AnomalySeverity), nullable=False, default=AnomalySeverity.medium)
    amount_label = Column(String(100))      # "$2.1M"
    account_ref  = Column(String(100))
    period       = Column(String(50))       # "Q3-Q4 FY2024"
    assertion    = Column(String(50))       # "cutoff", "occurrence", "completeness", "authorization"
    is_addressed = Column(Boolean, default=False)
    wp_section_id = Column(UUID(as_uuid=True), ForeignKey("wp_sections.id", ondelete="SET NULL"), nullable=True)

    engagement = relationship("AuditEngagement", back_populates="anomalies")

    __table_args__ = (
        Index("ix_anomalies_engagement_sev", "engagement_id", "severity"),
    )


class InterviewQuestion(Base):
    """Risk-mapped interview question for a specific audittee role."""
    __tablename__ = "interview_questions"

    id            = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    engagement_id = Column(UUID(as_uuid=True), ForeignKey("audit_engagements.id", ondelete="CASCADE"), nullable=False, index=True)
    work_paper_id = Column(UUID(as_uuid=True), ForeignKey("copilot_work_papers.id", ondelete="SET NULL"), nullable=True)

    question    = Column(Text, nullable=False)
    risk_level  = Column(String(10), default="medium")  # "high" | "medium" | "low"
    assertion   = Column(String(50))                     # "cutoff" | "completeness" | "authorization" | "occurrence"
    target_role = Column(String(100))                    # "Controller" | "CFO" | "IT Manager"
    sort_order  = Column(Integer, default=0)

    work_paper = relationship("CopilotWorkPaper", back_populates="questions")


# ── COMPANY PROFILE ───────────────────────────────────────────────────────────

class OrgProfile(Base):
    """Canonical company identity — one per org."""
    __tablename__ = "org_profiles"

    id                   = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id               = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True)
    legal_name           = Column(String(255), nullable=False)
    trading_name         = Column(String(255))
    year_founded         = Column(Integer)
    employee_range       = Column(String(50))
    annual_revenue_range = Column(String(50))
    hq_country           = Column(String(2))
    hq_city              = Column(String(100))
    stock_ticker         = Column(String(20))
    website              = Column(String(500))
    description          = Column(String(500))
    logo_url             = Column(String(500))
    updated_by           = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (Index("ix_org_profiles_org_id", "org_id"),)


class LineOfBusiness(Base):
    __tablename__ = "lines_of_business"

    id                       = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id                   = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name                     = Column(String(255), nullable=False)
    description              = Column(Text)
    status                   = Column(String(20), nullable=False, default="active")
    launch_date              = Column(String(10))
    revenue_contribution_pct = Column(Integer)
    is_primary               = Column(Boolean, default=False)

    __table_args__ = (Index("ix_lob_org_id", "org_id"),)


class OrgGeography(Base):
    __tablename__ = "org_geographies"

    id               = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id           = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    country          = Column(String(2), nullable=False)
    region           = Column(String(50))
    state_province   = Column(String(100))
    presence_type    = Column(String(30), nullable=False, default="operational")
    lob_ids          = Column(JSON, default=list)
    regulatory_flags = Column(JSON, default=list)

    __table_args__ = (Index("ix_geo_org_id", "org_id"),)


class OrgIndustry(Base):
    __tablename__ = "org_industries"

    id             = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id         = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    code           = Column(String(20), nullable=False)
    name           = Column(String(255), nullable=False)
    classification = Column(String(20), nullable=False, default="secondary")
    lob_ids        = Column(JSON, default=list)

    __table_args__ = (Index("ix_industry_org_id", "org_id"),)


class OrgProduct(Base):
    __tablename__ = "org_products"

    id                   = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id               = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name                 = Column(String(255), nullable=False)
    description          = Column(Text)
    product_type         = Column(String(30), nullable=False, default="product")
    lob_id               = Column(UUID(as_uuid=True))
    geography_ids        = Column(JSON, default=list)
    customer_segment_ids = Column(JSON, default=list)
    status               = Column(String(20), nullable=False, default="live")
    launch_date          = Column(String(10))
    data_sensitivity     = Column(String(20), nullable=False, default="low")

    __table_args__ = (Index("ix_products_org_id", "org_id"),)


class CustomerSegment(Base):
    __tablename__ = "org_customer_segments"

    id                  = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id              = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name                = Column(String(255), nullable=False)
    segment_type        = Column(String(20), nullable=False, default="b2b")
    includes_minors     = Column(Boolean, default=False)
    includes_healthcare = Column(Boolean, default=False)
    includes_financial  = Column(Boolean, default=False)
    geography_ids       = Column(JSON, default=list)
    lob_ids             = Column(JSON, default=list)
    estimated_size      = Column(String(100))

    __table_args__ = (Index("ix_segments_org_id", "org_id"),)


class ThirdPartyDependency(Base):
    __tablename__ = "org_third_parties"

    id                = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id            = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name              = Column(String(255), nullable=False)
    category          = Column(String(40), nullable=False, default="saas_vendor")
    tier              = Column(String(10), nullable=False, default="tier_2")
    geography_ids     = Column(JSON, default=list)
    sub_processors    = Column(JSON, default=list)
    last_assessed     = Column(String(10))
    assessment_status = Column(String(20), nullable=False, default="not_assessed")

    __table_args__ = (Index("ix_third_parties_org_id", "org_id"),)


class DataTechProfile(Base):
    __tablename__ = "org_data_tech_profiles"

    id                              = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id                          = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True)
    uses_ai_ml                      = Column(Boolean, default=False)
    ai_use_cases                    = Column(JSON, default=list)
    cloud_providers                 = Column(JSON, default=list)
    data_residency_requirements     = Column(JSON, default=list)
    handles_personal_data           = Column(Boolean, default=False)
    handles_sensitive_personal_data = Column(Boolean, default=False)
    handles_payment_data            = Column(Boolean, default=False)
    handles_health_data             = Column(Boolean, default=False)
    handles_classified_data         = Column(Boolean, default=False)
    core_tech_stack                 = Column(JSON, default=list)

    __table_args__ = (Index("ix_data_tech_org_id", "org_id"),)


class ProfileChangeLog(Base):
    __tablename__ = "profile_change_logs"

    id                 = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    org_id             = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    changed_by         = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    changed_at         = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    entity_type        = Column(String(50), nullable=False)
    entity_id          = Column(UUID(as_uuid=True))
    field_changed      = Column(String(100))
    old_value          = Column(JSON)
    new_value          = Column(JSON)
    change_summary     = Column(Text)
    propagation_status = Column(String(20), default="pending")
    affected_modules   = Column(JSON, default=list)
    propagation_result = Column(JSON, default=dict)

    __table_args__ = (
        Index("ix_change_log_org_id", "org_id"),
        Index("ix_change_log_changed_at", "org_id", "changed_at"),
    )
