import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { authApi, orgsApi } from '@/api/client'
import { useAuthStore, useUIStore } from '@/store'
import { Button, Input, Spinner } from '@/components/ui'

// ── Login ─────────────────────────────────────────────────────────────────────
export const LoginPage: React.FC = () => {
  const navigate = useNavigate()
  const { setTokens, setUser, setOrg } = useAuthStore()
  const { addToast } = useUIStore()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Forgot-password state
  const [showForgot, setShowForgot] = useState(false)
  const [fpEmail, setFpEmail] = useState('')
  const [fpToken, setFpToken] = useState('')
  const [fpNewPwd, setFpNewPwd] = useState('')
  const [fpLoading, setFpLoading] = useState(false)
  const [fpError, setFpError] = useState('')
  const [fpDone, setFpDone] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const tokens = await authApi.login({ email, password })
      setTokens(tokens.access_token, tokens.refresh_token)
      const [user, org] = await Promise.all([authApi.me(), orgsApi.me()])
      setUser(user)
      setOrg(org)
      addToast({ type: 'success', title: 'Welcome back', body: `Signed in as ${user.full_name}` })
      navigate(org.onboarding_complete ? '/' : '/onboarding')
    } catch {
      setError('Incorrect email or password')
    } finally {
      setLoading(false)
    }
  }

  const handleGetToken = async (e: React.FormEvent) => {
    e.preventDefault()
    setFpLoading(true)
    setFpError('')
    try {
      const res = await authApi.forgotPassword(fpEmail)
      setFpToken(res.token)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setFpError(msg ?? 'Email not found')
    } finally {
      setFpLoading(false)
    }
  }

  const handleResetPwd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (fpNewPwd.length < 8) { setFpError('Password must be at least 8 characters'); return }
    setFpLoading(true)
    setFpError('')
    try {
      await authApi.resetPassword(fpToken, fpNewPwd)
      setFpDone(true)
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setFpError(msg ?? 'Reset failed — token may have expired')
    } finally {
      setFpLoading(false)
    }
  }

  return (
    <div style={authShell}>
      <div style={authCard}>
        <div style={logoWrap}>
          <div style={logoMark}>
            <svg viewBox="0 0 14 14" fill="none" width="16" height="16">
              <path d="M7 1.5L12 4v6L7 12.5 2 10V4L7 1.5z" stroke="white" strokeWidth="1.3" strokeLinejoin="round"/>
              <circle cx="7" cy="7" r="2" fill="white"/>
            </svg>
          </div>
          <span style={{ fontSize: 18, fontWeight: 500, letterSpacing: -0.3 }}>Aegis</span>
        </div>

        {!showForgot ? (
          <>
            <h1 style={{ fontSize: 22, fontWeight: 300, letterSpacing: -0.4, marginBottom: 6 }}>Sign in</h1>
            <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 28 }}>Intelligent GRC Platform</p>
            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <Input label="Email" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" required />
              <Input label="Password" type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" required />
              {error && <p style={{ fontSize: 12, color: 'var(--red)', marginTop: -6 }}>{error}</p>}
              <Button variant="primary" size="md" type="submit" loading={loading} style={{ width: '100%', marginTop: 4 }}>
                Sign in →
              </Button>
            </form>
            <p style={{ fontSize: 12, color: 'var(--text3)', textAlign: 'center', marginTop: 16 }}>
              <button
                onClick={() => { setShowForgot(true); setFpEmail(email) }}
                style={{ background: 'none', border: 'none', color: 'var(--accent2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}
              >
                Forgot password?
              </button>
            </p>
            <p style={{ fontSize: 12, color: 'var(--text3)', textAlign: 'center', marginTop: 8 }}>
              No account?{' '}
              <Link to="/register" style={{ color: 'var(--accent2)', textDecoration: 'none' }}>Create one</Link>
            </p>
          </>
        ) : fpDone ? (
          <>
            <h1 style={{ fontSize: 20, fontWeight: 300, letterSpacing: -0.4, marginBottom: 8 }}>Password reset</h1>
            <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 24 }}>Your password has been updated. You can now sign in.</p>
            <Button variant="primary" size="md" style={{ width: '100%' }} onClick={() => { setShowForgot(false); setFpDone(false); setFpToken(''); setFpNewPwd('') }}>
              Back to sign in →
            </Button>
          </>
        ) : (
          <>
            <h1 style={{ fontSize: 20, fontWeight: 300, letterSpacing: -0.4, marginBottom: 6 }}>Reset password</h1>
            <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 24 }}>
              Enter your email to get a reset token, then set a new password.
            </p>

            <form onSubmit={handleGetToken} style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
              <Input label="Email" type="email" value={fpEmail} onChange={e => setFpEmail(e.target.value)} placeholder="you@company.com" required />
              <Button variant="primary" size="md" type="submit" loading={fpLoading && !fpToken} style={{ width: '100%' }}>
                Get reset token
              </Button>
            </form>

            {fpToken && (
              <>
                <div style={{ background: 'var(--bg2)', border: '1px solid var(--border2)', borderRadius: 8, padding: '10px 14px', marginBottom: 16 }}>
                  <p style={{ fontSize: 11, color: 'var(--text2)', marginBottom: 6 }}>Your reset token (expires in 30 min):</p>
                  <code style={{ fontSize: 13, color: 'var(--accent2)', wordBreak: 'break-all', fontFamily: 'monospace' }}>{fpToken}</code>
                </div>
                <form onSubmit={handleResetPwd} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <Input label="Reset token" value={fpToken} onChange={e => setFpToken(e.target.value)} required />
                  <Input label="New password" type="password" value={fpNewPwd} onChange={e => setFpNewPwd(e.target.value)} placeholder="Min 8 characters" required />
                  {fpError && <p style={{ fontSize: 12, color: 'var(--red)', marginTop: -4 }}>{fpError}</p>}
                  <Button variant="primary" size="md" type="submit" loading={fpLoading} style={{ width: '100%' }}>
                    Set new password →
                  </Button>
                </form>
              </>
            )}

            {fpError && !fpToken && <p style={{ fontSize: 12, color: 'var(--red)', marginTop: -8 }}>{fpError}</p>}

            <p style={{ fontSize: 12, color: 'var(--text3)', textAlign: 'center', marginTop: 20 }}>
              <button
                onClick={() => setShowForgot(false)}
                style={{ background: 'none', border: 'none', color: 'var(--accent2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}
              >
                ← Back to sign in
              </button>
            </p>
          </>
        )}
      </div>
    </div>
  )
}

