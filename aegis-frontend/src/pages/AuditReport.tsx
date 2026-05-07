/**
 * AuditReportPage — Premium AI-generated audit report viewer
 *
 * Sections: Cover · Executive Summary · F-1..F-4 findings · Appendices · Assembly Log
 * Features: Inline management responses · Draft→Review→Publish workflow · Distribution hub
 */
import React, { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { auditReportApi } from '@/api/client'
import type { AuditReport, AuditFinding, AuditRecommendation, FindingResponse } from '@/types'
import { Spinner, Button } from '@/components/ui'

// ─── Colour helpers ───────────────────────────────────────────────────────────
const SEV_COLOR: Record<string, string> = {
  Critical: 'var(--red)', High: 'var(--amber)', Medium: 'var(--blue)', Low: 'var(--teal)',
}
const RATING_COLOR: Record<string, string> = {
  Satisfactory: 'var(--teal)', 'Needs Improvement': 'var(--amber)', Unsatisfactory: 'var(--red)',
}
const TREND_ICON: Record<string, string> = { up: '↑', down: '↓', stable: '→' }
const STATUS_LABELS: Record<string, string> = {
  assembling: 'Assembling…', draft: 'Draft', review: 'Under review', published: 'Published',
}

// ─── Sidebar sections ─────────────────────────────────────────────────────────
type Section =
  | 'cover' | 'exec' | 'finding_0' | 'finding_1' | 'finding_2' | 'finding_3'
  | 'appendix_a' | 'appendix_b' | 'assembly' | 'distribute'

const SIDEBAR_ITEMS: Array<{ id: Section; label: string; indent?: boolean }> = [
  { id: 'cover',      label: 'Cover' },
  { id: 'exec',       label: 'Executive Summary' },
  { id: 'finding_0',  label: 'F-1 Finding', indent: true },
  { id: 'finding_1',  label: 'F-2 Finding', indent: true },
  { id: 'finding_2',  label: 'F-3 Finding', indent: true },
  { id: 'finding_3',  label: 'F-4 Finding', indent: true },
  { id: 'appendix_a', label: 'Appendix A — Risk Matrix' },
  { id: 'appendix_b', label: 'Appendix B — Controls Tested' },
  { id: 'assembly',   label: 'AI Assembly Log' },
  { id: 'distribute', label: 'Distribute' },
]

// ─── Inline finding label overrides ──────────────────────────────────────────
function getSidebarLabel(section: Section, report: AuditReport): string {
  if (section.startsWith('finding_')) {
    const idx = parseInt(section.split('_')[1])
    const f = report.findings[idx]
    if (f) return `${f.id} · ${f.title.slice(0, 22)}${f.title.length > 22 ? '…' : ''}`
  }
  return SIDEBAR_ITEMS.find(i => i.id === section)?.label ?? section
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

const SectionWrap: React.FC<{ id: string; children: React.ReactNode }> = ({ id, children }) => (
  <div id={`section-${id}`} style={{ marginBottom: 56 }}>
    {children}
  </div>
)

const SectionTitle: React.FC<{ children: React.ReactNode; sub?: string }> = ({ children, sub }) => (
  <div style={{ marginBottom: 24 }}>
    <div style={{ fontSize: 11, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 6, fontWeight: 500 }}>
      {sub}
    </div>
    <h2 style={{ fontSize: 22, fontWeight: 300, letterSpacing: '-0.5px', color: 'var(--text)', lineHeight: 1.2 }}>
      {children}
    </h2>
    <div style={{ width: 32, height: 2, background: 'var(--accent)', borderRadius: 2, marginTop: 10 }} />
  </div>
)

const Label: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '.1em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 5 }}>
    {children}
  </div>
)

const Body: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <p style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.75, ...style }}>
    {children}
  </p>
)

const Divider = () => (
  <div style={{ height: 1, background: 'var(--border)', margin: '20px 0' }} />
)

