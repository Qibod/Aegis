import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { risksApi } from '@/api/client'
import { useUIStore } from '@/store'
import {
  Button, SeverityChip, Avatar, CoverageBar,
  EmptyState, Spinner, Input,
} from '@/components/ui'
import type { Risk, RiskCreate, RiskSeverity } from '@/types'

export const RisksPage: React.FC = () => {
  const qc = useQueryClient()
  const { addToast } = useUIStore()
  const [showCreate, setShowCreate] = useState(false)
  const [filter, setFilter] = useState<{ severity?: string; domain?: string }>({})

  const { data, isLoading } = useQuery({
    queryKey: ['risks', filter],
    queryFn: () => risksApi.list(filter),
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
      addToast({ type: 'info', title: 'Risk deleted' })
    },
  })

  return (
    <div className="page animate-fade">
      <div className="page-header">
        <div>
          <div className="page-title">Risk Register</div>
          <div className="page-sub">
            {data ? `${data.total} risks` : 'Loading...'} · {data ? `${data.items.filter(r => r.inherent_severity === 'high' || r.inherent_severity === 'critical').length} high/critical` : ''}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select className="input" style={{ width: 130 }} value={filter.severity ?? ''} onChange={e => setFilter(f => ({ ...f, severity: e.target.value || undefined }))}>
            <option value="">All severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <Button variant="primary" size="md" onClick={() => setShowCreate(true)}>+ Add risk</Button>
        </div>
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {isLoading
          ? <div style={{ display: 'flex', justifyContent: 'center', padding: '3rem' }}><Spinner /></div>
          : !data?.items.length
          ? <EmptyState title="No risks yet" body="Add your first risk or run AI fingerprinting during onboarding" />
          : <table className="table">
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
                {data.items.map(risk => (
                  <RiskTableRow key={risk.id} risk={risk} onDelete={() => deleteMutation.mutate(risk.id)} />
                ))}
              </tbody>
            </table>
        }
      </div>

      {showCreate && (
        <CreateRiskModal
          onClose={() => setShowCreate(false)}
          onSubmit={createMutation.mutate}
          loading={createMutation.isPending}
        />
      )}
    </div>
  )
}

// ── Risk table row ────────────────────────────────────────────────────────────
const RiskTableRow: React.FC<{ risk: Risk; onDelete: () => void }> = ({ risk, onDelete }) => (
  <tr>
    <td style={{ paddingLeft: 24 }}>
      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)' }}>{risk.name}</div>
      <div style={{ fontSize: 11, color: 'var(--text2)' }}>{risk.domain ?? '—'}</div>
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
        : <span style={{ fontSize: 11, color: 'var(--text3)' }}>Unassigned</span>
      }
    </td>
    <td>
      <Button variant="danger" size="sm" onClick={e => { e.stopPropagation(); onDelete() }}>Delete</Button>
    </td>
  </tr>
)

// ── Create risk modal ─────────────────────────────────────────────────────────
const DOMAINS = ['Financial crime', 'Data & privacy', 'Cyber & IT', 'Operational', 'Compliance', 'Financial', 'Strategic']

const CreateRiskModal: React.FC<{ onClose: () => void; onSubmit: (d: RiskCreate) => void; loading: boolean }> = ({
  onClose, onSubmit, loading,
}) => {
  const [form, setForm] = useState<RiskCreate>({
    name: '', domain: '', description: '',
    inherent_severity: 'medium', likelihood: 3, impact: 3, framework_tags: [],
  })

  const set = (k: keyof RiskCreate) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

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

const modalOverlay: React.CSSProperties = {
  position: 'fixed', inset: 0, background: 'rgba(10,11,14,.85)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 500, animation: 'fadeIn .2s ease',
}
const modalCard: React.CSSProperties = {
  background: 'var(--bg1)', border: '1px solid var(--border2)',
  borderRadius: 14, padding: '28px 28px 24px',
  width: '100%', maxWidth: 480,
}
const labelStyle: React.CSSProperties = {
  display: 'block', fontSize: 11, fontWeight: 500,
  color: 'var(--text2)', textTransform: 'uppercase',
  letterSpacing: '0.05em', marginBottom: 5,
}
