import React, { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, AlertTriangle, Shield, GitBranch,
  Calendar, Radio, Activity, Settings, LogOut, Clock, BookOpen, Layers, Bot,
  Sun, Moon, Building2, KeyRound,
} from 'lucide-react'
import { useAuthStore, useUIStore } from '@/store'
import { Avatar, LiveDot } from '@/components/ui'
import { authApi } from '@/api/client'
import styles from './Layout.module.css'
import { AssistantProvider } from '@/components/assistant/AssistantProvider'
import { GRCAssistant } from '@/components/assistant/GRCAssistant'

// ── Theme helpers ─────────────────────────────────────────────────────────────
function getInitialTheme(): 'dark' | 'light' {
  return (localStorage.getItem('aegis-theme') as 'dark' | 'light') ?? 'dark'
}
function applyTheme(theme: 'dark' | 'light') {
  if (theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light')
  } else {
    document.documentElement.removeAttribute('data-theme')
  }
  localStorage.setItem('aegis-theme', theme)
}

interface NavItem {
  id: string
  label: string
  icon: React.ReactNode
  path: string
  badge?: string
  badgeVariant?: 'red' | 'blue'
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard',  label: 'Dashboard',      icon: <LayoutDashboard size={15} />, path: '/' },
  { id: 'company-profile', label: 'Company Profile', icon: <Building2 size={15} />, path: '/company-profile' },
  { id: 'radar',      label: 'Risk Radar',      icon: <Radio size={15} />,           path: '/radar',   badge: 'Live', badgeVariant: 'blue' },
  { id: 'risks',      label: 'Risk Universe',   icon: <AlertTriangle size={15} />,   path: '/risks' },
  { id: 'terrain',    label: 'Risk Terrain',    icon: <Layers size={15} />,          path: '/terrain', badge: 'New', badgeVariant: 'blue' },
  { id: 'controls',   label: 'Controls',        icon: <Shield size={15} />,          path: '/controls' },
  { id: 'canvas',     label: 'Control Canvas',  icon: <GitBranch size={15} />,       path: '/canvas' },
  { id: 'audit',      label: 'Audit Planner',   icon: <Calendar size={15} />,        path: '/audit' },
  { id: 'audit-copilot', label: 'AI Co-Auditor', icon: <Bot size={15} />,            path: '/audit-copilot', badge: 'Live', badgeVariant: 'blue' },
  { id: 'pulse',        label: 'Control Pulse',   icon: <Activity size={15} />,  path: '/pulse' },
  { id: 'time-machine', label: 'Time Machine',      icon: <Clock size={15} />,     path: '/time-machine', badge: 'New', badgeVariant: 'blue' },
  { id: 'regulatory',   label: 'Reg Change Agent',  icon: <BookOpen size={15} />,  path: '/regulatory',   badge: 'Live', badgeVariant: 'blue' },
]

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  const { toasts, removeToast, addToast } = useUIStore()

  const [theme, setTheme] = useState<'dark' | 'light'>(getInitialTheme)
  const [showChangePwd, setShowChangePwd] = useState(false)
  const [pwdForm, setPwdForm] = useState({ current: '', next: '', confirm: '' })
  const [pwdError, setPwdError] = useState('')
  const [pwdLoading, setPwdLoading] = useState(false)

  useEffect(() => { applyTheme(theme) }, [theme])

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const openChangePwd = () => {
    setPwdForm({ current: '', next: '', confirm: '' })
    setPwdError('')
    setShowChangePwd(true)
  }

  const handleChangePwd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (pwdForm.next !== pwdForm.confirm) {
      setPwdError('New passwords do not match')
      return
    }
    if (pwdForm.next.length < 8) {
      setPwdError('New password must be at least 8 characters')
      return
    }
    setPwdLoading(true)
    setPwdError('')
    try {
      await authApi.changePassword(pwdForm.current, pwdForm.next)
      setShowChangePwd(false)
      addToast({ type: 'success', title: 'Password changed successfully' })
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setPwdError(msg ?? 'Failed to change password')
    } finally {
      setPwdLoading(false)
    }
  }

  return (
    <AssistantProvider>
    <div className={styles.shell}>
      {/* Topbar */}
      <header className={styles.topbar}>
        <div className={styles.logo}>
          <div className={styles.logoMark}>
            <svg viewBox="0 0 14 14" fill="none" width="14" height="14">
              <path d="M7 1.5L12 4v6L7 12.5 2 10V4L7 1.5z" stroke="white" strokeWidth="1.3" strokeLinejoin="round" />
              <circle cx="7" cy="7" r="2" fill="white" />
            </svg>
          </div>
          <span>Aegis</span>
        </div>

        <div className={styles.companyPill}>
          <div className={styles.companyDot} />
          <span>{user?.full_name?.split(' ')[0] ?? 'My'} · GRC Platform</span>
        </div>

        <div className={styles.topbarRight}>
          <div className={styles.liveBadge}>
            <LiveDot />
            <span>Live</span>
          </div>
          <button
            onClick={toggleTheme}
            className={styles.themeToggle}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>
          <Avatar initials={user?.initials} color={user?.avatar_color} size={28} />
        </div>
      </header>

      <div className={styles.body}>
        {/* Sidebar */}
        <nav className={styles.sidebar}>
          <div className={styles.navSection}>
            {NAV_ITEMS.map(item => {
              const active = location.pathname === item.path ||
                (item.path !== '/' && location.pathname.startsWith(item.path))
              return (
                <button
                  key={item.id}
                  className={`${styles.navItem} ${active ? styles.navItemActive : ''}`}
                  onClick={() => navigate(item.path)}
                >
                  <span className={styles.navIcon}>{item.icon}</span>
                  <span className={styles.navLabel}>{item.label}</span>
                  {item.badge && (
                    <span className={`${styles.navBadge} ${item.badgeVariant === 'blue' ? styles.navBadgeBlue : ''}`}>
                      {item.badge}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          <div className={styles.sidebarBottom}>
            <div className={styles.sidebarDivider} />
            <button className={styles.navItem} onClick={() => navigate('/settings')}>
              <span className={styles.navIcon}><Settings size={15} /></span>
              <span className={styles.navLabel}>Settings</span>
            </button>
            <button className={styles.navItem} onClick={openChangePwd}>
              <span className={styles.navIcon}><KeyRound size={15} /></span>
              <span className={styles.navLabel}>Change password</span>
            </button>
            <button className={styles.navItem} onClick={handleLogout}>
              <span className={styles.navIcon}><LogOut size={15} /></span>
              <span className={styles.navLabel}>Sign out</span>
            </button>
          </div>
        </nav>

        {/* Main */}
        <main className={styles.main}>
          {children}
        </main>
      </div>

      {/* Change Password Modal */}
      {showChangePwd && (
        <div className={styles.modalOverlay} onClick={() => setShowChangePwd(false)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <span>Change password</span>
              <button className={styles.modalClose} onClick={() => setShowChangePwd(false)}>×</button>
            </div>
            <form onSubmit={handleChangePwd} className={styles.modalBody}>
              <label className={styles.fieldLabel}>Current password</label>
              <input
                type="password"
                className={styles.field}
                value={pwdForm.current}
                onChange={e => setPwdForm(f => ({ ...f, current: e.target.value }))}
                required
                autoFocus
              />
              <label className={styles.fieldLabel}>New password</label>
              <input
                type="password"
                className={styles.field}
                value={pwdForm.next}
                onChange={e => setPwdForm(f => ({ ...f, next: e.target.value }))}
                required
              />
              <label className={styles.fieldLabel}>Confirm new password</label>
              <input
                type="password"
                className={styles.field}
                value={pwdForm.confirm}
                onChange={e => setPwdForm(f => ({ ...f, confirm: e.target.value }))}
                required
              />
              {pwdError && <div className={styles.fieldError}>{pwdError}</div>}
              <button type="submit" className={styles.submitBtn} disabled={pwdLoading}>
                {pwdLoading ? 'Saving…' : 'Update password'}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Toast stack */}
      <div className={styles.toastStack}>
        {toasts.map(toast => (
          <div key={toast.id} className={styles.toast}>
            <div className={`${styles.toastDot} ${styles[`toastDot-${toast.type}`]}`} />
            <div style={{ flex: 1 }}>
              <div className={styles.toastTitle}>{toast.title}</div>
              {toast.body && <div className={styles.toastBody}>{toast.body}</div>}
            </div>
            <button className={styles.toastClose} onClick={() => removeToast(toast.id)}>×</button>
          </div>
        ))}
      </div>

      <GRCAssistant />
    </div>
    </AssistantProvider>
  )
}
