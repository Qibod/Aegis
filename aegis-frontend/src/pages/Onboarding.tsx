import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { orgsApi } from '@/api/client'
import { useAuthStore, useUIStore } from '@/store'
import { Button, Input } from '@/components/ui'
import type { FingerprintResponse } from '@/types'

// ── Step indicators ────────────────────────────────────────────────────────────
const STEPS = ['Identify', 'Review', 'Risk Domains', 'Frameworks', 'Done']

// ── Master list of all known risk domains ─────────────────────────────────────
const ALL_RISK_DOMAINS = [
  'Cybersecurity & Information Security',
  'Data Privacy & Protection',
  'Financial Crime & Fraud',
  'Operational Risk',
  'Reputational Risk',
  'Legal & Regulatory Compliance',
  'Third-Party & Vendor Risk',
  'Business Continuity & Resilience',
  'Human Resources & People Risk',
  'Environmental, Social & Governance (ESG)',
  'Physical Security',
  'Technology & IT Risk',
  'Supply Chain Risk',
  'Geopolitical & Country Risk',
  'Model & Algorithmic Risk',
  'Climate & Environmental Risk',
  'Intellectual Property Risk',
  'Health & Safety',
  'Anti-Bribery & Corruption',
  'Sanctions & Trade Compliance',
  'Credit & Liquidity Risk',
  'Market & Financial Risk',
  'Conduct & Culture Risk',
  'Product Liability & Safety',
  'Tax & Transfer Pricing Risk',
]

