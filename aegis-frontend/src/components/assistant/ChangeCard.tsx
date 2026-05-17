/**
 * ChangeCard — inline card rendered inside the GRC Assistant chat for
 * a proposed profile change. Shows current vs proposed value and
 * Approve / Reject actions.
 */
import React from 'react'
import { Check, X } from 'lucide-react'
import type { AssistantChangeProposal } from '@/types'

interface ChangeCardProps {
  proposal: AssistantChangeProposal
  onApprove: () => void
  onReject: () => void
}

function displayValue(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export const ChangeCard: React.FC<ChangeCardProps> = ({ proposal, onApprove, onReject }) => {
  const resolved = proposal.status !== 'pending_approval'

  return (
    <div style={{
      borderRadius: 8, border: `1px solid ${resolved ? 'var(--border)' : 'var(--accent)44'}`,
      background: resolved ? 'var(--bg2)' : 'rgba(123,109,170,.06)',
      padding: '10px 12px', marginTop: 6,
      opacity: resolved ? 0.6 : 1,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 8 }}>
        Proposed change
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 9, color: 'var(--text3)', marginBottom: 2 }}>Field</div>
          <div style={{ fontSize: 11, color: 'var(--text2)' }}>
            {proposal.entity_type} · {proposal.field_name.replace(/_/g, ' ')}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 8 }}>
        <ValueBox label="Current" value={proposal.current_value} color="var(--text3)" />
        <ValueBox label="Proposed" value={proposal.proposed_value} color="var(--accent2)" />
      </div>

      {proposal.rationale && (
        <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 8, fontStyle: 'italic' }}>
          "{proposal.rationale}"
        </div>
      )}

      {!resolved ? (
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="btn btn-ghost btn-sm" style={{ flex: 1 }} onClick={onReject}>
            <X size={11} style={{ marginRight: 4 }} />Reject
          </button>
          <button className="btn btn-primary btn-sm" style={{ flex: 1 }} onClick={onApprove}>
            <Check size={11} style={{ marginRight: 4 }} />Approve
          </button>
        </div>
      ) : (
        <div style={{ fontSize: 11, fontWeight: 600, color: proposal.status === 'approved' ? 'var(--teal2)' : 'var(--text3)', textAlign: 'center' }}>
          {proposal.status === 'approved' ? '✓ Applied' : '✗ Rejected'}
        </div>
      )}
    </div>
  )
}

const ValueBox: React.FC<{ label: string; value: unknown; color: string }> = ({ label, value, color }) => (
  <div style={{ padding: '6px 8px', borderRadius: 6, background: 'var(--bg1)', border: '1px solid var(--border)' }}>
    <div style={{ fontSize: 9, color: 'var(--text3)', marginBottom: 3 }}>{label}</div>
    <div style={{ fontSize: 11, color, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
      {displayValue(value)}
    </div>
  </div>
)
