/**
 * VerificationTick — shows a small icon next to a field value indicating its
 * AI verification status. Clicking opens a popover with validator details and
 * a "Re-verify" button for admins.
 *
 * States (7):
 *  verified         — green ✓
 *  verified_b_only  — green ✓ with B superscript
 *  verifying        — amber spinner
 *  flagged          — amber ⚠
 *  unknown          — grey ?
 *  unverifiable     — grey –
 *  empty            — nothing rendered
 */
import React, { useState, useRef, useEffect } from 'react'
import type { FieldStatus } from '@/types'

interface ValidatorResult {
  status: string
  confidence?: number
  sources?: string[]
  validated_at?: string | null
  proposed_alternative?: { value: unknown } | null
}

interface VerificationTickProps {
  fieldStatus?: FieldStatus | null
  validationA?: ValidatorResult | null
  validationB?: ValidatorResult | null
  entityType: string
  entityId: string
  fieldName: string
  isAdmin?: boolean
  onReVerify?: () => void
}

type TickState = 'verified' | 'verified_b_only' | 'verifying' | 'flagged' | 'unknown' | 'unverifiable' | 'empty'

function resolveTickState(
  fieldStatus: FieldStatus | null | undefined,
  a: ValidatorResult | null | undefined,
  b: ValidatorResult | null | undefined,
): TickState {
  if (!fieldStatus || fieldStatus === 'user_edited') return 'empty'

  if (fieldStatus === 'flagged_for_review') return 'flagged'
  if (fieldStatus === 'unverifiable') return 'unverifiable'
  if (fieldStatus === 'unknown') return 'unknown'

  if (fieldStatus === 'verified' || fieldStatus === 'verified_after_dispute') {
    if (!a && b) return 'verified_b_only'
    return 'verified'
  }

  if (fieldStatus === 'disputed') return 'flagged'
  if (fieldStatus === 'seeded') {
    if (a || b) return 'verifying'
    return 'unknown'
  }

  return 'empty'
}

const SPINNER_KEYFRAMES = `
@keyframes vt-spin { to { transform: rotate(360deg) } }
`

function injectSpinnerStyle() {
  if (typeof document !== 'undefined' && !document.getElementById('vt-spinner-style')) {
    const s = document.createElement('style')
    s.id = 'vt-spinner-style'
    s.textContent = SPINNER_KEYFRAMES
    document.head.appendChild(s)
  }
}

export const VerificationTick: React.FC<VerificationTickProps> = ({
  fieldStatus, validationA, validationB,
  entityType, entityId, fieldName,
  isAdmin, onReVerify,
}) => {
  injectSpinnerStyle()
  const tickState = resolveTickState(fieldStatus, validationA, validationB)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  if (tickState === 'empty') return null

  const icon = (() => {
    switch (tickState) {
      case 'verified':
        return (
          <span style={{ color: 'var(--teal2)', fontSize: 11, lineHeight: 1 }} aria-label="Verified">
            ✓
          </span>
        )
      case 'verified_b_only':
        return (
          <span style={{ color: 'var(--teal2)', fontSize: 11, lineHeight: 1, position: 'relative' }} aria-label="Verified by Validator B">
            ✓<sup style={{ fontSize: 7, position: 'absolute', top: -2, right: -6, color: 'var(--blue)' }}>B</sup>
          </span>
        )
      case 'verifying':
        return (
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none"
            style={{ animation: 'vt-spin 0.9s linear infinite', flexShrink: 0 }}
            aria-label="Verifying">
            <circle cx="5" cy="5" r="3.5" stroke="var(--amber)" strokeWidth="1.5"
              strokeDasharray="14" strokeDashoffset="5" strokeLinecap="round" />
          </svg>
        )
      case 'flagged':
        return (
          <span style={{ color: 'var(--amber)', fontSize: 10, lineHeight: 1 }} aria-label="Flagged for review">
            ⚠
          </span>
        )
      case 'unknown':
        return (
          <span style={{ color: 'var(--text3)', fontSize: 11, lineHeight: 1 }} aria-label="Unknown">
            ?
          </span>
        )
      case 'unverifiable':
        return (
          <span style={{ color: 'var(--text3)', fontSize: 11, lineHeight: 1 }} aria-label="Unverifiable">
            –
          </span>
        )
    }
  })()

  const sourceValidator = validationB ?? validationA
  const confidence = sourceValidator?.confidence
  const sources = sourceValidator?.sources ?? []
  const validatedAt = sourceValidator?.validated_at

  return (
    <span ref={ref} style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', marginLeft: 4, cursor: 'pointer', verticalAlign: 'middle' }}
      onClick={() => setOpen(o => !o)}>
      {icon}

      {open && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, zIndex: 200,
          background: 'var(--bg1)', border: '1px solid var(--border)',
          borderRadius: 8, padding: 12, width: 260, marginTop: 4,
          boxShadow: '0 4px 16px rgba(0,0,0,.4)',
        }} onClick={e => e.stopPropagation()}>
          <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '.05em', color: 'var(--text2)' }}>
            Verification status
          </div>

          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            <ValidatorBadge label="A" result={validationA} />
            <ValidatorBadge label="B" result={validationB} />
          </div>

          {confidence != null && (
            <div style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 6 }}>
              Confidence: <span style={{ fontWeight: 600, color: confidence >= 0.9 ? 'var(--teal2)' : 'var(--amber)' }}>
                {Math.round(confidence * 100)}%
              </span>
            </div>
          )}

          {sources.length > 0 && (
            <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 8 }}>
              {sources.slice(0, 2).map((s, i) => (
                <div key={i} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s}</div>
              ))}
              {sources.length > 2 && <div>+{sources.length - 2} more</div>}
            </div>
          )}

          {validatedAt && (
            <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 8 }}>
              {new Date(validatedAt).toLocaleString()}
            </div>
          )}

          {isAdmin && onReVerify && (
            <button
              className="btn btn-ghost btn-sm"
              style={{ width: '100%', fontSize: 11 }}
              onClick={() => { onReVerify(); setOpen(false) }}
            >
              Re-verify
            </button>
          )}
        </div>
      )}
    </span>
  )
}

const STATUS_COLOR: Record<string, string> = {
  verified: 'var(--teal2)', verified_after_dispute: 'var(--teal2)',
  disputed: 'var(--amber)', flagged_for_review: 'var(--amber)',
  unverifiable: 'var(--text3)', verified_qa_pass: 'var(--teal2)',
  verified_qa_fail: 'var(--red)',
}

const ValidatorBadge: React.FC<{ label: string; result?: ValidatorResult | null }> = ({ label, result }) => (
  <div style={{
    flex: 1, padding: '6px 8px', borderRadius: 6, background: 'var(--bg2)',
    border: `1px solid ${result ? (STATUS_COLOR[result.status] ?? 'var(--border)') + '55' : 'var(--border)'}`,
  }}>
    <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text3)', marginBottom: 3 }}>Validator {label}</div>
    {result
      ? <div style={{ fontSize: 11, color: STATUS_COLOR[result.status] ?? 'var(--text2)', fontWeight: 500 }}>
          {result.status.replace(/_/g, ' ')}
        </div>
      : <div style={{ fontSize: 11, color: 'var(--text3)' }}>—</div>
    }
  </div>
)
