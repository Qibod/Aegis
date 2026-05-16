// ── Radar page ────────────────────────────────────────────────────────────────
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Radio, Scale, ShieldAlert, Network, Globe,
  X, AlertTriangle, CheckCircle2, Clock, DollarSign,
  Activity, MapPin, Package, Workflow, Shield, ChevronRight,
} from 'lucide-react'
import { radarApi, pulseApi, auditApi, controlsApi, auditReportApi } from '@/api/client'
import { Button, SeverityChip, StatusChip, Chip, EmptyState, Spinner, ProgressBar, LiveDot, Input } from '@/components/ui'
import type { Signal, PulseControl, AuditPlan, AuditTask, Control } from '@/types'

// ── Impact derivation ─────────────────────────────────────────────────────────

interface ImpactData {
  effectiveDateStr: string
  daysUntil: number
  geos: Array<{ code: string; name: string; revenue_pct?: number }>
  processes: Array<{ name: string; severity: string; change_required: string }>
  products: Array<{ name: string; type: string; impact: string }>
  financialLines: Array<{ label: string; value: string; type: 'cost' | 'revenue_risk' | 'fine' }>
  opImpacts: string[]
  guardrails: Array<{ name: string; status: 'in_place' | 'partial'; note?: string }>
  gaps: string[]
}

