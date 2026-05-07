/**
 * AuditCopilotPage — Three-panel AI Co-Auditor workspace
 *
 * Left   — Engagement navigation (work papers, anomalies, evidence, capabilities)
 * Centre — Mode-aware co-auditor chat (Anomaly review / Draft work paper / Interview prep / Free query)
 * Right  — Live work paper editor + interview question list
 */

import React, { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { auditCopilotApi } from '@/api/client'
import type {
  AuditEngagement, CopilotWorkPaper, WPSection,
  EngagementAnomaly, InterviewQuestion, CopilotMode,
} from '@/types'
import { Spinner } from '@/components/ui'

// ─── colours ──────────────────────────────────────────────────────────────────
const SEV: Record<string, string> = { high: 'var(--red)', medium: 'var(--amber)', low: 'var(--teal)' }
const RISK_COL: Record<string, string> = { high: 'var(--red)', medium: 'var(--amber)', low: 'var(--teal)' }
const SEC_STATUS_COL: Record<string, string> = {
  empty:       'var(--text3)',
  ai_drafting: 'var(--accent2)',
  drafted:     'var(--amber)',
  approved:    'var(--teal)',
}
const WP_STATUS_COL: Record<string, string> = {
  draft:     'var(--text3)',
  in_review: 'var(--amber)',
  approved:  'var(--teal)',
}

// ─── Mode config ───────────────────────────────────────────────────────────────
type ModeKey = CopilotMode
const MODES: Array<{ key: ModeKey; label: string }> = [
  { key: 'anomaly_review',  label: 'Anomaly review' },
  { key: 'draft_workpaper', label: 'Draft work paper' },
  { key: 'interview_prep',  label: 'Interview prep' },
  { key: 'free_query',      label: 'Free query' },
]

// ─── Capabilities ──────────────────────────────────────────────────────────────
const CAPABILITIES = [
  { label: 'Anomaly detection', desc: 'Statistical analysis on GL, JEs, and trial balance', tier: 'live' },
  { label: 'Interview prep',    desc: 'Risk-mapped questions from audit findings',           tier: 'live' },
  { label: 'Work paper drafting', desc: 'AI fills sections as findings emerge in chat',      tier: 'live' },
  { label: 'Data querying',     desc: 'Ask anything about engagement data in plain language', tier: 'live' },
  { label: 'Contract analysis', desc: 'Extract terms and revenue clauses from agreements',   tier: 'beta' },
  { label: 'Multi-entity rollup', desc: 'Cross-subsidiary comparison and consolidation',     tier: 'beta' },
  { label: 'Prior year trends',   desc: 'Variance narration vs prior year periods',          tier: 'soon' },
  { label: 'Confirmation drafting', desc: 'Auto-draft bank and debtor confirmation letters', tier: 'soon' },
]

const TIER_COLOR: Record<string, string> = { live: 'var(--teal)', beta: 'var(--blue)', soon: 'var(--amber)' }

// ─── Message types ────────────────────────────────────────────────────────────
interface ChatMessage {
  id:          string
  role:        'user' | 'assistant'
  content:     string
  mode:        ModeKey
  anomalyCard?: { count: number; period: string; items: Array<{ title: string; severity: string; amount: string }> }
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

const SectionRow: React.FC<{
  sec: WPSection
  onDraftClick: () => void
  draftingId: string | null
}> = ({ sec, onDraftClick, draftingId }) => {
  const isDrafting = draftingId === sec.id
  const col = SEC_STATUS_COL[sec.status] || 'var(--text3)'
  const isEditable = sec.status !== 'empty'

  return (
    <div style={{ display: 'flex', alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border)', gap: 8 }}>
      <div style={{ width: 14, height: 14, borderRadius: '50%', border: `1.5px solid ${col}`, background: sec.status === 'approved' ? col : sec.status === 'ai_drafting' ? col + '33' : 'transparent', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        {sec.status === 'approved' && <svg width="8" height="8" viewBox="0 0 8 8" fill="none"><path d="M1.5 4l2 2 3-3" stroke="white" strokeWidth="1.2" strokeLinecap="round"/></svg>}
        {sec.status === 'ai_drafting' && <div style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--accent2)', animation: 'pulse 2s infinite' }} />}
      </div>
      <div style={{ flex: 1, fontSize: 12, color: sec.status === 'empty' ? 'var(--text3)' : 'var(--text)' }}>{sec.title}</div>
      <div style={{ fontSize: 10, fontWeight: 500, color: col }}>
        {isDrafting ? 'AI drafting…' : sec.status === 'empty' ? 'Empty' : sec.status === 'ai_drafting' ? 'Drafting' : sec.status === 'drafted' ? 'Draft' : 'Approved'}
      </div>
    </div>
  )
}

const AnomalyCard: React.FC<{
  anomaly: EngagementAnomaly
  onAddToWP: (id: string) => void
  adding: boolean
}> = ({ anomaly, onAddToWP, adding }) => {
  const [open, setOpen] = useState(false)
  const col = SEV[anomaly.severity]

  return (
    <div style={{ borderRadius: 8, border: `1px solid ${col}33`, background: col + '08', marginBottom: 6, overflow: 'hidden' }}>
      <div onClick={() => setOpen(v => !v)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', cursor: 'pointer' }}>
        <div style={{ width: 7, height: 7, borderRadius: '50%', background: col, flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>{anomaly.title}</div>
          <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 1 }}>{anomaly.amount_label} · {anomaly.account_ref}</div>
        </div>
        <span style={{ fontSize: 9, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: col }}>{anomaly.severity}</span>
        <span style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 2 }}>{open ? '▲' : '▼'}</span>
      </div>
      {open && (
        <div style={{ padding: '0 12px 10px', borderTop: `1px solid ${col}22` }}>
          <p style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.6, marginTop: 8, marginBottom: 10 }}>{anomaly.description}</p>
          <div style={{ display: 'flex', gap: 6 }}>
            <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4, background: 'var(--bg3)', color: 'var(--text3)' }}>
              {anomaly.assertion}
            </span>
            <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4, background: 'var(--bg3)', color: 'var(--text3)' }}>
              {anomaly.period}
            </span>
          </div>
          {!anomaly.is_addressed && (
            <button
              onClick={() => onAddToWP(anomaly.id)}
              disabled={adding}
              style={{ marginTop: 10, width: '100%', height: 28, borderRadius: 6, border: '1px solid rgba(108,99,255,.35)', background: 'rgba(108,99,255,.1)', color: adding ? 'var(--text3)' : 'var(--accent2)', fontSize: 11, fontWeight: 500, cursor: adding ? 'not-allowed' : 'pointer', fontFamily: 'var(--font)' }}>
              {adding ? 'AI drafting section…' : 'Add to work paper'}
            </button>
          )}
          {anomaly.is_addressed && (
            <div style={{ marginTop: 8, fontSize: 10, color: 'var(--teal)', fontWeight: 500 }}>✓ Added to work paper</div>
          )}
        </div>
      )}
    </div>
  )
}

