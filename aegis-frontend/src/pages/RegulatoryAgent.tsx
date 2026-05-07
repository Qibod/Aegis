import React, { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { regulatoryApi } from '@/api/client'
import { Button, SeverityChip, Spinner, EmptyState } from '@/components/ui'
import type { RegulatoryChange, RegulatoryChangeListItem, RegulatoryDeadline, RegChangeTask } from '@/types'

// ── Constants ─────────────────────────────────────────────────────────────────

const PIPELINE_STAGES = [
  { key: 'ingested',  label: 'Ingest feeds',      icon: '⬇' },
  { key: 'filtered',  label: 'Relevance filter',  icon: '⚖' },
  { key: 'mapped',    label: 'Map to controls',   icon: '🗺' },
  { key: 'assessed',  label: 'Assess impact',     icon: '🔎' },
  { key: 'actioned',  label: 'Generate action plan', icon: '📋' },
]

const STAGE_ORDER = ['ingested','filtered','mapped','assessed','actioned']

const SOURCE_COLORS: Record<string, string> = {
  'EBA':     '#4f9cf9', 'DNB': '#e05c5c', 'AP (NL)': '#8b5cf6',
  'EC':      '#f59e0b', 'ISO': '#10b981', 'SEC':     '#6366f1',
  'ENISA':   '#06b6d4', 'FATF': '#ef4444',
  'default': '#6c63ff',
}

const GAP_COLORS: Record<string, string> = {
  'Critical gap':   'var(--red)',
  'Partial gap':    'var(--amber)',
  'Update required':'var(--blue)',
  'Review required':'var(--teal)',
  'Adequate':       'var(--text3)',
}

const ROLE_COLORS: Record<string, string> = {
  'MLRO':       'rgba(224,82,82,.15)',
  'Legal':      'rgba(139,92,246,.15)',
  'IT':         'rgba(79,156,249,.15)',
  'Compliance': 'rgba(245,158,11,.15)',
  'Audit':      'rgba(30,185,138,.15)',
}
const ROLE_TEXT: Record<string, string> = {
  'MLRO': 'var(--red)', 'Legal': '#a78bfa', 'IT': '#4f9cf9',
  'Compliance': 'var(--amber)', 'Audit': 'var(--teal)',
}

const SEV_COLOR: Record<string, string> = {
  critical: 'var(--red)', high: 'var(--amber)',
  medium: 'var(--blue)', low: 'var(--teal)',
}

// ── Main page ─────────────────────────────────────────────────────────────────

export const RegulatoryAgentPage: React.FC = () => {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [sevFilter, setSevFilter] = useState('')
  const [simulating, setSimulating] = useState(false)
  const [newChangeId, setNewChangeId] = useState<string | null>(null)

  const { data: listData, isLoading } = useQuery({
    queryKey: ['reg-changes', sevFilter],
    queryFn: () => regulatoryApi.list({ severity: sevFilter || undefined }),
    refetchInterval: 30_000,
  })

  const { data: deadlines } = useQuery({
    queryKey: ['reg-deadlines'],
    queryFn: regulatoryApi.deadlines,
    staleTime: 60_000,
  })

  const { data: selected, isLoading: loadingDetail } = useQuery({
    queryKey: ['reg-change', selectedId],
    queryFn: () => regulatoryApi.get(selectedId!),
    enabled: !!selectedId,
  })

  const simulateMutation = useMutation({
    mutationFn: regulatoryApi.simulateUpdate,
    onMutate: () => setSimulating(true),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['reg-changes'] })
      qc.invalidateQueries({ queryKey: ['reg-deadlines'] })
      setNewChangeId(data.id)
      setSelectedId(data.id)
      setTimeout(() => setNewChangeId(null), 4000)
      setSimulating(false)
    },
    onError: () => setSimulating(false),
  })

  const dismissMutation = useMutation({
    mutationFn: regulatoryApi.dismiss,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reg-changes'] })
      setSelectedId(null)
    },
  })

  const updateTaskMutation = useMutation({
    mutationFn: ({ taskId, status }: { taskId: string; status: string }) =>
      regulatoryApi.updateTask(taskId, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reg-change', selectedId] }),
  })

  // Determine the highest stage reached across all changes for the pipeline bar
  const maxStage = listData?.items.reduce((max, item) => {
    const idx = STAGE_ORDER.indexOf(item.pipeline_stage)
    return Math.max(max, idx)
  }, 0) ?? 4

  return (
    <div className="page animate-fade" style={{ display: 'flex', flexDirection: 'column' }}>
      {/* ── Header ── */}
      <div className="page-header" style={{ flexShrink: 0 }}>
        <div>
          <div className="page-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span>Regulatory Change Agent</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(30,185,138,.12)', border: '1px solid rgba(30,185,138,.25)', borderRadius: 99, padding: '3px 10px' }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--teal)', animation: 'pulse 2s infinite' }} />
              <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--teal2)' }}>Monitoring 12 feeds</span>
            </div>
          </div>
          <div className="page-sub">Last scan: 4 min ago · {listData?.total ?? 0} changes detected</div>
        </div>
        <Button variant="primary" size="md" loading={simulating}
          onClick={() => simulateMutation.mutate()}>
          ↻ Simulate live update
        </Button>
      </div>

      {/* ── Pipeline strip ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 0, padding: '10px 24px', borderBottom: '1px solid var(--border)', flexShrink: 0, background: 'var(--bg1)', overflowX: 'auto' }}>
        {PIPELINE_STAGES.map((stage, i) => {
          const reached = i <= maxStage
          const active  = i === maxStage
          return (
            <React.Fragment key={stage.key}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 12px', borderRadius: 6,
                background: active ? 'rgba(108,99,255,.15)' : reached ? 'rgba(30,185,138,.08)' : 'transparent',
                border: active ? '1px solid rgba(108,99,255,.3)' : '1px solid transparent',
                flexShrink: 0,
              }}>
                <span style={{ fontSize: 13 }}>{stage.icon}</span>
                <span style={{ fontSize: 11, fontWeight: active ? 600 : 400, color: active ? 'var(--accent2)' : reached ? 'var(--teal2)' : 'var(--text3)', whiteSpace: 'nowrap' }}>
                  {stage.label}
                </span>
              </div>
              {i < PIPELINE_STAGES.length - 1 && (
                <div style={{ width: 20, height: 1, background: i < maxStage ? 'rgba(30,185,138,.4)' : 'var(--border2)', flexShrink: 0 }}>
                  <div style={{ fontSize: 10, color: 'var(--text3)', textAlign: 'center', marginTop: -8 }}>→</div>
                </div>
              )}
            </React.Fragment>
          )
        })}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 5, flexShrink: 0 }}>
          {[{label:'All',v:''},{label:'Critical',v:'critical'},{label:'High',v:'high'},{label:'Medium',v:'medium'}].map(f => (
            <button key={f.v} onClick={() => setSevFilter(f.v)}
              style={{ fontSize: 11, fontWeight: 500, padding: '3px 10px', borderRadius: 99, cursor: 'pointer', fontFamily: 'var(--font)', border: '1px solid',
                background: sevFilter === f.v ? 'rgba(108,99,255,.2)' : 'none',
                borderColor: sevFilter === f.v ? 'rgba(108,99,255,.4)' : 'var(--border2)',
                color: sevFilter === f.v ? 'var(--accent2)' : 'var(--text2)',
              }}>{f.label}</button>
          ))}
        </div>
      </div>

      {/* ── Stat strip ── */}
      {listData && (
        <div style={{ display: 'flex', gap: 20, padding: '8px 24px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
          <StatPill label="Critical" value={listData.counts.critical} color="var(--red)" />
          <StatPill label="High" value={listData.counts.high} color="var(--amber)" />
          <StatPill label="New today" value={listData.counts.new} color="var(--accent2)" />
          <StatPill label="Total" value={listData.total} color="var(--text3)" />
        </div>
      )}

      {/* ── Main two-panel layout ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left: feed */}
        <div style={{ width: 400, flexShrink: 0, borderRight: '1px solid var(--border)', overflowY: 'auto' }}>
          {isLoading ? (
            <div style={{ display:'flex', justifyContent:'center', padding:'3rem' }}><Spinner /></div>
          ) : !listData?.items.length ? (
            <EmptyState title="No changes detected" body="Feed monitoring will surface relevant changes automatically" />
          ) : listData.items.map(item => (
            <FeedCard
              key={item.id}
              item={item}
              isSelected={selectedId === item.id}
              isNew={newChangeId === item.id}
              onClick={() => setSelectedId(item.id)}
            />
          ))}
        </div>

        {/* Right: detail panel */}
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
          {!selectedId ? (
            <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', flex:1, gap:10 }}>
              <div style={{ fontSize: 32 }}>📋</div>
              <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>Select a change</div>
              <div style={{ fontSize: 12, color: 'var(--text3)' }}>to see AI impact assessment and auto-generated action plan</div>
            </div>
          ) : loadingDetail ? (
            <div style={{ display:'flex', justifyContent:'center', padding:'3rem' }}><Spinner /></div>
          ) : selected ? (
            <DetailPanel
              change={selected}
              onDismiss={() => dismissMutation.mutate(selected.id)}
              onToggleTask={(taskId, current) =>
                updateTaskMutation.mutate({ taskId, status: current === 'done' ? 'pending' : 'done' })
              }
            />
          ) : null}
        </div>
      </div>

      {/* ── Deadline calendar strip ── */}
      {deadlines && deadlines.length > 0 && (
        <DeadlineStrip deadlines={deadlines} onSelect={setSelectedId} />
      )}
    </div>
  )
}

// ── Feed card ─────────────────────────────────────────────────────────────────

const FeedCard: React.FC<{
  item: RegulatoryChangeListItem
  isSelected: boolean
  isNew: boolean
  onClick: () => void
}> = ({ item, isSelected, isNew, onClick }) => {
  const srcColor = SOURCE_COLORS[item.source] ?? SOURCE_COLORS.default
  const progress = item.task_total > 0 ? (item.task_done / item.task_total) * 100 : 0

  return (
    <div onClick={onClick}
      style={{
        padding: '12px 16px', borderBottom: '1px solid var(--border)', cursor: 'pointer',
        transition: 'all .15s',
        background: isSelected ? 'rgba(108,99,255,.08)' : isNew ? 'rgba(30,185,138,.05)' : 'transparent',
        borderLeft: `3px solid ${isSelected ? 'var(--accent)' : isNew ? 'var(--teal)' : 'transparent'}`,
        animation: isNew ? 'slideInLeft .4s ease' : undefined,
      }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
        <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 6px', borderRadius: 3, background: srcColor + '22', color: srcColor, textTransform: 'uppercase', letterSpacing: '.05em', flexShrink: 0 }}>
          {item.source}
        </span>
        <span style={{ fontSize: 10, color: 'var(--text3)', marginLeft: 'auto' }}>
          {new Date(item.published_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}
        </span>
        <SeverityChip severity={item.severity} />
        {item.is_new && (
          <span style={{ fontSize: 9, fontWeight: 600, color: 'var(--accent2)', background: 'rgba(108,99,255,.15)', padding: '1px 5px', borderRadius: 99 }}>New</span>
        )}
      </div>

      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', lineHeight: 1.35, marginBottom: 5 }}>{item.title}</div>
      {item.summary && (
        <div style={{ fontSize: 11, color: 'var(--text3)', lineHeight: 1.4, marginBottom: 7, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {item.summary}
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        {item.tags.slice(0, 3).map(t => (
          <span key={t} style={{ fontSize: 9, fontWeight: 500, padding: '2px 6px', borderRadius: 3, background: 'var(--bg3)', color: 'var(--text3)' }}>{t}</span>
        ))}
        {item.deadline_label && (
          <span style={{ fontSize: 9, fontWeight: 600, padding: '2px 7px', borderRadius: 3, background: 'rgba(224,82,82,.12)', color: 'var(--red)', marginLeft: 'auto' }}>
            Deadline: {item.deadline_label}
          </span>
        )}
      </div>

      {item.task_total > 0 && (
        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ flex: 1, height: 3, background: 'var(--bg3)', borderRadius: 99, overflow: 'hidden' }}>
            <div style={{ height: '100%', background: progress === 100 ? 'var(--teal)' : 'var(--accent)', borderRadius: 99, width: `${progress}%`, transition: 'width .3s' }} />
          </div>
          <span style={{ fontSize: 9, color: 'var(--text3)', whiteSpace: 'nowrap' }}>{item.task_done}/{item.task_total} tasks</span>
        </div>
      )}
    </div>
  )
}

// ── Detail panel ──────────────────────────────────────────────────────────────

const DetailPanel: React.FC<{
  change: RegulatoryChange
  onDismiss: () => void
  onToggleTask: (taskId: string, current: string) => void
}> = ({ change, onDismiss, onToggleTask }) => {
  const [expandedPhases, setExpandedPhases] = useState<Set<number>>(new Set([1, 2, 3]))
  const srcColor = SOURCE_COLORS[change.source] ?? SOURCE_COLORS.default

  const togglePhase = (phase: number) => {
    setExpandedPhases(prev => {
      const next = new Set(prev)
      next.has(phase) ? next.delete(phase) : next.add(phase)
      return next
    })
  }

  const phases = [1, 2, 3]
  const phaseLabels: Record<number, string> = {}
  const tasksByPhase: Record<number, RegChangeTask[]> = {}
  for (const t of change.tasks) {
    if (!tasksByPhase[t.phase]) tasksByPhase[t.phase] = []
    tasksByPhase[t.phase].push(t)
    if (t.phase_label) phaseLabels[t.phase] = t.phase_label
  }

  return (
    <div className="animate-fade" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 3, background: srcColor + '22', color: srcColor, textTransform: 'uppercase', letterSpacing: '.05em' }}>
            {change.source}
          </span>
          {change.regulation_family && (
            <span style={{ fontSize: 10, fontWeight: 500, padding: '2px 7px', borderRadius: 3, background: 'var(--bg2)', color: 'var(--text3)' }}>{change.regulation_family}</span>
          )}
          <SeverityChip severity={change.severity} />
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
            <Button variant="ghost" size="sm" onClick={onDismiss}>Dismiss</Button>
          </div>
        </div>
        <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)', lineHeight: 1.35, marginBottom: 8 }}>{change.title}</div>
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
          {change.tags.map(t => (
            <span key={t} style={{ fontSize: 10, fontWeight: 500, padding: '2px 8px', borderRadius: 3, background: 'var(--bg2)', color: 'var(--text3)' }}>{t}</span>
          ))}
          {change.deadline_label && (
            <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 3, background: 'rgba(224,82,82,.12)', color: 'var(--red)' }}>
              ⏱ Deadline: {change.deadline_label}
            </span>
          )}
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
        {/* Impact assessment */}
        <SectionHeading>Impact assessment &amp; action plan</SectionHeading>

        {change.impact_assessment && (
          <div style={{ background: 'rgba(108,99,255,.07)', border: '1px solid rgba(108,99,255,.2)', borderRadius: 10, padding: '12px 14px', marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent2)', animation: 'pulse 2s infinite' }} />
              <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--accent2)', textTransform: 'uppercase', letterSpacing: '.05em' }}>AI Assessment</span>
            </div>
            <div style={{ fontSize: 12, color: 'rgba(232,234,240,.9)', lineHeight: 1.65 }}>{change.impact_assessment}</div>
          </div>
        )}

        {/* Matched controls */}
        {change.matched_controls.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 8 }}>Control impact</div>
            {change.matched_controls.map((mc, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 10px', background: 'var(--bg2)', borderRadius: 7, marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: 'var(--text)', flex: 1 }}>{mc.control_name}</span>
                <span style={{ fontSize: 10, fontWeight: 600, color: GAP_COLORS[mc.gap_type] ?? 'var(--text3)', marginLeft: 8, flexShrink: 0 }}>{mc.gap_type}</span>
              </div>
            ))}
          </div>
        )}

        {/* Action plan phases */}
        {change.tasks.length > 0 && (
          <div>
            <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 10 }}>Action plan</div>
            {phases.map(phase => {
              const tasks = tasksByPhase[phase] ?? []
              if (!tasks.length) return null
              const expanded = expandedPhases.has(phase)
              const done = tasks.filter(t => t.status === 'done').length
              const phaseColors = ['rgba(108,99,255,.15)', 'rgba(232,168,56,.15)', 'rgba(30,185,138,.15)']
              const phaseText  = ['var(--accent2)', 'var(--amber)', 'var(--teal2)']

              return (
                <div key={phase} style={{ marginBottom: 10, background: 'var(--bg1)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
                  <div onClick={() => togglePhase(phase)}
                    style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', borderBottom: expanded ? '1px solid var(--border)' : 'none', cursor: 'pointer', userSelect: 'none' }}>
                    <div style={{ width: 22, height: 22, borderRadius: '50%', background: phaseColors[phase-1], display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 600, color: phaseText[phase-1], flexShrink: 0 }}>
                      {phase}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>{phaseLabels[phase] ?? `Phase ${phase}`}</div>
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text3)' }}>{done}/{tasks.length}</div>
                    {/* Phase mini progress */}
                    <div style={{ width: 40, height: 3, background: 'var(--bg3)', borderRadius: 99, overflow: 'hidden' }}>
                      <div style={{ height: '100%', background: phaseText[phase-1], width: `${tasks.length > 0 ? (done/tasks.length)*100 : 0}%` }} />
                    </div>
                    <span style={{ fontSize: 10, color: 'var(--text3)' }}>{expanded ? '▲' : '▼'}</span>
                  </div>

                  {expanded && tasks.map(task => (
                    <div key={task.id}
                      style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 14px', borderBottom: '1px solid var(--border)' }}>
                      <div onClick={() => onToggleTask(task.id, task.status)}
                        style={{ width: 14, height: 14, borderRadius: 3, border: `1.5px solid ${task.status === 'done' ? 'var(--accent)' : 'var(--border2)'}`, background: task.status === 'done' ? 'var(--accent)' : 'none', cursor: 'pointer', flexShrink: 0, marginTop: 2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        {task.status === 'done' && <svg width="8" height="8" viewBox="0 0 8 8" fill="none"><path d="M1.5 4l2 2 3-3" stroke="white" strokeWidth="1.2" strokeLinecap="round"/></svg>}
                      </div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 12, color: task.status === 'done' ? 'var(--text3)' : 'var(--text)', textDecoration: task.status === 'done' ? 'line-through' : 'none', lineHeight: 1.35 }}>
                          {task.label}
                        </div>
                        {task.due_week && (
                          <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2 }}>Week {task.due_week}</div>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: 4, flexShrink: 0, alignItems: 'center' }}>
                        {task.is_priority && <span style={{ fontSize: 9, fontWeight: 600, color: 'var(--red)', background: 'rgba(224,82,82,.12)', padding: '1px 5px', borderRadius: 99 }}>P1</span>}
                        {task.role && (
                          <span style={{ fontSize: 9, fontWeight: 600, padding: '1px 6px', borderRadius: 3, background: ROLE_COLORS[task.role] ?? 'var(--bg2)', color: ROLE_TEXT[task.role] ?? 'var(--text3)' }}>
                            {task.role}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        )}

        {/* No tasks — offer AI generation */}
        {change.tasks.length === 0 && (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <div style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 10 }}>No action plan generated yet</div>
            <Button variant="primary" size="sm"
              onClick={() => regulatoryApi.assess(change.id)}>
              Generate AI action plan
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Deadline calendar strip ───────────────────────────────────────────────────

const DeadlineStrip: React.FC<{
  deadlines: RegulatoryDeadline[]
  onSelect: (id: string) => void
}> = ({ deadlines, onSelect }) => (
  <div style={{ borderTop: '1px solid var(--border)', background: 'var(--bg1)', padding: '10px 24px', flexShrink: 0 }}>
    <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 8 }}>Upcoming deadlines</div>
    <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 2 }}>
      {deadlines.map(d => {
        const isUrgent = d.days_remaining <= 30
        const isCritical = d.days_remaining <= 7
        const color = isCritical ? 'var(--red)' : isUrgent ? 'var(--amber)' : 'var(--text3)'
        const bg = isCritical ? 'rgba(224,82,82,.12)' : isUrgent ? 'rgba(232,168,56,.12)' : 'var(--bg2)'
        const border = isCritical ? 'rgba(224,82,82,.3)' : isUrgent ? 'rgba(232,168,56,.3)' : 'var(--border)'

        return (
          <div key={d.change_id} onClick={() => onSelect(d.change_id)}
            style={{ flexShrink: 0, padding: '8px 12px', borderRadius: 8, background: bg, border: `1px solid ${border}`, cursor: 'pointer', minWidth: 120, maxWidth: 160 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color, marginBottom: 3 }}>
              {isCritical ? '🚨 ' : isUrgent ? '⚠️ ' : ''}{d.deadline_label ?? `${d.days_remaining}d`}
            </div>
            <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text)', lineHeight: 1.3, marginBottom: 3 }}>{d.regulation_family ?? 'Regulatory'}</div>
            <div style={{ fontSize: 9, color: 'var(--text3)', lineHeight: 1.3, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{d.title}</div>
          </div>
        )
      })}
    </div>
  </div>
)

// ── Shared mini components ────────────────────────────────────────────────────

const StatPill: React.FC<{ label: string; value: number; color: string }> = ({ label, value, color }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
    <span style={{ fontSize: 14, fontWeight: 300, color, letterSpacing: '-0.5px' }}>{value}</span>
    <span style={{ fontSize: 11, color: 'var(--text3)' }}>{label}</span>
  </div>
)

const SectionHeading: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 12 }}>{children}</div>
)
