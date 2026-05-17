import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { risksApi, profileApi } from '@/api/client'
import { useUIStore } from '@/store'
import {
  Button, SeverityChip, Avatar, CoverageBar,
  EmptyState, Spinner, Input,
} from '@/components/ui'
import type {
  Risk, RiskCreate, HeatCell,
  LOB, OrgGeo, OrgProduct, CustomerSegment,
} from '@/types'

// ── Constants ─────────────────────────────────────────────────────────────────

const CANONICAL_DOMAINS = ['Financial Crime', 'Data & Privacy', 'Cyber & IT', 'Operational', 'Compliance', 'Strategic']
const LOB_COLOURS = ['#7b6daa', '#b87c3a', '#4e806a', '#4d6e9e', '#b34f42', '#867d72']

const SEV_BG: Record<string, string> = {
  critical: 'rgba(179,79,66,.45)',
  high:     'rgba(179,79,66,.25)',
  medium:   'rgba(184,124,58,.2)',
  low:      'rgba(78,128,106,.2)',
}
const SEV_TEXT: Record<string, string> = {
  critical: '#e87060',
  high:     '#cc6050',
  medium:   '#c9943a',
  low:      '#6a9e84',
}

const flagEmoji = (code: string) =>
  code.toUpperCase().split('').map(c => String.fromCodePoint(0x1F1E0 - 0x41 + c.charCodeAt(0))).join('')

const coverageColour = (pct: number) =>
  pct >= 70 ? 'var(--teal2)' : pct >= 40 ? 'var(--amber)' : 'var(--red)'

// ── Page state ─────────────────────────────────────────────────────────────────

type ViewMode = 'swimlane' | 'heat' | 'table'
type GroupBy = 'lob' | 'geography' | 'product' | 'segment'

interface PageState {
  view: ViewMode
  groupBy: GroupBy
  severity: string
  domain: string
  geoId: string
  lobId: string
}

// ── Main page component ───────────────────────────────────────────────────────