const QuestionRow: React.FC<{ q: InterviewQuestion }> = ({ q }) => (
  <div style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
    <p style={{ fontSize: 12, color: 'var(--text)', lineHeight: 1.55, marginBottom: 6 }}>{q.question}</p>
    <div style={{ display: 'flex', gap: 5 }}>
      <span style={{ fontSize: 9, fontWeight: 600, padding: '2px 6px', borderRadius: 4, textTransform: 'uppercase', letterSpacing: '.05em', background: RISK_COL[q.risk_level] + '20', color: RISK_COL[q.risk_level] }}>{q.risk_level} risk</span>
      {q.assertion && (
        <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: 'var(--bg3)', color: 'var(--text3)', textTransform: 'capitalize' }}>{q.assertion}</span>
      )}
    </div>
  </div>
)

// ─── Inline anomaly summary card in chat ─────────────────────────────────────
const ChatAnomalyCard: React.FC<{ anomalies: EngagementAnomaly[] }> = ({ anomalies }) => (
  <div style={{ marginTop: 12, borderRadius: 9, border: '1px solid var(--border2)', background: 'var(--bg2)', overflow: 'hidden' }}>
    <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--red)', animation: 'pulse 2s infinite' }} />
      <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text2)' }}>Anomalies detected · {anomalies[0]?.period ?? 'FY2024'}</span>
    </div>
    {anomalies.slice(0, 3).map(a => (
      <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 14px', borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: SEV[a.severity], minWidth: 52 }}>{a.amount_label ?? ''}</span>
        <span style={{ flex: 1, fontSize: 12, color: 'var(--text)' }}>{a.title}</span>
        <span style={{ fontSize: 9, fontWeight: 600, padding: '2px 6px', borderRadius: 4, background: SEV[a.severity] + '20', color: SEV[a.severity], textTransform: 'uppercase', letterSpacing: '.05em' }}>{a.severity}</span>
      </div>
    ))}
    {anomalies.length > 3 && (
      <div style={{ padding: '6px 14px', fontSize: 11, color: 'var(--text3)' }}>+{anomalies.length - 3} more…</div>
    )}
  </div>
)

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