function deriveImpact(sig: Signal): ImpactData {
  const combined = [sig.title, sig.body ?? '', ...sig.tags].join(' ').toLowerCase()

  // ── Geographies ──────────────────────────────────────────────────────────
  const geos: ImpactData['geos'] = []
  if (/\beu\b|european union|gdpr|dora|mica|ai act|esma|eba/.test(combined))
    geos.push({ code: 'EU', name: 'European Union', revenue_pct: 38 })
  if (/\buk\b|united kingdom|fca|pra|hmrc/.test(combined))
    geos.push({ code: 'UK', name: 'United Kingdom', revenue_pct: 22 })
  if (/\bus\b|united states|sec|finra|occ|ffiec|cfpb/.test(combined))
    geos.push({ code: 'US', name: 'United States', revenue_pct: 45 })
  if (/singapore|mas\b|monetary authority of singapore/.test(combined))
    geos.push({ code: 'SG', name: 'Singapore', revenue_pct: 12 })
  if (/apac|asia pacific|hong kong|japan/.test(combined))
    geos.push({ code: 'APAC', name: 'Asia-Pacific', revenue_pct: 18 })
  if (geos.length === 0)
    geos.push({ code: 'GLOBAL', name: 'Global', revenue_pct: 100 })

  // ── Processes ─────────────────────────────────────────────────────────────
  const processes: ImpactData['processes'] = []
  if (/kyc|know your customer|onboard|identity verif/.test(combined))
    processes.push({ name: 'Customer Onboarding & KYC', severity: 'high', change_required: 'Enhanced verification steps and data retention protocols' })
  if (/aml|anti.money|financial crime|transaction monitor/.test(combined))
    processes.push({ name: 'AML Transaction Monitoring', severity: 'high', change_required: 'Screening rule updates and alert threshold recalibration' })
  if (/\bdata\b|privacy|gdpr|consent|retention/.test(combined))
    processes.push({ name: 'Data Governance & Privacy', severity: 'critical', change_required: 'New consent flows, DPIAs, and data minimisation protocols' })
  if (/\bai\b|model risk|algorithm|automated decision|machine learning/.test(combined))
    processes.push({ name: 'AI / ML Model Deployment', severity: 'critical', change_required: 'Conformity assessment and human-oversight integration required' })
  if (/vendor|third.party|supply chain|outsourc/.test(combined))
    processes.push({ name: 'Vendor Risk Management', severity: 'high', change_required: 'Enhanced due diligence cadence and contractual clause uplift' })
  if (/cyber|incident|breach|vulnerability|ransomware/.test(combined))
    processes.push({ name: 'Incident Response & CSIRT', severity: 'high', change_required: 'Notification timelines shortened; escalation paths to be updated' })
  if (/payment|settlement|transfer|swift/.test(combined))
    processes.push({ name: 'Payments Processing', severity: 'medium', change_required: 'Transaction screening and routing rule updates' })
  if (/credit|lending|loan|underwriting/.test(combined))
    processes.push({ name: 'Credit Underwriting', severity: 'medium', change_required: 'Explainability requirements trigger model and process changes' })
  if (processes.length === 0)
    processes.push({ name: 'Compliance & Risk Management', severity: 'medium', change_required: 'Policy review and targeted control uplift required' })

  // ── Products ──────────────────────────────────────────────────────────────
  const products: ImpactData['products'] = []
  if (/\bai\b|model risk|algorithm|automated decision/.test(combined))
    products.push({ name: 'AI Decision Engine', type: 'system', impact: 'Conformity assessment gate required before next production release' })
  if (/payment|transfer|wallet/.test(combined))
    products.push({ name: 'Payments Platform', type: 'product', impact: 'Screening logic and transaction routing may need redesign' })
  if (/credit|lending|loan/.test(combined))
    products.push({ name: 'Credit Assessment', type: 'product', impact: 'Per-applicant explainability output now required by regulation' })
  if (/kyc|onboard|identity/.test(combined))
    products.push({ name: 'Onboarding Suite', type: 'product', impact: 'Biometric & document check standards updated; re-certification needed' })
  if (/trading|investment|portfolio/.test(combined))
    products.push({ name: 'Investment Platform', type: 'service', impact: 'Suitability framework and disclosure language require updates' })
  if (/vendor|third.party/.test(combined))
    products.push({ name: 'Vendor Portal', type: 'system', impact: 'Due diligence questionnaire and risk scoring model overhaul' })
  if (products.length === 0)
    products.push({ name: 'Core Platform', type: 'system', impact: 'Compliance controls and reporting modules will be impacted' })

  // ── Financial impact ──────────────────────────────────────────────────────
  const financialLines: ImpactData['financialLines'] = []
  if (sig.category === 'regulatory') {
    if (sig.severity === 'critical') {
      financialLines.push({ label: 'Compliance implementation cost', value: '+$1.5M – $3.2M', type: 'cost' })
      financialLines.push({ label: 'Revenue at risk (non-compliance)', value: '$4.8M – $12M ARR', type: 'revenue_risk' })
      financialLines.push({ label: 'Maximum regulatory fine', value: '€30M or 6% of global revenue', type: 'fine' })
    } else if (sig.severity === 'high') {
      financialLines.push({ label: 'Compliance implementation cost', value: '+$600K – $1.4M', type: 'cost' })
      financialLines.push({ label: 'Revenue at risk (non-compliance)', value: '$1.2M – $3.6M ARR', type: 'revenue_risk' })
      financialLines.push({ label: 'Maximum regulatory fine', value: '€10M or 2% of global revenue', type: 'fine' })
    } else {
      financialLines.push({ label: 'Compliance adaptation cost', value: '+$150K – $450K', type: 'cost' })
    }
  } else if (sig.category === 'threat') {
    if (sig.severity === 'critical') {
      financialLines.push({ label: 'Breach remediation cost', value: '$2.1M – $5.4M', type: 'cost' })
      financialLines.push({ label: 'Customer churn / LTV at risk', value: '$8M – $15M', type: 'revenue_risk' })
      financialLines.push({ label: 'Regulatory fine (data breach)', value: 'Up to €20M or 4% of revenue', type: 'fine' })
    } else {
      financialLines.push({ label: 'Incident response & remediation', value: '$200K – $900K', type: 'cost' })
      financialLines.push({ label: 'Reputational revenue risk', value: '$500K – $2M', type: 'revenue_risk' })
    }
  } else if (sig.category === 'vendor') {
    financialLines.push({ label: 'Vendor replacement or uplift cost', value: '$250K – $1.2M', type: 'cost' })
    financialLines.push({ label: 'Service disruption impact', value: '$100K – $400K per week', type: 'revenue_risk' })
  } else {
    financialLines.push({ label: 'Operational adaptation cost', value: '$100K – $500K', type: 'cost' })
    financialLines.push({ label: 'Market access / revenue risk', value: '$500K – $3M ARR', type: 'revenue_risk' })
  }

  // ── Operational impacts ───────────────────────────────────────────────────
  const opImpacts: string[] = []
  if (sig.category === 'regulatory') {
    opImpacts.push('Policy and procedure documentation update: 4–8 weeks')
    if (sig.severity === 'critical' || sig.severity === 'high') {
      opImpacts.push('Product release freeze until conformity confirmed: 6–12 weeks')
      opImpacts.push('Additional compliance headcount required: +2–4 FTE')
      opImpacts.push('Board-level sign-off gate required before feature deployment')
      opImpacts.push('Legal counsel engagement for regulatory mapping: 3–6 weeks')
    }
  } else if (sig.category === 'threat') {
    opImpacts.push('Emergency patch cycle across affected systems: 48–72 hrs')
    opImpacts.push('Full penetration test and vulnerability re-scan: 3–4 weeks')
    opImpacts.push('Incident response tabletop exercise for CSIRT team')
    opImpacts.push('Customer notification protocol activated if breach is confirmed')
  } else if (sig.category === 'vendor') {
    opImpacts.push('Vendor risk re-assessment and updated scoring: 2–3 weeks')
    opImpacts.push('Contingency and failover testing for dependent systems: 4–6 weeks')
    opImpacts.push('Contract renegotiation or replacement RFP: 8–16 weeks')
  } else {
    opImpacts.push('Risk exposure assessment across affected business lines')
    opImpacts.push('Scenario planning with finance and strategy teams: 2–4 weeks')
    opImpacts.push('Customer-facing communications review if market-visible')
  }

  // ── Guardrails in place ───────────────────────────────────────────────────
  const guardrails: ImpactData['guardrails'] = []
  if (sig.impacted_control_ids.length > 0)
    guardrails.push({
      name: `${sig.impacted_control_ids.length} existing control${sig.impacted_control_ids.length !== 1 ? 's' : ''} mapped`,
      status: 'partial',
      note: 'Partially address this signal — gap delta requires CxO review',
    })
  if (/kyc|aml/.test(combined))
    guardrails.push({ name: 'Transaction monitoring (SWIFT-integrated, 24/7)', status: 'in_place', note: 'Covers 100% of payment flows' })
  if (/\bdata\b|privacy/.test(combined))
    guardrails.push({ name: 'Data classification and handling policy', status: 'partial', note: 'Missing cross-border transfer protocols for new jurisdictions' })
  if (/cyber|threat|breach/.test(combined))
    guardrails.push({ name: 'EDR + SIEM deployment', status: 'in_place', note: 'Covers 94% of endpoints; cloud workloads fully instrumented' })
  if (/vendor/.test(combined))
    guardrails.push({ name: 'Vendor risk assessment framework', status: 'partial', note: 'Tier 1 vendors covered; Tier 2 and sub-processors have gaps' })
  if (/\bai\b|model/.test(combined))
    guardrails.push({ name: 'Model risk management policy', status: 'partial', note: 'Predates EU AI Act — conformity assessment requirement not yet met' })
  if (guardrails.length === 0)
    guardrails.push({ name: 'General compliance framework in place', status: 'partial', note: 'Requires targeted assessment against this specific signal' })

  // ── Gaps ─────────────────────────────────────────────────────────────────
  const gaps: string[] = []
  if (sig.category === 'regulatory' && (sig.severity === 'critical' || sig.severity === 'high')) {
    gaps.push('No documented conformity or impact assessment for this regulation')
    gaps.push('Regulatory registration or notification has not been initiated')
    gaps.push('Board-level governance charter not yet established for this domain')
  }
  if (/\bai\b|model/.test(combined)) {
    gaps.push('Human-in-the-loop controls absent for Tier 1 automated decisions')
    gaps.push('Explainability reports not generated for production-deployed models')
  }
  if (/\bdata\b|privacy/.test(combined)) {
    gaps.push('Cross-border data transfer impact assessments are incomplete')
    gaps.push('Data retention schedule not aligned to new requirements')
  }
  if (/vendor/.test(combined)) {
    gaps.push('Sub-contractor visibility does not extend below Tier 2')
    gaps.push('Exit strategy for critical vendor dependencies not tested')
  }
  if (/cyber|threat/.test(combined)) {
    gaps.push('Threat intelligence feeds not integrated with SIEM alerting rules')
    gaps.push('Regulatory breach notification playbook last reviewed >12 months ago')
  }
  if (gaps.length === 0) {
    gaps.push('Policy uplift and staff awareness training program required')
    gaps.push('Evidence collection cadence needs to be formalised for this domain')
  }

  // ── Effective date ────────────────────────────────────────────────────────
  const base = sig.published_at ? new Date(sig.published_at) : new Date()
  const offsetDays =
    sig.category === 'regulatory'
      ? sig.severity === 'critical' ? 180 : 365
      : sig.category === 'threat'
        ? 0
        : 90
  const effectiveDate = new Date(base.getTime() + offsetDays * 86_400_000)
  const effectiveDateStr = effectiveDate.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })
  const daysUntil = Math.max(0, Math.floor((effectiveDate.getTime() - Date.now()) / 86_400_000))

  return { effectiveDateStr, daysUntil, geos, processes, products, financialLines, opImpacts, guardrails, gaps }
}

