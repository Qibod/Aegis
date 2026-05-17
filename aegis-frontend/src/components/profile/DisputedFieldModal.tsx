/**
 * DisputedFieldModal — three-option resolution UI for flagged_for_review fields.
 * Options: (1) keep seeded value, (2) accept B's alternative, (3) enter custom value.
 * Default-selects the option with higher confidence.
 */
import React, { useState } from 'react'
import { Spinner } from '@/components/ui'
import { validationApi } from '@/api/client'

interface DisputedFieldModalProps {
  validationId: string
  fieldLabel: string
  seededValue: unknown
  seededConfidence?: number
  alternativeValue: unknown
  alternativeConfidence?: number
  onResolved: () => void
  onClose: () => void
}

type Option = 'seeded' | 'alternative' | 'user_input'

function displayValue(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export const DisputedFieldModal: React.FC<DisputedFieldModalProps> = ({
  validationId, fieldLabel,
  seededValue, seededConfidence,
  alternativeValue, alternativeConfidence,
  onResolved, onClose,
}) => {
  const defaultOption: Option =
    (alternativeConfidence ?? 0) > (seededConfidence ?? 0) ? 'alternative' : 'seeded'

  const [selected, setSelected] = useState<Option>(defaultOption)
  const [customValue, setCustomValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const chosenValue = selected === 'seeded'
    ? seededValue
    : selected === 'alternative'
      ? alternativeValue
      : customValue

  const handleResolve = async () => {
    setError('')
    if (selected === 'user_input' && !customValue.trim()) {
      setError('Please enter a value.')
      return
    }
    setSaving(true)
    try {
      await validationApi.resolveField(validationId, {
        chosen_value: chosenValue,
        resolution_source: selected,
      })
      onResolved()
      onClose()
    } catch {
      setError('Failed to save resolution. Please try again.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,.65)', zIndex: 500,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div className="card animate-fade" style={{ width: 520, padding: 0 }} onClick={e => e.stopPropagation()}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: 14, fontWeight: 500 }}>Resolve disputed field</div>
          <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 3 }}>
            <span style={{ color: 'var(--text3)' }}>Field: </span>{fieldLabel}
          </div>
        </div>

        <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          <OptionCard
            id="seeded"
            selected={selected === 'seeded'}
            onSelect={() => setSelected('seeded')}
            label="Keep seeded value"
            description={displayValue(seededValue)}
            confidence={seededConfidence}
            recommended={defaultOption === 'seeded'}
          />
          {alternativeValue != null && (
            <OptionCard
              id="alternative"
              selected={selected === 'alternative'}
              onSelect={() => setSelected('alternative')}
              label="Accept Validator B's suggestion"
              description={displayValue(alternativeValue)}
              confidence={alternativeConfidence}
              recommended={defaultOption === 'alternative'}
            />
          )}
          <OptionCard
            id="user_input"
            selected={selected === 'user_input'}
            onSelect={() => setSelected('user_input')}
            label="Enter correct value"
            description={null}
          >
            {selected === 'user_input' && (
              <input
                className="input"
                style={{ marginTop: 8, width: '100%', fontSize: 12, padding: '5px 8px' }}
                placeholder="Enter the correct value…"
                value={customValue}
                onChange={e => setCustomValue(e.target.value)}
                autoFocus
              />
            )}
          </OptionCard>
        </div>

        {error && (
          <div style={{ padding: '0 20px 12px', fontSize: 11, color: 'var(--red)' }}>{error}</div>
        )}

        <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={onClose} disabled={saving}>Cancel</button>
          <button className="btn btn-primary btn-sm" onClick={handleResolve} disabled={saving}>
            {saving ? <Spinner size={12} /> : 'Apply resolution'}
          </button>
        </div>
      </div>
    </div>
  )
}

const OptionCard: React.FC<{
  id: string; selected: boolean; onSelect: () => void
  label: string; description: string | null
  confidence?: number; recommended?: boolean
  children?: React.ReactNode
}> = ({ id, selected, onSelect, label, description, confidence, recommended, children }) => (
  <div
    onClick={onSelect}
    style={{
      padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
      border: `1px solid ${selected ? 'var(--accent)' : 'var(--border)'}`,
      background: selected ? 'rgba(123,109,170,.08)' : 'var(--bg2)',
      transition: 'border-color .12s',
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{
        width: 14, height: 14, borderRadius: '50%', flexShrink: 0,
        border: `2px solid ${selected ? 'var(--accent)' : 'var(--border)'}`,
        background: selected ? 'var(--accent)' : 'transparent',
        transition: 'all .12s',
      }} />
      <span style={{ fontSize: 12, fontWeight: 500 }}>{label}</span>
      {recommended && (
        <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, background: 'rgba(123,109,170,.2)', color: 'var(--accent2)', fontWeight: 600 }}>
          RECOMMENDED
        </span>
      )}
      {confidence != null && (
        <span style={{ marginLeft: 'auto', fontSize: 10, color: confidence >= 0.9 ? 'var(--teal2)' : 'var(--amber)' }}>
          {Math.round(confidence * 100)}%
        </span>
      )}
    </div>
    {description != null && (
      <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 4, paddingLeft: 22 }}>{description}</div>
    )}
    {children && <div style={{ paddingLeft: 22 }}>{children}</div>}
  </div>
)