const StepBar: React.FC<{ current: number }> = ({ current }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 40 }}>
    {STEPS.map((label, i) => {
      const done = i < current
      const active = i === current
      return (
        <React.Fragment key={label}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
            <div style={{
              width: 28, height: 28, borderRadius: '50%',
              background: done ? 'var(--accent)' : active ? 'var(--accent)' : 'var(--bg2)',
              border: `2px solid ${done || active ? 'var(--accent)' : 'var(--border2)'}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 600, color: done || active ? '#fff' : 'var(--text3)',
              transition: 'all 0.2s',
            }}>
              {done ? '✓' : i + 1}
            </div>
            <span style={{ fontSize: 10, color: active ? 'var(--text)' : 'var(--text3)', fontWeight: active ? 600 : 400, whiteSpace: 'nowrap' }}>
              {label}
            </span>
          </div>
          {i < STEPS.length - 1 && (
            <div style={{
              flex: 1, height: 2, margin: '0 4px', marginBottom: 20,
              background: done ? 'var(--accent)' : 'var(--border2)',
              transition: 'background 0.3s',
            }} />
          )}
        </React.Fragment>
      )
    })}
  </div>
)

// ── Step 1 — Identify ──────────────────────────────────────────────────────────
const ANALYSIS_STEPS = [
  'Looking up company profile…',
  'Identifying business lines…',
  'Determining jurisdiction & regulators…',
  'Mapping applicable regulations…',
  'Generating risk profile…',
  'Finalising GRC fingerprint…',
]

const StepIdentify: React.FC<{
  onNext: (fp: FingerprintResponse) => void
}> = ({ onNext }) => {
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [statusIdx, setStatusIdx] = useState(0)

  useEffect(() => {
    if (!loading) { setStatusIdx(0); return }
    const interval = setInterval(() => {
      setStatusIdx(i => (i < ANALYSIS_STEPS.length - 1 ? i + 1 : i))
    }, 5000)
    return () => clearInterval(interval)
  }, [loading])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    setLoading(true)
    setError('')
    try {
      const fp = await orgsApi.fingerprint(name.trim())
      onNext(fp)
    } catch {
      setError('Could not fingerprint this company. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2 style={headingStyle}>What organisation are you setting up GRC for?</h2>
      <p style={subStyle}>We'll use AI to identify your industry, jurisdiction, applicable regulations, and risk profile.</p>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 28 }}>
        <Input
          label="Company name"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder="e.g. Uber Technologies, Inc."
          required
          disabled={loading}
        />
        {error && <p style={{ fontSize: 12, color: 'var(--red)' }}>{error}</p>}
        <Button variant="primary" type="submit" loading={loading} style={{ alignSelf: 'flex-start', marginTop: 4 }}>
          Analyse →
        </Button>
      </form>

      {loading && (
        <div style={{
          marginTop: 24, padding: '14px 16px',
          background: 'var(--bg2)', border: '1px solid var(--border)',
          borderRadius: 10,
        }}>
          <p style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>
            AI Analysis in progress · ~30s
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {ANALYSIS_STEPS.map((step, i) => (
              <div key={step} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 9,
                  background: i < statusIdx ? 'var(--accent)' : i === statusIdx ? 'rgba(99,102,241,0.15)' : 'var(--bg3)',
                  border: i === statusIdx ? '1.5px solid var(--accent)' : '1.5px solid transparent',
                }}>
                  {i < statusIdx && <span style={{ color: '#fff' }}>✓</span>}
                  {i === statusIdx && (
                    <svg width="8" height="8" viewBox="0 0 18 18" fill="none" style={{ animation: 'spin 0.8s linear infinite' }}>
                      <circle cx="9" cy="9" r="7" stroke="var(--accent)" strokeWidth="2.5" strokeDasharray="30" strokeDashoffset="10" strokeLinecap="round" />
                    </svg>
                  )}
                </div>
                <span style={{
                  fontSize: 12,
                  color: i < statusIdx ? 'var(--text3)' : i === statusIdx ? 'var(--text)' : 'var(--text3)',
                  fontWeight: i === statusIdx ? 500 : 400,
                  textDecoration: i < statusIdx ? 'line-through' : 'none',
                  opacity: i > statusIdx ? 0.4 : 1,
                }}>
                  {step}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Step 2 — Review fingerprint ────────────────────────────────────────────────
const StepReview: React.FC<{ fp: FingerprintResponse }> = ({ fp }) => (
  <div>
    <h2 style={headingStyle}>Your GRC fingerprint</h2>
    <p style={subStyle}>Review the AI-generated profile for <strong>{fp.company_name}</strong>. We'll use this to seed your risk register, controls, and framework mapping.</p>

    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 24 }}>
      <InfoCard label="Industry" value={fp.industry_label ?? '—'} />
      <InfoCard label="Jurisdiction" value={fp.jurisdiction ?? '—'} />
      <InfoCard label="Primary Regulator(s)" value={fp.regulator ?? '—'} />
      <InfoCard label="Organisation Scale" value={fp.employee_range ?? '—'} />
    </div>

    {fp.detected_regulations.length > 0 && (
      <Section title="Applicable Regulations">
        <TagList items={fp.detected_regulations} color="var(--accent)" />
      </Section>
    )}

    {fp.risk_domains.length > 0 && (
      <Section title="Risk Domains">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {fp.risk_domains.map(d => (
            <div key={d.name} style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'var(--bg2)', border: '1px solid var(--border)',
              borderRadius: 8, padding: '5px 10px', fontSize: 12,
            }}>
              <span style={{
                width: 8, height: 8, borderRadius: '50%',
                background: d.severity === 'critical' ? 'var(--red)' : d.severity === 'high' ? '#f97316' : 'var(--yellow)',
                flexShrink: 0,
              }} />
              {d.name}
              <span style={{ color: 'var(--text3)', fontSize: 11 }}>({d.risk_count})</span>
            </div>
          ))}
        </div>
      </Section>
    )}
  </div>
)

// ── Step 3 — Risk Domains ─────────────────────────────────────────────────────
const StepRiskDomains: React.FC<{
  fp: FingerprintResponse
  selectedDomains: string[]
  setSelectedDomains: (d: string[]) => void
}> = ({ fp, selectedDomains, setSelectedDomains }) => {
  const aiDomainNames = fp.risk_domains.map(d => d.name)
  const suggestions = ALL_RISK_DOMAINS.filter(
    d => !aiDomainNames.some(a => a.toLowerCase().includes(d.toLowerCase().split('&')[0].trim()) ||
      d.toLowerCase().includes(a.toLowerCase().split('&')[0].trim()))
  )

  const toggle = (name: string) =>
    setSelectedDomains(
      selectedDomains.includes(name)
        ? selectedDomains.filter(d => d !== name)
        : [...selectedDomains, name]
    )

  return (
    <div>
      <h2 style={headingStyle}>Risk domains</h2>
      <p style={subStyle}>
        These domains were detected by AI for your organisation. Add any others that apply to your business.
      </p>

      {/* AI-detected — shown as locked/selected */}
      <Section title={`AI detected · ${aiDomainNames.length}`}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {fp.risk_domains.map(d => (
            <div key={d.name} style={{
              display: 'flex', alignItems: 'center', gap: 10,
              background: 'rgba(99,102,241,0.06)',
              border: '1.5px solid rgba(99,102,241,0.25)',
              borderRadius: 9, padding: '9px 12px',
            }}>
              <div style={{
                width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                background: 'var(--accent)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 9, color: '#fff',
              }}>✓</div>
              <span style={{ fontSize: 13, color: 'var(--text)', flex: 1 }}>{d.name}</span>
              <span style={{
                fontSize: 10, padding: '2px 7px', borderRadius: 5, fontWeight: 600,
                background: d.severity === 'critical' ? 'rgba(239,68,68,0.12)' :
                  d.severity === 'high' ? 'rgba(249,115,22,0.12)' : 'rgba(234,179,8,0.12)',
                color: d.severity === 'critical' ? 'var(--red)' :
                  d.severity === 'high' ? '#f97316' : 'var(--yellow)',
              }}>
                {d.severity}
              </span>
            </div>
          ))}
        </div>
      </Section>

      {/* Suggested additional domains */}
      <Section title="Suggested additions">
        <p style={{ fontSize: 12, color: 'var(--text3)', marginBottom: 10 }}>
          Select any additional domains relevant to your organisation.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {suggestions.map(name => {
            const active = selectedDomains.includes(name)
            return (
              <button
                key={name}
                onClick={() => toggle(name)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', borderRadius: 20, cursor: 'pointer',
                  fontSize: 12, fontWeight: active ? 500 : 400,
                  background: active ? 'rgba(99,102,241,0.12)' : 'var(--bg2)',
                  border: `1.5px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                  color: active ? 'var(--accent)' : 'var(--text2)',
                  transition: 'all 0.15s',
                }}
              >
                {active ? '✓ ' : '+ '}{name}
              </button>
            )
          })}
        </div>
        {selectedDomains.filter(d => !aiDomainNames.includes(d)).length > 0 && (
          <p style={{ fontSize: 12, color: 'var(--accent)', marginTop: 10 }}>
            {selectedDomains.filter(d => !aiDomainNames.includes(d)).length} additional domain(s) added
          </p>
        )}
      </Section>
    </div>
  )
}

