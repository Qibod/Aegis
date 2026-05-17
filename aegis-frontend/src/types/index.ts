// ── Auth ─────────────────────────────────────────────────────────────────────
export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  full_name: string
  password: string
  role: string
}

// ── Users ────────────────────────────────────────────────────────────────────
export interface User {
  id: string
  email: string
  full_name: string
  initials: string | null
  avatar_color: string
  role: string
  is_active: boolean
  created_at: string
}

// ── Organizations ─────────────────────────────────────────────────────────────
export interface Organization {
  id: string
  name: string
  slug: string
  industry_label: string | null
  jurisdiction: string | null
  regulator: string | null
  onboarding_complete: boolean
  created_at: string
}

export interface FingerprintRisk {
  name: string
  domain: string
  severity: string
  description: string
  likelihood: number
  impact: number
  framework_tags: string[]
}

export interface FingerprintControl {
  name: string
  domain: string
  type: string
  description: string
  framework_tags: string[]
}

export interface FingerprintResponse {
  company_name: string
  industry_code: string | null
  industry_label: string | null
  jurisdiction: string | null
  regulator: string | null
  employee_range: string | null
  detected_processes: string[]
  detected_regulations: string[]
  risk_domains: Array<{ name: string; risk_count: number; severity: string }>
  suggested_frameworks: string[]
  confidence_score: number
  risks: FingerprintRisk[]
  controls: FingerprintControl[]
  business_lines: string[]
  business_summary: string
}

// ── Risks ─────────────────────────────────────────────────────────────────────
export type RiskSeverity = 'low' | 'medium' | 'high' | 'critical'

export interface Risk {
  id: string
  org_id: string
  name: string
  description: string | null
  domain: string | null
  inherent_severity: RiskSeverity
  residual_severity: RiskSeverity
  likelihood: number
  impact: number
  control_coverage_pct: number
  framework_tags: string[]
  ai_assessment: Record<string, unknown>
  ai_seeded: boolean
  owner: User | null
  created_at: string
  updated_at: string
  lob_id: string | null
  lob_name: string | null
  geography_ids: string[]
  product_ids: string[]
  segment_ids: string[]
}

export interface RiskListResponse {
  items: Risk[]
  total: number
  page: number
  page_size: number
}

export interface RiskCreate {
  name: string
  description?: string
  domain?: string
  inherent_severity?: RiskSeverity
  likelihood?: number
  impact?: number
  framework_tags?: string[]
  owner_id?: string
  lob_id?: string
  geography_ids?: string[]
  product_ids?: string[]
  segment_ids?: string[]
}

// ── Risk Universe ──────────────────────────────────────────────────────────────
export interface DomainCoverage {
  domain: string
  risk_count: number
  avg_coverage_pct: number
  worst_severity: RiskSeverity
}

export interface HeatCell {
  lob_id: string
  lob_name: string
  domain: string
  risk_count: number
  worst_severity: RiskSeverity
}

export interface UniverseSummary {
  total_risks: number
  high_critical_count: number
  unowned_count: number
  avg_coverage_pct: number
  domain_coverage: DomainCoverage[]
  heat_cells: HeatCell[]
  needs_attention: Risk[]
}

// ── Controls ──────────────────────────────────────────────────────────────────
export type ControlStatus = 'effective' | 'partial' | 'ineffective' | 'not_tested'
export type ControlType = 'automated' | 'manual' | 'compensating'

export interface Control {
  id: string
  org_id: string
  name: string
  description: string | null
  domain: string | null
  control_type: ControlType
  status: ControlStatus
  last_tested_at: string | null
  next_test_due: string | null
  framework_tags: string[]
  integration_source: string | null
  ai_seeded: boolean
  owner: User | null
  created_at: string
  updated_at: string
}

// ── Canvas ────────────────────────────────────────────────────────────────────
export type NodeType = 'risk' | 'control' | 'process' | 'evidence'
export type EdgeType = 'mitigates' | 'partially_mitigates' | 'evidences' | 'generates'

export interface CanvasNode {
  id: string
  org_id: string
  node_type: NodeType
  pos_x: number
  pos_y: number
  risk_id: string | null
  control_id: string | null
  label: string | null
  node_metadata: Record<string, unknown>
  is_orphan: boolean
  ai_gap_flag: string | null
  risk?: Risk
  control?: Control
}

export interface CanvasEdge {
  id: string
  from_node_id: string
  to_node_id: string
  edge_type: EdgeType
  created_at: string
}

