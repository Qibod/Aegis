import React, { useState, useCallback, useMemo } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { timeMachineApi } from '@/api/client'
import { Button, Spinner, EmptyState } from '@/components/ui'
import type { TimeMachineSnapshot, TimeMachineEvent, SimulationResult, SimulationFinding } from '@/types'

// ── Scenario definitions ──────────────────────────────────────────────────────

interface Scenario {
  key: string
  label: string
  icon: string
  description: string
  defaultParams: Record<string, number>
}

const SCENARIOS: Scenario[] = [
  {
    key: 'data_breach', label: 'Major Data Breach', icon: '🔓',
    description: 'Simulate a large-scale breach of customer PII across cloud and on-prem systems.',
    defaultParams: { affected_records: 450000, control_effectiveness_pct: 45, detection_lag_days: 18, response_readiness_pct: 55 },
  },
  {
    key: 'regulatory_action', label: 'Regulatory Enforcement', icon: '⚖️',
    description: 'DNB or AFM opens a formal enforcement action based on AML/KYC deficiencies.',
    defaultParams: { affected_records: 0, control_effectiveness_pct: 50, detection_lag_days: 0, response_readiness_pct: 60 },
  },
  {
    key: 'ransomware', label: 'Ransomware Attack', icon: '💀',
    description: 'Ransomware encrypts core banking and payment infrastructure — partial recovery only.',
    defaultParams: { affected_records: 120000, control_effectiveness_pct: 40, detection_lag_days: 3, response_readiness_pct: 50 },
  },
  {
    key: 'third_party_failure', label: 'Critical Vendor Failure', icon: '🔗',
    description: 'Primary KYC or payment processor experiences a sustained outage.',
    defaultParams: { affected_records: 0, control_effectiveness_pct: 55, detection_lag_days: 2, response_readiness_pct: 65 },
  },
  {
    key: 'ai_bias', label: 'Algorithmic Bias Finding', icon: '🤖',
    description: 'Regulator finds demographic disparity in your credit or fraud ML model.',
    defaultParams: { affected_records: 80000, control_effectiveness_pct: 35, detection_lag_days: 0, response_readiness_pct: 40 },
  },
  {
    key: 'pre_audit', label: 'Pre-Audit Stress Test', icon: '🔍',
    description: 'Simulate exactly what a DNB/AFM examination team would find today.',
    defaultParams: { affected_records: 0, control_effectiveness_pct: 50, detection_lag_days: 14, response_readiness_pct: 65 },
  },
]

const PARAM_CONFIG = [
  { key: 'affected_records',         label: 'Affected records',        min: 0,   max: 2000000, step: 10000, unit: '', format: (v: number) => v >= 1000 ? `${(v/1000).toFixed(0)}K` : `${v}` },
  { key: 'control_effectiveness_pct', label: 'Control effectiveness',  min: 10,  max: 95,      step: 5,     unit: '%', format: (v: number) => `${v}%` },
  { key: 'detection_lag_days',        label: 'Detection lag',          min: 0,   max: 60,      step: 1,     unit: 'days', format: (v: number) => `${v}d` },
  { key: 'response_readiness_pct',    label: 'Response readiness',     min: 10,  max: 95,      step: 5,     unit: '%', format: (v: number) => `${v}%` },
]

// ── Colours ───────────────────────────────────────────────────────────────────

const SEV_COLOR: Record<string, string> = {
  critical: 'var(--red)', high: 'var(--amber)',
  medium: 'var(--blue)', low: 'var(--teal)',
}

const SENTIMENT_COLOR: Record<string, string> = {
  positive: 'var(--teal)', negative: 'var(--red)', neutral: 'rgba(108,99,255,.7)',
}

const SCORE_COLOR = (score: number) =>
  score >= 70 ? 'var(--red)' : score >= 45 ? 'var(--amber)' : 'var(--teal)'

// ── Main page ─────────────────────────────────────────────────────────────────

