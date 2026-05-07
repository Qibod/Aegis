import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { dashboardApi } from '@/api/client'
import { useAuthStore } from '@/store'
import {
  Card, Chip, SeverityChip, Spinner, Avatar,
  CoverageBar, EmptyState, LiveDot,
} from '@/components/ui'
import type { Risk, Signal } from '@/types'

export const DashboardPage: React.FC = () => {
  const { user } = useAuthStore()
  const navigate = useNavigate()

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: dashboardApi.get,
    refetchInterval: 30_000,
  })

  const greeting = () => {
    const h = new Date().getHours()
    if (h < 12) return 'Good morning'
    if (h < 17) return 'Good afternoon'
    return 'Good evening'
  }

  if (isLoading) return <LoadingState />
  if (error || !data) return <ErrorState />

  const { metrics, ai_insights, top_risks, framework_coverage, recent_signals } = data

  return (
    <div className="page animate-fade">
      <div className="page-header">
        <div>
          <div className="page-title">{greeting()}, {user?.full_name?.split(' ')[0] ?? 'there'}</div>
          <div className="page-sub">Here's where things stand — {new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}</div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-ghost btn-md" onClick={() => navigate('/audit')}>Plan audit</button>
          <button className="btn btn-primary btn-md" onClick={() => navigate('/radar')}>View signals →</button>
        </div>
      </div>

      <div className="page-body">
        {/* Metrics */}
        <div className="grid-4" style={{ marginBottom: 20 }}>
          <MetricCard
            label="Open risks"
            value={metrics.total_risks}
            sub={`${metrics.high_risks} high · ${metrics.medium_risks} medium`}
            color="var(--red)"
            onClick={() => navigate('/risks')}
          />
          <MetricCard
            label="Controls mapped"
            value={metrics.controls_mapped}
            sub={`${metrics.control_gaps} gaps detected`}
            color="var(--amber)"
            onClick={() => navigate('/controls')}
          />
          <MetricCard
            label="Audit areas"
            value={metrics.audit_areas}
            sub="Ready to plan"
            color="var(--teal2)"
            onClick={() => navigate('/audit')}
          />
          <MetricCard
            label="Frameworks"
            value={metrics.frameworks_active}
            sub="Active"
            color="var(--accent2)"
          />
        </div>

        {/* AI Insights */}
        {ai_insights.length > 0 && (
          <div className="ai-panel">
            <div className="ai-header">
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent2)', animation: 'pulse 2s infinite' }} />
              AI audit co-pilot — {ai_insights.length} insight{ai_insights.length !== 1 ? 's' : ''} today
            </div>
            {ai_insights.map((insight, i) => (
              <div key={i} className="ai-insight">
                {insight.text}
                <div className="ai-source">Source: {insight.source}</div>
              </div>
            ))}
          </div>
        )}

        <div className="grid-2">
          {/* Top risks */}
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
              <span style={{ fontSize: 12, fontWeight: 500 }}>Top risks by severity</span>
              <button className="btn btn-ghost btn-sm" onClick={() => navigate('/risks')}>View all →</button>
            </div>
            {top_risks.length === 0
              ? <EmptyState title="No risks yet" body="Create your first risk or run AI fingerprinting" />
              : <table className="table">
                  <thead><tr><th>Risk</th><th>Severity</th><th>Coverage</th><th>Owner</th></tr></thead>
                  <tbody>
                    {top_risks.slice(0, 7).map(risk => (
                      <RiskRow key={risk.id} risk={risk} onClick={() => navigate(`/risks`)} />
                    ))}
                  </tbody>
                </table>
            }
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {/* Framework coverage */}
            <div className="card">
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
                <span style={{ fontSize: 12, fontWeight: 500 }}>Framework coverage</span>
              </div>
              <div style={{ padding: 16 }}>
                {framework_coverage.length === 0
                  ? <EmptyState title="No frameworks configured" />
                  : framework_coverage.map(fw => (
                    <div key={fw.code} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                      <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text2)', width: 90, flexShrink: 0 }}>{fw.label}</span>
                      <div style={{ flex: 1 }}><CoverageBar value={fw.coverage_pct} /></div>
                      <span style={{ fontSize: 11, fontWeight: 500, width: 32, textAlign: 'right', color: fw.coverage_pct >= 70 ? 'var(--teal2)' : fw.coverage_pct >= 40 ? 'var(--amber)' : 'var(--red)' }}>
                        {Math.round(fw.coverage_pct)}%
                      </span>
                    </div>
                  ))
                }
              </div>
            </div>

            {/* Live signals */}
            <div className="card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
                <span style={{ fontSize: 12, fontWeight: 500 }}>Live signals</span>
                <button className="btn btn-ghost btn-sm" onClick={() => navigate('/radar')}>See all →</button>
              </div>
              {recent_signals.length === 0
                ? <EmptyState title="No signals yet" body="Signal feeds will appear here" />
                : recent_signals.slice(0, 3).map(s => <SignalRow key={s.id} signal={s} />)
              }
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────
const MetricCard: React.FC<{ label: string; value: number; sub: string; color: string; onClick?: () => void }> = ({
  label, value, sub, color, onClick,
}) => (
  <div className="metric-card" onClick={onClick}>
    <div className="metric-label">{label}</div>
    <div className="metric-value" style={{ color }}>{value}</div>
    <div className="metric-sub">{sub}</div>
  </div>
)

const RiskRow: React.FC<{ risk: Risk; onClick: () => void }> = ({ risk, onClick }) => (
  <tr onClick={onClick}>
    <td>
      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>{risk.name}</div>
      <div style={{ fontSize: 11, color: 'var(--text2)' }}>{risk.domain}</div>
    </td>
    <td><SeverityChip severity={risk.inherent_severity} /></td>
    <td style={{ width: 100 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <div style={{ flex: 1 }}><CoverageBar value={risk.control_coverage_pct} /></div>
        <span style={{ fontSize: 10, color: 'var(--text3)', width: 28 }}>{Math.round(risk.control_coverage_pct)}%</span>
      </div>
    </td>
    <td>
      {risk.owner
        ? <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <Avatar initials={risk.owner.initials} color={risk.owner.avatar_color} size={18} />
            <span style={{ fontSize: 11, color: 'var(--text2)' }}>{risk.owner.full_name.split(' ')[0]}</span>
          </div>
        : <span style={{ fontSize: 11, color: 'var(--text3)' }}>Unassigned</span>
      }
    </td>
  </tr>
)

const SignalRow: React.FC<{ signal: Signal }> = ({ signal }) => {
  const sc: Record<string, string> = { critical: 'var(--red)', high: 'var(--amber)', medium: 'var(--blue)', info: 'var(--teal)' }
  return (
    <div style={{ padding: '9px 14px', borderBottom: '1px solid var(--border)', cursor: 'pointer' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
        <span style={{ fontSize: 10, fontWeight: 500, padding: '1px 6px', borderRadius: 3, background: sc[signal.severity] + '22', color: sc[signal.severity] }}>{signal.source}</span>
        {signal.is_new && <span style={{ fontSize: 9, fontWeight: 500, color: 'var(--accent2)', background: 'rgba(108,99,255,.15)', padding: '1px 5px', borderRadius: 99 }}>New</span>}
      </div>
      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', lineHeight: 1.35 }}>{signal.title.slice(0, 80)}{signal.title.length > 80 ? '…' : ''}</div>
    </div>
  )
}

const LoadingState = () => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
    <Spinner size={24} />
  </div>
)

const ErrorState = () => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text2)', fontSize: 13 }}>
    Could not load dashboard. Check your connection.
  </div>
)