export const AuditCopilotPage: React.FC = () => {
  const qc = useQueryClient()

  // State
  const [mode, setMode] = useState<ModeKey>('anomaly_review')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput]       = useState('')
  const [leftTab, setLeftTab]   = useState<'papers' | 'anomalies' | 'evidence' | 'capabilities'>('papers')
  const [selectedWP, setSelectedWP] = useState<string | null>(null)
  const [draftingSection, setDraftingSection] = useState<string | null>(null)
  const [roleFilter, setRoleFilter] = useState<string>('Controller')
  const chatEndRef = useRef<HTMLDivElement>(null)

  // Data
  const { data: engagements, isLoading } = useQuery({
    queryKey: ['copilot-engagements'],
    queryFn:  () => auditCopilotApi.listEngagements(),
  })
  const eng: AuditEngagement | null = engagements?.[0] ?? null
  const activeWP = eng?.work_papers.find(wp => wp.is_active) ?? null
  const displayWP = eng?.work_papers.find(wp => wp.id === selectedWP) ?? activeWP

  const { data: questions } = useQuery({
    queryKey: ['copilot-questions', eng?.id, roleFilter],
    queryFn:  () => auditCopilotApi.getQuestions(eng!.id, roleFilter),
    enabled:  !!eng,
  })

  // Chat mutation
  const chatMut = useMutation({
    mutationFn: (msg: string) => auditCopilotApi.chat(eng!.id, {
      mode,
      message: msg,
      history: messages.map(m => ({ role: m.role, content: m.content })),
    }),
    onSuccess: (data, msg) => {
      const userMsg: ChatMessage = {
        id: Date.now() + '-u', role: 'user', content: msg, mode,
      }
      const aiMsg: ChatMessage = {
        id: Date.now() + '-a', role: 'assistant', content: data.response, mode,
        anomalyCard: data.refs_anomaly && mode === 'anomaly_review' ? { count: eng?.open_anomaly_count ?? 0, period: 'Q3-Q4 FY2024', items: [] } : undefined,
      }
      setMessages(prev => [...prev, userMsg, aiMsg])
    },
  })

  // Add anomaly to work paper
  const pushAnomalyMut = useMutation({
    mutationFn: (anomalyId: string) => auditCopilotApi.pushAnomalyToWorkpaper(anomalyId),
    onMutate: (anomalyId) => setDraftingSection(anomalyId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['copilot-engagements'] })
      setDraftingSection(null)
    },
    onError: () => setDraftingSection(null),
  })

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, chatMut.isPending])

  // Send message
  const send = () => {
    if (!input.trim() || !eng || chatMut.isPending) return
    const msg = input.trim()
    setInput('')
    chatMut.mutate(msg)
  }

  // Initial greeting on first load
  useEffect(() => {
    if (eng && messages.length === 0) {
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: `I've completed the analytical procedures on ${eng.client_name}'s revenue ledger. Found **${eng.open_anomaly_count} items** that warrant discussion — ${eng.anomalies.filter(a => a.severity === 'high').length > 0 ? `${eng.anomalies.filter(a => a.severity === 'high').length} I'd classify as high priority.` : 'none critical.'} Want to walk through them now, or should I draft the preliminary risk memo first?`,
        mode: 'anomaly_review',
        anomalyCard: eng.open_anomaly_count > 0 ? { count: eng.open_anomaly_count, period: 'Q3-Q4 FY2024', items: [] } : undefined,
      }])
    }
  }, [eng])

  if (isLoading || !eng) {
    return (
      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spinner />
      </div>
    )
  }

  const openAnomalies = eng.anomalies.filter(a => !a.is_addressed)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* ── Top bar ── */}
      <div style={{ height: 48, flexShrink: 0, display: 'flex', alignItems: 'center', padding: '0 16px', borderBottom: '1px solid var(--border)', background: 'var(--bg1)', gap: 12 }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginRight: 8 }}>
          <div style={{ width: 28, height: 28, borderRadius: 7, background: 'linear-gradient(135deg, var(--accent), var(--teal))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg viewBox="0 0 14 14" fill="none" width="14" height="14">
              <path d="M7 2L11.5 4.5v5L7 12l-4.5-2.5v-5L7 2z" stroke="white" strokeWidth="1.2" strokeLinejoin="round"/>
              <circle cx="7" cy="7" r="1.8" fill="white"/>
            </svg>
          </div>
          <span style={{ fontSize: 13, fontWeight: 600, letterSpacing: '-0.3px' }}>AuditAI</span>
        </div>

        <div style={{ width: 1, height: 18, background: 'var(--border2)' }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text2)' }}>
          <span style={{ fontSize: 11 }}>📋</span>
          <span style={{ fontWeight: 500, color: 'var(--text)' }}>{eng.client_name}</span>
          <span style={{ color: 'var(--text3)' }}>·</span>
          <span>{eng.name}</span>
          <span style={{ color: 'var(--text3)' }}>·</span>
          <span>{eng.phase}</span>
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '4px 10px', borderRadius: 99, background: 'rgba(108,99,255,.12)', border: '1px solid rgba(108,99,255,.25)' }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent2)', animation: 'pulse 2s infinite' }} />
            <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--accent2)' }}>Co-auditor active</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--teal)' }} />
            <span style={{ fontSize: 11, color: 'var(--teal)', fontWeight: 500 }}>Live</span>
          </div>
        </div>
      </div>

      {/* ── Three-panel body ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* ═══ LEFT SIDEBAR (220px) ═══════════════════════════════════════════ */}
        <div style={{ width: 220, flexShrink: 0, borderRight: '1px solid var(--border)', background: 'var(--bg1)', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
          <div style={{ padding: '12px 14px' }}>

            {/* Engagement section */}
            <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 8 }}>Engagement</div>
            {[
              { key: 'papers'       as const, label: 'Co-auditor chat',  icon: '💬', count: null },
              { key: 'papers'       as const, label: 'Work papers',       icon: '📄', count: eng.work_paper_count },
              { key: 'capabilities' as const, label: 'Interview prep',    icon: '👤', count: 12 },
              { key: 'anomalies'    as const, label: 'Anomalies',         icon: '⚠',  count: openAnomalies.length, countColor: 'var(--red)' },
            ].map((item, i) => (
              <button key={i}
                onClick={() => setLeftTab(item.key)}
                style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 6, border: 'none', background: leftTab === item.key ? 'rgba(108,99,255,.1)' : 'transparent', cursor: 'pointer', fontFamily: 'var(--font)', marginBottom: 1 }}>
                <span style={{ fontSize: 12 }}>{item.icon}</span>
                <span style={{ flex: 1, fontSize: 12, color: 'var(--text2)', textAlign: 'left' }}>{item.label}</span>
                {item.count !== null && item.count > 0 && (
                  <span style={{ fontSize: 10, fontWeight: 600, padding: '1px 5px', borderRadius: 99, background: (item.countColor ?? 'rgba(108,99,255,.2)'), color: item.countColor ? 'white' : 'var(--accent2)', minWidth: 18, textAlign: 'center' }}>
                    {item.count}
                  </span>
                )}
              </button>
            ))}

            {/* Evidence section */}
            <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text3)', marginTop: 16, marginBottom: 8 }}>Evidence</div>
            {[
              { icon: '🗃', label: 'GL data' },
              { icon: '⚖', label: 'Trial balance' },
              { icon: '📬', label: 'Confirmations', count: 3 },
              { icon: '📑', label: 'Contracts' },
            ].map((item, i) => (
              <button key={i} style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 6, border: 'none', background: 'transparent', cursor: 'pointer', fontFamily: 'var(--font)', marginBottom: 1 }}>
                <span style={{ fontSize: 12 }}>{item.icon}</span>
                <span style={{ flex: 1, fontSize: 12, color: 'var(--text2)', textAlign: 'left' }}>{item.label}</span>
                {item.count && <span style={{ fontSize: 10, color: 'var(--text3)' }}>{item.count}</span>}
              </button>
            ))}

            {/* Capabilities section */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 16, marginBottom: 8 }}>
              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text3)' }}>Capabilities</div>
              <div style={{ display: 'flex', gap: 4 }}>
                {(['live', 'beta', 'soon'] as const).map(t => (
                  <span key={t} style={{ fontSize: 8, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em', color: TIER_COLOR[t] }}>{t}</span>
                ))}
              </div>
            </div>
            {CAPABILITIES.map((cap, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '5px 8px', borderRadius: 6, marginBottom: 2 }}>
                <div style={{ width: 7, height: 7, borderRadius: '50%', background: TIER_COLOR[cap.tier], flexShrink: 0, marginTop: 3 }} />
                <div>
                  <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text2)' }}>{cap.label}</div>
                  <div style={{ fontSize: 10, color: 'var(--text3)', lineHeight: 1.45, marginTop: 1 }}>{cap.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ═══ CENTRE — Chat ══════════════════════════════════════════════════ */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>

          {/* Mode tabs */}
          <div style={{ height: 40, flexShrink: 0, display: 'flex', alignItems: 'center', borderBottom: '1px solid var(--border)', background: 'var(--bg1)', padding: '0 16px', gap: 4 }}>
            {MODES.map(m => (
              <button key={m.key} onClick={() => setMode(m.key)}
                style={{ height: 28, padding: '0 12px', borderRadius: 6, border: 'none', background: mode === m.key ? 'rgba(108,99,255,.12)' : 'transparent', color: mode === m.key ? 'var(--accent2)' : 'var(--text2)', fontSize: 12, fontWeight: mode === m.key ? 500 : 400, cursor: 'pointer', fontFamily: 'var(--font)', transition: 'all .12s' }}>
                {m.label}
              </button>
            ))}
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
            {messages.map(msg => (
              <div key={msg.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', animation: 'fadeIn .2s ease' }}>
                {/* Avatar */}
                <div style={{ width: 28, height: 28, borderRadius: '50%', flexShrink: 0, background: msg.role === 'assistant' ? 'linear-gradient(135deg, var(--accent), var(--teal))' : 'var(--bg3)', border: '1px solid var(--border2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: msg.role === 'assistant' ? 11 : 12, fontWeight: 600, color: msg.role === 'assistant' ? 'white' : 'var(--text2)' }}>
                  {msg.role === 'assistant' ? 'AI' : 'VR'}
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  {/* Mode badge */}
                  {msg.role === 'assistant' && (
                    <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 5 }}>
                      AuditAI · <span style={{ color: 'var(--accent2)' }}>{MODES.find(m => m.key === msg.mode)?.label ?? msg.mode} mode</span>
                    </div>
                  )}

                  {/* Bubble */}
                  <div style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.65, padding: msg.role === 'assistant' ? '12px 14px' : '10px 14px', background: msg.role === 'assistant' ? 'var(--bg2)' : 'rgba(108,99,255,.08)', borderRadius: msg.role === 'assistant' ? '4px 12px 12px 12px' : '12px 4px 12px 12px', border: `1px solid ${msg.role === 'assistant' ? 'var(--border)' : 'rgba(108,99,255,.2)'}`, maxWidth: 680 }}>
                    {/* Render bold markdown inline */}
                    {msg.content.split(/\*\*([^*]+)\*\*/g).map((part, i) =>
                      i % 2 === 1 ? <strong key={i}>{part}</strong> : part
                    )}
                  </div>

                  {/* Anomaly summary card */}
                  {msg.anomalyCard && eng.anomalies.length > 0 && (
                    <div style={{ maxWidth: 480 }}>
                      <ChatAnomalyCard anomalies={eng.anomalies.filter(a => a.severity === 'high')} />
                    </div>
                  )}

                  {/* Action buttons (assistant messages only) */}
                  {msg.role === 'assistant' && msg.mode === 'anomaly_review' && (
                    <div style={{ display: 'flex', gap: 5, marginTop: 8, flexWrap: 'wrap' }}>
                      {[
                        { label: '⇄ Compare to prior year' },
                        { label: '↗ Show JE history' },
                        { label: '+ Add to work paper' },
                        { label: '⚠ Escalate to manager' },
                      ].map(btn => (
                        <button key={btn.label}
                          style={{ height: 26, padding: '0 10px', borderRadius: 6, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text2)', fontSize: 11, cursor: 'pointer', fontFamily: 'var(--font)' }}>
                          {btn.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Typing indicator */}
            {chatMut.isPending && (
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'linear-gradient(135deg, var(--accent), var(--teal))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, color: 'white' }}>AI</div>
                <div style={{ padding: '12px 16px', background: 'var(--bg2)', borderRadius: '4px 12px 12px 12px', border: '1px solid var(--border)', display: 'flex', gap: 4, alignItems: 'center' }}>
                  {[0, 0.2, 0.4].map(d => (
                    <div key={d} style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent2)', animation: `pulse 1.2s ${d}s infinite` }} />
                  ))}
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input bar */}
          <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', background: 'var(--bg1)', display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            {/* Mode selector chip */}
            <div style={{ flexShrink: 0 }}>
              <select value={mode} onChange={e => setMode(e.target.value as ModeKey)}
                style={{ height: 32, padding: '0 8px', borderRadius: 6, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--accent2)', fontSize: 11, fontWeight: 500, fontFamily: 'var(--font)', cursor: 'pointer', outline: 'none' }}>
                {MODES.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
              </select>
            </div>

            {/* Text input */}
            <textarea value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder={
                mode === 'anomaly_review'  ? 'Ask about a specific anomaly or finding…' :
                mode === 'draft_workpaper' ? 'Tell me which section to draft…' :
                mode === 'interview_prep'  ? 'Generate questions for a specific role or assertion…' :
                'Ask anything about the engagement…'
              }
              rows={1}
              style={{ flex: 1, resize: 'none', background: 'var(--bg2)', border: '1px solid var(--border2)', borderRadius: 8, color: 'var(--text)', fontFamily: 'var(--font)', fontSize: 13, padding: '8px 12px', outline: 'none', lineHeight: 1.5, maxHeight: 120, overflowY: 'auto' }}
            />

            {/* Send */}
            <button onClick={send} disabled={!input.trim() || chatMut.isPending}
              style={{ width: 36, height: 36, borderRadius: 8, border: 'none', background: input.trim() && !chatMut.isPending ? 'var(--accent)' : 'var(--bg3)', color: 'white', cursor: input.trim() && !chatMut.isPending ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transition: 'background .15s' }}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 7h10M8 3l4 4-4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </button>
          </div>
        </div>

        {/* ═══ RIGHT PANEL (284px) ════════════════════════════════════════════ */}
        <div style={{ width: 284, flexShrink: 0, borderLeft: '1px solid var(--border)', background: 'var(--bg1)', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>

          {/* Work paper section */}
          {displayWP && (
            <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 8 }}>Current document</div>

              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)', lineHeight: 1.3, marginBottom: 3 }}>
                {displayWP.title}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                <span style={{ fontSize: 10, color: 'var(--text3)' }}>{displayWP.code}</span>
                <span style={{ fontSize: 9, color: 'var(--text3)' }}>·</span>
                <span style={{ fontSize: 10, fontWeight: 500, color: WP_STATUS_COL[displayWP.status] }}>
                  {displayWP.status === 'draft' ? 'Draft' : displayWP.status === 'in_review' ? 'In review' : 'Approved'}
                </span>
              </div>

              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 6 }}>Sections</div>
              {displayWP.sections.map(sec => (
                <SectionRow
                  key={sec.id}
                  sec={sec}
                  onDraftClick={() => {}}
                  draftingId={pushAnomalyMut.isPending ? draftingSection : null}
                />
              ))}

              {/* Work paper switcher */}
              <div style={{ marginTop: 10 }}>
                <select
                  value={selectedWP ?? displayWP.id}
                  onChange={e => setSelectedWP(e.target.value)}
                  style={{ width: '100%', height: 28, borderRadius: 5, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text2)', fontSize: 11, fontFamily: 'var(--font)', padding: '0 6px', outline: 'none' }}>
                  {eng.work_papers.map(wp => (
                    <option key={wp.id} value={wp.id}>{wp.code} — {wp.title.slice(0, 32)}{wp.title.length > 32 ? '…' : ''}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {/* Anomaly quick-access */}
          <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border)' }}>
            <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 8 }}>
              Anomalies
              <span style={{ marginLeft: 6, fontWeight: 700, color: openAnomalies.length > 0 ? 'var(--red)' : 'var(--teal)' }}>{openAnomalies.length}</span>
            </div>
            {eng.anomalies.map(a => (
              <AnomalyCard
                key={a.id}
                anomaly={a}
                onAddToWP={() => pushAnomalyMut.mutate(a.id)}
                adding={pushAnomalyMut.isPending && draftingSection === a.id}
              />
            ))}
          </div>

          {/* Interview questions */}
          <div style={{ padding: '14px 16px', flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text3)' }}>
                Interview prep · <span style={{ color: 'var(--accent2)', textTransform: 'none', letterSpacing: 0, fontSize: 10 }}>{roleFilter}</span>
              </div>
              <select value={roleFilter} onChange={e => setRoleFilter(e.target.value)}
                style={{ marginLeft: 'auto', height: 22, borderRadius: 4, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font)', padding: '0 4px', outline: 'none', cursor: 'pointer' }}>
                {['Controller', 'CFO', 'IT Manager'].map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>

            {questions
              ?.filter(q => q.target_role === roleFilter)
              .map(q => <QuestionRow key={q.id} q={q} />)
            }
            {(!questions || questions.filter(q => q.target_role === roleFilter).length === 0) && (
              <div style={{ fontSize: 12, color: 'var(--text3)', padding: '20px 0', textAlign: 'center' }}>
                No questions for {roleFilter}
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}
