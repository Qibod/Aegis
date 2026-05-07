// ── Radar page ────────────────────────────────────────────────────────────────
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { radarApi, pulseApi, auditApi, controlsApi, auditReportApi } from '@/api/client'
import { Button, SeverityChip, StatusChip, Chip, EmptyState, Spinner, ProgressBar, LiveDot, Input } from '@/components/ui'
import type { Signal, PulseControl, AuditPlan, AuditTask, Control } from '@/types'

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
    onSuccess: () => qc.invalidateQueries({ queryKey: ['signals'] }),
  })

  const CATS = ['', 'regulatory', 'threat', 'vendor', 'macro']
  const CAT_LABELS: Record<string, string> = { '': 'All', regulatory: 'Regulatory', threat: 'Threat intel', vendor: 'Vendor', macro: 'Macro' }
  const SEV_COLORS: Record<string, string> = { critical: 'var(--red)', high: 'var(--amber)', medium: 'var(--blue)', info: 'var(--teal)' }

  return (
    <div className="page animate-fade">
      <div className="page-header">
        <div>
          <div className="page-title">Risk Radar</div>
          <div className="page-sub">{data?.total ?? 0} signals · refreshes every 15s</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <LiveDot />
          <span style={{ fontSize: 12, color: 'var(--teal2)', fontWeight: 500 }}>Live</span>
        </div>
      </div>

      {data && (
        <div style={{ display: 'flex', gap: 12, padding: '10px 24px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          {[{label:'Critical',v:'critical'},{label:'High',v:'high'},{label:'New today',v:''}].map(s => (
            <div key={s.label} style={{ fontSize: 12, color: 'var(--text2)' }}>
              <span style={{ fontWeight: 500, color: s.v === 'critical' ? 'var(--red)' : s.v === 'high' ? 'var(--amber)' : 'var(--accent2)', marginRight: 4 }}>
                {s.v === 'critical' ? data.counts.critical : s.v === 'high' ? data.counts.high : data.counts.new_today}
              </span>{s.label}
            </div>
          ))}
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 5 }}>
            {CATS.map(c => (
              <button key={c} onClick={() => setCatFilter(c)}
                style={{ fontSize: 11, fontWeight: 500, padding: '3px 10px', borderRadius: 99, cursor: 'pointer', fontFamily: 'var(--font)', border: '1px solid', transition: 'all .12s',
                  background: catFilter === c ? 'rgba(108,99,255,.2)' : 'none',
                  borderColor: catFilter === c ? 'rgba(108,99,255,.4)' : 'var(--border2)',
                  color: catFilter === c ? 'var(--accent2)' : 'var(--text2)',
                }}>{CAT_LABELS[c]}</button>
            ))}
          </div>
        </div>
      )}

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ flex: 1.6, overflowY: 'auto', borderRight: '1px solid var(--border)' }}>
          {isLoading
            ? <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}><Spinner /></div>
            : !data?.items.length
            ? <EmptyState title="No signals" body="Signal feeds will populate as data sources are configured" />
            : data.items.map(sig => (
              <div key={sig.id} onClick={() => setSelected(sig)}
                style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', cursor: 'pointer', transition: 'background .12s',
                  background: selected?.id === sig.id ? 'rgba(108,99,255,.08)' : 'transparent',
                  borderLeft: selected?.id === sig.id ? '2px solid var(--accent)' : '2px solid transparent',
                }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <span style={{ fontSize: 9, fontWeight: 500, padding: '2px 6px', borderRadius: 3, background: SEV_COLORS[sig.severity] + '22', color: SEV_COLORS[sig.severity], textTransform: 'uppercase', letterSpacing: '.05em' }}>{sig.source}</span>
                  <span style={{ fontSize: 10, color: 'var(--text3)', marginLeft: 'auto' }}>{new Date(sig.created_at).toLocaleDateString()}</span>
                  <SeverityChip severity={sig.severity} />
                  {sig.is_new && <span style={{ fontSize: 9, fontWeight: 500, color: 'var(--accent2)', background: 'rgba(108,99,255,.15)', padding: '1px 5px', borderRadius: 99 }}>New</span>}
                </div>
                <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', lineHeight: 1.35, marginBottom: 5 }}>{sig.title}</div>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {sig.tags.slice(0,3).map(t => <span key={t} style={{ fontSize: 9, color: 'var(--text3)', background: 'var(--bg3)', padding: '1px 5px', borderRadius: 99 }}>{t}</span>)}
                </div>
              </div>
            ))
          }
        </div>

        <div style={{ width: 280, flexShrink: 0, overflowY: 'auto', padding: 16 }}>
          {!selected
            ? <EmptyState title="Select a signal" body="Click a signal to see AI impact assessment" />
            : (
              <div className="animate-fade">
                <div style={{ fontSize: 10, fontWeight: 500, letterSpacing: '.05em', textTransform: 'uppercase', color: 'var(--text3)', marginBottom: 4 }}>{selected.source} · Signal detail</div>
                <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)', lineHeight: 1.3, marginBottom: 10 }}>{selected.title}</div>
                <div style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.55, marginBottom: 12 }}>{selected.body}</div>
                {selected.ai_recommendation && (
                  <div style={{ background: 'rgba(108,99,255,.08)', border: '1px solid rgba(108,99,255,.25)', borderRadius: 10, padding: '10px 12px', marginBottom: 12 }}>
                    <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--accent2)', marginBottom: 5, display: 'flex', alignItems: 'center', gap: 5 }}>
                      <div style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--accent2)', animation: 'pulse 2s infinite' }} />
                      AI recommendation
                    </div>
                    <div style={{ fontSize: 12, color: 'rgba(232,234,240,.85)', lineHeight: 1.5 }}>{selected.ai_recommendation}</div>
                  </div>
                )}
                <Button variant="danger" size="sm" onClick={() => { dismiss.mutate(selected.id); setSelected(null) }}>Dismiss signal</Button>
              </div>
            )
          }
        </div>
      </div>
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