// ─── Assembling skeleton ──────────────────────────────────────────────────────
const AssemblingView: React.FC<{ log: AuditReport['assembly_log'] }> = ({ log }) => {
  const stages = [
    { n: 1, label: 'Executive Summary' },
    { n: 2, label: 'Finding Narratives' },
    { n: 3, label: 'Recommendations' },
    { n: 4, label: 'Document Structure' },
  ]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 32, padding: '60px 0' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 28, fontWeight: 300, letterSpacing: '-0.5px', marginBottom: 8 }}>Assembling report…</div>
        <div style={{ fontSize: 13, color: 'var(--text2)' }}>Claude is running 4 analysis stages. This takes about 30–60 seconds.</div>
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        {stages.map((s, i) => {
          const done = log.some(l => l.stage === s.n && l.status === 'done')
          const active = !done && (i === 0 || log.some(l => l.stage === stages[i - 1].n && l.status === 'done'))
          return (
            <React.Fragment key={s.n}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, minWidth: 100 }}>
                <div style={{
                  width: 36, height: 36, borderRadius: '50%', border: '2px solid',
                  borderColor: done ? 'var(--teal)' : active ? 'var(--accent)' : 'var(--border2)',
                  background: done ? 'rgba(30,185,138,.1)' : 'transparent',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: done ? 16 : 12, color: done ? 'var(--teal)' : active ? 'var(--accent2)' : 'var(--text3)',
                  transition: 'all .3s',
                }}>
                  {done ? '✓' : active ? <span style={{ animation: 'spin 0.8s linear infinite', display: 'inline-block' }}>⟳</span> : s.n}
                </div>
                <div style={{ fontSize: 11, color: done ? 'var(--teal)' : active ? 'var(--accent2)' : 'var(--text3)', textAlign: 'center', fontWeight: done || active ? 500 : 400 }}>
                  {s.label}
                </div>
                {done && log.find(l => l.stage === s.n) && (
                  <div style={{ fontSize: 10, color: 'var(--text3)' }}>{(log.find(l => l.stage === s.n)!.duration_ms / 1000).toFixed(1)}s</div>
                )}
              </div>
              {i < stages.length - 1 && (
                <div style={{ width: 40, height: 2, background: done ? 'var(--teal)' : 'var(--border2)', borderRadius: 2, transition: 'background .3s' }} />
              )}
            </React.Fragment>
          )
        })}
      </div>
    </div>
  )
}