export const RisksPage: React.FC = () => {
  const qc = useQueryClient()
  const { addToast } = useUIStore()
  const [showCreate, setShowCreate] = useState(false)
  const [state, setState] = useState<PageState>({
    view: 'swimlane', groupBy: 'lob', severity: '', domain: '', geoId: '', lobId: '',
  })

  const set = <K extends keyof PageState>(k: K, v: PageState[K]) =>
    setState(s => ({ ...s, [k]: v }))

  const riskFilter = {
    severity: state.severity || undefined,
    domain: state.domain || undefined,
    lob_id: state.lobId || undefined,
    geo_id: state.geoId || undefined,
    page_size: 200,
  }

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['risks', 'universe-summary'],
    queryFn: risksApi.universeSummary,
  })

  const { data: riskData, isLoading: risksLoading } = useQuery({
    queryKey: ['risks', riskFilter],
    queryFn: () => risksApi.list(riskFilter),
  })

  const { data: lobs = [] } = useQuery({
    queryKey: ['profile', 'lobs'],
    queryFn: profileApi.listLobs,
  })

  const { data: geos = [] } = useQuery({
    queryKey: ['profile', 'geos'],
    queryFn: profileApi.listGeos,
  })

  const { data: products = [] } = useQuery({
    queryKey: ['profile', 'products'],
    queryFn: profileApi.listProducts,
  })

  const { data: segments = [] } = useQuery({
    queryKey: ['profile', 'segments'],
    queryFn: profileApi.listSegments,
  })

  const createMutation = useMutation({
    mutationFn: risksApi.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['risks'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      setShowCreate(false)
      addToast({ type: 'success', title: 'Risk created' })
    },
    onError: () => addToast({ type: 'error', title: 'Failed to create risk' }),
  })

  const deleteMutation = useMutation({
    mutationFn: risksApi.delete,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['risks'] })
      qc.invalidateQueries({ queryKey: ['risks', 'universe-summary'] })
      addToast({ type: 'info', title: 'Risk deleted' })
    },
  })

  const risks = riskData?.items ?? []
  const allDomains = Array.from(new Set(risks.map(r => r.domain).filter(Boolean) as string[]))

  const switchToTableFiltered = (lobId?: string, domain?: string) => {
    setState(s => ({
      ...s,
      view: 'table',
      lobId: lobId ?? s.lobId,
      domain: domain ?? s.domain,
    }))
  }

  return (
    <div className="page animate-fade" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title">Risk Universe</div>
          <div className="page-sub">
            {summary ? `${summary.total_risks} risks · ${summary.high_critical_count} high/critical` : 'Loading...'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {geos.length > 0 && (
            <select
              className="input"
              style={{ width: 180 }}
              value={state.geoId}
              onChange={e => set('geoId', e.target.value)}
            >
              <option value="">All geographies</option>
              {geos.map(g => (
                <option key={g.id} value={g.id}>
                  {flagEmoji(g.country)} {g.country}
                  {g.regulatory_flags?.length ? ` (${(g.regulatory_flags as string[]).slice(0, 2).join(', ')})` : ''}
                </option>
              ))}
            </select>
          )}
          <Button variant="primary" size="md" onClick={() => setShowCreate(true)}>+ Add risk</Button>
        </div>
      </div>

      {/* Summary band */}
      <SummaryBand
        summary={summary}
        loading={summaryLoading}
        geoFiltered={!!state.geoId}
        onAttentionClick={() => set('view', 'table')}
      />

      {/* Toolbar */}
      <RisksToolbar
        state={state}
        allDomains={allDomains}
        onViewChange={v => set('view', v)}
        onGroupByChange={v => set('groupBy', v)}
        onSeverityChange={v => set('severity', v)}
        onDomainChange={v => set('domain', v)}
      />

      {/* Main view area */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {risksLoading
          ? <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}><Spinner /></div>
          : state.view === 'heat'
          ? <HeatMatrixView
              summary={summary}
              lobs={lobs}
              onCellClick={(lobId, domain) => switchToTableFiltered(lobId, domain)}
            />
          : state.view === 'swimlane'
          ? <SwimlaneView
              risks={risks}
              groupBy={state.groupBy}
              lobs={lobs}
              geos={geos}
              products={products}
              segments={segments}
              total={riskData?.total ?? 0}
              onDelete={id => deleteMutation.mutate(id)}
            />
          : <TableView risks={risks} onDelete={id => deleteMutation.mutate(id)} />
        }
      </div>

      {showCreate && (
        <CreateRiskModal
          lobs={lobs}
          geos={geos}
          onClose={() => setShowCreate(false)}
          onSubmit={createMutation.mutate}
          loading={createMutation.isPending}
        />
      )}
    </div>
  )
}

// ── Summary Band ──────────────────────────────────────────────────────────────

interface SummaryData {
  total_risks: number
  high_critical_count: number
  unowned_count: number
  avg_coverage_pct: number
  domain_coverage: Array<{ domain: string; risk_count: number; avg_coverage_pct: number; worst_severity: string }>
  needs_attention: Risk[]
}