// ── Signal impact drawer ──────────────────────────────────────────────────────

const ImpactSection: React.FC<{
  icon: React.ReactNode
  title: string
  children: React.ReactNode
  accentColor?: string
}> = ({ icon, title, children, accentColor = 'var(--accent2)' }) => (
  <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 12 }}>
      <span style={{ color: accentColor, display: 'flex', alignItems: 'center' }}>{icon}</span>
      <span style={{ fontSize: 10, fontWeight: 600, color: accentColor, textTransform: 'uppercase', letterSpacing: '.08em' }}>{title}</span>
    </div>
    {children}
  </div>
)

const SubLabel: React.FC<{ label: string }> = ({ label }) => (
  <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 7 }}>{label}</div>
)

const FIN_COLOR = { cost: 'var(--amber)', revenue_risk: 'var(--red)', fine: '#c05050' } as const
const FIN_ICON  = { cost: '💸', revenue_risk: '📉', fine: '⚖️' } as const

const SignalImpactDrawer: React.FC<{
  signal: Signal
  onClose: () => void
  onDismiss: () => void
  isDismissing: boolean
}> = ({ signal, onClose, onDismiss, isDismissing }) => {
  const impact = deriveImpact(signal)
  const SEV_COLORS: Record<string, string> = {
    critical: 'var(--red)', high: 'var(--amber)', medium: 'var(--blue)', info: 'var(--teal)',
  }
  const sevColor = SEV_COLORS[signal.severity] ?? 'var(--text3)'
  const urgent = impact.daysUntil > 0 && impact.daysUntil < 90

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(10,11,14,.60)', zIndex: 200 }}
      />

      {/* Drawer panel */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 520,
        background: 'var(--bg1)', borderLeft: '1px solid var(--border2)',
        zIndex: 201, display: 'flex', flexDirection: 'column',
        boxShadow: '-12px 0 60px rgba(0,0,0,.45)',
        animation: 'slideInRight .22s ease both',
      }}>

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              {/* Badges row */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 9 }}>
                <span style={{
                  fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 4,
                  background: sevColor + '22', color: sevColor,
                  textTransform: 'uppercase', letterSpacing: '.06em',
                }}>{signal.source}</span>
                <SeverityChip severity={signal.severity} />
                {signal.is_new && (
                  <span style={{
                    fontSize: 9, fontWeight: 600, color: 'var(--accent2)',
                    background: 'rgba(108,99,255,.15)', padding: '2px 7px',
                    borderRadius: 99, letterSpacing: '.04em',
                  }}>NEW</span>
                )}
                {/* Effective date badge */}
                <span style={{
                  display: 'flex', alignItems: 'center', gap: 4,
                  fontSize: 10, fontWeight: 500, padding: '2px 9px', borderRadius: 99,
                  background: urgent ? 'rgba(179,79,66,.14)' : 'rgba(78,128,106,.12)',
                  color: urgent ? 'var(--red)' : 'var(--teal2)',
                  border: `1px solid ${urgent ? 'rgba(179,79,66,.25)' : 'rgba(78,128,106,.2)'}`,
                }}>
                  <Clock size={10} />
                  Effective {impact.effectiveDateStr}
                  {impact.daysUntil > 0 && (
                    <span style={{ opacity: .75 }}>· {impact.daysUntil} days</span>
                  )}
                  {impact.daysUntil === 0 && (
                    <span style={{ fontWeight: 700 }}> · IN EFFECT</span>
                  )}
                </span>
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', lineHeight: 1.35 }}>
                {signal.title}
              </div>
            </div>
            <button
              onClick={onClose}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: 6, color: 'var(--text3)', borderRadius: 6, flexShrink: 0,
                display: 'flex', alignItems: 'center',
              }}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* ── Scrollable body ─────────────────────────────────────────────── */}
        <div style={{ flex: 1, overflowY: 'auto' }}>

          {/* Signal summary */}
          {signal.body && (
            <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)' }}>
              <div style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.65 }}>{signal.body}</div>
            </div>
          )}

          {/* ── Business impact ────────────────────────────────────────────── */}
          <ImpactSection icon={<Workflow size={13} />} title="Business Impact">

            <SubLabel label="Affected Processes" />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
              {impact.processes.map((p, i) => {
                const pc = ({ critical: 'var(--red)', high: 'var(--amber)', medium: 'var(--blue)', low: 'var(--teal)' } as Record<string,string>)[p.severity] ?? 'var(--text3)'
                return (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'flex-start', gap: 10,
                    padding: '9px 11px', borderRadius: 8,
                    background: 'var(--bg2)', border: `1px solid ${pc}22`,
                  }}>
                    <div style={{ width: 6, height: 6, borderRadius: '50%', background: pc, flexShrink: 0, marginTop: 5 }} />
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>{p.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 2, lineHeight: 1.4 }}>{p.change_required}</div>
                    </div>
                  </div>
                )
              })}
            </div>

            <SubLabel label="Affected Products & Systems" />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
              {impact.products.map((p, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 8,
                  padding: '8px 11px', borderRadius: 8,
                  background: 'var(--bg2)', border: '1px solid var(--border)',
                }}>
                  <Package size={12} color="var(--text3)" style={{ flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>{p.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 2 }}>{p.impact}</div>
                  </div>
                </div>
              ))}
            </div>

            <SubLabel label="Affected Geographies" />
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {impact.geos.map((g, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 5,
                  padding: '5px 10px', borderRadius: 99,
                  background: 'rgba(108,99,255,.10)', border: '1px solid rgba(108,99,255,.22)',
                }}>
                  <MapPin size={10} color="var(--accent2)" />
                  <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--accent2)' }}>{g.name}</span>
                  {g.revenue_pct !== undefined && (
                    <span style={{ fontSize: 10, color: 'var(--text3)' }}>{g.revenue_pct}% rev.</span>
                  )}
                </div>
              ))}
            </div>
          </ImpactSection>

          {/* ── Financial impact ───────────────────────────────────────────── */}
          <ImpactSection icon={<DollarSign size={13} />} title="Financial Impact" accentColor="var(--amber)">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
              {impact.financialLines.map((line, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '10px 12px', borderRadius: 8,
                  background: 'var(--bg2)',
                  borderLeft: `3px solid ${FIN_COLOR[line.type]}`,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 14 }}>{FIN_ICON[line.type]}</span>
                    <span style={{ fontSize: 12, color: 'var(--text2)' }}>{line.label}</span>
                  </div>
                  <span style={{
                    fontSize: 12, fontWeight: 700, color: FIN_COLOR[line.type],
                    whiteSpace: 'nowrap', marginLeft: 12,
                  }}>{line.value}</span>
                </div>
              ))}
            </div>
            <div style={{
              padding: '8px 11px', borderRadius: 7,
              background: 'rgba(184,124,58,.06)', border: '1px solid rgba(184,124,58,.18)',
              fontSize: 10, color: 'var(--amber)', lineHeight: 1.6,
            }}>
              Figures assume no remediation initiated within 30 days and reflect the company's current inability to respond. Existing guardrails (below) may reduce exposure.
            </div>
          </ImpactSection>

          {/* ── Operational impact ─────────────────────────────────────────── */}
          <ImpactSection icon={<Activity size={13} />} title="Operational Impact">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              {impact.opImpacts.map((item, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <ChevronRight size={12} color="var(--accent2)" style={{ flexShrink: 0, marginTop: 2 }} />
                  <span style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.5 }}>{item}</span>
                </div>
              ))}
            </div>
          </ImpactSection>

          {/* ── Guardrails in place ────────────────────────────────────────── */}
          <ImpactSection icon={<Shield size={13} />} title="Existing Guardrails" accentColor="var(--teal2)">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {impact.guardrails.map((g, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 8,
                  padding: '8px 11px', borderRadius: 8,
                  background: g.status === 'in_place' ? 'rgba(78,128,106,.08)' : 'rgba(184,124,58,.07)',
                  border: `1px solid ${g.status === 'in_place' ? 'rgba(78,128,106,.22)' : 'rgba(184,124,58,.22)'}`,
                }}>
                  {g.status === 'in_place'
                    ? <CheckCircle2 size={13} color="var(--teal2)" style={{ flexShrink: 0, marginTop: 1 }} />
                    : <AlertTriangle size={13} color="var(--amber)" style={{ flexShrink: 0, marginTop: 1 }} />
                  }
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 500, color: g.status === 'in_place' ? 'var(--teal2)' : 'var(--amber)' }}>
                      {g.name}
                    </div>
                    {g.note && (
                      <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 2, lineHeight: 1.4 }}>{g.note}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </ImpactSection>

          {/* ── Gaps needing CxO attention ────────────────────────────────── */}
          <ImpactSection
            icon={<AlertTriangle size={13} />}
            title="Gaps Requiring CxO Attention"
            accentColor="var(--red)"
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {impact.gaps.map((gap, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 8,
                  padding: '8px 11px', borderRadius: 8,
                  background: 'rgba(179,79,66,.07)', border: '1px solid rgba(179,79,66,.20)',
                }}>
                  <AlertTriangle size={12} color="var(--red)" style={{ flexShrink: 0, marginTop: 2 }} />
                  <span style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.5 }}>{gap}</span>
                </div>
              ))}
            </div>
          </ImpactSection>

          {/* ── AI recommendation ──────────────────────────────────────────── */}
          {signal.ai_recommendation && (
            <ImpactSection
              icon={<div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent2)', animation: 'pulse 2s infinite' }} />}
              title="AI Recommendation"
            >
              <div style={{ fontSize: 12, color: 'rgba(228,220,208,.85)', lineHeight: 1.65 }}>
                {signal.ai_recommendation}
              </div>
            </ImpactSection>
          )}

          <div style={{ height: 24 }} />
        </div>

        {/* ── Footer ─────────────────────────────────────────────────────── */}
        <div style={{
          padding: '14px 20px', borderTop: '1px solid var(--border)',
          flexShrink: 0, display: 'flex', justifyContent: 'flex-end', gap: 8,
        }}>
          <Button variant="ghost" size="md" onClick={onClose}>Close</Button>
          <Button variant="danger" size="sm" onClick={onDismiss} loading={isDismissing}>
            Dismiss signal
          </Button>
        </div>
      </div>
    </>
  )
}