// ─── Finding card ─────────────────────────────────────────────────────────────
const FindingSection: React.FC<{
  finding: AuditFinding
  idx: number
  recommendation: AuditRecommendation | undefined
  existingResponse: FindingResponse | undefined
  reportId: string
  readOnly: boolean
}> = ({ finding, idx, recommendation, existingResponse, reportId, readOnly }) => {
  const [open, setOpen] = useState(false)
  const [responseText, setResponseText] = useState(existingResponse?.response_text ?? recommendation?.management_response_placeholder ?? '')
  const [responderName, setResponderName] = useState(existingResponse?.responder_name ?? '')
  const [responderRole, setResponderRole] = useState(existingResponse?.responder_role ?? '')
  const [targetDate, setTargetDate] = useState(existingResponse?.target_date ?? recommendation?.target_date_label ?? '')
  const [saved, setSaved] = useState(false)
  const qc = useQueryClient()

  const saveMutation = useMutation({
    mutationFn: () => auditReportApi.upsertFindingResponse(reportId, idx, {
      response_text: responseText,
      responder_name: responderName,
      responder_role: responderRole,
      target_date: targetDate,
    }),
    onSuccess: () => {
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      qc.invalidateQueries({ queryKey: ['audit-report', reportId] })
    },
  })

  const color = SEV_COLOR[finding.severity] ?? 'var(--text3)'

  return (
    <SectionWrap id={`finding_${idx}`}>
      {/* Finding header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16, marginBottom: 20 }}>
        <div style={{ flexShrink: 0, width: 44, height: 44, borderRadius: 10, background: color + '18', border: '1px solid ' + color + '44', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span style={{ fontSize: 13, fontWeight: 700, color }}>{finding.id}</span>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 4 }}>
            <h3 style={{ fontSize: 18, fontWeight: 300, letterSpacing: '-0.3px', color: 'var(--text)' }}>{finding.title}</h3>
            <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '.08em', padding: '2px 8px', borderRadius: 4, background: color + '18', color, textTransform: 'uppercase' }}>
              {finding.severity}
            </span>
            <span style={{ fontSize: 10, color: 'var(--text3)', background: 'var(--bg3)', padding: '2px 8px', borderRadius: 4 }}>{finding.domain}</span>
          </div>
        </div>
      </div>

      {/* Observation (always visible) */}
      <div style={{ padding: '14px 16px', background: 'var(--bg2)', borderRadius: 10, border: '1px solid var(--border)', marginBottom: 16 }}>
        <Label>Observation</Label>
        <Body>{finding.observation}</Body>
      </div>

      {/* IIA detail grid (expandable) */}
      <button
        onClick={() => setOpen(v => !v)}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent2)', fontSize: 12, fontWeight: 500, padding: '4px 0', display: 'flex', alignItems: 'center', gap: 6, marginBottom: open ? 16 : 0 }}
      >
        <span style={{ fontSize: 10, transition: 'transform .2s', transform: open ? 'rotate(90deg)' : 'none', display: 'inline-block' }}>▶</span>
        {open ? 'Hide detail' : 'Show IIA criteria · condition · cause · effect'}
      </button>

      {open && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20, animation: 'fadeIn .2s ease' }}>
          {[
            { label: 'Criteria', text: finding.criteria },
            { label: 'Condition', text: finding.condition },
            { label: 'Cause', text: finding.cause },
            { label: 'Effect', text: finding.effect },
          ].map(({ label, text }) => (
            <div key={label} style={{ padding: '12px 14px', background: 'var(--bg3)', borderRadius: 8, border: '1px solid var(--border)' }}>
              <Label>{label}</Label>
              <Body style={{ fontSize: 12, lineHeight: 1.6 }}>{text}</Body>
            </div>
          ))}
        </div>
      )}

      {/* Recommendation */}
      {recommendation && (
        <div style={{ padding: '14px 16px', background: 'rgba(108,99,255,.04)', borderRadius: 10, border: '1px solid rgba(108,99,255,.18)', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <Label>Recommendation</Label>
            <span style={{ marginLeft: 'auto', fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 99, background: 'rgba(108,99,255,.14)', color: 'var(--accent2)' }}>
              {recommendation.priority} priority · {recommendation.target_date_label}
            </span>
          </div>
          <Body style={{ fontSize: 12 }}>{recommendation.recommendation}</Body>
        </div>
      )}

      {/* Management Response box */}
      {!readOnly && (
        <div style={{ padding: '16px', background: 'var(--bg1)', borderRadius: 10, border: '1px solid var(--border2)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Label>Management Response</Label>
            {existingResponse && (
              <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--teal)', fontWeight: 500 }}>✓ Saved</span>
            )}
          </div>
          <textarea
            value={responseText}
            onChange={e => setResponseText(e.target.value)}
            placeholder={recommendation?.management_response_placeholder ?? 'Management agrees with the finding and will…'}
            style={{
              width: '100%', minHeight: 72, background: 'var(--bg2)', border: '1px solid var(--border2)',
              borderRadius: 7, color: 'var(--text)', fontFamily: 'var(--font)', fontSize: 12, lineHeight: 1.6,
              padding: '10px 12px', resize: 'vertical', outline: 'none', boxSizing: 'border-box',
            }}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
            <input
              value={responderName}
              onChange={e => setResponderName(e.target.value)}
              placeholder="Responder name"
              style={{ flex: 1, minWidth: 140, height: 32, background: 'var(--bg2)', border: '1px solid var(--border2)', borderRadius: 6, color: 'var(--text)', fontFamily: 'var(--font)', fontSize: 11, padding: '0 10px', outline: 'none' }}
            />
            <input
              value={responderRole}
              onChange={e => setResponderRole(e.target.value)}
              placeholder="Role / title"
              style={{ flex: 1, minWidth: 120, height: 32, background: 'var(--bg2)', border: '1px solid var(--border2)', borderRadius: 6, color: 'var(--text)', fontFamily: 'var(--font)', fontSize: 11, padding: '0 10px', outline: 'none' }}
            />
            <input
              value={targetDate}
              onChange={e => setTargetDate(e.target.value)}
              placeholder="Target date (e.g. Q3 2025)"
              style={{ flex: 1, minWidth: 140, height: 32, background: 'var(--bg2)', border: '1px solid var(--border2)', borderRadius: 6, color: 'var(--text)', fontFamily: 'var(--font)', fontSize: 11, padding: '0 10px', outline: 'none' }}
            />
            <Button
              variant="primary" size="sm"
              onClick={() => saveMutation.mutate()}
              loading={saveMutation.isPending}
            >
              {saved ? '✓ Saved' : 'Save response'}
            </Button>
          </div>
        </div>
      )}

      {/* Read-only saved response */}
      {readOnly && existingResponse && (
        <div style={{ padding: '14px 16px', background: 'rgba(30,185,138,.05)', borderRadius: 10, border: '1px solid rgba(30,185,138,.2)' }}>
          <Label>Management Response</Label>
          <Body style={{ fontSize: 12 }}>{existingResponse.response_text}</Body>
          {(existingResponse.responder_name || existingResponse.target_date) && (
            <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text3)' }}>
              {existingResponse.responder_name && <span>{existingResponse.responder_name}{existingResponse.responder_role ? ` · ${existingResponse.responder_role}` : ''}</span>}
              {existingResponse.target_date && <span style={{ marginLeft: 12 }}>Target: {existingResponse.target_date}</span>}
            </div>
          )}
        </div>
      )}
    </SectionWrap>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────────────────────
export const AuditReportPage: React.FC = () => {
  const { reportId } = useParams<{ reportId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [activeSection, setActiveSection] = useState<Section>('cover')
  const mainRef = useRef<HTMLDivElement>(null)

  const { data: report, isLoading } = useQuery({
    queryKey: ['audit-report', reportId],
    queryFn: () => auditReportApi.get(reportId!),
    refetchInterval: (query) => {
      const d = query.state.data as AuditReport | undefined
      return d?.status === 'assembling' ? 3000 : false
    },
    enabled: !!reportId,
  })

  const statusMutation = useMutation({
    mutationFn: (status: string) => auditReportApi.updateStatus(reportId!, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['audit-report', reportId] }),
  })

  // Scroll to section when sidebar clicked
  const scrollTo = (section: Section) => {
    setActiveSection(section)
    const el = document.getElementById(`section-${section}`)
    if (el && mainRef.current) {
      mainRef.current.scrollTo({ top: el.offsetTop - 24, behavior: 'smooth' })
    }
  }

  // Update active section on scroll
  useEffect(() => {
    const main = mainRef.current
    if (!main) return
    const handler = () => {
      const sections = SIDEBAR_ITEMS.map(i => i.id)
      for (let i = sections.length - 1; i >= 0; i--) {
        const el = document.getElementById(`section-${sections[i]}`)
        if (el && el.offsetTop - 100 <= main.scrollTop) {
          setActiveSection(sections[i])
          break
        }
      }
    }
    main.addEventListener('scroll', handler)
    return () => main.removeEventListener('scroll', handler)
  }, [report])

  if (isLoading || !report) {
    return (
      <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spinner />
      </div>
    )
  }

  const isAssembling = report.status === 'assembling'
  const isPublished = report.status === 'published'
  const readOnly = isPublished
  const ratingColor = RATING_COLOR[report.overall_rating ?? ''] ?? 'var(--text3)'

  // Next status action
  const nextAction = report.status === 'draft' ? { label: 'Submit for review', next: 'review' }
    : report.status === 'review' ? { label: 'Publish report', next: 'published' }
    : null

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Top bar */}
      <div style={{
        height: 52, flexShrink: 0, display: 'flex', alignItems: 'center', padding: '0 20px',
        borderBottom: '1px solid var(--border)', background: 'var(--bg1)', gap: 12,
      }}>
        <button
          onClick={() => navigate('/audit')}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', fontSize: 12, display: 'flex', alignItems: 'center', gap: 5 }}
        >
          ← Back to Audit Planner
        </button>
        <div style={{ width: 1, height: 16, background: 'var(--border2)' }} />
        <div style={{ flex: 1, fontSize: 13, fontWeight: 400, color: 'var(--text)', letterSpacing: '-0.2px' }}>
          {report.title}
        </div>

        {/* Status badge */}
        <div style={{
          fontSize: 11, fontWeight: 500, padding: '3px 10px', borderRadius: 99,
          background: isAssembling ? 'rgba(108,99,255,.15)' : isPublished ? 'rgba(30,185,138,.12)' : 'rgba(232,168,56,.12)',
          color: isAssembling ? 'var(--accent2)' : isPublished ? 'var(--teal)' : 'var(--amber)',
          display: 'flex', alignItems: 'center', gap: 5,
        }}>
          {isAssembling && <span style={{ animation: 'spin 0.8s linear infinite', display: 'inline-block', fontSize: 10 }}>⟳</span>}
          {STATUS_LABELS[report.status]}
        </div>

        {/* Overall rating */}
        {report.overall_rating && !isAssembling && (
          <div style={{ fontSize: 11, fontWeight: 600, padding: '3px 10px', borderRadius: 99, background: ratingColor + '18', color: ratingColor, border: '1px solid ' + ratingColor + '40' }}>
            {report.overall_rating}
          </div>
        )}

        {/* Action buttons */}
        {!isAssembling && (
          <div style={{ display: 'flex', gap: 6 }}>
            {nextAction && (
              <Button variant="primary" size="sm" onClick={() => statusMutation.mutate(nextAction.next)} loading={statusMutation.isPending}>
                {nextAction.label}
              </Button>
            )}
            {isPublished && (
              <Button variant="ghost" size="sm" onClick={() => scrollTo('distribute')}>
                Distribute
              </Button>
            )}
          </div>
        )}
      </div>

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left sidebar */}
        <div style={{
          width: 220, flexShrink: 0, borderRight: '1px solid var(--border)',
          background: 'var(--bg1)', overflowY: 'auto', padding: '16px 0',
        }}>
          <div style={{ padding: '0 14px', marginBottom: 12 }}>
            <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text3)' }}>Contents</div>
          </div>
          {SIDEBAR_ITEMS.map(item => {
            const label = report ? getSidebarLabel(item.id, report) : item.label
            const active = activeSection === item.id
            // Hide finding sections if not enough findings
            if (item.id.startsWith('finding_')) {
              const idx = parseInt(item.id.split('_')[1])
              if (report.findings.length <= idx && !isAssembling) return null
            }
            return (
              <button
                key={item.id}
                onClick={() => scrollTo(item.id)}
                style={{
                  width: '100%', background: active ? 'rgba(108,99,255,.1)' : 'none',
                  border: 'none', borderLeft: `2px solid ${active ? 'var(--accent)' : 'transparent'}`,
                  cursor: 'pointer', padding: '7px 14px 7px ' + (item.indent ? '22px' : '14px'),
                  textAlign: 'left', transition: 'all .12s',
                  color: active ? 'var(--accent2)' : 'var(--text2)',
                  fontSize: item.indent ? 11 : 12,
                  fontFamily: 'var(--font)',
                  fontWeight: active ? 500 : 400,
                }}
              >
                {label}
              </button>
            )
          })}
        </div>

        {/* Main content */}
        <div ref={mainRef} style={{ flex: 1, overflowY: 'auto', padding: '32px 48px', maxWidth: 860 }}>
          {isAssembling ? (
            <AssemblingView log={report.assembly_log} />
          ) : (
            <>
              {/* ── Cover ──────────────────────────────────────────────────── */}
              <SectionWrap id="cover">
                <div style={{ padding: '48px 0 32px' }}>
                  <div style={{ fontSize: 10, letterSpacing: '.15em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 16, fontWeight: 600 }}>
                    Internal Audit Report
                  </div>
                  <h1 style={{ fontSize: 36, fontWeight: 300, letterSpacing: '-1px', lineHeight: 1.15, color: 'var(--text)', marginBottom: 20, maxWidth: 560 }}>
                    {report.exec_summary?.headline ?? report.title}
                  </h1>
                  <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 32 }}>
                    <div><Label>Period</Label><div style={{ fontSize: 13, color: 'var(--text)' }}>{report.exec_summary?.period ?? `${report.period_start} – ${report.period_end}`}</div></div>
                    <div><Label>Status</Label><div style={{ fontSize: 13, color: 'var(--text)' }}>{STATUS_LABELS[report.status]}</div></div>
                    {report.overall_rating && (
                      <div>
                        <Label>Overall rating</Label>
                        <div style={{ fontSize: 13, fontWeight: 600, color: ratingColor }}>{report.overall_rating}</div>
                      </div>
                    )}
                    {report.doc_structure?.independence_statement && (
                      <div style={{ width: '100%' }}>
                        <Label>Independence</Label>
                        <div style={{ fontSize: 11, color: 'var(--text3)', fontStyle: 'italic' }}>{report.doc_structure.independence_statement}</div>
                      </div>
                    )}
                  </div>

                  {/* Key metrics strip */}
                  {report.exec_summary?.key_metrics && report.exec_summary.key_metrics.length > 0 && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12 }}>
                      {report.exec_summary.key_metrics.map((m, i) => (
                        <div key={i} style={{ padding: '14px 16px', background: 'var(--bg2)', borderRadius: 10, border: '1px solid var(--border)' }}>
                          <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 4 }}>{m.label}</div>
                          <div style={{ fontSize: 20, fontWeight: 300, letterSpacing: '-0.5px', color: 'var(--text)' }}>
                            {m.value}
                          </div>
                          <div style={{ fontSize: 11, color: m.trend === 'up' ? 'var(--teal)' : m.trend === 'down' ? 'var(--red)' : 'var(--text3)', marginTop: 2 }}>
                            {TREND_ICON[m.trend] ?? '→'} {m.trend}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </SectionWrap>

              {/* ── Executive Summary ─────────────────────────────────────── */}
              <SectionWrap id="exec">
                <SectionTitle sub="Section 1">Executive Summary</SectionTitle>
                {report.exec_summary?.body && <Body style={{ marginBottom: 20 }}>{report.exec_summary.body}</Body>}
                {report.exec_summary?.audit_scope && (
                  <>
                    <Divider />
                    <Label>Audit Scope</Label>
                    <Body style={{ marginBottom: 16 }}>{report.exec_summary.audit_scope}</Body>
                  </>
                )}
                {report.exec_summary?.limitations && (
                  <>
                    <Label>Scope Limitations</Label>
                    <Body style={{ fontSize: 12, color: 'var(--text3)', fontStyle: 'italic' }}>{report.exec_summary.limitations}</Body>
                  </>
                )}
                {report.doc_structure?.scope_statement && (
                  <>
                    <Divider />
                    <Label>Scope Statement</Label>
                    <Body style={{ fontSize: 12 }}>{report.doc_structure.scope_statement}</Body>
                  </>
                )}
                {report.doc_structure?.methodology && (
                  <>
                    <div style={{ height: 12 }} />
                    <Label>Methodology</Label>
                    <Body style={{ fontSize: 12 }}>{report.doc_structure.methodology}</Body>
                  </>
                )}
              </SectionWrap>

              {/* ── Findings ──────────────────────────────────────────────── */}
              {report.findings.length > 0 && (
                <div>
                  <div style={{ marginBottom: 24 }}>
                    <div style={{ fontSize: 10, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 6, fontWeight: 600 }}>Section 2</div>
                    <h2 style={{ fontSize: 22, fontWeight: 300, letterSpacing: '-0.5px' }}>Audit Findings</h2>
                    <div style={{ width: 32, height: 2, background: 'var(--accent)', borderRadius: 2, marginTop: 10, marginBottom: 6 }} />
                    <Body style={{ fontSize: 12 }}>{report.findings.length} findings identified, ordered by severity.</Body>
                  </div>
                  {report.findings.map((f, idx) => (
                    <FindingSection
                      key={f.id}
                      finding={f}
                      idx={idx}
                      recommendation={report.recommendations.find(r => r.finding_id === f.id)}
                      existingResponse={report.finding_responses.find(r => r.finding_index === idx)}
                      reportId={report.id}
                      readOnly={readOnly}
                    />
                  ))}
                </div>
              )}

              {/* ── Appendix A — Risk Matrix ──────────────────────────────── */}
              <SectionWrap id="appendix_a">
                <SectionTitle sub="Appendix A">Risk Matrix</SectionTitle>
                {report.doc_structure?.appendix_a_risk_matrix ? (
                  <>
                    <Body style={{ marginBottom: 20, fontSize: 12 }}>{report.doc_structure.appendix_a_risk_matrix.description}</Body>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead>
                        <tr>
                          {['Domain', 'Inherent', 'Residual', 'Trend'].map(h => (
                            <th key={h} style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '1px solid var(--border2)', fontSize: 10, fontWeight: 600, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text3)' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {report.doc_structure.appendix_a_risk_matrix.matrix.map((row, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                            <td style={{ padding: '10px 12px', color: 'var(--text)', fontWeight: 500 }}>{row.domain}</td>
                            <td style={{ padding: '10px 12px', color: row.inherent === 'H' ? 'var(--red)' : row.inherent === 'M' ? 'var(--amber)' : 'var(--teal)', fontWeight: 600 }}>{row.inherent === 'H' ? 'High' : row.inherent === 'M' ? 'Medium' : 'Low'}</td>
                            <td style={{ padding: '10px 12px', color: row.residual === 'H' ? 'var(--red)' : row.residual === 'M' ? 'var(--amber)' : 'var(--teal)', fontWeight: 600 }}>{row.residual === 'H' ? 'High' : row.residual === 'M' ? 'Medium' : 'Low'}</td>
                            <td style={{ padding: '10px 12px', color: 'var(--text2)', fontSize: 14 }}>{row.trend}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                ) : (
                  <Body style={{ color: 'var(--text3)', fontSize: 12 }}>Risk matrix not yet generated.</Body>
                )}
              </SectionWrap>

              {/* ── Appendix B — Controls Tested ─────────────────────────── */}
              <SectionWrap id="appendix_b">
                <SectionTitle sub="Appendix B">Controls Tested</SectionTitle>
                {report.doc_structure?.appendix_b_controls_tested ? (
                  <>
                    <Body style={{ marginBottom: 20, fontSize: 12 }}>{report.doc_structure.appendix_b_controls_tested.description}</Body>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead>
                        <tr>
                          {['Control', 'Type', 'Result', 'Sample'].map(h => (
                            <th key={h} style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '1px solid var(--border2)', fontSize: 10, fontWeight: 600, letterSpacing: '.08em', textTransform: 'uppercase', color: 'var(--text3)' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {report.doc_structure.appendix_b_controls_tested.items.map((row, i) => {
                          const resultColor = row.result === 'Effective' ? 'var(--teal)' : row.result === 'Partial' ? 'var(--amber)' : 'var(--red)'
                          return (
                            <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                              <td style={{ padding: '10px 12px', color: 'var(--text)', fontWeight: 500 }}>{row.control}</td>
                              <td style={{ padding: '10px 12px', color: 'var(--text2)' }}>{row.type}</td>
                              <td style={{ padding: '10px 12px' }}>
                                <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4, background: resultColor + '18', color: resultColor }}>{row.result}</span>
                              </td>
                              <td style={{ padding: '10px 12px', color: 'var(--text3)' }}>n={row.sample_size}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </>
                ) : (
                  <Body style={{ color: 'var(--text3)', fontSize: 12 }}>Controls appendix not yet generated.</Body>
                )}
              </SectionWrap>

              {/* ── AI Assembly Log ───────────────────────────────────────── */}
              <SectionWrap id="assembly">
                <SectionTitle sub="Appendix C">AI Assembly Log</SectionTitle>
                <Body style={{ marginBottom: 20, fontSize: 12 }}>
                  This report was assembled by the Aegis AI pipeline using {report.assembly_log.length} sequential analysis stages.
                  Total assembly time: {report.assembly_log.reduce((a, l) => a + l.duration_ms, 0) / 1000}s
                </Body>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {report.assembly_log.map(l => (
                    <div key={l.stage} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--bg2)', borderRadius: 8, border: '1px solid var(--border)' }}>
                      <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'rgba(30,185,138,.1)', border: '1px solid rgba(30,185,138,.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, color: 'var(--teal)', fontWeight: 600, flexShrink: 0 }}>
                        {l.stage}
                      </div>
                      <div style={{ flex: 1, fontSize: 12, color: 'var(--text)' }}>{l.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--teal)', fontWeight: 500 }}>✓ {(l.duration_ms / 1000).toFixed(1)}s</div>
                    </div>
                  ))}
                  {report.assembled_at && (
                    <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>
                      Assembled at {new Date(report.assembled_at).toLocaleString()}
                    </div>
                  )}
                </div>
              </SectionWrap>

              {/* ── Distribute ────────────────────────────────────────────── */}
              <SectionWrap id="distribute">
                <SectionTitle sub="Distribution">Share &amp; Distribute</SectionTitle>
                <Body style={{ marginBottom: 24, fontSize: 12 }}>
                  {isPublished
                    ? 'Report is published. Mark distribution channels below.'
                    : 'Publish the report first before distributing to stakeholders.'}
                </Body>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  {[
                    { key: 'audit_committee', label: 'Audit Committee', icon: '🏛', desc: 'Quarterly oversight body' },
                    { key: 'board', label: 'Board', icon: '📋', desc: 'Board of directors' },
                    { key: 'control_owners', label: 'Control Owners', icon: '🔧', desc: 'Operational leads' },
                    { key: 'regulator', label: 'Regulator', icon: '⚖️', desc: 'DNB / AFM submission' },
                  ].map(({ key, label, icon, desc }) => {
                    const enabled = report.distribution?.[key as keyof typeof report.distribution]
                    return (
                      <div key={key} style={{
                        padding: '16px', borderRadius: 10,
                        border: `1px solid ${enabled ? 'rgba(30,185,138,.3)' : 'var(--border)'}`,
                        background: enabled ? 'rgba(30,185,138,.04)' : 'var(--bg2)',
                        display: 'flex', gap: 12, alignItems: 'flex-start',
                      }}>
                        <span style={{ fontSize: 20 }}>{icon}</span>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', marginBottom: 3 }}>{label}</div>
                          <div style={{ fontSize: 11, color: 'var(--text3)' }}>{desc}</div>
                        </div>
                        {enabled
                          ? <span style={{ fontSize: 11, color: 'var(--teal)', fontWeight: 500, whiteSpace: 'nowrap' }}>✓ Included</span>
                          : <span style={{ fontSize: 11, color: 'var(--text3)', whiteSpace: 'nowrap' }}>Not included</span>
                        }
                      </div>
                    )
                  })}
                </div>
                {isPublished && report.published_at && (
                  <div style={{ marginTop: 20, padding: '12px 16px', background: 'rgba(30,185,138,.06)', borderRadius: 8, border: '1px solid rgba(30,185,138,.2)', fontSize: 12, color: 'var(--teal)' }}>
                    ✓ Published {new Date(report.published_at).toLocaleString()} · PDF export available in your email
                  </div>
                )}
              </SectionWrap>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