const SummaryBand: React.FC<{
  summary: SummaryData | undefined
  loading: boolean
  geoFiltered: boolean
  onAttentionClick: () => void
}> = ({ summary, loading, geoFiltered, onAttentionClick }) => {
  if (loading || !summary) {
    return (
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', height: 90, alignItems: 'center', justifyContent: 'center' }}>
        <Spinner />
      </div>
    )
  }

  const topDomains = summary.domain_coverage.slice(0, 4)

  return (
    <div style={{
      display: 'flex', flexShrink: 0,
      borderBottom: '1px solid var(--border)',
      background: 'var(--bg1)',
    }}>
      {/* Panel 1 — Total */}
      <div style={bandPanel}>
        <div style={bandLabel}>Total risks</div>
        <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--text)', lineHeight: 1.1 }}>
          {summary.total_risks}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 2 }}>
          {summary.high_critical_count} high/critical · {summary.total_risks - summary.high_critical_count} med/low
        </div>
      </div>

      <div style={bandDivider} />

      {/* Panel 2 — Avg coverage */}
      <div style={bandPanel}>
        <div style={bandLabel}>Avg control coverage</div>
        <div style={{ fontSize: 28, fontWeight: 700, color: coverageColour(summary.avg_coverage_pct), lineHeight: 1.1 }}>
          {Math.round(summary.avg_coverage_pct)}%
        </div>
        <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 2 }}>
          {summary.unowned_count} unowned risk{summary.unowned_count !== 1 ? 's' : ''}
        </div>
      </div>

      <div style={bandDivider} />

      {/* Panel 3 — Coverage frontier */}
      <div style={{ ...bandPanel, flex: 1.5 }}>
        <div style={bandLabel}>
          Coverage frontier{geoFiltered ? ' (filtered)' : ''}
        </div>
        {topDomains.length === 0
          ? <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>No domains yet</div>
          : topDomains.map(d => (
            <div key={d.domain} style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
              <div style={{ fontSize: 10, color: 'var(--text2)', width: 72, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {d.domain.substring(0, 10)}
              </div>
              <div style={{ flex: 1, height: 4, background: 'var(--bg3)', borderRadius: 2, overflow: 'hidden' }}>
                <div style={{
                  height: '100%',
                  width: `${d.avg_coverage_pct}%`,
                  background: coverageColour(d.avg_coverage_pct),
                  borderRadius: 2,
                }} />
              </div>
              <div style={{ fontSize: 10, color: 'var(--text2)', width: 28, textAlign: 'right' }}>
                {Math.round(d.avg_coverage_pct)}%
              </div>
            </div>
          ))
        }
      </div>

      <div style={bandDivider} />

      {/* Panel 4 — Needs attention */}
      <div style={{ ...bandPanel, flex: 1.5 }}>
        <div style={bandLabel}>Needs attention now</div>
        {summary.needs_attention.length === 0
          ? <div style={{ fontSize: 11, color: 'var(--teal2)', marginTop: 4 }}>All critical risks are owned and covered</div>
          : summary.needs_attention.map(r => (
            <div
              key={r.id}
              onClick={onAttentionClick}
              style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 5, cursor: 'pointer' }}
            >
              <div style={{
                width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                background: (r.inherent_severity === 'critical' || r.inherent_severity === 'high') ? 'var(--red)' : 'var(--amber)',
              }} />
              <div style={{ fontSize: 11, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 180 }}>
                {r.name.substring(0, 45)}
              </div>
            </div>
          ))
        }
      </div>
    </div>
  )
}

const bandPanel: React.CSSProperties = {
  flex: 1, padding: '12px 16px', display: 'flex', flexDirection: 'column', justifyContent: 'center',
}
const bandDivider: React.CSSProperties = {
  width: 1, background: 'var(--border)', flexShrink: 0, alignSelf: 'stretch',
}
const bandLabel: React.CSSProperties = {
  fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2,
}

// ── Toolbar ───────────────────────────────────────────────────────────────────