// ── Radar page ────────────────────────────────────────────────────────────────

export const RadarPage: React.FC = () => {
  const [selected, setSelected] = useState<Signal | null>(null)
  const [catFilter, setCatFilter] = useState<string>('')
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['signals', catFilter],
    queryFn: () => radarApi.list({ category: catFilter || undefined }),
    refetchInterval: 15_000,
  })

  const dismiss = useMutation({
    mutationFn: (id: string) => radarApi.dismiss(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['signals'] }); setSelected(null) },
  })

  const SEV_COLORS: Record<string, string> = {
    critical: 'var(--red)', high: 'var(--amber)', medium: 'var(--blue)', info: 'var(--teal)',
  }

  const CATEGORIES = [
    { key: '',           label: 'All signals', icon: Radio,       desc: 'Every risk signal',              countKey: 'all' as const },
    { key: 'regulatory', label: 'Regulatory',  icon: Scale,       desc: 'Rules, enforcement & guidance',  countKey: 'cat_regulatory' as const },
    { key: 'threat',     label: 'Threat intel',icon: ShieldAlert, desc: 'Cyber threats, CVEs & campaigns', countKey: 'cat_threat' as const },
    { key: 'vendor',     label: 'Third-party', icon: Network,     desc: 'Vendor & supply-chain risk',      countKey: 'cat_vendor' as const },
    { key: 'macro',      label: 'Macro',       icon: Globe,       desc: 'Geopolitical, economic & sector', countKey: 'cat_macro' as const },
  ]
  const c = data?.counts

  return (
    <div className="page animate-fade">
      <div className="page-header">
        <div>
          <div className="page-title">Risk Radar</div>
          <div className="page-sub">{data?.total ?? 0} signals · refreshes every 15s</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          {c && (
            <div style={{ display: 'flex', gap: 12 }}>
              <span style={{ fontSize: 12, color: 'var(--text2)' }}><b style={{ color: 'var(--red)' }}>{c.critical}</b> critical</span>
              <span style={{ fontSize: 12, color: 'var(--text2)' }}><b style={{ color: 'var(--amber)' }}>{c.high}</b> high</span>
              <span style={{ fontSize: 12, color: 'var(--text2)' }}><b style={{ color: 'var(--accent2)' }}>{c.new_today}</b> new today</span>
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <LiveDot />
            <span style={{ fontSize: 12, color: 'var(--teal2)', fontWeight: 500 }}>Live</span>
          </div>
        </div>
      </div>

      {/* ── Category navigation ──────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 8, padding: '12px 24px', borderBottom: '1px solid var(--border)', flexShrink: 0, overflowX: 'auto' }}>
        {CATEGORIES.map(cat => {
          const active = catFilter === cat.key
          const Icon = cat.icon
          const count = c?.[cat.countKey] ?? 0
          return (
            <button key={cat.key || 'all'} onClick={() => setCatFilter(cat.key)}
              style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px',
                borderRadius: 'var(--r2)', cursor: 'pointer', fontFamily: 'var(--font)',
                textAlign: 'left', transition: 'all .14s', border: '1px solid', flexShrink: 0,
                background: active ? 'rgba(123,109,170,.14)' : 'var(--bg1)',
                borderColor: active ? 'rgba(123,109,170,.45)' : 'var(--border)',
              }}>
              <div style={{
                width: 30, height: 30, borderRadius: 'var(--r)', display: 'flex',
                alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                background: active ? 'rgba(123,109,170,.20)' : 'var(--bg3)',
              }}>
                <Icon size={15} color={active ? 'var(--accent2)' : 'var(--text2)'} />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                  <span style={{ fontSize: 13, fontWeight: 500, color: active ? 'var(--accent2)' : 'var(--text)' }}>{cat.label}</span>
                  <span style={{
                    fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 99,
                    minWidth: 18, textAlign: 'center',
                    background: active ? 'rgba(123,109,170,.25)' : 'var(--bg3)',
                    color: active ? 'var(--accent2)' : 'var(--text3)',
                  }}>{count}</span>
                </div>
                <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 1 }}>{cat.desc}</div>
              </div>
            </button>
          )
        })}
      </div>

      {/* ── Signal list ──────────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {isLoading
          ? <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}><Spinner /></div>
          : !data?.items.length
          ? <EmptyState title="No signals" body="Signal feeds will populate as data sources are configured" />
          : data.items.map(sig => (
            <div
              key={sig.id}
              onClick={() => setSelected(sig)}
              style={{
                padding: '13px 20px', borderBottom: '1px solid var(--border)',
                cursor: 'pointer', transition: 'background .12s',
                background: selected?.id === sig.id ? 'rgba(108,99,255,.07)' : 'transparent',
                borderLeft: selected?.id === sig.id ? '3px solid var(--accent)' : '3px solid transparent',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
                <span style={{
                  fontSize: 9, fontWeight: 600, padding: '2px 6px', borderRadius: 3,
                  background: SEV_COLORS[sig.severity] + '22', color: SEV_COLORS[sig.severity],
                  textTransform: 'uppercase', letterSpacing: '.05em',
                }}>{sig.source}</span>
                <span style={{ fontSize: 10, color: 'var(--text3)', marginLeft: 'auto' }}>
                  {new Date(sig.created_at).toLocaleDateString()}
                </span>
                <SeverityChip severity={sig.severity} />
                {sig.is_new && (
                  <span style={{
                    fontSize: 9, fontWeight: 500, color: 'var(--accent2)',
                    background: 'rgba(108,99,255,.15)', padding: '1px 5px', borderRadius: 99,
                  }}>New</span>
                )}
              </div>
              <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', lineHeight: 1.35, marginBottom: 6 }}>
                {sig.title}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {sig.tags.slice(0, 3).map(t => (
                    <span key={t} style={{ fontSize: 9, color: 'var(--text3)', background: 'var(--bg3)', padding: '1px 5px', borderRadius: 99 }}>{t}</span>
                  ))}
                </div>
                <span style={{ fontSize: 10, color: 'var(--accent2)', display: 'flex', alignItems: 'center', gap: 3, flexShrink: 0, marginLeft: 8 }}>
                  View impact <ChevronRight size={11} />
                </span>
              </div>
            </div>
          ))
        }
      </div>

      {/* ── Impact drawer overlay ────────────────────────────────────────── */}
      {selected && (
        <SignalImpactDrawer
          signal={selected}
          onClose={() => setSelected(null)}
          onDismiss={() => dismiss.mutate(selected.id)}
          isDismissing={dismiss.isPending}
        />
      )}
    </div>
  )
}

// ── Pulse page ────────────────────────────────────────────────────────────────
export const PulsePage: React.FC = () => {
  const { data, isLoading } = useQuery({
    queryKey: ['pulse'],
    queryFn: pulseApi.get,
    refetchInterval: 30_000,
  })

  if (isLoading) return <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}><Spinner /></div>

  return (
    <div className="page animate-fade">
      <div className="page-header">
        <div>
          <div className="page-title">Control Pulse</div>
          <div className="page-sub">{data?.total_monitored ?? 0} controls monitored · refreshes every 30s</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <LiveDot />
          <span style={{ fontSize: 12, color: 'var(--teal2)', fontWeight: 500 }}>{data?.passing_count ?? 0} passing</span>
          {(data?.degraded_count ?? 0) > 0 && <span style={{ fontSize: 12, color: 'var(--amber)', fontWeight: 500 }}>{data?.degraded_count} degraded</span>}
          {(data?.failing_count ?? 0) > 0 && <span style={{ fontSize: 12, color: 'var(--red)', fontWeight: 500 }}>{data?.failing_count} failing</span>}
        </div>
      </div>
      <div className="page-body">
        {!data?.controls.length
          ? <EmptyState title="No monitored controls" body="Controls are seeded after AI fingerprinting during onboarding" />
          : data.controls.map(ctrl => <PulseCard key={ctrl.control_id} control={ctrl} />)
        }
      </div>
    </div>
  )
}

