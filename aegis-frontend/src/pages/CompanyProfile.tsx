import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Building2, Globe, Shield, RefreshCw, Layers,
  FileText, AlertTriangle, ChevronRight, Check,
  Briefcase, MapPin, Users, Cpu,
} from 'lucide-react'
import { orgsApi } from '@/api/client'
import { useAuthStore, useUIStore } from '@/store'
import { Spinner, EmptyState } from '@/components/ui'
import type { FingerprintResponse } from '@/types'

// ── Severity colour map ───────────────────────────────────────────────────────
const SEV_COLOR: Record<string, string> = {
  critical: 'var(--red)',
  high: 'var(--amber)',
  medium: 'var(--blue)',
  low: 'var(--teal2)',
}
const SEV_BG: Record<string, string> = {
  critical: 'rgba(179,79,66,.13)',
  high: 'rgba(184,124,58,.13)',
  medium: 'rgba(77,110,158,.13)',
  low: 'rgba(78,128,106,.13)',
}

export const CompanyProfilePage: React.FC = () => {
  const { org } = useAuthStore()
  const { addToast } = useUIStore()
  const qc = useQueryClient()
  const [rescanName, setRescanName] = useState('')
  const [showRescan, setShowRescan] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['org-profile'],
    queryFn: orgsApi.profile,
  })

  const rescanMutation = useMutation({
    mutationFn: (name: string) => orgsApi.fingerprint(name),
    onSuccess: (fp) => {
      addToast({ type: 'success', title: 'Scan complete', body: `${fp.company_name} re-fingerprinted successfully` })
      qc.setQueryData(['org-profile'], (prev: typeof data) =>
        prev ? { ...prev, fingerprint_data: fp } : prev
      )
      setShowRescan(false)
    },
    onError: () => {
      addToast({ type: 'error', title: 'Scan failed', body: 'Could not fingerprint company. Try again.' })
    },
  })

  const handleRescan = () => {
    const name = rescanName.trim() || org?.name || ''
    if (!name) return
    rescanMutation.mutate(name)
  }

  if (isLoading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <Spinner size={24} />
    </div>
  )

  if (error || !data) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text2)', fontSize: 13 }}>
      Could not load company profile. Check your connection.
    </div>
  )

  const fp: FingerprintResponse | null = data.fingerprint_data && Object.keys(data.fingerprint_data).length > 0
    ? data.fingerprint_data as unknown as FingerprintResponse
    : null

  return (
    <div className="page animate-fade">
      <div className="page-header">
        <div>
          <div className="page-title">Company Profile</div>
          <div className="page-sub">AI-mapped fingerprint of your organisation's risk, process, and regulatory landscape</div>
        </div>
        <button
          className="btn btn-ghost btn-md"
          onClick={() => setShowRescan(v => !v)}
        >
          <RefreshCw size={13} style={{ marginRight: 6 }} />
          Re-scan
        </button>
      </div>

      <div className="page-body" style={{ paddingBottom: 32 }}>

        {/* Re-scan panel */}
        {showRescan && (
          <div className="card animate-slide" style={{ padding: 16, marginBottom: 16, display: 'flex', gap: 10, alignItems: 'center' }}>
            <Building2 size={14} color="var(--text2)" />
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder={`Company name (default: ${org?.name ?? 'your company'})`}
              value={rescanName}
              onChange={e => setRescanName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleRescan()}
            />
            <button
              className="btn btn-primary btn-md"
              onClick={handleRescan}
              disabled={rescanMutation.isPending}
            >
              {rescanMutation.isPending ? <Spinner size={12} /> : 'Scan'}
            </button>
          </div>
        )}

        {/* ── Top identity strip ────────────────────────────────────────────── */}
        <div className="card" style={{ marginBottom: 14 }}>
          <div style={{ padding: '18px 20px', display: 'flex', alignItems: 'center', gap: 20 }}>
            <div style={{
              width: 52, height: 52, borderRadius: 12,
              background: 'linear-gradient(135deg, var(--accent) 0%, var(--accent2) 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              <Building2 size={22} color="#fff" />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 18, fontWeight: 400, letterSpacing: -0.3, color: 'var(--text)' }}>
                {fp?.company_name ?? data.name}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 3, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                {(fp?.industry_label ?? data.industry_label) && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Briefcase size={11} />{fp?.industry_label ?? data.industry_label}
                  </span>
                )}
                {(fp?.jurisdiction ?? data.jurisdiction) && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <MapPin size={11} />{fp?.jurisdiction ?? data.jurisdiction}
                  </span>
                )}
                {(fp?.regulator ?? data.regulator) && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Shield size={11} />{fp?.regulator ?? data.regulator}
                  </span>
                )}
                {fp?.employee_range && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Users size={11} />{fp.employee_range} employees
                  </span>
                )}
              </div>
            </div>
            {fp?.confidence_score !== undefined && (
              <div style={{ textAlign: 'center', flexShrink: 0 }}>
                <div style={{ fontSize: 22, fontWeight: 300, color: fp.confidence_score >= 0.8 ? 'var(--teal2)' : fp.confidence_score >= 0.6 ? 'var(--amber)' : 'var(--red)' }}>
                  {Math.round(fp.confidence_score * 100)}%
                </div>
                <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2 }}>AI confidence</div>
              </div>
            )}
          </div>

          {fp?.business_summary && (
            <div style={{ padding: '12px 20px 16px', borderTop: '1px solid var(--border)', color: 'var(--text2)', fontSize: 12, lineHeight: 1.6 }}>
              {fp.business_summary}
            </div>
          )}
        </div>

        {!fp ? (
          <EmptyState
            title="No fingerprint data"
            body="Use Re-scan to generate an AI company fingerprint for your organisation."
          />
        ) : (
          <>
            {/* ── Stats row ─────────────────────────────────────────────────── */}
            <div className="grid-4" style={{ marginBottom: 14 }}>
              <StatCard icon={<AlertTriangle size={14} />} label="Risk domains" value={fp.risk_domains.length} color="var(--red)" />
              <StatCard icon={<Shield size={14} />} label="Frameworks" value={fp.suggested_frameworks.length} color="var(--accent2)" />
              <StatCard icon={<Cpu size={14} />} label="Processes" value={fp.detected_processes.length} color="var(--teal2)" />
              <StatCard icon={<Globe size={14} />} label="Regulations" value={fp.detected_regulations.length} color="var(--amber)" />
            </div>

            <div className="grid-2" style={{ marginBottom: 14 }}>
              {/* ── Risk Domains ────────────────────────────────────────────── */}
              <div className="card">
                <SectionHeader icon={<AlertTriangle size={13} />} title="Risk Domains" />
                <div style={{ padding: '8px 0' }}>
                  {fp.risk_domains.length === 0
                    ? <EmptyPlaceholder text="No risk domains detected" />
                    : fp.risk_domains.map(d => (
                      <div key={d.name} style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '8px 16px', borderBottom: '1px solid var(--border)',
                      }}>
                        <div style={{
                          width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                          background: SEV_COLOR[d.severity] ?? 'var(--text3)',
                        }} />
                        <span style={{ flex: 1, fontSize: 12, color: 'var(--text)' }}>{d.name}</span>
                        <span style={{
                          fontSize: 10, fontWeight: 500, padding: '2px 6px', borderRadius: 4,
                          background: SEV_BG[d.severity] ?? 'var(--bg2)',
                          color: SEV_COLOR[d.severity] ?? 'var(--text2)',
                        }}>{d.severity}</span>
                        <span style={{ fontSize: 11, color: 'var(--text3)', width: 24, textAlign: 'right' }}>
                          {d.risk_count}
                        </span>
                      </div>
                    ))
                  }
                </div>
              </div>

              {/* ── Suggested Frameworks ────────────────────────────────────── */}
              <div className="card">
                <SectionHeader icon={<Layers size={13} />} title="Regulatory Frameworks" />
                <div style={{ padding: '8px 0' }}>
                  {fp.suggested_frameworks.length === 0
                    ? <EmptyPlaceholder text="No frameworks detected" />
                    : fp.suggested_frameworks.map(f => (
                      <div key={f} style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '9px 16px', borderBottom: '1px solid var(--border)',
                      }}>
                        <Check size={12} color="var(--teal2)" />
                        <span style={{ fontSize: 12, color: 'var(--text)' }}>{f}</span>
                        <ChevronRight size={12} color="var(--text3)" style={{ marginLeft: 'auto' }} />
                      </div>
                    ))
                  }
                </div>
              </div>
            </div>

            <div className="grid-2">
              {/* ── Detected Processes ──────────────────────────────────────── */}
              <div className="card">
                <SectionHeader icon={<Cpu size={13} />} title="Business Processes" />
                <div style={{ padding: '8px 0' }}>
                  {fp.detected_processes.length === 0
                    ? <EmptyPlaceholder text="No processes detected" />
                    : fp.detected_processes.map((p, i) => (
                      <div key={i} style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '8px 16px', borderBottom: '1px solid var(--border)',
                      }}>
                        <div style={{ width: 18, height: 18, borderRadius: 4, background: 'var(--bg2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                          <span style={{ fontSize: 9, fontWeight: 600, color: 'var(--text3)' }}>{i + 1}</span>
                        </div>
                        <span style={{ fontSize: 12, color: 'var(--text)' }}>{p}</span>
                      </div>
                    ))
                  }
                </div>
              </div>

              {/* ── Regulations + Business Lines ─────────────────────────────── */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div className="card">
                  <SectionHeader icon={<Globe size={13} />} title="Detected Regulations" />
                  <div style={{ padding: '8px 0' }}>
                    {fp.detected_regulations.length === 0
                      ? <EmptyPlaceholder text="No regulations detected" />
                      : fp.detected_regulations.map((r, i) => (
                        <div key={i} style={{
                          display: 'flex', alignItems: 'center', gap: 8,
                          padding: '7px 16px', borderBottom: '1px solid var(--border)',
                        }}>
                          <span style={{
                            fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4,
                            background: 'rgba(123,109,170,.13)', color: 'var(--accent2)',
                          }}>{r}</span>
                        </div>
                      ))
                    }
                  </div>
                </div>

                {fp.business_lines && fp.business_lines.length > 0 && (
                  <div className="card">
                    <SectionHeader icon={<FileText size={13} />} title="Business Lines" />
                    <div style={{ padding: '8px 0' }}>
                      {fp.business_lines.map((b, i) => (
                        <div key={i} style={{
                          padding: '7px 16px', borderBottom: '1px solid var(--border)',
                          fontSize: 12, color: 'var(--text)',
                        }}>{b}</div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

const StatCard: React.FC<{ icon: React.ReactNode; label: string; value: number; color: string }> = ({
  icon, label, value, color,
}) => (
  <div className="metric-card">
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, color: 'var(--text2)' }}>
      {icon}
      <span className="metric-label" style={{ marginBottom: 0 }}>{label}</span>
    </div>
    <div className="metric-value" style={{ color }}>{value}</div>
  </div>
)

const SectionHeader: React.FC<{ icon: React.ReactNode; title: string }> = ({ icon, title }) => (
  <div style={{
    display: 'flex', alignItems: 'center', gap: 7,
    padding: '11px 16px', borderBottom: '1px solid var(--border)',
  }}>
    <span style={{ color: 'var(--text2)' }}>{icon}</span>
    <span style={{ fontSize: 12, fontWeight: 500 }}>{title}</span>
  </div>
)

const EmptyPlaceholder: React.FC<{ text: string }> = ({ text }) => (
  <div style={{ padding: '14px 16px', fontSize: 12, color: 'var(--text3)' }}>{text}</div>
)