const RisksToolbar: React.FC<{
  state: PageState
  allDomains: string[]
  onViewChange: (v: ViewMode) => void
  onGroupByChange: (v: GroupBy) => void
  onSeverityChange: (v: string) => void
  onDomainChange: (v: string) => void
}> = ({ state, allDomains, onViewChange, onGroupByChange, onSeverityChange, onDomainChange }) => {
  const views: { key: ViewMode; label: string }[] = [
    { key: 'swimlane', label: '≡ Swimlane' },
    { key: 'heat', label: '⊞ Heat matrix' },
    { key: 'table', label: '☰ Table' },
  ]

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 16px',
      borderBottom: '1px solid var(--border)', background: 'var(--bg1)', flexShrink: 0,
    }}>
      {/* View toggle */}
      <div style={{ display: 'flex', background: 'var(--bg3)', borderRadius: 6, padding: 2, gap: 1 }}>
        {views.map(v => (
          <button
            key={v.key}
            onClick={() => onViewChange(v.key)}
            style={{
              padding: '4px 10px', borderRadius: 4, fontSize: 11, fontWeight: 500,
              border: 'none', cursor: 'pointer', transition: 'all .15s',
              background: state.view === v.key ? 'var(--bg1)' : 'transparent',
              color: state.view === v.key ? 'var(--text)' : 'var(--text2)',
              boxShadow: state.view === v.key ? '0 0 0 1px var(--border2)' : 'none',
            }}
          >
            {v.label}
          </button>
        ))}
      </div>

      {/* Group by (swimlane only) */}
      {state.view === 'swimlane' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 11, color: 'var(--text2)' }}>Group by:</span>
          <select
            className="input"
            style={{ width: 160, height: 28, fontSize: 11 }}
            value={state.groupBy}
            onChange={e => onGroupByChange(e.target.value as GroupBy)}
          >
            <option value="lob">Line of business</option>
            <option value="geography">Geography</option>
            <option value="product">Product</option>
            <option value="segment">Customer segment</option>
          </select>
        </div>
      )}

      <div style={{ flex: 1 }} />

      {/* Severity filter */}
      <select
        className="input"
        style={{ width: 130, height: 28, fontSize: 11 }}
        value={state.severity}
        onChange={e => onSeverityChange(e.target.value)}
      >
        <option value="">All severities</option>
        <option value="critical">Critical</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
      </select>

      {/* Domain filter */}
      <select
        className="input"
        style={{ width: 150, height: 28, fontSize: 11 }}
        value={state.domain}
        onChange={e => onDomainChange(e.target.value)}
      >
        <option value="">All domains</option>
        {allDomains.map(d => <option key={d} value={d}>{d}</option>)}
      </select>
    </div>
  )
}

// ── Heat Matrix View ──────────────────────────────────────────────────────────