const PulseCard: React.FC<{ control: PulseControl }> = ({ control }) => {
  const STATUS_COLORS: Record<string, string> = {
    passing: 'var(--teal)', failing: 'var(--red)',
    degraded: 'var(--amber)', unknown: 'var(--text3)',
  }
  const statusColor = STATUS_COLORS[control.current_status] ?? 'var(--text3)'
  const metrics = control.current_metrics as Record<string, number | string>
  const metricEntries = Object.entries(metrics).slice(0, 4)

  return (
    <div className="card" style={{ marginBottom: 12, borderLeft: `3px solid ${statusColor}30` }}>
      <div style={{ padding: '12px 16px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
            <div style={{ width: 7, height: 7, borderRadius: '50%', background: statusColor, flexShrink: 0 }} />
            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{control.control_name}</div>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 15 }}>
            {control.integration_source ?? 'Manual review'} · {control.current_status.toUpperCase()}
          </div>
        </div>
        <StatusChip status={control.current_status} />
      </div>
      {metricEntries.length > 0 && (
        <div style={{ padding: '0 16px 12px', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {metricEntries.map(([k, v]) => {
            const isAlert = (typeof v === 'number' && (
              (k.includes('critical') && v > 0) ||
              (k.includes('overdue') && v > 0) ||
              (k.includes('unpatched') && v > 0)
            ))
            return (
              <div key={k} style={{ background: 'var(--bg2)', borderRadius: 8, padding: '7px 12px', minWidth: 80 }}>
                <div style={{ fontSize: 19, fontWeight: 300, color: isAlert ? 'var(--red)' : control.current_status === 'passing' ? 'var(--teal)' : 'var(--text)', letterSpacing: '-0.5px' }}>{v}</div>
                <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 1, whiteSpace: 'nowrap' }}>{k.replace(/_/g, ' ')}</div>
              </div>
            )
          })}
        </div>
      )}
      {control.ai_alert && (
        <div style={{ margin: '0 16px 14px', background: 'rgba(108,99,255,.08)', border: '1px solid rgba(108,99,255,.2)', borderRadius: 8, padding: '9px 12px', fontSize: 12, color: 'rgba(232,234,240,.85)', lineHeight: 1.55 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--accent2)', animation: 'pulse 2s infinite' }} />
            <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--accent2)', textTransform: 'uppercase', letterSpacing: '.05em' }}>AI Insight</span>
          </div>
          {control.ai_alert}
        </div>
      )}
    </div>
  )
}

