import React, { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Building2, Briefcase, Globe, Shield, Cpu, Users, Server,
  History, Pencil, Plus, Trash2, Check, X, ChevronRight,
  AlertTriangle, Clock,
} from 'lucide-react'
import { profileApi, validationApi } from '@/api/client'
import { useAuthStore, useUIStore } from '@/store'
import { Spinner } from '@/components/ui'
import { VerificationTick } from '@/components/profile/VerificationTick'
import { DisputedFieldModal } from '@/components/profile/DisputedFieldModal'
import { ReseedProposalsPanel } from '@/components/profile/ReseedProposalsPanel'
import type {
  FullProfile, OrgIdentity, LOB, OrgGeo, OrgIndustry,
  OrgProduct, CustomerSegment, ThirdParty, DataTech, PropagationPreview,
  FieldStatus,
} from '@/types'

// ── Constants ─────────────────────────────────────────────────────────────────
const SECTIONS = [
  { id: 'identity',   label: 'Organisation Identity', icon: <Building2 size={13} /> },
  { id: 'lobs',       label: 'Lines of Business',     icon: <Briefcase size={13} /> },
  { id: 'geos',       label: 'Geographies',            icon: <Globe size={13} /> },
  { id: 'industries', label: 'Industries',             icon: <Briefcase size={13} /> },
  { id: 'products',   label: 'Products & Services',    icon: <Cpu size={13} /> },
  { id: 'segments',   label: 'Customer Segments',      icon: <Users size={13} /> },
  { id: 'third',      label: 'Third-Party Dependencies', icon: <Shield size={13} /> },
  { id: 'datatech',   label: 'Data & Technology',      icon: <Server size={13} /> },
  { id: 'changelog',  label: 'Change History',         icon: <History size={13} /> },
]

const EMPLOYEE_RANGES = ['<50', '50–200', '200–1000', '1000–5000', '5000–20000', '>20000']
const REVENUE_RANGES  = ['<$1M', '$1M–$10M', '$10M–$50M', '$50M–$100M', '$100M–$500M', '$500M–$1B', '>$1B']
const PRESENCE_TYPES  = ['headquarters', 'operational', 'registered_only', 'data_processing', 'planned_expansion']
const TIER_COLORS: Record<string, string> = { tier_1: 'var(--red)', tier_2: 'var(--amber)', tier_3: 'var(--teal2)' }
const STATUS_COLORS: Record<string, string> = { active: 'var(--teal2)', planned: 'var(--blue)', archived: 'var(--text3)' }
const ASSESS_COLORS: Record<string, string> = { passed: 'var(--teal2)', flagged: 'var(--red)', in_progress: 'var(--amber)', not_assessed: 'var(--text3)' }
const SENS_COLORS: Record<string, string>   = { critical: 'var(--red)', high: 'var(--red)', medium: 'var(--amber)', low: 'var(--teal2)', none: 'var(--text3)' }

// ── Shared UI atoms ───────────────────────────────────────────────────────────
const SectionCard: React.FC<{
  id: string; title: string; icon: React.ReactNode
  editing: boolean; onEdit: () => void; onCancel: () => void; onSave: () => void
  saving?: boolean; children: React.ReactNode; badge?: React.ReactNode
}> = ({ id, title, icon, editing, onEdit, onCancel, onSave, saving, children, badge }) => (
  <div id={id} className="card" style={{ marginBottom: 14, scrollMarginTop: 16 }}>
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <span style={{ color: 'var(--text2)' }}>{icon}</span>
        <span style={{ fontSize: 12, fontWeight: 500 }}>{title}</span>
        {badge}
      </div>
      <div style={{ display: 'flex', gap: 6 }}>
        {editing ? (
          <>
            <button className="btn btn-ghost btn-sm" onClick={onCancel} disabled={saving}><X size={12} /></button>
            <button className="btn btn-primary btn-sm" onClick={onSave} disabled={saving}>
              {saving ? <Spinner size={11} /> : <><Check size={12} style={{ marginRight: 4 }} />Save</>}
            </button>
          </>
        ) : (
          <button className="btn btn-ghost btn-sm" onClick={onEdit}><Pencil size={12} style={{ marginRight: 4 }} />Edit</button>
        )}
      </div>
    </div>
    <div style={{ padding: 16 }}>{children}</div>
  </div>
)

const Field: React.FC<{
  label: string; value?: string | number | null; children?: React.ReactNode; tick?: React.ReactNode
}> = ({ label, value, children, tick }) => (
  <div style={{ marginBottom: 14 }}>
    <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text3)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.04em' }}>{label}</div>
    {children ?? (
      <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
        <span style={{ fontSize: 12, color: value ? 'var(--text)' : 'var(--text3)' }}>{value ?? '—'}</span>
        {tick}
      </div>
    )}
  </div>
)

// ── Verification state hook ───────────────────────────────────────────────────

interface ValidatorSlot { status: string; confidence?: number; sources?: string[]; validated_at?: string | null; proposed_alternative?: { value: unknown } | null }

function useEntityVerification(entityType: string, entityId: string | undefined) {
  return useQuery({
    queryKey: ['verification', entityType, entityId],
    queryFn: () => validationApi.getState(entityType, entityId!),
    enabled: !!entityId,
    staleTime: 60_000,
  })
}

interface DisputedField {
  validationId: string
  fieldLabel: string
  seededValue: unknown
  seededConfidence?: number
  alternativeValue: unknown
  alternativeConfidence?: number
}

const Inp: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = (p) => (
  <input className="input" style={{ width: '100%', fontSize: 12, padding: '5px 8px' }} {...p} />
)

const Sel: React.FC<React.SelectHTMLAttributes<HTMLSelectElement> & { opts: string[] }> = ({ opts, ...p }) => (
  <select className="input" style={{ width: '100%', fontSize: 12, padding: '5px 8px' }} {...p}>
    <option value="">— select —</option>
    {opts.map(o => <option key={o} value={o}>{o}</option>)}
  </select>
)