export const TimeMachinePage: React.FC = () => {
  const [tab, setTab] = useState<'history' | 'simulate'>('history')

  return (
    <div className="page animate-fade" style={{ display: 'flex', flexDirection: 'column' }}>
      <div className="page-header">
        <div>
          <div className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 20 }}>⏱</span> GRC Time Machine
          </div>
          <div className="page-sub">Travel through your GRC history · Stress-test future scenarios</div>
        </div>
        <div style={{ display: 'flex', gap: 4, background: 'var(--bg2)', borderRadius: 8, padding: 3 }}>
          {(['history', 'simulate'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{ padding: '5px 16px', borderRadius: 6, border: 'none', cursor: 'pointer', fontFamily: 'var(--font)',
                fontSize: 12, fontWeight: 500, transition: 'all .15s',
                background: tab === t ? 'var(--bg1)' : 'none',
                color: tab === t ? 'var(--text)' : 'var(--text3)',
                boxShadow: tab === t ? '0 1px 3px rgba(0,0,0,.3)' : 'none',
              }}>
              {t === 'history' ? '📅 History' : '⚡ Simulate'}
            </button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflow: 'hidden' }}>
        {tab === 'history' ? <HistoryTab /> : <SimulateTab />}
      </div>
    </div>
  )
}

// ── History tab ───────────────────────────────────────────────────────────────