// ── Audit planner page ────────────────────────────────────────────────────────
export const AuditPage: React.FC = () => {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [selected, setSelected] = useState<AuditPlan | null>(null)

  const { data: plans, isLoading } = useQuery({ queryKey: ['audit-plans'], queryFn: auditApi.listPlans })
  const { data: reports } = useQuery({ queryKey: ['audit-reports'], queryFn: auditReportApi.list })

  const createPlan = useMutation({
    mutationFn: auditApi.createPlan,
    onSuccess: (plan) => { qc.invalidateQueries({ queryKey: ['audit-plans'] }); setSelected(plan); setShowCreate(false) },
  })

  const toggleTask = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => auditApi.updateTask(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['audit-plans'] }),
  })

  const generateReport = useMutation({
    mutationFn: auditReportApi.generate,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['audit-reports'] })
      navigate(`/audit/reports/${data.report_id}`)
    },
  })

  const latestReport = reports?.[0]

  return (
    <div className="page animate-fade">
      <div className="page-header">
        <div>
          <div className="page-title">Audit Planner</div>
          <div className="page-sub">{plans?.length ?? 0} audit plan{plans?.length !== 1 ? 's' : ''}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {latestReport && (
            <button
              onClick={() => navigate(`/audit/reports/${latestReport.id}`)}
              style={{ fontSize: 12, padding: '6px 14px', borderRadius: 7, border: '1px solid var(--border2)', background: 'var(--bg2)', color: 'var(--text2)', cursor: 'pointer', fontFamily: 'var(--font)', display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: latestReport.status === 'published' ? 'var(--teal)' : latestReport.status === 'assembling' ? 'var(--accent2)' : 'var(--amber)', display: 'inline-block', flexShrink: 0 }} />
              View latest report
            </button>
          )}
          <Button variant="ghost" size="md" onClick={() => generateReport.mutate()} loading={generateReport.isPending}>
            ✦ Generate AI Report
          </Button>
          <Button variant="primary" size="md" onClick={() => setShowCreate(true)}>+ New plan</Button>
        </div>
      </div>
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ width: 260, flexShrink: 0, borderRight: '1px solid var(--border)', overflowY: 'auto', padding: 12 }}>
          {isLoading
            ? <Spinner />
            : !plans?.length
            ? <EmptyState title="No audit plans" body="Create your first plan to get started" />
            : plans.map(p => (
              <div key={p.id} onClick={() => setSelected(p)}
                style={{ padding: '10px 12px', borderRadius: 8, cursor: 'pointer', marginBottom: 4, transition: 'background .12s',
                  background: selected?.id === p.id ? 'rgba(108,99,255,.15)' : 'transparent',
                  border: `1px solid ${selected?.id === p.id ? 'rgba(108,99,255,.25)' : 'transparent'}`,
                }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)', marginBottom: 4 }}>{p.name}</div>
                <ProgressBar value={p.progress_pct} color="var(--accent)" height={3} />
                <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 4 }}>{p.done_count}/{p.task_count} tasks · {Math.round(p.progress_pct)}%</div>
              </div>
            ))
          }
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          {!selected
            ? <EmptyState title="Select a plan" body="Click a plan to view and manage its tasks" />
            : (
              <div className="animate-fade">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                  <div>
                    <h2 style={{ fontSize: 16, fontWeight: 500 }}>{selected.name}</h2>
                    <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 2 }}>{selected.done_count}/{selected.task_count} tasks · {Math.round(selected.progress_pct)}% complete</div>
                  </div>
                  <ProgressBar value={selected.progress_pct} color="var(--accent)" height={5} />
                </div>
                {selected.tasks.length === 0
                  ? <EmptyState title="No tasks yet" body="Tasks are generated by AI when you create a plan with scope" />
                  : [1, 2, 3].map(phase => {
                    const tasks = selected.tasks.filter(t => t.phase === phase)
                    if (!tasks.length) return null
                    return (
                      <div key={phase} style={{ marginBottom: 16, background: 'var(--bg1)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
                        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', fontSize: 12, fontWeight: 500, color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ width: 22, height: 22, borderRadius: '50%', background: ['rgba(108,99,255,.15)','rgba(232,168,56,.15)','rgba(30,185,138,.15)'][phase-1], display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 500, color: ['var(--accent2)','var(--amber)','var(--teal2)'][phase-1] }}>{phase}</div>
                          {tasks[0].phase_label ?? `Phase ${phase}`}
                        </div>
                        {tasks.map(task => (
                          <div key={task.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '8px 14px', borderBottom: '1px solid var(--border)' }}>
                            <div onClick={() => toggleTask.mutate({ id: task.id, status: task.status === 'done' ? 'pending' : 'done' })}
                              style={{ width: 14, height: 14, borderRadius: 3, border: `1.5px solid ${task.status === 'done' ? 'var(--accent)' : 'var(--border2)'}`, background: task.status === 'done' ? 'var(--accent)' : 'none', cursor: 'pointer', flexShrink: 0, marginTop: 2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              {task.status === 'done' && <svg width="8" height="8" viewBox="0 0 8 8" fill="none"><path d="M1.5 4l2 2 3-3" stroke="white" strokeWidth="1.2" strokeLinecap="round"/></svg>}
                            </div>
                            <div style={{ flex: 1, fontSize: 12, color: task.status === 'done' ? 'var(--text3)' : 'var(--text)', textDecoration: task.status === 'done' ? 'line-through' : 'none' }}>{task.label}</div>
                            {task.is_priority && <span style={{ fontSize: 9, fontWeight: 500, color: 'var(--red)', background: 'rgba(224,82,82,.12)', padding: '1px 5px', borderRadius: 99 }}>Priority</span>}
                          </div>
                        ))}
                      </div>
                    )
                  })
                }
              </div>
            )
          }
        </div>
      </div>

      {showCreate && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(10,11,14,.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 500 }} onClick={() => setShowCreate(false)}>
          <div style={{ background: 'var(--bg1)', border: '1px solid var(--border2)', borderRadius: 14, padding: '28px', width: 400 }} onClick={e => e.stopPropagation()}>
            <h3 style={{ marginBottom: 18, fontWeight: 500 }}>New audit plan</h3>
            <form onSubmit={async e => { e.preventDefault(); const fd = new FormData(e.target as HTMLFormElement); createPlan.mutate({ name: fd.get('name') as string, description: fd.get('desc') as string }) }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <Input label="Plan name" name="name" placeholder="e.g. AML & Financial Crime Audit" required />
                <Input label="Description (optional)" name="desc" placeholder="Scope, objectives..." />
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 20 }}>
                <Button variant="ghost" size="md" type="button" onClick={() => setShowCreate(false)}>Cancel</Button>
                <Button variant="primary" size="md" type="submit" loading={createPlan.isPending}>Create plan</Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Controls page ─────────────────────────────────────────────────────────────