const Pill: React.FC<{ label: string; color?: string; onRemove?: () => void }> = ({ label, color = 'var(--accent2)', onRemove }) => (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4, background: color + '22', color, marginRight: 4, marginBottom: 4 }}>
    {label}
    {onRemove && <button onClick={onRemove} style={{ background: 'none', border: 'none', cursor: 'pointer', color, lineHeight: 1, padding: 0 }}>×</button>}
  </span>
)

const EmptyRow: React.FC<{ text: string }> = ({ text }) => (
  <div style={{ padding: '20px 0', textAlign: 'center', fontSize: 12, color: 'var(--text3)' }}>{text}</div>
)

// ── Propagation Modal ─────────────────────────────────────────────────────────
const PropagationModal: React.FC<{
  preview: PropagationPreview; onApply: (approved: string[]) => void; onDismiss: () => void; applying: boolean
}> = ({ preview, onApply, onDismiss, applying }) => {
  const [selected, setSelected] = useState<Set<string>>(new Set(preview.affected_modules.map(m => m.module)))
  const toggle = (m: string) => setSelected(s => { const n = new Set(s); n.has(m) ? n.delete(m) : n.add(m); return n })
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="card animate-fade" style={{ width: 560, maxHeight: '80vh', overflow: 'auto', padding: 0 }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontSize: 14, fontWeight: 500 }}>Your changes affect {preview.affected_modules.length} modules</div>
          <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 3 }}>{preview.change_summary}</div>
        </div>
        <div style={{ padding: '12px 20px' }}>
          {preview.affected_modules.map(mod => (
            <div key={mod.module} style={{ marginBottom: 14, padding: 12, background: 'var(--bg2)', borderRadius: 6, border: `1px solid ${selected.has(mod.module) ? 'var(--accent)' : 'var(--border)'}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <input type="checkbox" checked={selected.has(mod.module)} onChange={() => toggle(mod.module)} style={{ accentColor: 'var(--accent)' }} />
                <span style={{ fontSize: 12, fontWeight: 500 }}>{mod.module_label}</span>
                <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 3, background: 'rgba(123,109,170,.15)', color: 'var(--accent2)' }}>{mod.count} change{mod.count !== 1 ? 's' : ''}</span>
              </div>
              {mod.preview.slice(0, 2).map((p, i) => (
                <div key={i} style={{ fontSize: 11, color: 'var(--text2)', paddingLeft: 24, marginBottom: 4 }}>
                  <span style={{ fontWeight: 500, color: 'var(--text)' }}>{p.title}</span> — {p.rationale}
                </div>
              ))}
            </div>
          ))}
        </div>
        <div style={{ padding: '12px 20px', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <button className="btn btn-ghost btn-sm" onClick={onDismiss}>Save profile only</button>
          <button className="btn btn-primary btn-md" onClick={() => onApply([...selected])} disabled={applying}>
            {applying ? <Spinner size={12} /> : `Apply selected (${selected.size})`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export const CompanyProfilePage: React.FC = () => {
  const { user } = useAuthStore()
  const { addToast } = useUIStore()
  const qc = useQueryClient()
  const isAdmin = user?.role === 'admin' || user?.role === 'head_of_audit'

  const [activeSection, setActiveSection] = useState('identity')
  const [propagation, setPropagation] = useState<PropagationPreview | null>(null)
  const [applyingProp, setApplyingProp] = useState(false)
  const [disputedField, setDisputedField] = useState<DisputedField | null>(null)

  const refs = Object.fromEntries(SECTIONS.map(s => [s.id, useRef<HTMLDivElement>(null)]))

  const { data, isLoading } = useQuery({ queryKey: ['full-profile'], queryFn: profileApi.get })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['full-profile'] })

  const scrollTo = (id: string) => {
    setActiveSection(id)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const pollPropagation = async (changeLogId: string) => {
    for (let i = 0; i < 12; i++) {
      await new Promise(r => setTimeout(r, 2500))
      try {
        const preview = await profileApi.getPropagation(changeLogId)
        if (preview.affected_modules.length > 0) { setPropagation(preview); return }
      } catch { /* ignore */ }
    }
  }

  const applyPropagation = async (approved: string[]) => {
    if (!propagation) return
    setApplyingProp(true)
    try {
      await profileApi.applyPropagation(propagation.change_log_id, approved)
      addToast({ type: 'success', title: 'Changes applied', body: `${approved.length} module(s) updated` })
      setPropagation(null)
      invalidate()
    } catch {
      addToast({ type: 'error', title: 'Apply failed' })
    } finally { setApplyingProp(false) }
  }

  if (isLoading) return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}><Spinner size={24} /></div>

  const profile = data as FullProfile | undefined

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* ── Left nav ─────────────────────────────────────────────────────── */}
      <nav style={{ width: 220, flexShrink: 0, borderRight: '1px solid var(--border)', padding: '16px 0', overflowY: 'auto', background: 'var(--bg1)' }}>
        <div style={{ padding: '0 12px 12px', fontSize: 10, fontWeight: 600, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '.06em' }}>Company Profile</div>
        {SECTIONS.map(s => (
          <button
            key={s.id}
            onClick={() => scrollTo(s.id)}
            style={{
              width: '100%', textAlign: 'left', padding: '7px 14px',
              display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
              background: activeSection === s.id ? 'rgba(123,109,170,.12)' : 'none',
              color: activeSection === s.id ? 'var(--accent2)' : 'var(--text2)',
              border: 'none', cursor: 'pointer', borderLeft: activeSection === s.id ? '2px solid var(--accent)' : '2px solid transparent',
            }}
          >
            {s.icon}{s.label}
            {s.id === 'changelog' && (profile?.pending_propagations ?? 0) > 0 && (
              <span style={{ marginLeft: 'auto', width: 6, height: 6, borderRadius: '50%', background: 'var(--amber)', flexShrink: 0 }} />
            )}
          </button>
        ))}
      </nav>

      {/* ── Right content ────────────────────────────────────────────────── */}
      <main style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
        <div style={{ maxWidth: 860 }}>
          <div style={{ marginBottom: 20 }}>
            <div className="page-title">Company Profile</div>
            <div className="page-sub">Canonical context for all AI features — changes propagate across the platform</div>
          </div>

          <ReseedProposalsPanel isAdmin={isAdmin} onApplied={invalidate} />

          <IdentitySection     data={profile?.identity ?? null}           isAdmin={isAdmin} onSaved={pollPropagation} onInvalidate={invalidate} addToast={addToast} onDisputed={setDisputedField} />
          <LobSection          data={profile?.lines_of_business ?? []}    isAdmin={isAdmin} onSaved={pollPropagation} onInvalidate={invalidate} addToast={addToast} />
          <GeoSection          data={profile?.geographies ?? []}          isAdmin={isAdmin} onSaved={pollPropagation} onInvalidate={invalidate} addToast={addToast} />
          <IndustrySection     data={profile?.industries ?? []}           isAdmin={isAdmin} onSaved={pollPropagation} onInvalidate={invalidate} addToast={addToast} />
          <ProductSection      data={profile?.products ?? []}             isAdmin={isAdmin} onSaved={pollPropagation} onInvalidate={invalidate} addToast={addToast} />
          <SegmentSection      data={profile?.customer_segments ?? []}    isAdmin={isAdmin} onSaved={pollPropagation} onInvalidate={invalidate} addToast={addToast} />
          <ThirdPartySection   data={profile?.third_parties ?? []}        isAdmin={isAdmin} onSaved={pollPropagation} onInvalidate={invalidate} addToast={addToast} />
          <DataTechSection     data={profile?.data_tech ?? null}          isAdmin={isAdmin} onSaved={pollPropagation} onInvalidate={invalidate} addToast={addToast} />
          <ChangeLogSection />
        </div>
      </main>

      {propagation && (
        <PropagationModal
          preview={propagation}
          onApply={applyPropagation}
          onDismiss={() => setPropagation(null)}
          applying={applyingProp}
        />
      )}

      {disputedField && (
        <DisputedFieldModal
          validationId={disputedField.validationId}
          fieldLabel={disputedField.fieldLabel}
          seededValue={disputedField.seededValue}
          seededConfidence={disputedField.seededConfidence}
          alternativeValue={disputedField.alternativeValue}
          alternativeConfidence={disputedField.alternativeConfidence}
          onResolved={invalidate}
          onClose={() => setDisputedField(null)}
        />
      )}
    </div>
  )
}

// ── Section: Identity ─────────────────────────────────────────────────────────
const IdentitySection: React.FC<SectionProps<OrgIdentity | null>> = ({ data, isAdmin, onSaved, onInvalidate, addToast, onDisputed }) => {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Partial<OrgIdentity>>({})
  const [saving, setSaving] = useState(false)

  const { data: vState, refetch: refetchV } = useEntityVerification('org_profiles', data?.id)
  const vFields = (vState as { fields?: Record<string, { a?: ValidatorSlot; b?: ValidatorSlot }> })?.fields ?? {}

  const tick = (fieldName: string, label: string) => {
    const f = vFields[fieldName]
    const statusMap = (data as unknown as Record<string, unknown>)?.[`field_status_map`] as Record<string, FieldStatus> | undefined
    const fieldStatus = statusMap?.[fieldName]
    const bResult = f?.b ?? null
    return (
      <VerificationTick
        fieldStatus={fieldStatus}
        validationA={f?.a ?? null}
        validationB={bResult}
        entityType="org_profiles"
        entityId={data?.id ?? ''}
        fieldName={fieldName}
        isAdmin={isAdmin}
        onReVerify={() => {
          if (!data?.id) return
          validationApi.verifyField('org_profiles', data.id, fieldName).then(() => refetchV())
          if ((fieldStatus === 'flagged_for_review') && bResult?.proposed_alternative && onDisputed) {
            onDisputed({
              validationId: fieldName,
              fieldLabel: label,
              seededValue: (data as unknown as Record<string, unknown>)?.[fieldName],
              seededConfidence: f?.a?.confidence,
              alternativeValue: bResult.proposed_alternative.value,
              alternativeConfidence: bResult.confidence,
            })
          }
        }}
      />
    )
  }

  const startEdit = () => { setForm(data ?? {}); setEditing(true) }
  const cancel = () => setEditing(false)
  const f = (k: keyof OrgIdentity) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(p => ({ ...p, [k]: e.target.value || null }))

  const save = async () => {
    setSaving(true)
    try {
      let res: { id?: string }
      if (data) res = await profileApi.updateIdentity(form)
      else res = await profileApi.createIdentity(form)
      onInvalidate()
      setEditing(false)
      addToast({ type: 'success', title: 'Identity saved' })
      if (res.id) onSaved?.('')
    } catch { addToast({ type: 'error', title: 'Save failed' }) }
    finally { setSaving(false) }
  }

  return (
    <SectionCard id="identity" title="Organisation Identity" icon={<Building2 size={13} />}
      editing={editing} onEdit={startEdit} onCancel={cancel} onSave={save} saving={saving}>
      {editing ? (
        <div className="grid-2">
          {([['legal_name','Legal name'],['trading_name','Trading name'],['hq_country','HQ country (2-letter)'],['hq_city','HQ city'],['stock_ticker','Stock ticker'],['website','Website']] as [keyof OrgIdentity, string][]).map(([k, label]) => (
            <Field key={k} label={label}><Inp value={(form[k] as string) ?? ''} onChange={f(k)} /></Field>
          ))}
          <Field label="Employee range"><Sel opts={EMPLOYEE_RANGES} value={(form.employee_range as string) ?? ''} onChange={f('employee_range')} /></Field>
          <Field label="Annual revenue range"><Sel opts={REVENUE_RANGES} value={(form.annual_revenue_range as string) ?? ''} onChange={f('annual_revenue_range')} /></Field>
          <Field label="Year founded"><Inp type="number" value={(form.year_founded as number) ?? ''} onChange={e => setForm(p => ({ ...p, year_founded: e.target.value ? Number(e.target.value) : null }))} /></Field>
          <div style={{ gridColumn: '1/-1' }}>
            <Field label="Description (max 500 chars)">
              <textarea className="input" rows={3} maxLength={500} style={{ width: '100%', fontSize: 12, padding: '5px 8px', resize: 'vertical' }}
                value={(form.description as string) ?? ''} onChange={f('description')} />
            </Field>
          </div>
        </div>
      ) : data ? (
        <div className="grid-2">
          <Field label="Legal name" value={data.legal_name} tick={tick('legal_name', 'Legal name')} />
          <Field label="Trading name" value={data.trading_name} tick={tick('trading_name', 'Trading name')} />
          <Field label="HQ" value={[data.hq_city, data.hq_country].filter(Boolean).join(', ')} tick={tick('hq_country', 'HQ country')} />
          <Field label="Employee range" value={data.employee_range} tick={tick('employee_range', 'Employee range')} />
          <Field label="Revenue range" value={data.annual_revenue_range} tick={tick('annual_revenue_range', 'Annual revenue range')} />
          <Field label="Founded" value={data.year_founded?.toString()} tick={tick('year_founded', 'Year founded')} />
          <Field label="Website" value={data.website} tick={tick('website', 'Website')} />
          <Field label="Ticker" value={data.stock_ticker} tick={tick('stock_ticker', 'Stock ticker')} />
          {data.description && <div style={{ gridColumn: '1/-1' }}><Field label="Description" value={data.description} tick={tick('description', 'Description')} /></div>}
        </div>
      ) : (
        <EmptyRow text="No identity configured — click Edit to set up your company profile." />
      )}
    </SectionCard>
  )
}

// ── Section: Lines of Business ────────────────────────────────────────────────
const LobSection: React.FC<SectionProps<LOB[]>> = ({ data, isAdmin, onSaved, onInvalidate, addToast }) => {
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState<Partial<LOB>>({ status: 'active', is_primary: false })
  const [saving, setSaving] = useState(false)
  const showArchived = data.some(l => l.status === 'archived')

  const save = async () => {
    if (!form.name) return
    setSaving(true)
    try {
      const res = await profileApi.createLob(form)
      onInvalidate(); setAdding(false); setForm({ status: 'active', is_primary: false })
      addToast({ type: 'success', title: `LOB "${res.name}" added` })
      onSaved?.('')
    } catch { addToast({ type: 'error', title: 'Save failed' }) }
    finally { setSaving(false) }
  }

  const archive = async (id: string, name: string) => {
    try { await profileApi.archiveLob(id); onInvalidate(); addToast({ type: 'info', title: `"${name}" archived` }) }
    catch { addToast({ type: 'error', title: 'Archive failed' }) }
  }

  const visible = editing ? data : data.filter(l => l.status !== 'archived')

  return (
    <SectionCard id="lobs" title="Lines of Business" icon={<Briefcase size={13} />}
      editing={editing} onEdit={() => setEditing(true)} onCancel={() => { setEditing(false); setAdding(false) }} onSave={() => setEditing(false)}>
      <table className="table">
        <thead><tr><th>Name</th><th>Status</th><th>Primary?</th><th>Revenue %</th>{editing && <th></th>}</tr></thead>
        <tbody>
          {visible.length === 0 && !adding && <tr><td colSpan={5}><EmptyRow text="No lines of business yet" /></td></tr>}
          {visible.map(l => (
            <tr key={l.id}>
              <td style={{ fontSize: 12 }}>{l.name}{l.description && <div style={{ fontSize: 11, color: 'var(--text3)' }}>{l.description}</div>}</td>
              <td><Pill label={l.status} color={STATUS_COLORS[l.status]} /></td>
              <td>{l.is_primary ? <Check size={12} color="var(--teal2)" /> : null}</td>
              <td style={{ fontSize: 12, color: 'var(--text2)' }}>{l.revenue_contribution_pct != null ? `${l.revenue_contribution_pct}%` : '—'}</td>
              {editing && <td><button className="btn btn-ghost btn-sm" onClick={() => archive(l.id, l.name)}><Trash2 size={11} /></button></td>}
            </tr>
          ))}
          {adding && (
            <tr>
              <td><Inp placeholder="Name" value={form.name ?? ''} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} /></td>
              <td><Sel opts={['active','planned','archived']} value={form.status ?? 'active'} onChange={e => setForm(p => ({ ...p, status: e.target.value as LOB['status'] }))} /></td>
              <td><input type="checkbox" checked={form.is_primary ?? false} onChange={e => setForm(p => ({ ...p, is_primary: e.target.checked }))} /></td>
              <td><Inp type="number" placeholder="%" value={form.revenue_contribution_pct ?? ''} onChange={e => setForm(p => ({ ...p, revenue_contribution_pct: e.target.value ? Number(e.target.value) : null }))} /></td>
              <td style={{ display: 'flex', gap: 4 }}>
                <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? <Spinner size={11} /> : <Check size={11} />}</button>
                <button className="btn btn-ghost btn-sm" onClick={() => setAdding(false)}><X size={11} /></button>
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {editing && !adding && <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => setAdding(true)}><Plus size={12} style={{ marginRight: 4 }} />Add LOB</button>}
    </SectionCard>
  )
}

// ── Section: Geographies ──────────────────────────────────────────────────────
const GeoSection: React.FC<SectionProps<OrgGeo[]>> = ({ data, isAdmin, onSaved, onInvalidate, addToast }) => {
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState<Partial<OrgGeo>>({ presence_type: 'operational' })
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (!form.country) return
    setSaving(true)
    try {
      await profileApi.createGeo(form); onInvalidate(); setAdding(false); setForm({ presence_type: 'operational' })
      addToast({ type: 'success', title: `Geography "${form.country}" added` }); onSaved?.('')
    } catch { addToast({ type: 'error', title: 'Save failed' }) }
    finally { setSaving(false) }
  }

  const del = async (id: string, country: string) => {
    try { await profileApi.deleteGeo(id); onInvalidate(); addToast({ type: 'info', title: `${country} removed` }) }
    catch { addToast({ type: 'error', title: 'Delete failed' }) }
  }

  return (
    <SectionCard id="geos" title="Geographies" icon={<Globe size={13} />}
      editing={editing} onEdit={() => setEditing(true)} onCancel={() => { setEditing(false); setAdding(false) }} onSave={() => setEditing(false)}>
      <table className="table">
        <thead><tr><th>Country</th><th>Presence</th><th>Regulations</th>{editing && <th></th>}</tr></thead>
        <tbody>
          {data.length === 0 && !adding && <tr><td colSpan={4}><EmptyRow text="No geographies configured" /></td></tr>}
          {data.map(g => (
            <tr key={g.id}>
              <td style={{ fontSize: 12, fontWeight: 500 }}>{g.country}{g.region && <span style={{ color: 'var(--text3)', fontWeight: 400 }}> · {g.region}</span>}</td>
              <td><Pill label={g.presence_type.replace(/_/g, ' ')} color="var(--blue)" /></td>
              <td>{g.regulatory_flags.slice(0, 3).map(r => <Pill key={r} label={r} color="var(--accent2)" />)}{g.regulatory_flags.length > 3 && <Pill label={`+${g.regulatory_flags.length - 3}`} />}</td>
              {editing && <td><button className="btn btn-ghost btn-sm" onClick={() => del(g.id, g.country)}><Trash2 size={11} /></button></td>}
            </tr>
          ))}
          {adding && (
            <tr>
              <td><Inp placeholder="DE, US, GB…" maxLength={2} style={{ textTransform: 'uppercase', width: 60 }} value={form.country ?? ''} onChange={e => setForm(p => ({ ...p, country: e.target.value.toUpperCase() }))} /></td>
              <td><Sel opts={PRESENCE_TYPES} value={form.presence_type ?? 'operational'} onChange={e => setForm(p => ({ ...p, presence_type: e.target.value }))} /></td>
              <td style={{ fontSize: 11, color: 'var(--text3)' }}>Auto-derived on save</td>
              <td style={{ display: 'flex', gap: 4 }}>
                <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? <Spinner size={11} /> : <Check size={11} />}</button>
                <button className="btn btn-ghost btn-sm" onClick={() => setAdding(false)}><X size={11} /></button>
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {editing && !adding && <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => setAdding(true)}><Plus size={12} style={{ marginRight: 4 }} />Add geography</button>}
    </SectionCard>
  )
}

// ── Section: Industries ───────────────────────────────────────────────────────
const IndustrySection: React.FC<SectionProps<OrgIndustry[]>> = ({ data, isAdmin, onSaved, onInvalidate, addToast }) => {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Partial<OrgIndustry>>({ classification: 'secondary' })
  const [saving, setSaving] = useState(false)

  const add = async () => {
    if (!form.name || !form.code) return
    setSaving(true)
    try {
      await profileApi.createIndustry(form); onInvalidate(); setForm({ classification: 'secondary' })
      addToast({ type: 'success', title: `Industry "${form.name}" added` }); onSaved?.('')
    } catch { addToast({ type: 'error', title: 'Save failed' }) }
    finally { setSaving(false) }
  }

  const del = async (id: string) => {
    try { await profileApi.deleteIndustry(id); onInvalidate() }
    catch { addToast({ type: 'error', title: 'Delete failed' }) }
  }

  return (
    <SectionCard id="industries" title="Industries & Regulatory Sectors" icon={<Briefcase size={13} />}
      editing={editing} onEdit={() => setEditing(true)} onCancel={() => setEditing(false)} onSave={() => setEditing(false)}>
      <div style={{ marginBottom: 12 }}>
        {data.length === 0 && <EmptyRow text="No industries configured" />}
        {data.map(i => (
          <span key={i.id} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, marginRight: 6, marginBottom: 6, padding: '4px 10px', borderRadius: 6, background: i.classification === 'primary' ? 'rgba(123,109,170,.2)' : 'var(--bg2)', border: '1px solid var(--border)', fontSize: 12 }}>
            {i.classification === 'primary' && <span style={{ fontSize: 9, color: 'var(--accent2)' }}>★</span>}
            {i.name} <span style={{ fontSize: 10, color: 'var(--text3)' }}>{i.code}</span>
            {editing && <button onClick={() => del(i.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', lineHeight: 1 }}>×</button>}
          </span>
        ))}
      </div>
      {editing && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Inp placeholder="Code (e.g. 5221)" style={{ width: 110 }} value={form.code ?? ''} onChange={e => setForm(p => ({ ...p, code: e.target.value }))} />
          <Inp placeholder="Industry name" style={{ flex: 1 }} value={form.name ?? ''} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
          <Sel opts={['primary', 'secondary']} value={form.classification ?? 'secondary'} style={{ width: 120 }} onChange={e => setForm(p => ({ ...p, classification: e.target.value as 'primary' | 'secondary' }))} />
          <button className="btn btn-primary btn-sm" onClick={add} disabled={saving}>{saving ? <Spinner size={11} /> : <Plus size={11} />}</button>
        </div>
      )}
    </SectionCard>
  )
}

// ── Section: Products ─────────────────────────────────────────────────────────
const ProductSection: React.FC<SectionProps<OrgProduct[]>> = ({ data, isAdmin, onSaved, onInvalidate, addToast }) => {
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState<Partial<OrgProduct>>({ product_type: 'product', status: 'live', data_sensitivity: 'low' })
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (!form.name) return
    setSaving(true)
    try {
      await profileApi.createProduct(form); onInvalidate(); setAdding(false); setForm({ product_type: 'product', status: 'live', data_sensitivity: 'low' })
      addToast({ type: 'success', title: `Product "${form.name}" added` }); onSaved?.('')
    } catch { addToast({ type: 'error', title: 'Save failed' }) }
    finally { setSaving(false) }
  }

  const del = async (id: string) => {
    try { await profileApi.deleteProduct(id); onInvalidate() }
    catch { addToast({ type: 'error', title: 'Delete failed' }) }
  }

  return (
    <SectionCard id="products" title="Products & Services" icon={<Cpu size={13} />}
      editing={editing} onEdit={() => setEditing(true)} onCancel={() => { setEditing(false); setAdding(false) }} onSave={() => setEditing(false)}>
      <div className="grid-3">
        {data.length === 0 && !adding && <div style={{ gridColumn: '1/-1' }}><EmptyRow text="No products configured" /></div>}
        {data.map(p => (
          <div key={p.id} style={{ padding: 12, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <div style={{ fontSize: 12, fontWeight: 500 }}>{p.name}</div>
              {editing && <button className="btn btn-ghost btn-sm" onClick={() => del(p.id)}><Trash2 size={11} /></button>}
            </div>
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              <Pill label={p.product_type} color="var(--blue)" />
              <Pill label={p.status} color={p.status === 'live' ? 'var(--teal2)' : p.status === 'beta' ? 'var(--amber)' : 'var(--text3)'} />
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 10 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: SENS_COLORS[p.data_sensitivity] ?? 'var(--text3)' }} />
                <span style={{ color: 'var(--text3)' }}>{p.data_sensitivity}</span>
              </span>
            </div>
          </div>
        ))}
      </div>
      {editing && !adding && <button className="btn btn-ghost btn-sm" style={{ marginTop: 10 }} onClick={() => setAdding(true)}><Plus size={12} style={{ marginRight: 4 }} />Add product</button>}
      {adding && (
        <div style={{ marginTop: 10, padding: 12, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg2)' }}>
          <div className="grid-2" style={{ marginBottom: 8 }}>
            <Field label="Name"><Inp value={form.name ?? ''} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} /></Field>
            <Field label="Type"><Sel opts={['product','service','platform','api','data_product']} value={form.product_type ?? 'product'} onChange={e => setForm(p => ({ ...p, product_type: e.target.value }))} /></Field>
            <Field label="Status"><Sel opts={['live','beta','sunset','planned']} value={form.status ?? 'live'} onChange={e => setForm(p => ({ ...p, status: e.target.value }))} /></Field>
            <Field label="Data sensitivity"><Sel opts={['none','low','medium','high','critical']} value={form.data_sensitivity ?? 'low'} onChange={e => setForm(p => ({ ...p, data_sensitivity: e.target.value }))} /></Field>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? <Spinner size={11} /> : 'Add'}</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setAdding(false)}>Cancel</button>
          </div>
        </div>
      )}
    </SectionCard>
  )
}

// ── Section: Customer Segments ────────────────────────────────────────────────
const SegmentSection: React.FC<SectionProps<CustomerSegment[]>> = ({ data, isAdmin, onSaved, onInvalidate, addToast }) => {
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState<Partial<CustomerSegment>>({ segment_type: 'b2b', includes_minors: false, includes_healthcare: false, includes_financial: false })
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (!form.name) return
    setSaving(true)
    try {
      await profileApi.createSegment(form); onInvalidate(); setAdding(false); setForm({ segment_type: 'b2b' })
      addToast({ type: 'success', title: `Segment "${form.name}" added` }); onSaved?.('')
    } catch { addToast({ type: 'error', title: 'Save failed' }) }
    finally { setSaving(false) }
  }

  const del = async (id: string) => {
    try { await profileApi.deleteSegment(id); onInvalidate() }
    catch { addToast({ type: 'error', title: 'Delete failed' }) }
  }

  return (
    <SectionCard id="segments" title="Customer Segments" icon={<Users size={13} />}
      editing={editing} onEdit={() => setEditing(true)} onCancel={() => { setEditing(false); setAdding(false) }} onSave={() => setEditing(false)}>
      <table className="table">
        <thead><tr><th>Segment</th><th>Type</th><th>Flags</th><th>Est. size</th>{editing && <th></th>}</tr></thead>
        <tbody>
          {data.length === 0 && !adding && <tr><td colSpan={5}><EmptyRow text="No segments configured" /></td></tr>}
          {data.map(s => (
            <tr key={s.id}>
              <td style={{ fontSize: 12, fontWeight: 500 }}>{s.name}</td>
              <td><Pill label={s.segment_type.toUpperCase()} color="var(--blue)" /></td>
              <td>
                {s.includes_minors && <span title="Includes minors" style={{ marginRight: 4 }}>👶</span>}
                {s.includes_healthcare && <span title="Healthcare" style={{ marginRight: 4 }}>🏥</span>}
                {s.includes_financial && <span title="Financial" style={{ marginRight: 4 }}>💳</span>}
              </td>
              <td style={{ fontSize: 12, color: 'var(--text2)' }}>{s.estimated_size ?? '—'}</td>
              {editing && <td><button className="btn btn-ghost btn-sm" onClick={() => del(s.id)}><Trash2 size={11} /></button></td>}
            </tr>
          ))}
          {adding && (
            <tr>
              <td><Inp placeholder="Name" value={form.name ?? ''} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} /></td>
              <td><Sel opts={['b2b','b2c','b2g','b2b2c','internal']} value={form.segment_type ?? 'b2b'} onChange={e => setForm(p => ({ ...p, segment_type: e.target.value }))} /></td>
              <td>
                <label style={{ marginRight: 8, fontSize: 11 }}><input type="checkbox" checked={form.includes_minors ?? false} onChange={e => setForm(p => ({ ...p, includes_minors: e.target.checked }))} /> 👶</label>
                <label style={{ marginRight: 8, fontSize: 11 }}><input type="checkbox" checked={form.includes_healthcare ?? false} onChange={e => setForm(p => ({ ...p, includes_healthcare: e.target.checked }))} /> 🏥</label>
                <label style={{ fontSize: 11 }}><input type="checkbox" checked={form.includes_financial ?? false} onChange={e => setForm(p => ({ ...p, includes_financial: e.target.checked }))} /> 💳</label>
              </td>
              <td><Inp placeholder="10M users" value={form.estimated_size ?? ''} onChange={e => setForm(p => ({ ...p, estimated_size: e.target.value || null }))} /></td>
              <td style={{ display: 'flex', gap: 4 }}>
                <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? <Spinner size={11} /> : <Check size={11} />}</button>
                <button className="btn btn-ghost btn-sm" onClick={() => setAdding(false)}><X size={11} /></button>
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {editing && !adding && <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => setAdding(true)}><Plus size={12} style={{ marginRight: 4 }} />Add segment</button>}
    </SectionCard>
  )
}

// ── Section: Third Parties ────────────────────────────────────────────────────
const ThirdPartySection: React.FC<SectionProps<ThirdParty[]>> = ({ data, isAdmin, onSaved, onInvalidate, addToast }) => {
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState<Partial<ThirdParty>>({ category: 'saas_vendor', tier: 'tier_2', assessment_status: 'not_assessed' })
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (!form.name) return
    setSaving(true)
    try {
      await profileApi.createThirdParty(form); onInvalidate(); setAdding(false); setForm({ category: 'saas_vendor', tier: 'tier_2', assessment_status: 'not_assessed' })
      addToast({ type: 'success', title: `Vendor "${form.name}" added` }); onSaved?.('')
    } catch { addToast({ type: 'error', title: 'Save failed' }) }
    finally { setSaving(false) }
  }

  const del = async (id: string) => {
    try { await profileApi.deleteThirdParty(id); onInvalidate() }
    catch { addToast({ type: 'error', title: 'Delete failed' }) }
  }

  return (
    <SectionCard id="third" title="Third-Party Dependencies" icon={<Shield size={13} />}
      editing={editing} onEdit={() => setEditing(true)} onCancel={() => { setEditing(false); setAdding(false) }} onSave={() => setEditing(false)}>
      <table className="table">
        <thead><tr><th>Vendor</th><th>Category</th><th>Tier</th><th>Assessment</th>{editing && <th></th>}</tr></thead>
        <tbody>
          {data.length === 0 && !adding && <tr><td colSpan={5}><EmptyRow text="No vendors configured" /></td></tr>}
          {data.map(t => (
            <tr key={t.id} style={{ borderLeft: t.tier === 'tier_1' ? '2px solid var(--red)' : t.tier === 'tier_2' ? '2px solid var(--amber)' : 'none' }}>
              <td style={{ fontSize: 12, fontWeight: 500 }}>{t.name}</td>
              <td style={{ fontSize: 11, color: 'var(--text2)' }}>{t.category.replace(/_/g, ' ')}</td>
              <td><Pill label={t.tier.replace('_', ' ')} color={TIER_COLORS[t.tier] ?? 'var(--text3)'} /></td>
              <td><Pill label={t.assessment_status.replace(/_/g, ' ')} color={ASSESS_COLORS[t.assessment_status] ?? 'var(--text3)'} /></td>
              {editing && <td><button className="btn btn-ghost btn-sm" onClick={() => del(t.id)}><Trash2 size={11} /></button></td>}
            </tr>
          ))}
          {adding && (
            <tr>
              <td><Inp placeholder="Vendor name" value={form.name ?? ''} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} /></td>
              <td><Sel opts={['cloud_infrastructure','payment_processor','data_processor','saas_vendor','outsourced_function','critical_supplier','regulatory_agent']} value={form.category ?? 'saas_vendor'} onChange={e => setForm(p => ({ ...p, category: e.target.value }))} /></td>
              <td><Sel opts={['tier_1','tier_2','tier_3']} value={form.tier ?? 'tier_2'} onChange={e => setForm(p => ({ ...p, tier: e.target.value }))} /></td>
              <td><Sel opts={['not_assessed','in_progress','passed','flagged']} value={form.assessment_status ?? 'not_assessed'} onChange={e => setForm(p => ({ ...p, assessment_status: e.target.value }))} /></td>
              <td style={{ display: 'flex', gap: 4 }}>
                <button className="btn btn-primary btn-sm" onClick={save} disabled={saving}>{saving ? <Spinner size={11} /> : <Check size={11} />}</button>
                <button className="btn btn-ghost btn-sm" onClick={() => setAdding(false)}><X size={11} /></button>
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {editing && !adding && <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} onClick={() => setAdding(true)}><Plus size={12} style={{ marginRight: 4 }} />Add vendor</button>}
    </SectionCard>
  )
}

// ── Section: Data & Tech ──────────────────────────────────────────────────────
const DataTechSection: React.FC<SectionProps<DataTech | null>> = ({ data, isAdmin, onSaved, onInvalidate, addToast }) => {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Partial<DataTech>>({})
  const [saving, setSaving] = useState(false)

  const startEdit = () => { setForm(data ?? {}); setEditing(true) }

  const save = async () => {
    setSaving(true)
    try {
      await profileApi.updateDataTech(form); onInvalidate(); setEditing(false)
      addToast({ type: 'success', title: 'Data & tech profile saved' }); onSaved?.('')
    } catch { addToast({ type: 'error', title: 'Save failed' }) }
    finally { setSaving(false) }
  }

  const boolField = (key: keyof DataTech, label: string) => (
    <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontSize: 12 }}>{label}</span>
      {editing
        ? <input type="checkbox" checked={(form[key] as boolean) ?? false} onChange={e => setForm(p => ({ ...p, [key]: e.target.checked }))} style={{ accentColor: 'var(--accent)', width: 16, height: 16 }} />
        : <span style={{ fontSize: 12, color: data?.[key] ? 'var(--teal2)' : 'var(--text3)' }}>{data?.[key] ? 'Yes' : 'No'}</span>
      }
    </div>
  )

  return (
    <SectionCard id="datatech" title="Data & Technology Profile" icon={<Server size={13} />}
      editing={editing} onEdit={startEdit} onCancel={() => setEditing(false)} onSave={save} saving={saving}>
      <div className="grid-2">
        <div>
          {boolField('uses_ai_ml', 'Uses AI / ML')}
          {boolField('handles_personal_data', 'Handles personal data')}
          {boolField('handles_sensitive_personal_data', 'Handles sensitive personal data')}
          {boolField('handles_payment_data', 'Handles payment data')}
          {boolField('handles_health_data', 'Handles health data')}
          {boolField('handles_classified_data', 'Handles classified data')}
        </div>
        <div>
          <Field label="Cloud providers">
            {editing
              ? <div>{['AWS','GCP','Azure','OCI','On-prem','Other'].map(c => (
                  <label key={c} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginRight: 10, marginBottom: 6, fontSize: 12 }}>
                    <input type="checkbox" checked={(form.cloud_providers ?? []).includes(c)} style={{ accentColor: 'var(--accent)' }}
                      onChange={e => setForm(p => ({ ...p, cloud_providers: e.target.checked ? [...(p.cloud_providers ?? []), c] : (p.cloud_providers ?? []).filter(x => x !== c) }))} />
                    {c}
                  </label>
                ))}</div>
              : <div>{(data?.cloud_providers ?? []).map(c => <Pill key={c} label={c} color="var(--blue)" />)}</div>
            }
          </Field>
          {(data?.uses_ai_ml || form.uses_ai_ml) && (
            <Field label="AI use cases">
              {editing
                ? <textarea className="input" rows={2} style={{ width: '100%', fontSize: 12, padding: '5px 8px' }}
                    placeholder="One per line"
                    value={(form.ai_use_cases ?? []).join('\n')}
                    onChange={e => setForm(p => ({ ...p, ai_use_cases: e.target.value.split('\n').filter(Boolean) }))} />
                : <div>{(data?.ai_use_cases ?? []).map(c => <Pill key={c} label={c} color="var(--amber)" />)}</div>
              }
            </Field>
          )}
          <Field label="Core tech stack">
            {editing
              ? <Inp placeholder="React, FastAPI, PostgreSQL…" value={(form.core_tech_stack ?? []).join(', ')}
                  onChange={e => setForm(p => ({ ...p, core_tech_stack: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))} />
              : <div>{(data?.core_tech_stack ?? []).map(t => <Pill key={t} label={t} color="var(--teal2)" />)}</div>
            }
          </Field>
        </div>
      </div>
    </SectionCard>
  )
}

// ── Section: Change Log ───────────────────────────────────────────────────────
const ChangeLogSection: React.FC = () => {
  const [page, setPage] = useState(1)
  const { data, isLoading } = useQuery({ queryKey: ['profile-changelog', page], queryFn: () => profileApi.getChangeLog(page) })
  const PROP_COLORS: Record<string, string> = { confirmed: 'var(--teal2)', rejected: 'var(--red)', partial: 'var(--amber)', pending: 'var(--amber)' }

  return (
    <div id="changelog" className="card" style={{ marginBottom: 14, scrollMarginTop: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
        <span style={{ color: 'var(--text2)' }}><History size={13} /></span>
        <span style={{ fontSize: 12, fontWeight: 500 }}>Change History</span>
      </div>
      <div style={{ padding: 16 }}>
        {isLoading ? <Spinner size={16} /> : (
          <>
            <table className="table">
              <thead><tr><th>Date</th><th>Section</th><th>Summary</th><th>Propagation</th></tr></thead>
              <tbody>
                {(data?.items ?? []).length === 0 && <tr><td colSpan={4}><EmptyRow text="No changes recorded yet" /></td></tr>}
                {(data?.items ?? []).map(e => (
                  <tr key={e.id}>
                    <td style={{ fontSize: 11, color: 'var(--text2)', whiteSpace: 'nowrap' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Clock size={10} />{new Date(e.changed_at).toLocaleDateString()}</div>
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--text3)' }}>{e.entity_type.replace(/([A-Z])/g, ' $1').trim()}</td>
                    <td style={{ fontSize: 12 }}>{e.change_summary}</td>
                    <td><Pill label={e.propagation_status} color={PROP_COLORS[e.propagation_status] ?? 'var(--text3)'} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {(data?.total ?? 0) > (data?.page_size ?? 20) && (
              <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
                <button className="btn btn-ghost btn-sm" disabled={(data?.items.length ?? 0) < (data?.page_size ?? 20)} onClick={() => setPage(p => p + 1)}>Next →</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ── Shared prop type ──────────────────────────────────────────────────────────
interface SectionProps<T> {
  data: T; isAdmin: boolean
  onSaved: (changeLogId: string) => void
  onInvalidate: () => void
  addToast: (t: { type: 'success' | 'error' | 'info' | 'warning'; title: string; body?: string }) => void
  onDisputed?: (d: DisputedField) => void
}