const HeatMatrixView: React.FC<{
  summary: { heat_cells: HeatCell[] } | undefined
  lobs: LOB[]
  onCellClick: (lobId: string, domain: string) => void
}> = ({ summary, lobs, onCellClick }) => {
  if (!lobs.length) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--text2)' }}>
        Link risks to lines of business to unlock the heat matrix.{' '}
        <a href="/company-profile" style={{ color: 'var(--accent)' }}>Add your lines of business in Company Profile.</a>
      </div>
    )
  }

  const sortedLobs = [...lobs].sort((a, b) =>
    (b.is_primary ? 1 : 0) - (a.is_primary ? 1 : 0) || a.name.localeCompare(b.name)
  )
  const heatCells = summary?.heat_cells ?? []

  const getCell = (lobId: string, domain: string) =>
    heatCells.find(c => c.lob_id === lobId && c.domain === domain)

  return (
    <div style={{ padding: 20, overflow: 'auto' }}>
      <table style={{ borderCollapse: 'separate', borderSpacing: 4 }}>
        <thead>
          <tr>
            <th style={{ width: 130, textAlign: 'left', fontSize: 11, color: 'var(--text3)', paddingBottom: 8 }}></th>
            {CANONICAL_DOMAINS.map(d => (
              <th key={d} style={{ fontSize: 10, color: 'var(--text2)', fontWeight: 500, paddingBottom: 8, textAlign: 'center', minWidth: 90 }}>{d}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedLobs.map(lob => (
            <tr key={lob.id}>
              <td style={{ fontSize: 11, color: 'var(--text2)', paddingRight: 8, whiteSpace: 'nowrap', overflow: 'hidden', maxWidth: 130, textOverflow: 'ellipsis' }}>
                {lob.name}
              </td>
              {CANONICAL_DOMAINS.map(domain => {
                const cell = getCell(lob.id, domain)
                return (
                  <td key={domain}>
                    <div
                      style={{
                        padding: '8px 6px', textAlign: 'center', borderRadius: 4, minWidth: 80,
                        background: cell ? SEV_BG[cell.worst_severity] : 'var(--bg3)',
                        cursor: cell ? 'pointer' : 'default',
                        transition: 'filter .15s, transform .15s',
                      }}
                      onClick={() => cell && onCellClick(lob.id, domain)}
                      onMouseEnter={e => { if (cell) { const el = e.currentTarget as HTMLElement; el.style.filter = 'brightness(1.15)'; el.style.transform = 'scale(1.03)' } }}
                      onMouseLeave={e => { const el = e.currentTarget as HTMLElement; el.style.filter = ''; el.style.transform = '' }}
                    >
                      {cell
                        ? <>
                            <div style={{ fontSize: 16, fontWeight: 700, color: SEV_TEXT[cell.worst_severity] }}>{cell.risk_count}</div>
                            <div style={{ fontSize: 9, color: SEV_TEXT[cell.worst_severity], textTransform: 'capitalize' }}>{cell.worst_severity}</div>
                          </>
                        : <span style={{ color: 'var(--text3)', fontSize: 13 }}>—</span>
                      }
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
          {/* Unlinked row */}
          <tr>
            <td style={{ fontSize: 11, color: 'var(--text3)', paddingRight: 8 }}>Unlinked</td>
            {CANONICAL_DOMAINS.map(domain => (
              <td key={domain}>
                <div style={{ padding: '8px 6px', textAlign: 'center', background: 'var(--bg3)', borderRadius: 4, minWidth: 80 }}>
                  <span style={{ color: 'var(--text3)', fontSize: 13 }}>—</span>
                </div>
              </td>
            ))}
          </tr>
        </tbody>
      </table>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
        {(['low', 'medium', 'high', 'critical'] as const).map(s => (
          <span key={s} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: SEV_BG[s], color: SEV_TEXT[s], textTransform: 'capitalize', fontWeight: 500 }}>
            {s}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Swimlane View ─────────────────────────────────────────────────────────────

interface SwimGroup {
  id: string
  label: string
  colour: string
  risks: Risk[]
}

const SwimlaneView: React.FC<{
  risks: Risk[]
  groupBy: GroupBy
  lobs: LOB[]
  geos: OrgGeo[]
  products: OrgProduct[]
  segments: CustomerSegment[]
  total: number
  onDelete: (id: string) => void
}> = ({ risks, groupBy, lobs, geos, products, segments, total, onDelete }) => {
  const groups = buildGroups(risks, groupBy, lobs, geos, products, segments)

  return (
    <div style={{ padding: '12px 16px' }}>
      {total > 200 && (
        <div style={{ padding: '8px 12px', marginBottom: 12, background: 'var(--bg3)', borderRadius: 6, fontSize: 11, color: 'var(--text2)' }}>
          Showing first 200 risks. Use filters to narrow results.
        </div>
      )}
      {groups.map(group => (
        <SwimlaneGroupRow key={group.id} group={group} geos={geos} onDelete={onDelete} />
      ))}
    </div>
  )
}

function buildGroups(
  risks: Risk[],
  groupBy: GroupBy,
  lobs: LOB[],
  geos: OrgGeo[],
  products: OrgProduct[],
  segments: CustomerSegment[],
): SwimGroup[] {
  if (groupBy === 'lob') {
    const sorted = [...lobs]
      .filter(l => l.status === 'active' || l.status === 'planned')
      .sort((a, b) => (b.is_primary ? 1 : 0) - (a.is_primary ? 1 : 0) || a.name.localeCompare(b.name))
    const groups: SwimGroup[] = sorted.map((lob, i) => ({
      id: lob.id, label: lob.name,
      colour: LOB_COLOURS[i % LOB_COLOURS.length],
      risks: risks.filter(r => r.lob_id === lob.id),
    }))
    const unlinked = risks.filter(r => !r.lob_id)
    if (unlinked.length > 0 || groups.length === 0) {
      groups.push({ id: 'unlinked', label: 'Unlinked', colour: 'var(--text3)', risks: unlinked })
    }
    return groups
  }

  if (groupBy === 'geography') {
    const sorted = [...geos].sort((a, b) => {
      if (a.presence_type === 'headquarters') return -1
      if (b.presence_type === 'headquarters') return 1
      return a.country.localeCompare(b.country)
    })
    const groups: SwimGroup[] = sorted.map((geo, i) => ({
      id: geo.id, label: `${flagEmoji(geo.country)} ${geo.country}`,
      colour: LOB_COLOURS[i % LOB_COLOURS.length],
      risks: risks.filter(r => (r.geography_ids ?? []).includes(geo.id)),
    }))
    const unlinked = risks.filter(r => !(r.geography_ids ?? []).length)
    if (unlinked.length > 0) groups.push({ id: 'unlinked', label: 'Unlinked', colour: 'var(--text3)', risks: unlinked })
    return groups
  }

  if (groupBy === 'product') {
    const sorted = [...products].filter(p => p.status === 'live' || p.status === 'beta')
    const groups: SwimGroup[] = sorted.map((p, i) => ({
      id: p.id, label: p.name,
      colour: LOB_COLOURS[i % LOB_COLOURS.length],
      risks: risks.filter(r => (r.product_ids ?? []).includes(p.id)),
    }))
    const unlinked = risks.filter(r => !(r.product_ids ?? []).length)
    if (unlinked.length > 0) groups.push({ id: 'unlinked', label: 'Unlinked', colour: 'var(--text3)', risks: unlinked })
    return groups
  }

  const sorted = [...segments].sort((a, b) => a.segment_type.localeCompare(b.segment_type))
  const groups: SwimGroup[] = sorted.map((seg, i) => ({
    id: seg.id, label: seg.name,
    colour: LOB_COLOURS[i % LOB_COLOURS.length],
    risks: risks.filter(r => (r.segment_ids ?? []).includes(seg.id)),
  }))
  const unlinked = risks.filter(r => !(r.segment_ids ?? []).length)
  if (unlinked.length > 0) groups.push({ id: 'unlinked', label: 'Unlinked', colour: 'var(--text3)', risks: unlinked })
  return groups
}

const SwimlaneGroupRow: React.FC<{
  group: SwimGroup
  geos: OrgGeo[]
  onDelete: (id: string) => void
}> = ({ group, geos, onDelete }) => {
  const [open, setOpen] = useState(true)

  const critCount = group.risks.filter(r => r.inherent_severity === 'critical').length
  const highCount = group.risks.filter(r => r.inherent_severity === 'high').length
  const avgCov = group.risks.length
    ? Math.round(group.risks.reduce((s, r) => s + r.control_coverage_pct, 0) / group.risks.length)
    : 0

  return (
    <div style={{ marginBottom: 8, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)' }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'var(--bg2)', cursor: 'pointer', userSelect: 'none' }}
      >
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: group.colour, flexShrink: 0 }} />
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', flex: 1 }}>{group.label}</div>
        <span style={{ fontSize: 11, color: 'var(--text2)', marginRight: 4 }}>{group.risks.length} risks</span>
        {critCount > 0 && <Chip label={`${critCount} critical`} color="var(--red)" />}
        {highCount > 0 && <Chip label={`${highCount} high`} color="var(--amber)" />}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginLeft: 8 }}>
          <span style={{ fontSize: 10, color: 'var(--text2)' }}>Coverage</span>
          <div style={{ width: 60, height: 4, background: 'var(--bg3)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${avgCov}%`, background: coverageColour(avgCov), borderRadius: 2 }} />
          </div>
          <span style={{ fontSize: 10, color: 'var(--text2)' }}>{avgCov}%</span>
        </div>
        <div style={{ marginLeft: 8, fontSize: 12, color: 'var(--text3)', transform: open ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform .2s' }}>›</div>
      </div>

      {open && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 100px 120px 100px', padding: '6px 12px', borderBottom: '1px solid var(--border)', background: 'var(--bg1)' }}>
            {['Risk', 'Severity', 'Coverage', 'Owner'].map(h => (
              <div key={h} style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{h}</div>
            ))}
          </div>
          {group.risks.length === 0
            ? <div style={{ padding: '12px', fontSize: 11, color: 'var(--text3)' }}>No risks match current filters</div>
            : group.risks.map(risk => (
                <RiskSwimlaneRow key={risk.id} risk={risk} geos={geos} onDelete={() => onDelete(risk.id)} />
              ))
          }
        </div>
      )}
    </div>
  )
}

const RiskSwimlaneRow: React.FC<{ risk: Risk; geos: OrgGeo[]; onDelete: () => void }> = ({ risk, geos, onDelete }) => {
  const geoFlags = (risk.geography_ids ?? [])
    .map(gid => geos.find(g => g.id === gid))
    .filter(Boolean)
    .map(g => flagEmoji(g!.country))
    .join(' ')

  return (
    <div
      style={{ display: 'grid', gridTemplateColumns: '1fr 100px 120px 100px', padding: '8px 12px', borderBottom: '1px solid var(--border)', background: 'var(--bg1)', transition: 'background .15s' }}
      onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg3)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg1)')}
    >
      <div>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 300 }}>
          {risk.name.substring(0, 60)}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text2)', marginTop: 1 }}>
          {risk.domain ?? '—'}{geoFlags ? ` · ${geoFlags}` : ''}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <SeverityChip severity={risk.inherent_severity} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <div style={{ flex: 1 }}><CoverageBar value={risk.control_coverage_pct} /></div>
        <span style={{ fontSize: 10, color: 'var(--text3)', width: 28 }}>{Math.round(risk.control_coverage_pct)}%</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {risk.owner
          ? <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Avatar initials={risk.owner.initials} color={risk.owner.avatar_color} size={18} />
              <span style={{ fontSize: 11, color: 'var(--text2)' }}>{risk.owner.full_name.split(' ')[0]}</span>
            </div>
          : <span style={{ fontSize: 11, color: 'var(--red)' }}>Unassigned</span>
        }
      </div>
    </div>
  )
}

// ── Table View ────────────────────────────────────────────────────────────────

const TableView: React.FC<{ risks: Risk[]; onDelete: (id: string) => void }> = ({ risks, onDelete }) => {
  if (!risks.length) {
    return <EmptyState title="No risks match filters" body="Try adjusting your filters or add a new risk." />
  }
  return (
    <table className="table">
      <thead>
        <tr>
          <th style={{ paddingLeft: 24 }}>Risk</th>
          <th>Severity</th>
          <th>Framework</th>
          <th>Coverage</th>
          <th>Owner</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {risks.map(risk => (
          <RiskTableRow key={risk.id} risk={risk} onDelete={() => onDelete(risk.id)} />
        ))}
      </tbody>
    </table>
  )
}

const RiskTableRow: React.FC<{ risk: Risk; onDelete: () => void }> = ({ risk, onDelete }) => (
  <tr>
    <td style={{ paddingLeft: 24 }}>
      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>{risk.name}</div>
      <div style={{ fontSize: 11, color: 'var(--text2)' }}>{risk.domain ?? '—'}{risk.lob_name ? ` · ${risk.lob_name}` : ''}</div>
    </td>
    <td><SeverityChip severity={risk.inherent_severity} /></td>
    <td>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {(risk.framework_tags ?? []).slice(0, 2).map(t => (
          <span key={t} style={{ fontSize: 10, fontWeight: 500, padding: '1px 6px', borderRadius: 99, background: 'rgba(30,185,138,.12)', color: 'var(--teal2)' }}>{t}</span>
        ))}
      </div>
    </td>
    <td style={{ width: 120 }}>
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
        : <span style={{ fontSize: 11, color: 'var(--red)' }}>Unassigned</span>
      }
    </td>
    <td>
      <Button variant="danger" size="sm" onClick={e => { e.stopPropagation(); onDelete() }}>Delete</Button>
    </td>
  </tr>
)

// ── Create Risk Modal ─────────────────────────────────────────────────────────

const DOMAINS = ['Financial Crime', 'Data & Privacy', 'Cyber & IT', 'Operational', 'Compliance', 'Financial', 'Strategic']

const CreateRiskModal: React.FC<{
  lobs: LOB[]
  geos: OrgGeo[]
  onClose: () => void
  onSubmit: (d: RiskCreate) => void
  loading: boolean
}> = ({ lobs, geos, onClose, onSubmit, loading }) => {
  const [form, setForm] = useState<RiskCreate>({
    name: '', domain: '', description: '',
    inherent_severity: 'medium', likelihood: 3, impact: 3, framework_tags: [],
    lob_id: undefined, geography_ids: [],
  })

  const set = (k: keyof RiskCreate) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const handleGeoChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const selected = Array.from(e.target.selectedOptions).map(o => o.value)
    setForm(f => ({ ...f, geography_ids: selected }))
  }

  return (
    <div style={modalOverlay} onClick={onClose}>
      <div style={modalCard} onClick={e => e.stopPropagation()}>
        <h3 style={{ marginBottom: 20, fontWeight: 500 }}>Add risk</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Input label="Risk name" value={form.name} onChange={set('name')} placeholder="e.g. AML transaction monitoring failure" required />
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Domain</label>
              <select className="input" value={form.domain} onChange={set('domain')}>
                <option value="">Select domain</option>
                {DOMAINS.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label style={labelStyle}>Severity</label>
              <select className="input" value={form.inherent_severity} onChange={set('inherent_severity')}>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
          </div>

          {lobs.length > 0 && (
            <div>
              <label style={labelStyle}>Line of business</label>
              <select className="input" value={form.lob_id ?? ''} onChange={e => setForm(f => ({ ...f, lob_id: e.target.value || undefined }))}>
                <option value="">— None —</option>
                {lobs.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </div>
          )}

          {geos.length > 0 && (
            <div>
              <label style={labelStyle}>Geographies (hold Cmd/Ctrl to select multiple)</label>
              <select
                className="input"
                multiple
                style={{ height: 80 }}
                value={form.geography_ids ?? []}
                onChange={handleGeoChange}
              >
                {geos.map(g => (
                  <option key={g.id} value={g.id}>
                    {flagEmoji(g.country)} {g.country}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label style={labelStyle}>Description</label>
            <textarea
              className="input" style={{ height: 80, resize: 'none' }}
              value={form.description} onChange={set('description') as any}
              placeholder="Describe the risk..."
            />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 20 }}>
          <Button variant="ghost" size="md" onClick={onClose}>Cancel</Button>
          <Button variant="primary" size="md" loading={loading} onClick={() => onSubmit(form)}>Create risk</Button>
        </div>
      </div>
    </div>
  )
}

// ── Shared helpers ────────────────────────────────────────────────────────────

const Chip: React.FC<{ label: string; color: string }> = ({ label, color }) => (
  <span style={{ fontSize: 10, fontWeight: 500, padding: '2px 7px', borderRadius: 99, background: `${color}22`, color }}>
    {label}
  </span>
)

const modalOverlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(10,11,14,.85)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 500, animation: 'fadeIn .2s ease',
}
const modalCard: React.CSSProperties = {
  background: 'var(--bg1)', border: '1px solid var(--border2)',
  borderRadius: 14, padding: '28px 28px 24px',
  width: '100%', maxWidth: 500, maxHeight: '90vh', overflowY: 'auto',
}
const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 11, fontWeight: 500,
  color: 'var(--text2)', textTransform: 'uppercase',
  letterSpacing: '0.05em', marginBottom: 5,
}