// ── Register ──────────────────────────────────────────────────────────────────
export const RegisterPage: React.FC = () => {
  const navigate = useNavigate()
  const { setTokens, setUser, setOrg } = useAuthStore()
  const { addToast } = useUIStore()
  const [form, setForm] = useState({ email: '', full_name: '', password: '', org_name: '', role: 'head_of_audit' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await authApi.register({ email: form.email, full_name: form.full_name, password: form.password, role: form.role }, form.org_name)
      const tokens = await authApi.login({ email: form.email, password: form.password })
      setTokens(tokens.access_token, tokens.refresh_token)
      const [user, org] = await Promise.all([authApi.me(), orgsApi.me()])
      setUser(user)
      setOrg(org)
      addToast({ type: 'success', title: 'Account created', body: 'Your GRC environment is ready.' })
      navigate('/onboarding')
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={authShell}>
      <div style={authCard}>
        <div style={logoWrap}>
          <div style={logoMark}>
            <svg viewBox="0 0 14 14" fill="none" width="16" height="16">
              <path d="M7 1.5L12 4v6L7 12.5 2 10V4L7 1.5z" stroke="white" strokeWidth="1.3" strokeLinejoin="round"/>
              <circle cx="7" cy="7" r="2" fill="white"/>
            </svg>
          </div>
          <span style={{ fontSize: 18, fontWeight: 500, letterSpacing: -0.3 }}>Aegis</span>
        </div>
        <h1 style={{ fontSize: 22, fontWeight: 300, letterSpacing: -0.4, marginBottom: 6 }}>Create account</h1>
        <p style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 28 }}>Set up your GRC environment</p>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Input label="Organisation name" value={form.org_name} onChange={set('org_name')} placeholder="Uber Technologies, Inc." required />
          <Input label="Your name" value={form.full_name} onChange={set('full_name')} placeholder="Vijay Rao" required />
          <Input label="Email" type="email" value={form.email} onChange={set('email')} placeholder="vijay@uber.com" required />
          <Input label="Password" type="password" value={form.password} onChange={set('password')} placeholder="••••••••" required />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <label style={{ fontSize: 11, fontWeight: 500, color: 'var(--text2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Role</label>
            <select className="input" value={form.role} onChange={set('role')}>
              <option value="head_of_audit">Head of Audit</option>
              <option value="auditor">Auditor</option>
              <option value="org_admin">Org Admin</option>
              <option value="control_owner">Control Owner</option>
            </select>
          </div>
          {error && <p style={{ fontSize: 12, color: 'var(--red)', marginTop: -6 }}>{error}</p>}
          <Button variant="primary" size="md" type="submit" loading={loading} style={{ width: '100%', marginTop: 4 }}>
            Create account →
          </Button>
        </form>
        <p style={{ fontSize: 12, color: 'var(--text3)', textAlign: 'center', marginTop: 20 }}>
          Already have an account?{' '}
          <Link to="/login" style={{ color: 'var(--accent2)', textDecoration: 'none' }}>Sign in</Link>
        </p>
      </div>
    </div>
  )
}

// ── Shared styles ─────────────────────────────────────────────────────────────
const authShell: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  minHeight: '100vh', background: 'var(--bg)',
  padding: 24,
}

const authCard: React.CSSProperties = {
  background: 'var(--bg1)', border: '1px solid var(--border2)',
  borderRadius: 16, padding: '36px 32px',
  width: '100%', maxWidth: 400,
  animation: 'fadeIn 0.3s ease',
}

const logoWrap: React.CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8,
  marginBottom: 28, color: 'var(--text)',
}

const logoMark: React.CSSProperties = {
  width: 30, height: 30, borderRadius: 8,
  background: 'var(--accent)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
}
