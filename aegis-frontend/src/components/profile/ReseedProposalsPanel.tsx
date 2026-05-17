/**
 * ReseedProposalsPanel — collapsible panel showing pending AI re-seed proposals.
 * Admins can approve or reject each proposal individually.
 */
import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Check, X } from 'lucide-react'
import { proposalsApi } from '@/api/client'
import { Spinner } from '@/components/ui'
import type { SeedingProposal } from '@/types'

interface ReseedProposalsPanelProps {
  isAdmin: boolean
  onApplied?: () => void
}

function displayValue(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'object' && v !== null && 'value' in v) return String((v as { value: unknown }).value)
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export const ReseedProposalsPanel: React.FC<ReseedProposalsPanelProps> = ({ isAdmin, onApplied }) => {
  const [expanded, setExpanded] = useState(false)
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['seeding-proposals'],
    queryFn: () => proposalsApi.list(),
    enabled: isAdmin,
    refetchInterval: 30_000,
  })

  const proposals: SeedingProposal[] = data?.proposals ?? []
  const count = proposals.length

  const approve = useMutation({
    mutationFn: (id: string) => proposalsApi.approve(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['seeding-proposals'] }); onApplied?.() },
  })
  const reject = useMutation({
    mutationFn: (id: string) => proposalsApi.reject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seeding-proposals'] }),
  })

  if (!isAdmin || count === 0) return null

  return (
    <div style={{ marginBottom: 14 }}>
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 12px', borderRadius: 8, border: '1px solid var(--amber)33',
          background: 'var(--amber)0d', cursor: 'pointer', textAlign: 'left',
        }}
      >
        <ChevronRight size={12} style={{ transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform .15s', color: 'var(--amber)', flexShrink: 0 }} />
        <span style={{ fontSize: 12, fontWeight: 500 }}>AI re-seed proposals</span>
        <span style={{
          marginLeft: 'auto', fontSize: 10, fontWeight: 700, padding: '1px 6px',
          borderRadius: 10, background: 'var(--amber)33', color: 'var(--amber)',
        }}>{count}</span>
      </button>

      {expanded && (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {isLoading
            ? <Spinner size={16} />
            : proposals.map(p => (
              <ProposalRow
                key={p.id}
                proposal={p}
                onApprove={() => approve.mutate(p.id)}
                onReject={() => reject.mutate(p.id)}
                approving={approve.isPending && approve.variables === p.id}
                rejecting={reject.isPending && reject.variables === p.id}
              />
            ))
          }
        </div>
      )}
    </div>
  )
}

const ProposalRow: React.FC<{
  proposal: SeedingProposal
  onApprove: () => void
  onReject: () => void
  approving: boolean
  rejecting: boolean
}> = ({ proposal, onApprove, onReject, approving, rejecting }) => (
  <div style={{
    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
    borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg2)',
    fontSize: 12,
  }}>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ color: 'var(--text3)', fontSize: 10, marginBottom: 2 }}>
        {proposal.entity_type} · {proposal.field_name.replace(/_/g, ' ')}
      </div>
      <div style={{ color: 'var(--text)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {displayValue(proposal.proposed_value)}
      </div>
    </div>

    <span style={{ fontSize: 10, color: proposal.confidence >= 0.9 ? 'var(--teal2)' : 'var(--amber)', flexShrink: 0 }}>
      {Math.round(proposal.confidence * 100)}%
    </span>

    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
      <button className="btn btn-ghost btn-sm" onClick={onReject} disabled={approving || rejecting} title="Reject">
        {rejecting ? <Spinner size={11} /> : <X size={11} />}
      </button>
      <button className="btn btn-primary btn-sm" onClick={onApprove} disabled={approving || rejecting} title="Approve">
        {approving ? <Spinner size={11} /> : <Check size={11} />}
      </button>
    </div>
  </div>
)
