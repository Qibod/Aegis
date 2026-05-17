import axios from 'axios'
import type {
  TokenResponse, LoginRequest, RegisterRequest, User,
  Organization, FingerprintResponse,
  Risk, RiskListResponse, RiskCreate, UniverseSummary,
  Control, CanvasData, CanvasNode, CanvasEdge,
  AuditPlan, AuditTask,
  SignalListResponse, Signal,
  PulseSummary,
  DashboardData,
  CopilotRequest, CopilotResponse,
  TimeMachineSnapshot, TimeMachineEvent, SimulationResult, SimulateRequest,
  RegulatoryChange, RegulatoryChangeListResponse, RegulatoryDeadline, RegChangeTask,
  AuditReport, FindingResponse,
  AuditEngagement, CopilotChatResponse, WPSection, InterviewQuestion, CopilotMode,
  FullProfile, OrgIdentity, LOB, OrgGeo, OrgIndustry, OrgProduct,
  CustomerSegment, ThirdParty, DataTech, ChangeLogEntry, PropagationPreview,
} from '@/types'

// ── Axios instance ────────────────────────────────────────────────────────────
// In dev: uses Vite proxy → localhost:8000
// In production: VITE_API_BASE_URL must point to deployed backend, e.g.
//   https://aegis-api.up.railway.app/api/v1
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// ── Auth interceptor — attach JWT to every request ────────────────────────────
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Response interceptor — auto-refresh on 401 ───────────────────────────────
let isRefreshing = false
let refreshQueue: Array<(token: string) => void> = []