export interface CanvasData {
  nodes: CanvasNode[]
  edges: CanvasEdge[]
}

// ── Audit ─────────────────────────────────────────────────────────────────────
export type TaskStatus = 'pending' | 'in_progress' | 'done' | 'blocked'
export type AuditStatus = 'planning' | 'fieldwork' | 'reporting' | 'closed'

export interface AuditTask {
  id: string
  plan_id: string
  phase: number
  phase_label: string | null
  label: string
  status: TaskStatus
  is_priority: boolean
  sort_order: number
  due_date: string | null
  completed_at: string | null
  assignee: User | null
}

export interface AuditPlan {
  id: string
  org_id: string
  name: string
  description: string | null
  status: AuditStatus
  planned_start: string | null
  planned_end: string | null
  task_count: number
  done_count: number
  progress_pct: number
  tasks: AuditTask[]
  created_at: string
}

// ── Signals ───────────────────────────────────────────────────────────────────
export type SignalSeverity = 'critical' | 'high' | 'medium' | 'info'
export type SignalCategory = 'regulatory' | 'threat' | 'vendor' | 'macro'

export interface Signal {
  id: string
  source: string
  category: SignalCategory
  severity: SignalSeverity
  title: string
  body: string | null
  external_url: string | null
  tags: string[]
  published_at: string | null
  relevance_score: number
  impacted_control_ids: string[]
  impacted_risk_ids: string[]
  ai_recommendation: string | null
  is_new: boolean
  created_at: string
}

export interface SignalListResponse {
  items: Signal[]
  total: number
  counts: {
    critical: number
    high: number
    medium: number
    info: number
    new_today: number
    all?: number
    cat_regulatory?: number
    cat_threat?: number
    cat_vendor?: number
    cat_macro?: number
  }
}

// ── Pulse ─────────────────────────────────────────────────────────────────────
export type PulseStatus = 'passing' | 'failing' | 'degraded' | 'unknown'

export interface PulseControl {
  control_id: string
  control_name: string
  integration_source: string | null
  current_status: PulseStatus
  current_metrics: Record<string, unknown>
  trend: Array<{ checked_at: string; status: PulseStatus; metrics: Record<string, unknown> }>
  ai_alert: string | null
}