// ── Step 4 — Select frameworks ─────────────────────────────────────────────────
const StepFrameworks: React.FC<{
  fp: FingerprintResponse
  selected: string[]
  setSelected: (s: string[]) => void
}> = ({ fp, selected, setSelected }) => {
  const toggle = (f: string) =>
    setSelected(selected.includes(f) ? selected.filter(x => x !== f) : [...selected, f])

  return (
    <div>
      <h2 style={headingStyle}>Select your frameworks</h2>
      <p style={subStyle}>These are the compliance frameworks we recommend based on your profile. Select the ones you want to track.</p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 24 }}>
        {fp.suggested_frameworks.map(f => {
          const active = selected.includes(f)
          return (
            <button
              key={f}
              onClick={() => toggle(f)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                background: active ? 'rgba(99,102,241,0.08)' : 'var(--bg2)',
                border: `1.5px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                borderRadius: 10, padding: '12px 14px',
                cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s',
              }}
            >
              <div style={{
                width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                background: active ? 'var(--accent)' : 'transparent',
                border: `2px solid ${active ? 'var(--accent)' : 'var(--border2)'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {active && <span style={{ color: '#fff', fontSize: 10, lineHeight: 1 }}>✓</span>}
              </div>
              <span style={{ fontSize: 13, color: 'var(--text)', fontWeight: active ? 500 : 400 }}>{f}</span>
            </button>
          )
        })}
      </div>

      <p style={{ fontSize: 12, color: 'var(--text3)', marginTop: 12 }}>
        {selected.length} framework{selected.length !== 1 ? 's' : ''} selected
      </p>
    </div>
  )
}

// ── Step 4 — Done ──────────────────────────────────────────────────────────────
const StepDone: React.FC<{ orgName: string; onEnter: () => void }> = ({ orgName, onEnter }) => (
  <div style={{ textAlign: 'center', padding: '16px 0' }}>
    <div style={{
      width: 64, height: 64, borderRadius: '50%',
      background: 'rgba(99,102,241,0.12)', border: '2px solid var(--accent)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      margin: '0 auto 20px',
      fontSize: 28,
    }}>
      🛡️
    </div>
    <h2 style={{ ...headingStyle, textAlign: 'center' }}>You're all set</h2>
    <p style={{ ...subStyle, textAlign: 'center', maxWidth: 340, margin: '8px auto 28px' }}>
      <strong>{orgName}</strong>'s GRC environment has been seeded with your risk register, controls, and framework mapping.
    </p>
    <Button variant="primary" onClick={onEnter} style={{ margin: '0 auto' }}>
      Enter Aegis →
    </Button>
  </div>
)

// ── Shared styles ─────────────────────────────────────────────────────────────
const headingStyle: React.CSSProperties = {
  fontSize: 20, fontWeight: 400, letterSpacing: -0.4, marginBottom: 6, color: 'var(--text)',
}
const subStyle: React.CSSProperties = {
  fontSize: 13, color: 'var(--text2)', lineHeight: 1.55,
}

// ── Sub-components ─────────────────────────────────────────────────────────────
const InfoCard: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div style={{
    background: 'var(--bg2)', border: '1px solid var(--border)',
    borderRadius: 10, padding: '12px 14px',
  }}>
    <p style={{ fontSize: 10, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4, fontWeight: 600 }}>{label}</p>
    <p style={{ fontSize: 13, color: 'var(--text)', fontWeight: 500 }}>{value}</p>
  </div>
)

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div style={{ marginTop: 20 }}>
    <p style={{ fontSize: 11, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, marginBottom: 10 }}>{title}</p>
    {children}
  </div>
)