export const ControlsPage: React.FC = () => {
  const { data, isLoading } = useQuery({ queryKey: ['controls'], queryFn: () => controlsApi.list() })

  return (
    <div className="page animate-fade">
      <div className="page-header">
        <div>
          <div className="page-title">Control Library</div>
          <div className="page-sub">{data?.length ?? 0} controls</div>
        </div>
        <Button variant="primary" size="md">+ Add control</Button>
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>
        {isLoading
          ? <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}><Spinner /></div>
          : !data?.length
          ? <EmptyState title="No controls yet" body="Controls are seeded automatically during AI fingerprinting" />
          : <table className="table">
              <thead><tr><th style={{ paddingLeft: 24 }}>Control</th><th>Type</th><th>Status</th><th>Last tested</th><th>Owner</th></tr></thead>
              <tbody>
                {data.map(ctrl => (
                  <tr key={ctrl.id}>
                    <td style={{ paddingLeft: 24 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>{ctrl.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text2)' }}>{ctrl.domain}</div>
                    </td>
                    <td><Chip label={ctrl.control_type} variant="gray" /></td>
                    <td><StatusChip status={ctrl.status} /></td>
                    <td style={{ fontSize: 11, color: 'var(--text3)' }}>{ctrl.last_tested_at ? new Date(ctrl.last_tested_at).toLocaleDateString() : 'Never'}</td>
                    <td>{ctrl.owner ? <span style={{ fontSize: 11, color: 'var(--text2)' }}>{ctrl.owner.full_name}</span> : <span style={{ fontSize: 11, color: 'var(--text3)' }}>Unassigned</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
        }
      </div>
    </div>
  )
}

// ── Settings page ─────────────────────────────────────────────────────────────
export const SettingsPage: React.FC = () => {
  const { user } = useAuthStore()
  return (
    <div className="page animate-fade">
      <div className="page-header">
        <div><div className="page-title">Settings</div></div>
      </div>
      <div className="page-body" style={{ maxWidth: 520 }}>
        <div className="card" style={{ marginBottom: 14 }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', fontSize: 12, fontWeight: 500 }}>Account</div>
          <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <Input label="Full name" defaultValue={user?.full_name ?? ''} />
            <Input label="Email" defaultValue={user?.email ?? ''} disabled />
            <div style={{ fontSize: 11, color: 'var(--text2)' }}>Role: <strong style={{ color: 'var(--text)' }}>{user?.role?.replace('_', ' ')}</strong></div>
          </div>
        </div>
        <div className="card">
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', fontSize: 12, fontWeight: 500 }}>Integrations</div>
          <div style={{ padding: 16 }}>
            {['Okta · Access management', 'AWS Security Hub · Vulnerability management', 'Onfido KYC · Identity verification'].map((item, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', borderBottom: i < 2 ? '1px solid var(--border)' : 'none' }}>
                <span style={{ fontSize: 12, color: 'var(--text2)' }}>{item}</span>
                <Button variant="ghost" size="sm">Connect</Button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// Need to import useAuthStore for SettingsPage
import { useAuthStore } from '@/store'