const HistoryTab: React.FC = () => {
  const [scrubIndex, setScrubIndex] = useState<number | null>(null)

  const { data: snapshots, isLoading: loadingSnaps } = useQuery({
    queryKey: ['tm-snapshots'],
    queryFn: timeMachineApi.snapshots,
    staleTime: 60_000,
  })

  const { data: events } = useQuery({
    queryKey: ['tm-events'],
    queryFn: timeMachineApi.events,
    staleTime: 60_000,
  })

  const currentIndex = scrubIndex ?? (snapshots ? snapshots.length - 1 : 0)
  const currentSnapshot = snapshots?.[currentIndex] ?? null
  const prevSnapshot = snapshots?.[Math.max(0, currentIndex - 1)] ?? null

  // Map events by month
  const eventsByMonth = useMemo<Record<string, TimeMachineEvent[]>>(() => {
    if (!events) return {}
    const m: Record<string, TimeMachineEvent[]> = {}
    for (const ev of events) {
      const month = ev.occurred_at.slice(0, 7)
      if (!m[month]) m[month] = []
      m[month].push(ev)
    }
    return m
  }, [events])

  const handleJumpToEvent = useCallback((ev: TimeMachineEvent) => {
    if (!snapshots) return
    const month = ev.occurred_at.slice(0, 7)
    const idx = snapshots.findIndex(s => s.snapshot_month === month)
    if (idx >= 0) setScrubIndex(idx)
  }, [snapshots])

  if (loadingSnaps) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '4rem' }}><Spinner /></div>
  )

  if (!snapshots?.length) return (
    <EmptyState title="No history yet" body="History snapshots are generated automatically. Try refreshing." />
  )

  const monthLabel = (m: string) => {
    const [y, mo] = m.split('-')
    return new Date(parseInt(y), parseInt(mo) - 1, 1).toLocaleString('default', { month: 'short', year: '2-digit' })
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* ── Metric cards ── */}
      {currentSnapshot && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, padding: '16px 24px', flexShrink: 0 }}>
          {[
            { label: 'Total risks', value: currentSnapshot.total_risks, delta: currentSnapshot.delta_risks, suffix: '', critical: currentSnapshot.critical_risks + ' critical' },
            { label: 'Controls', value: currentSnapshot.total_controls, delta: currentSnapshot.delta_controls, suffix: '', critical: currentSnapshot.effective_controls + ' effective' },
            { label: 'Coverage', value: currentSnapshot.coverage_pct.toFixed(0), delta: currentSnapshot.delta_coverage_pct, suffix: '%', critical: '' },
            { label: 'Frameworks', value: currentSnapshot.frameworks_active, delta: 0, suffix: '', critical: 'active' },
          ].map(card => (
            <div key={card.label} style={{ background: 'var(--bg1)', border: '1px solid var(--border)', borderRadius: 12, padding: '14px 18px' }}>
              <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 8 }}>{card.label}</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
                <div style={{ fontSize: 32, fontWeight: 200, color: 'var(--text)', letterSpacing: '-1px', lineHeight: 1 }}>{card.value}{card.suffix}</div>
                {card.delta !== 0 && (
                  <div style={{ fontSize: 11, fontWeight: 500, color: card.delta > 0 ? 'var(--teal)' : 'var(--red)', marginBottom: 3 }}>
                    {card.delta > 0 ? '▲' : '▼'} {Math.abs(card.delta)}{card.suffix}
                  </div>
                )}
              </div>
              {card.critical && <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>{card.critical}</div>}
            </div>
          ))}
        </div>
      )}

      {/* ── AI event banner ── */}
      {currentSnapshot && currentSnapshot.notable_events.length > 0 && (
        <div style={{ margin: '0 24px 12px', flexShrink: 0 }}>
          {currentSnapshot.notable_events.slice(0, 2).map((ev, i) => (
            <div key={i} style={{
              background: ev.sentiment === 'negative' ? 'rgba(224,82,82,.08)' : ev.sentiment === 'positive' ? 'rgba(30,185,138,.08)' : 'rgba(108,99,255,.08)',
              border: `1px solid ${ev.sentiment === 'negative' ? 'rgba(224,82,82,.25)' : ev.sentiment === 'positive' ? 'rgba(30,185,138,.25)' : 'rgba(108,99,255,.25)'}`,
              borderRadius: 10, padding: '10px 14px', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 10,
            }}>
              <span style={{ fontSize: 14 }}>{ev.sentiment === 'negative' ? '⚠️' : ev.sentiment === 'positive' ? '✅' : '📌'}</span>
              <div>
                <div style={{ fontSize: 11, fontWeight: 500, color: SENTIMENT_COLOR[ev.sentiment] }}>{monthLabel(currentSnapshot.snapshot_month)}</div>
                <div style={{ fontSize: 12, color: 'var(--text)', lineHeight: 1.4 }}>{ev.title}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Main body: timeline + diff ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', gap: 0 }}>
        {/* Timeline + scrubber */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', borderRight: '1px solid var(--border)' }}>
          {/* Scrubber */}
          <div style={{ padding: '8px 24px 16px', flexShrink: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text3)', marginBottom: 8 }}>
              <span>{snapshots ? monthLabel(snapshots[0].snapshot_month) : ''}</span>
              <span style={{ fontWeight: 500, color: 'var(--accent2)' }}>
                {currentSnapshot ? monthLabel(currentSnapshot.snapshot_month) : ''}
              </span>
              <span>{snapshots ? monthLabel(snapshots[snapshots.length - 1].snapshot_month) : ''}</span>
            </div>

            {/* Track with dots */}
            <div style={{ position: 'relative', height: 32, cursor: 'pointer' }}>
              {/* Coverage sparkline bar */}
              <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 4, background: 'var(--bg2)', borderRadius: 99, overflow: 'hidden' }}>
                {snapshots && snapshots.map((s, i) => (
                  <div key={i} style={{
                    position: 'absolute',
                    left: `${(i / (snapshots.length - 1)) * 100}%`,
                    bottom: 0,
                    width: `${100 / (snapshots.length - 1)}%`,
                    height: `${s.coverage_pct}%`,
                    maxHeight: '100%',
                    background: `rgba(108,99,255,${0.3 + (s.coverage_pct / 100) * 0.7})`,
                  }} />
                ))}
                {/* Progress fill */}
                <div style={{ position: 'absolute', left: 0, top: 0, bottom: 0, background: 'var(--accent)', opacity: 0.4, borderRadius: 99, width: `${(currentIndex / (snapshots.length - 1)) * 100}%`, transition: 'width .1s' }} />
              </div>

              {/* Event dots */}
              {snapshots && snapshots.map((s, i) => {
                const monthEvents = eventsByMonth[s.snapshot_month] ?? []
                if (!monthEvents.length) return null
                const sentiment = monthEvents[0].sentiment
                const x = (i / (snapshots.length - 1)) * 100
                return (
                  <div key={i} title={monthEvents[0].title}
                    onClick={() => setScrubIndex(i)}
                    style={{
                      position: 'absolute', bottom: 8,
                      left: `calc(${x}% - 5px)`,
                      width: 10, height: 10, borderRadius: '50%',
                      background: SENTIMENT_COLOR[sentiment],
                      border: `2px solid var(--bg)`,
                      cursor: 'pointer',
                      zIndex: 2,
                      transform: i === currentIndex ? 'scale(1.4)' : 'scale(1)',
                      transition: 'transform .15s',
                      boxShadow: sentiment === 'negative' ? '0 0 6px rgba(224,82,82,.6)' : sentiment === 'positive' ? '0 0 6px rgba(30,185,138,.6)' : 'none',
                    }}
                  />
                )
              })}

              {/* Scrubber handle */}
              <input type="range" min={0} max={(snapshots?.length ?? 1) - 1} value={currentIndex}
                onChange={e => setScrubIndex(parseInt(e.target.value))}
                style={{ position: 'absolute', bottom: -2, left: 0, right: 0, width: '100%', height: 20, opacity: 0, cursor: 'pointer', zIndex: 10 }}
              />
              {/* Visible thumb */}
              <div style={{
                position: 'absolute', bottom: -2,
                left: `calc(${(currentIndex / (snapshots.length - 1)) * 100}% - 8px)`,
                width: 16, height: 16, borderRadius: '50%',
                background: 'var(--accent)', border: '2px solid var(--bg1)',
                boxShadow: '0 2px 8px rgba(108,99,255,.5)',
                transition: 'left .05s',
                pointerEvents: 'none',
              }} />
            </div>

            {/* Month ticks */}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
              {snapshots && snapshots.filter((_, i) => i % 3 === 0 || i === snapshots.length - 1).map((s) => (
                <span key={s.snapshot_month} style={{ fontSize: 9, color: 'var(--text3)' }}>{monthLabel(s.snapshot_month)}</span>
              ))}
            </div>
          </div>

          {/* Coverage chart */}
          <div style={{ flex: 1, padding: '0 24px 16px', overflowY: 'auto' }}>
            <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 12 }}>Coverage trajectory</div>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 80 }}>
              {snapshots && snapshots.map((s, i) => (
                <div key={i} onClick={() => setScrubIndex(i)}
                  title={`${monthLabel(s.snapshot_month)}: ${s.coverage_pct}%`}
                  style={{
                    flex: 1, borderRadius: '3px 3px 0 0', cursor: 'pointer',
                    height: `${Math.max(4, s.coverage_pct)}%`,
                    background: i === currentIndex
                      ? 'var(--accent)'
                      : i < currentIndex
                      ? 'rgba(108,99,255,.4)'
                      : 'var(--bg3)',
                    transition: 'all .15s',
                  }}
                />
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text3)', marginTop: 4 }}>
              <span>0%</span><span>Coverage</span><span>100%</span>
            </div>

            {/* Notable events list */}
            <div style={{ marginTop: 20, fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 10 }}>All timeline events</div>
            {events && events.slice().reverse().map(ev => (
              <div key={ev.id} onClick={() => handleJumpToEvent(ev)}
                style={{ display: 'flex', gap: 8, padding: '7px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer', alignItems: 'flex-start' }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: SENTIMENT_COLOR[ev.sentiment], flexShrink: 0, marginTop: 3 }} />
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text)', lineHeight: 1.35 }}>{ev.title}</div>
                  <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2 }}>{monthLabel(ev.occurred_at.slice(0, 7))}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Diff panel */}
        <div style={{ width: 300, flexShrink: 0, overflowY: 'auto', padding: '16px 20px' }}>
          {!currentSnapshot ? (
            <EmptyState title="Drag the scrubber" body="to view the state at any point in time" />
          ) : (
            <div className="animate-fade">
              <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 12 }}>
                Changes vs prior month
              </div>

              {/* Risk diff */}
              <DiffSection title="Risks" diff={currentSnapshot.risk_diff} />
              <DiffSection title="Controls" diff={currentSnapshot.control_diff} />

              {/* Metrics comparison */}
              {prevSnapshot && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 10 }}>Metric deltas</div>
                  {[
                    { label: 'Total risks', from: prevSnapshot.total_risks, to: currentSnapshot.total_risks, higherIsBad: true },
                    { label: 'Critical risks', from: prevSnapshot.critical_risks, to: currentSnapshot.critical_risks, higherIsBad: true },
                    { label: 'Coverage %', from: prevSnapshot.coverage_pct, to: currentSnapshot.coverage_pct, higherIsBad: false, suffix: '%' },
                    { label: 'Effective controls', from: prevSnapshot.effective_controls, to: currentSnapshot.effective_controls, higherIsBad: false },
                  ].map(m => {
                    const delta = m.to - m.from
                    const improved = m.higherIsBad ? delta < 0 : delta > 0
                    const color = delta === 0 ? 'var(--text3)' : improved ? 'var(--teal)' : 'var(--red)'
                    return (
                      <div key={m.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 0', borderBottom: '1px solid var(--border)' }}>
                        <span style={{ fontSize: 11, color: 'var(--text2)' }}>{m.label}</span>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <span style={{ fontSize: 11, color: 'var(--text3)' }}>{m.from}{m.suffix}</span>
                          <span style={{ fontSize: 10, color: 'var(--text3)' }}>→</span>
                          <span style={{ fontSize: 12, fontWeight: 500, color }}>{m.to}{m.suffix}</span>
                          {delta !== 0 && <span style={{ fontSize: 10, color, fontWeight: 500 }}>{delta > 0 ? '+' : ''}{typeof m.from === 'number' && typeof m.to === 'number' ? delta.toFixed(m.suffix ? 1 : 0) : delta}{m.suffix}</span>}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

const DiffSection: React.FC<{ title: string; diff: Record<string, string[]> }> = ({ title, diff }) => {
  const added = diff.added ?? []
  const removed = diff.removed ?? []
  const changed = diff.changed ?? []
  if (!added.length && !removed.length && !changed.length) return null

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text)', marginBottom: 6 }}>{title}</div>
      {added.map((item, i) => (
        <div key={`a${i}`} style={{ fontSize: 11, color: 'var(--teal)', padding: '2px 0', display: 'flex', gap: 5 }}>
          <span>+</span>{item}
        </div>
      ))}
      {removed.map((item, i) => (
        <div key={`r${i}`} style={{ fontSize: 11, color: 'var(--red)', padding: '2px 0', display: 'flex', gap: 5 }}>
          <span>−</span>{item}
        </div>
      ))}
      {changed.map((item, i) => (
        <div key={`c${i}`} style={{ fontSize: 11, color: 'var(--amber)', padding: '2px 0', display: 'flex', gap: 5 }}>
          <span>~</span>{item}
        </div>
      ))}
    </div>
  )
}

// ── Simulate tab ──────────────────────────────────────────────────────────────

const SimulateTab: React.FC = () => {
  const [activeScenario, setActiveScenario] = useState<Scenario>(SCENARIOS[5]) // default: pre-audit
  const [params, setParams] = useState<Record<string, number>>(SCENARIOS[5].defaultParams)
  const [result, setResult] = useState<SimulationResult | null>(null)

  const simulate = useMutation({
    mutationFn: timeMachineApi.simulate,
    onSuccess: (data) => setResult(data),
  })

  const selectScenario = (s: Scenario) => {
    setActiveScenario(s)
    setParams(s.defaultParams)
    setResult(null)
  }

  const handleRun = () => {
    simulate.mutate({
      scenario_key: activeScenario.key,
      scenario_label: activeScenario.label,
      parameters: params,
    })
  }

  const scoreColor = result ? SCORE_COLOR(result.residual_risk_score) : 'var(--text3)'

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Left: scenario picker + params */}
      <div style={{ width: 340, flexShrink: 0, borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Scenario list */}
        <div style={{ padding: '16px 16px 8px', flexShrink: 0 }}>
          <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 10 }}>Select scenario</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {SCENARIOS.map(s => (
              <button key={s.key} onClick={() => selectScenario(s)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10, padding: '9px 11px', borderRadius: 8,
                  border: `1px solid ${activeScenario.key === s.key ? 'rgba(108,99,255,.4)' : 'transparent'}`,
                  background: activeScenario.key === s.key ? 'rgba(108,99,255,.12)' : 'var(--bg2)',
                  cursor: 'pointer', fontFamily: 'var(--font)', textAlign: 'left', width: '100%',
                }}>
                <span style={{ fontSize: 16, width: 24, textAlign: 'center' }}>{s.icon}</span>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 500, color: activeScenario.key === s.key ? 'var(--accent2)' : 'var(--text)' }}>{s.label}</div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Scenario description */}
        <div style={{ padding: '8px 16px 12px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <div style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.5 }}>{activeScenario.description}</div>
        </div>

        {/* Parameter sliders */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
          <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 14 }}>Parameters</div>
          {PARAM_CONFIG.filter(p => p.key !== 'affected_records' || activeScenario.defaultParams.affected_records > 0).map(p => {
            const val = params[p.key] ?? p.min
            return (
              <div key={p.key} style={{ marginBottom: 18 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 11, color: 'var(--text2)', fontWeight: 500 }}>{p.label}</span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent2)', minWidth: 48, textAlign: 'right' }}>{p.format(val)}</span>
                </div>
                <div style={{ position: 'relative' }}>
                  <div style={{ height: 4, background: 'var(--bg2)', borderRadius: 99, overflow: 'hidden' }}>
                    <div style={{ height: '100%', background: 'var(--accent)', borderRadius: 99, width: `${((val - p.min) / (p.max - p.min)) * 100}%` }} />
                  </div>
                  <input type="range" min={p.min} max={p.max} step={p.step} value={val}
                    onChange={e => setParams(prev => ({ ...prev, [p.key]: parseInt(e.target.value) }))}
                    style={{ position: 'absolute', top: -8, left: 0, right: 0, width: '100%', opacity: 0, cursor: 'pointer', height: 20 }}
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text3)', marginTop: 3 }}>
                  <span>{p.format(p.min)}</span><span>{p.format(p.max)}</span>
                </div>
              </div>
            )
          })}
        </div>

        {/* Run button */}
        <div style={{ padding: 16, borderTop: '1px solid var(--border)', flexShrink: 0 }}>
          <Button variant="primary" size="md" style={{ width: '100%' }}
            loading={simulate.isPending} onClick={handleRun}>
            ⚡ Run simulation
          </Button>
        </div>
      </div>

      {/* Right: results */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
        {!result && !simulate.isPending && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 12 }}>
            <div style={{ fontSize: 48 }}>{activeScenario.icon}</div>
            <div style={{ fontSize: 15, fontWeight: 500, color: 'var(--text)' }}>{activeScenario.label}</div>
            <div style={{ fontSize: 12, color: 'var(--text3)', maxWidth: 360, textAlign: 'center', lineHeight: 1.6 }}>{activeScenario.description}</div>
            <Button variant="primary" size="md" loading={simulate.isPending} onClick={handleRun}>Run simulation</Button>
          </div>
        )}

        {simulate.isPending && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 16 }}>
            <Spinner size={32} />
            <div style={{ fontSize: 13, color: 'var(--text2)' }}>Analysing control environment…</div>
          </div>
        )}

        {result && !simulate.isPending && (
          <div className="animate-fade">
            {/* Score cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12, marginBottom: 20 }}>
              <ScoreCard label="Residual risk score" value={`${result.residual_risk_score}/100`} color={scoreColor} sub="0=safe, 100=critical" />
              <ScoreCard label="Controls failing" value={`${result.controls_failing_count}`} color={result.controls_failing_count > 5 ? 'var(--red)' : 'var(--amber)'} sub="would fail examination" />
              <ScoreCard label="Regulatory exposure" value={`€${(result.regulatory_exposure_usd / 1_000_000).toFixed(1)}M`} color={result.regulatory_exposure_usd > 10_000_000 ? 'var(--red)' : 'var(--amber)'} sub="estimated fine basis" />
            </div>

            {/* Domain exposure */}
            <div style={{ background: 'var(--bg1)', border: '1px solid var(--border)', borderRadius: 12, padding: '16px 20px', marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 14 }}>Domain exposure</div>
              {result.domain_exposure.map(d => (
                <div key={d.domain} style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, color: 'var(--text)' }}>{d.domain}</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: d.exposure_pct > 60 ? 'var(--red)' : d.exposure_pct > 35 ? 'var(--amber)' : 'var(--teal)' }}>{d.exposure_pct}%</span>
                  </div>
                  <div style={{ height: 5, background: 'var(--bg3)', borderRadius: 99, overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', borderRadius: 99,
                      width: `${d.exposure_pct}%`,
                      background: d.exposure_pct > 60 ? 'var(--red)' : d.exposure_pct > 35 ? 'var(--amber)' : 'var(--teal)',
                    }} />
                  </div>
                </div>
              ))}
            </div>

            {/* Findings */}
            <div style={{ background: 'var(--bg1)', border: '1px solid var(--border)', borderRadius: 12, padding: '16px 20px', marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 12 }}>Examination findings</div>
              {result.findings.map((f, i) => (
                <FindingRow key={i} finding={f} />
              ))}
            </div>

            {/* AI recommendation */}
            <div style={{ background: 'rgba(108,99,255,.07)', border: '1px solid rgba(108,99,255,.25)', borderRadius: 12, padding: '16px 20px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent2)', animation: 'pulse 2s infinite' }} />
                <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent2)', textTransform: 'uppercase', letterSpacing: '.05em' }}>AI Remediation Analysis</span>
              </div>
              <div style={{ fontSize: 13, color: 'rgba(232,234,240,.9)', lineHeight: 1.65 }}>{result.ai_recommendation}</div>
              <div style={{ marginTop: 14 }}>
                <Button variant="primary" size="sm">Build remediation roadmap →</Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const ScoreCard: React.FC<{ label: string; value: string; color: string; sub: string }> = ({ label, value, color, sub }) => (
  <div style={{ background: 'var(--bg1)', border: '1px solid var(--border)', borderRadius: 12, padding: '14px 18px' }}>
    <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 8 }}>{label}</div>
    <div style={{ fontSize: 28, fontWeight: 200, color, letterSpacing: '-0.5px', lineHeight: 1 }}>{value}</div>
    <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 5 }}>{sub}</div>
  </div>
)

const FindingRow: React.FC<{ finding: SimulationFinding }> = ({ finding }) => {
  const [expanded, setExpanded] = useState(false)
  return (
    <div style={{ padding: '9px 0', borderBottom: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer' }} onClick={() => setExpanded(e => !e)}>
        <span style={{
          fontSize: 9, fontWeight: 600, padding: '2px 6px', borderRadius: 3, flexShrink: 0, marginTop: 1,
          background: SEV_COLOR[finding.severity] + '22', color: SEV_COLOR[finding.severity],
          textTransform: 'uppercase', letterSpacing: '.05em',
        }}>{finding.severity}</span>
        <div style={{ flex: 1, fontSize: 12, fontWeight: 500, color: 'var(--text)', lineHeight: 1.35 }}>{finding.title}</div>
        <span style={{ fontSize: 10, color: 'var(--text3)', flexShrink: 0 }}>{expanded ? '▲' : '▼'}</span>
      </div>
      {expanded && (
        <div style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.6, marginTop: 8, paddingLeft: 50 }}>
          {finding.description}
        </div>
      )}
    </div>
  )
}