export interface PulseSummary {
  passing_count: number
  failing_count: number
  degraded_count: number
  total_monitored: number
  controls: PulseControl[]
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export interface DashboardMetrics {
  total_risks: number
  high_risks: number
  medium_risks: number
  low_risks: number
  controls_mapped: number
  control_gaps: number
  audit_areas: number
  frameworks_active: number
}

export interface DashboardData {
  org: Organization
  metrics: DashboardMetrics
  ai_insights: Array<{ text: string; source: string; action: string }>
  top_risks: Risk[]
  framework_coverage: Array<{ code: string; label: string; coverage_pct: number }>
  recent_signals: Signal[]
}

// ── Copilot ───────────────────────────────────────────────────────────────────
export interface CopilotMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface CopilotRequest {
  message: string
  context_risk_id?: string
  context_control_id?: string
  conversation_history?: Array<{ role: string; content: string }>
}

export interface CopilotResponse {
  response: string
  suggested_actions: Array<{ label: string; action_type: string }>
}

// ── Time Machine ─────────────────────────────────────────────────────────────

export interface TimeMachineSnapshot {
  snapshot_month: string        // "YYYY-MM"
  total_risks: number
  critical_risks: number
  high_risks: number
  total_controls: number
  effective_controls: number
  coverage_pct: number
  frameworks_active: number
  open_audit_plans: number
  delta_risks: number
  delta_coverage_pct: number
  delta_controls: number
  notable_events: Array<{ type: string; title: string; sentiment: string }>
  risk_diff: Record<string, string[]>
  control_diff: Record<string, string[]>
}

export interface TimeMachineEvent {
  id: string
  event_type: string
  sentiment: 'positive' | 'negative' | 'neutral'
  title: string
  description: string | null
  entity_type: string | null
  entity_name: string | null
  occurred_at: string
}

export interface SimulationFinding {
  severity: 'critical' | 'high' | 'medium' | 'low'
  title: string
  description: string
}

export interface SimulationResult {
  id: string
  scenario_key: string
  scenario_label: string
  parameters: Record<string, number>
  residual_risk_score: number
  controls_failing_count: number
  regulatory_exposure_usd: number
  domain_exposure: Array<{ domain: string; exposure_pct: number }>
  ai_recommendation: string
  findings: SimulationFinding[]
  run_at: string
}

export interface SimulateRequest {
  scenario_key: string
  scenario_label: string
  parameters: Record<string, number>
}

// ── Regulatory Change Agent ───────────────────────────────────────────────────

export interface RegChangeMatchedControl {
  control_name: string
  gap_type: string
  severity: string
}

export interface RegChangeTask {
  id: string
  phase: number
  phase_label: string | null
  label: string
  role: string | null
  status: 'pending' | 'in_progress' | 'done'
  is_priority: boolean
  sort_order: number
  due_week: number | null
}

export interface RegulatoryChange {
  id: string
  source: string
  source_url: string | null
  regulation_family: string | null
  jurisdiction: string | null
  title: string
  summary: string | null
  severity: string
  relevance_score: number
  pipeline_stage: string
  deadline_at: string | null
  deadline_label: string | null
  impact_assessment: string | null
  matched_controls: RegChangeMatchedControl[]
  tags: string[]
  is_new: boolean
  is_dismissed: boolean
  published_at: string
  tasks: RegChangeTask[]
}

export interface RegulatoryChangeListItem {
  id: string
  source: string
  regulation_family: string | null
  title: string
  summary: string | null
  severity: string
  pipeline_stage: string
  deadline_label: string | null
  tags: string[]
  is_new: boolean
  published_at: string
  task_total: number
  task_done: number
}

export interface RegulatoryChangeListResponse {
  items: RegulatoryChangeListItem[]
  total: number
  counts: { critical: number; high: number; new: number }
}

export interface RegulatoryDeadline {
  change_id: string
  title: string
  regulation_family: string | null
  severity: string
  deadline_at: string
  deadline_label: string | null
  days_remaining: number
}

// ── AI Co-Auditor ─────────────────────────────────────────────────────────────

export type CopilotMode = 'anomaly_review' | 'draft_workpaper' | 'interview_prep' | 'free_query'
export type WPSectionStatus = 'empty' | 'ai_drafting' | 'drafted' | 'approved'
export type WorkPaperStatus = 'draft' | 'in_review' | 'approved'
export type AnomalySeverity = 'high' | 'medium' | 'low'

export interface WPSection {
  id: string
  title: string
  content: string | null
  status: WPSectionStatus
  sort_order: number
}

export interface EngagementAnomaly {
  id: string
  title: string
  description: string | null
  severity: AnomalySeverity
  amount_label: string | null
  account_ref: string | null
  period: string | null
  assertion: string | null
  is_addressed: boolean
}

export interface InterviewQuestion {
  id: string
  question: string
  risk_level: string
  assertion: string | null
  target_role: string | null
  sort_order: number
}

export interface CopilotWorkPaper {
  id: string
  code: string
  title: string
  area: string | null
  status: WorkPaperStatus
  is_active: boolean
  sort_order: number
  sections: WPSection[]
  question_count: number
}

export interface AuditEngagement {
  id: string
  name: string
  phase: string | null
  client_name: string | null
  period: string | null
  status: string
  work_paper_count: number
  anomaly_count: number
  open_anomaly_count: number
  work_papers: CopilotWorkPaper[]
  anomalies: EngagementAnomaly[]
}

export interface CopilotChatResponse {
  response: string
  refs_anomaly: boolean
  mode: string
}

// ── Audit Reports ─────────────────────────────────────────────────────────────

export interface AuditKeyMetric {
  label: string
  value: string
  trend: 'up' | 'down' | 'stable'
}

export interface AuditFinding {
  id: string          // "F-1"
  title: string
  severity: 'Critical' | 'High' | 'Medium' | 'Low'
  domain: string
  criteria: string
  condition: string
  cause: string
  effect: string
  observation: string
}

export interface AuditRecommendation {
  finding_id: string
  recommendation: string
  priority: 'Immediate' | 'High' | 'Medium' | 'Low'
  target_date_label: string
  effort: 'Low' | 'Medium' | 'High'
  management_response_placeholder: string
}

export interface FindingResponse {
  id: string
  finding_index: number
  response_text: string
  responder_name: string | null
  responder_role: string | null
  target_date: string | null
  agreed: boolean
  created_at: string
}

export interface AuditReportDocStructure {
  scope_statement: string
  methodology: string
  independence_statement: string
  appendix_a_risk_matrix: {
    description: string
    matrix: Array<{ domain: string; inherent: string; residual: string; trend: string }>
  }
  appendix_b_controls_tested: {
    description: string
    items: Array<{ control: string; type: string; result: string; sample_size: number }>
  }
  distribution: { audit_committee: boolean; board: boolean; control_owners: boolean; regulator: boolean }
}

export interface AuditReport {
  id: string
  org_id: string
  plan_id: string | null
  title: string
  status: 'assembling' | 'draft' | 'review' | 'published'
  overall_rating: string | null
  rating_score: number
  period_start: string | null
  period_end: string | null
  exec_summary: {
    headline?: string
    period?: string
    overall_rating?: string
    rating_score?: number
    body?: string
    key_metrics?: AuditKeyMetric[]
    audit_scope?: string
    limitations?: string | null
  }
  findings: AuditFinding[]
  recommendations: AuditRecommendation[]
  doc_structure: Partial<AuditReportDocStructure>
  assembly_log: Array<{ stage: number; name: string; status: string; duration_ms: number }>
  distribution: { audit_committee?: boolean; board?: boolean; control_owners?: boolean; regulator?: boolean }
  assembled_at: string | null
  published_at: string | null
  created_at: string
  finding_responses: FindingResponse[]
}

// ── Company Profile ───────────────────────────────────────────────────────────

export interface OrgIdentity {
  id: string; org_id: string; legal_name: string; trading_name: string | null
  year_founded: number | null; employee_range: string | null; annual_revenue_range: string | null
  hq_country: string | null; hq_city: string | null; stock_ticker: string | null
  website: string | null; description: string | null; logo_url: string | null
  updated_by: string | null; created_at: string; updated_at: string
}

export interface LOB {
  id: string; org_id: string; name: string; description: string | null
  status: 'active' | 'planned' | 'archived'; launch_date: string | null
  revenue_contribution_pct: number | null; is_primary: boolean; created_at: string; updated_at: string
}

export interface OrgGeo {
  id: string; org_id: string; country: string; region: string | null
  state_province: string | null; presence_type: string
  lob_ids: string[]; regulatory_flags: string[]; created_at: string
}

export interface OrgIndustry {
  id: string; org_id: string; code: string; name: string
  classification: 'primary' | 'secondary'; lob_ids: string[]; created_at: string
}

export interface OrgProduct {
  id: string; org_id: string; name: string; description: string | null
  product_type: string; lob_id: string | null; geography_ids: string[]
  customer_segment_ids: string[]; status: string; launch_date: string | null
  data_sensitivity: string; created_at: string; updated_at: string
}

export interface CustomerSegment {
  id: string; org_id: string; name: string; segment_type: string
  includes_minors: boolean; includes_healthcare: boolean; includes_financial: boolean
  geography_ids: string[]; lob_ids: string[]; estimated_size: string | null; created_at: string
}

export interface ThirdParty {
  id: string; org_id: string; name: string; category: string; tier: string
  geography_ids: string[]; sub_processors: string[]; last_assessed: string | null
  assessment_status: string; created_at: string
}

export interface DataTech {
  id: string; org_id: string; uses_ai_ml: boolean; ai_use_cases: string[]
  cloud_providers: string[]; data_residency_requirements: string[]
  handles_personal_data: boolean; handles_sensitive_personal_data: boolean
  handles_payment_data: boolean; handles_health_data: boolean
  handles_classified_data: boolean; core_tech_stack: string[]
  created_at: string; updated_at: string
}

export interface ChangeLogEntry {
  id: string; org_id: string; changed_by: string | null; changed_at: string
  entity_type: string; entity_id: string | null; field_changed: string | null
  old_value: unknown; new_value: unknown; change_summary: string | null
  propagation_status: string; affected_modules: string[]
  propagation_result: Record<string, unknown>
}

export interface FullProfile {
  identity: OrgIdentity | null; lines_of_business: LOB[]; geographies: OrgGeo[]
  industries: OrgIndustry[]; products: OrgProduct[]; customer_segments: CustomerSegment[]
  third_parties: ThirdParty[]; data_tech: DataTech | null; pending_propagations: number
}

export interface PropagationModulePreview {
  module: string; module_label: string; action_type: string; count: number
  preview: Array<{ title: string; severity: string; rationale: string }>; status: string
}

export interface PropagationPreview {
  change_log_id: string; change_summary: string
  affected_modules: PropagationModulePreview[]
}