api.interceptors.response.use(
  res => res,
  async err => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true
      const refreshToken = localStorage.getItem('refresh_token')

      if (!refreshToken) {
        localStorage.removeItem('access_token')
        window.location.href = '/login'
        return Promise.reject(err)
      }

      if (isRefreshing) {
        // Queue requests while a refresh is in progress
        return new Promise(resolve => {
          refreshQueue.push((token: string) => {
            original.headers.Authorization = `Bearer ${token}`
            resolve(api(original))
          })
        })
      }

      isRefreshing = true
      try {
        const { data } = await api.post<{ access_token: string; refresh_token: string }>(
          '/auth/refresh',
          { refresh_token: refreshToken }
        )
        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('refresh_token', data.refresh_token)
        api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`
        refreshQueue.forEach(cb => cb(data.access_token))
        refreshQueue = []
        original.headers.Authorization = `Bearer ${data.access_token}`
        return api(original)
      } catch {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        window.location.href = '/login'
        return Promise.reject(err)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (data: LoginRequest) =>
    api.post<TokenResponse>('/auth/login', data).then(r => r.data),

  register: (data: RegisterRequest, orgName: string) =>
    api.post<User>(`/auth/register?org_name=${encodeURIComponent(orgName)}`, data).then(r => r.data),

  me: () => api.get<User>('/auth/me').then(r => r.data),

  refresh: (refreshToken: string) =>
    api.post<TokenResponse>('/auth/refresh', { refresh_token: refreshToken }).then(r => r.data),

  changePassword: (current_password: string, new_password: string) =>
    api.post('/auth/change-password', { current_password, new_password }),

  forgotPassword: (email: string) =>
    api.post<{ token: string; message: string }>('/auth/forgot-password', { email }).then(r => r.data),

  resetPassword: (token: string, new_password: string) =>
    api.post('/auth/reset-password', { token, new_password }),
}

// ── Organizations ─────────────────────────────────────────────────────────────
export const orgsApi = {
  me: () => api.get<Organization>('/orgs/me').then(r => r.data),

  profile: () => api.get<Organization & { fingerprint_data: FingerprintResponse }>('/orgs/profile').then(r => r.data),

  fingerprint: (companyName: string) =>
    api.post<FingerprintResponse>('/orgs/fingerprint', { company_name: companyName }).then(r => r.data),

  completeOnboarding: (data: {
    fingerprint_data: Record<string, unknown>
    selected_frameworks: string[]
    risk_domains: string[]
  }) => api.post<Organization>('/orgs/complete-onboarding', data).then(r => r.data),
}

// ── Company Profile ───────────────────────────────────────────────────────────
export const profileApi = {
  get:            () => api.get<FullProfile>('/profile').then(r => r.data),

  createIdentity: (d: Partial<OrgIdentity>) => api.post<OrgIdentity>('/profile/identity', d).then(r => r.data),
  updateIdentity: (d: Partial<OrgIdentity>) => api.patch<OrgIdentity>('/profile/identity', d).then(r => r.data),

  listLobs:    () => api.get<LOB[]>('/profile/lines-of-business').then(r => r.data),
  createLob:   (d: Partial<LOB>) => api.post<LOB>('/profile/lines-of-business', d).then(r => r.data),
  updateLob:   (id: string, d: Partial<LOB>) => api.patch<LOB>(`/profile/lines-of-business/${id}`, d).then(r => r.data),
  archiveLob:  (id: string) => api.delete(`/profile/lines-of-business/${id}`),

  listGeos:    () => api.get<OrgGeo[]>('/profile/geographies').then(r => r.data),
  createGeo:   (d: Partial<OrgGeo>) => api.post<OrgGeo>('/profile/geographies', d).then(r => r.data),
  deleteGeo:   (id: string) => api.delete(`/profile/geographies/${id}`),

  listIndustries:   () => api.get<OrgIndustry[]>('/profile/industries').then(r => r.data),
  createIndustry:   (d: Partial<OrgIndustry>) => api.post<OrgIndustry>('/profile/industries', d).then(r => r.data),
  deleteIndustry:   (id: string) => api.delete(`/profile/industries/${id}`),

  listProducts:  () => api.get<OrgProduct[]>('/profile/products').then(r => r.data),
  createProduct: (d: Partial<OrgProduct>) => api.post<OrgProduct>('/profile/products', d).then(r => r.data),
  updateProduct: (id: string, d: Partial<OrgProduct>) => api.patch<OrgProduct>(`/profile/products/${id}`, d).then(r => r.data),
  deleteProduct: (id: string) => api.delete(`/profile/products/${id}`),

  listSegments:   () => api.get<CustomerSegment[]>('/profile/customer-segments').then(r => r.data),
  createSegment:  (d: Partial<CustomerSegment>) => api.post<CustomerSegment>('/profile/customer-segments', d).then(r => r.data),
  deleteSegment:  (id: string) => api.delete(`/profile/customer-segments/${id}`),

  listThirdParties:   () => api.get<ThirdParty[]>('/profile/third-parties').then(r => r.data),
  createThirdParty:   (d: Partial<ThirdParty>) => api.post<ThirdParty>('/profile/third-parties', d).then(r => r.data),
  updateThirdParty:   (id: string, d: Partial<ThirdParty>) => api.patch<ThirdParty>(`/profile/third-parties/${id}`, d).then(r => r.data),
  deleteThirdParty:   (id: string) => api.delete(`/profile/third-parties/${id}`),

  getDataTech:    () => api.get<DataTech | null>('/profile/data-tech').then(r => r.data),
  updateDataTech: (d: Partial<DataTech>) => api.patch<DataTech>('/profile/data-tech', d).then(r => r.data),

  getChangeLog:   (page = 1) => api.get<{ items: ChangeLogEntry[]; total: number; page: number; page_size: number }>(`/profile/change-log?page=${page}`).then(r => r.data),
  getPropagation: (id: string) => api.get<PropagationPreview>(`/profile/propagate/${id}`).then(r => r.data),
  applyPropagation: (change_log_id: string, approved_modules: string[]) =>
    api.post('/profile/propagate/apply', { change_log_id, approved_modules }).then(r => r.data),

  // kept for backward compat — legacy fingerprint display
  legacyProfile: () => api.get<Organization & { fingerprint_data: FingerprintResponse }>('/orgs/profile').then(r => r.data),
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export const dashboardApi = {
  get: () => api.get<DashboardData>('/dashboard').then(r => r.data),
}

// ── Risks ─────────────────────────────────────────────────────────────────────
export const risksApi = {
  list: (params?: { domain?: string; severity?: string; lob_id?: string; geo_id?: string; page?: number; page_size?: number }) =>
    api.get<RiskListResponse>('/risks', { params }).then(r => r.data),

  universeSummary: () =>
    api.get<UniverseSummary>('/risks/universe-summary').then(r => r.data),

  get: (id: string) => api.get<Risk>(`/risks/${id}`).then(r => r.data),

  create: (data: RiskCreate) => api.post<Risk>('/risks', data).then(r => r.data),

  update: (id: string, data: Partial<RiskCreate>) =>
    api.patch<Risk>(`/risks/${id}`, data).then(r => r.data),

  delete: (id: string) => api.delete(`/risks/${id}`),
}

// ── Controls ──────────────────────────────────────────────────────────────────
export const controlsApi = {
  list: (params?: { status?: string; domain?: string }) =>
    api.get<Control[]>('/controls', { params }).then(r => r.data),

  create: (data: Partial<Control>) => api.post<Control>('/controls', data).then(r => r.data),

  update: (id: string, data: Partial<Control>) =>
    api.patch<Control>(`/controls/${id}`, data).then(r => r.data),

  uploadEvidence: (controlId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post(`/controls/${controlId}/evidence`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
}

// ── Canvas ────────────────────────────────────────────────────────────────────
export const canvasApi = {
  get: () => api.get<CanvasData>('/canvas').then(r => r.data),

  createNode: (data: Partial<CanvasNode>) =>
    api.post<CanvasNode>('/canvas/nodes', data).then(r => r.data),

  updateNode: (id: string, data: { pos_x?: number; pos_y?: number; label?: string }) =>
    api.patch<CanvasNode>(`/canvas/nodes/${id}`, data).then(r => r.data),

  deleteNode: (id: string) => api.delete(`/canvas/nodes/${id}`),

  createEdge: (data: { from_node_id: string; to_node_id: string; edge_type: string }) =>
    api.post<CanvasEdge>('/canvas/edges', data).then(r => r.data),

  deleteEdge: (id: string) => api.delete(`/canvas/edges/${id}`),
}

// ── Audit ─────────────────────────────────────────────────────────────────────
export const auditApi = {
  listPlans: () => api.get<AuditPlan[]>('/audit/plans').then(r => r.data),

  createPlan: (data: { name: string; description?: string; scope_risk_ids?: string[] }) =>
    api.post<AuditPlan>('/audit/plans', data).then(r => r.data),

  getPlan: (id: string) => api.get<AuditPlan>(`/audit/plans/${id}`).then(r => r.data),

  createTask: (planId: string, data: Partial<AuditTask>) =>
    api.post<AuditTask>(`/audit/plans/${planId}/tasks`, data).then(r => r.data),

  updateTask: (taskId: string, data: { status?: string; assignee_id?: string }) =>
    api.patch<AuditTask>(`/audit/tasks/${taskId}`, data).then(r => r.data),
}

// ── Radar ─────────────────────────────────────────────────────────────────────
export const radarApi = {
  list: (params?: { category?: string; severity?: string; page?: number }) =>
    api.get<SignalListResponse>('/radar/signals', { params }).then(r => r.data),

  get: (id: string) => api.get<Signal>(`/radar/signals/${id}`).then(r => r.data),

  dismiss: (id: string) => api.post(`/radar/signals/${id}/dismiss`),
}

// ── Pulse ─────────────────────────────────────────────────────────────────────
export const pulseApi = {
  get: () => api.get<PulseSummary>('/pulse').then(r => r.data),
}

// ── Copilot ───────────────────────────────────────────────────────────────────
export const copilotApi = {
  chat: (data: CopilotRequest) =>
    api.post<CopilotResponse>('/copilot', data).then(r => r.data),
}

// ── Regulatory Change Agent ───────────────────────────────────────────────────
export const regulatoryApi = {
  list: (params?: { severity?: string; regulation?: string }) =>
    api.get<RegulatoryChangeListResponse>('/regulatory/changes', { params }).then(r => r.data),

  get: (id: string) =>
    api.get<RegulatoryChange>(`/regulatory/changes/${id}`).then(r => r.data),

  assess: (id: string) =>
    api.post<RegulatoryChange>(`/regulatory/changes/${id}/assess`).then(r => r.data),

  updateTask: (taskId: string, status: string) =>
    api.patch<RegChangeTask>(`/regulatory/tasks/${taskId}`, { status }).then(r => r.data),

  dismiss: (id: string) =>
    api.post(`/regulatory/dismiss/${id}`),

  deadlines: () =>
    api.get<RegulatoryDeadline[]>('/regulatory/deadlines').then(r => r.data),

  simulateUpdate: () =>
    api.post<RegulatoryChange>('/regulatory/simulate-update').then(r => r.data),
}

// ── AI Co-Auditor ─────────────────────────────────────────────────────────────
export const auditCopilotApi = {
  listEngagements: () =>
    api.get<AuditEngagement[]>('/audit-copilot/engagements').then(r => r.data),

  getEngagement: (id: string) =>
    api.get<AuditEngagement>(`/audit-copilot/engagements/${id}`).then(r => r.data),

  chat: (engagementId: string, data: {
    mode: CopilotMode
    message: string
    history: Array<{ role: string; content: string }>
  }) => api.post<CopilotChatResponse>(`/audit-copilot/engagements/${engagementId}/chat`, data).then(r => r.data),

  updateSection: (sectionId: string, data: { content?: string; status?: string }) =>
    api.patch<WPSection>(`/audit-copilot/sections/${sectionId}`, data).then(r => r.data),

  pushAnomalyToWorkpaper: (anomalyId: string) =>
    api.post<{ section: WPSection; anomaly_id: string }>(`/audit-copilot/anomalies/${anomalyId}/to-workpaper`, {}).then(r => r.data),

  getQuestions: (engagementId: string, targetRole?: string) =>
    api.get<InterviewQuestion[]>(`/audit-copilot/engagements/${engagementId}/questions`, { params: targetRole ? { target_role: targetRole } : {} }).then(r => r.data),
}

// ── Audit Reports ─────────────────────────────────────────────────────────────
export const auditReportApi = {
  generate: () =>
    api.post<{ report_id: string; status: string }>('/audit/reports/generate').then(r => r.data),

  list: () =>
    api.get<AuditReport[]>('/audit/reports').then(r => r.data),

  get: (id: string) =>
    api.get<AuditReport>(`/audit/reports/${id}`).then(r => r.data),

  updateStatus: (id: string, status: string) =>
    api.patch<AuditReport>(`/audit/reports/${id}/status`, { status }).then(r => r.data),

  upsertFindingResponse: (reportId: string, findingIndex: number, data: {
    response_text: string
    responder_name?: string
    responder_role?: string
    target_date?: string
    agreed?: boolean
  }) => api.post<FindingResponse>(`/audit/reports/${reportId}/findings/${findingIndex}/response`, data).then(r => r.data),

  deleteFindingResponse: (reportId: string, findingIndex: number) =>
    api.delete(`/audit/reports/${reportId}/findings/${findingIndex}/response`),
}

// ── Time Machine ──────────────────────────────────────────────────────────────
export const timeMachineApi = {
  snapshots: () => api.get<TimeMachineSnapshot[]>('/time-machine/snapshots').then(r => r.data),
  events: () => api.get<TimeMachineEvent[]>('/time-machine/events').then(r => r.data),
  simulate: (data: SimulateRequest) => api.post<SimulationResult>('/time-machine/simulate', data).then(r => r.data),
  simulations: () => api.get<SimulationResult[]>('/time-machine/simulations').then(r => r.data),
}

// ── v2.1 Validation & Proposals ───────────────────────────────────────────────
export const validationApi = {
  getState: (entityType: string, entityId: string) =>
    api.get(`/validation/state/${entityType}/${entityId}`).then(r => r.data),

  verifyField: (entityType: string, entityId: string, fieldName: string) =>
    api.post(`/validation/verify/${entityType}/${entityId}/${fieldName}`).then(r => r.data),

  resolveField: (validationId: string, body: {
    chosen_value: unknown
    resolution_source: 'seeded' | 'alternative' | 'user_input'
    source_note?: string
  }) => api.post(`/validation/resolve/${validationId}`, body).then(r => r.data),
}

export const proposalsApi = {
  list: () =>
    api.get('/validation/proposals').then(r => r.data),

  approve: (id: string) =>
    api.post(`/validation/proposals/${id}/approve`).then(r => r.data),

  reject: (id: string) =>
    api.post(`/validation/proposals/${id}/reject`).then(r => r.data),
}

// ── v2.1 GRC Assistant WebSocket ──────────────────────────────────────────────
export function createAssistantWS(): WebSocket {
  const base = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/^http/, 'ws')
  return new WebSocket(`${base}/assistant/ws`)
}

export default api