const TagList: React.FC<{ items: string[]; color: string }> = ({ items, color }) => (
  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
    {items.map(item => (
      <span key={item} style={{
        fontSize: 11, padding: '4px 9px', borderRadius: 6,
        background: `${color}18`, color, border: `1px solid ${color}40`,
        fontWeight: 500,
      }}>
        {item}
      </span>
    ))}
  </div>
)

// ── Main wizard ────────────────────────────────────────────────────────────────
export const OnboardingPage: React.FC = () => {
  const navigate = useNavigate()
  const { setOrg, org } = useAuthStore()
  const { addToast } = useUIStore()
  const [step, setStep] = useState(0)
  const [fp, setFp] = useState<FingerprintResponse | null>(null)
  const [selectedDomains, setSelectedDomains] = useState<string[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [completing, setCompleting] = useState(false)

  const handleFingerprintDone = (result: FingerprintResponse) => {
    setFp(result)
    setSelectedDomains(result.risk_domains.map(d => d.name))
    setSelected(result.suggested_frameworks)
    setStep(1)
  }

  const handleFrameworksDone = async () => {
    if (!fp || selected.length === 0) return
    setCompleting(true)
    try {
      const updatedOrg = await orgsApi.completeOnboarding({
        fingerprint_data: fp as unknown as Record<string, unknown>,
        selected_frameworks: selected,
        risk_domains: selectedDomains,
      })
      setOrg(updatedOrg)
      setStep(4)
    } catch {
      addToast({ type: 'error', title: 'Setup failed', body: 'Could not complete onboarding. Please try again.' })
    } finally {
      setCompleting(false)
    }
  }

  const handleEnter = () => navigate('/')

  return (
    <div style={{
      height: '100vh', background: 'var(--bg)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24,
      overflow: 'hidden',
    }}>
      <div style={{
        width: '100%', maxWidth: 560,
        background: 'var(--bg1)', border: '1px solid var(--border2)',
        borderRadius: 18,
        display: 'flex', flexDirection: 'column',
        maxHeight: 'calc(100vh - 48px)',
        animation: 'fadeIn 0.3s ease',
      }}>
        {/* Fixed header — logo + step bar */}
        <div style={{ padding: '32px 40px 0', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 28 }}>
            <div style={{
              width: 30, height: 30, borderRadius: 8, background: 'var(--accent)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <svg viewBox="0 0 14 14" fill="none" width="16" height="16">
                <path d="M7 1.5L12 4v6L7 12.5 2 10V4L7 1.5z" stroke="white" strokeWidth="1.3" strokeLinejoin="round"/>
                <circle cx="7" cy="7" r="2" fill="white"/>
              </svg>
            </div>
            <span style={{ fontSize: 16, fontWeight: 500, letterSpacing: -0.3 }}>Aegis</span>
            <span style={{ fontSize: 12, color: 'var(--text3)', marginLeft: 4 }}>Setup</span>
          </div>
          <StepBar current={step} />
        </div>

        {/* Scrollable content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 40px 24px' }}>
          {step === 0 && <StepIdentify onNext={handleFingerprintDone} />}
          {step === 1 && fp && <StepReview fp={fp} />}
          {step === 2 && fp && (
            <StepRiskDomains fp={fp} selectedDomains={selectedDomains} setSelectedDomains={setSelectedDomains} />
          )}
          {step === 3 && fp && <StepFrameworks fp={fp} selected={selected} setSelected={setSelected} />}
          {step === 4 && (
            <StepDone orgName={fp?.company_name ?? org?.name ?? 'Your organisation'} onEnter={handleEnter} />
          )}
        </div>

        {/* Pinned footer buttons */}
        {(step === 1 || step === 2 || step === 3) && (
          <div style={{
            flexShrink: 0, padding: '16px 40px 24px',
            borderTop: '1px solid var(--border)',
            display: 'flex', gap: 10,
          }}>
            <Button variant="ghost" onClick={() => setStep(s => s - 1)}>← Back</Button>
            {step === 1 && (
              <Button variant="primary" onClick={() => setStep(2)}>Looks good →</Button>
            )}
            {step === 2 && (
              <Button variant="primary" onClick={() => setStep(3)}>
                Continue → ({selectedDomains.length} domains)
              </Button>
            )}
            {step === 3 && (
              <Button variant="primary" loading={completing} disabled={selected.length === 0} onClick={handleFrameworksDone}>
                {completing ? 'Setting up…' : 'Complete setup →'}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
