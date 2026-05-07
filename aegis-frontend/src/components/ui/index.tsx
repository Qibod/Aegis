import React from 'react'
import { clsx } from 'clsx'

// ── Button ────────────────────────────────────────────────────────────────────
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  loading?: boolean
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'ghost', size = 'md', loading, children, className, disabled, ...props
}) => (
  <button
    className={clsx('btn', `btn-${variant}`, `btn-${size}`, className)}
    disabled={disabled || loading}
    {...props}
  >
    {loading ? <Spinner size={14} /> : children}
  </button>
)

// ── Card ──────────────────────────────────────────────────────────────────────
interface CardProps { children: React.ReactNode; className?: string; onClick?: () => void }

export const Card: React.FC<CardProps> = ({ children, className, onClick }) => (
  <div className={clsx('card', className)} onClick={onClick} style={{ cursor: onClick ? 'pointer' : undefined }}>
    {children}
  </div>
)

// ── Badge / Chip ──────────────────────────────────────────────────────────────
type ChipVariant = 'red' | 'amber' | 'teal' | 'blue' | 'purple' | 'gray'

interface ChipProps { label: string; variant?: ChipVariant; size?: 'sm' | 'xs' }

export const Chip: React.FC<ChipProps> = ({ label, variant = 'gray', size = 'sm' }) => (
  <span className={clsx('chip', `chip-${variant}`, size === 'xs' && 'chip-xs')}>{label}</span>
)

// ── Severity chip ─────────────────────────────────────────────────────────────
const SEV_VARIANT: Record<string, ChipVariant> = {
  critical: 'red', high: 'red', medium: 'amber', low: 'teal', info: 'blue',
}
const SEV_LABEL: Record<string, string> = {
  critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low', info: 'Info',
}
export const SeverityChip: React.FC<{ severity: string }> = ({ severity }) => (
  <Chip label={SEV_LABEL[severity] ?? severity} variant={SEV_VARIANT[severity] ?? 'gray'} />
)

// ── Status chip ───────────────────────────────────────────────────────────────
const STATUS_VARIANT: Record<string, ChipVariant> = {
  effective: 'teal', partial: 'amber', not_tested: 'gray', ineffective: 'red',
  passing: 'teal', failing: 'red', degraded: 'amber', unknown: 'gray',
  done: 'teal', in_progress: 'blue', pending: 'gray', blocked: 'red',
}
export const StatusChip: React.FC<{ status: string }> = ({ status }) => (
  <Chip
    label={status.replace('_', ' ')}
    variant={STATUS_VARIANT[status] ?? 'gray'}
  />
)

// ── Spinner ───────────────────────────────────────────────────────────────────
export const Spinner: React.FC<{ size?: number; color?: string }> = ({
  size = 18, color = 'var(--accent2)'
}) => (
  <svg
    width={size} height={size} viewBox="0 0 18 18" fill="none"
    style={{ animation: 'spin 0.8s linear infinite', flexShrink: 0 }}
  >
    <circle cx="9" cy="9" r="7" stroke={color} strokeWidth="1.5" strokeDasharray="30" strokeDashoffset="10" strokeLinecap="round" />
  </svg>
)

// ── Avatar ────────────────────────────────────────────────────────────────────
export const Avatar: React.FC<{ initials?: string | null; color?: string; size?: number }> = ({
  initials = '?', color = '#6c63ff', size = 24,
}) => (
  <div style={{
    width: size, height: size, borderRadius: '50%',
    background: color + '33', border: `1px solid ${color}44`,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: size * 0.38, fontWeight: 500, color, flexShrink: 0,
  }}>
    {(initials ?? '?').slice(0, 2).toUpperCase()}
  </div>
)

// ── Empty state ───────────────────────────────────────────────────────────────
export const EmptyState: React.FC<{ icon?: React.ReactNode; title: string; body?: string }> = ({
  icon, title, body
}) => (
  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '3rem', textAlign: 'center', color: 'var(--text3)', gap: 8 }}>
    {icon && <div style={{ marginBottom: 4, opacity: 0.4 }}>{icon}</div>}
    <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text2)' }}>{title}</div>
    {body && <div style={{ fontSize: 12 }}>{body}</div>}
  </div>
)

// ── Live dot ──────────────────────────────────────────────────────────────────
export const LiveDot: React.FC<{ color?: string }> = ({ color = 'var(--teal2)' }) => (
  <div style={{
    width: 6, height: 6, borderRadius: '50%', background: color,
    animation: 'pulse 1.6s infinite', flexShrink: 0,
  }} />
)

// ── Progress bar ──────────────────────────────────────────────────────────────
export const ProgressBar: React.FC<{ value: number; color?: string; height?: number }> = ({
  value, color = 'var(--accent)', height = 4,
}) => (
  <div style={{ height, background: 'var(--bg3)', borderRadius: height / 2, overflow: 'hidden', width: '100%' }}>
    <div style={{
      height, borderRadius: height / 2,
      width: `${Math.min(100, Math.max(0, value))}%`,
      background: color,
      transition: 'width 0.5s ease',
    }} />
  </div>
)

// ── Coverage bar ──────────────────────────────────────────────────────────────
export const CoverageBar: React.FC<{ value: number }> = ({ value }) => {
  const color = value >= 70 ? 'var(--teal)' : value >= 40 ? 'var(--amber)' : 'var(--red)'
  return <ProgressBar value={value} color={color} height={4} />
}

// ── Input ─────────────────────────────────────────────────────────────────────
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}
export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className, ...props }, ref) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {label && <label style={{ fontSize: 11, fontWeight: 500, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</label>}
      <input ref={ref} className={clsx('input', className)} {...props} />
      {error && <span style={{ fontSize: 11, color: 'var(--red)' }}>{error}</span>}
    </div>
  )
)
Input.displayName = 'Input'
