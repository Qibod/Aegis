import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User, Organization } from '@/types'

interface AuthState {
  user: User | null
  org: Organization | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  setTokens: (access: string, refresh: string) => void
  setUser: (user: User) => void
  setOrg: (org: Organization) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      org: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,

      setTokens: (access, refresh) => {
        localStorage.setItem('access_token', access)
        localStorage.setItem('refresh_token', refresh)
        set({ accessToken: access, refreshToken: refresh, isAuthenticated: true })
      },

      setUser: (user) => set({ user }),

      setOrg: (org) => set({ org }),

      logout: () => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        set({ user: null, org: null, accessToken: null, refreshToken: null, isAuthenticated: false })
      },
    }),
    {
      name: 'aegis-auth',
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
        user: state.user,
        org: state.org,
      }),
    }
  )
)

// ── UI store ──────────────────────────────────────────────────────────────────
interface UIState {
  sidebarCollapsed: boolean
  activeNav: string
  toasts: Toast[]
  setSidebarCollapsed: (v: boolean) => void
  setActiveNav: (v: string) => void
  addToast: (toast: Omit<Toast, 'id'>) => void
  removeToast: (id: string) => void
}

export interface Toast {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  title: string
  body?: string
}

export const useUIStore = create<UIState>((set) => ({
  sidebarCollapsed: false,
  activeNav: 'dashboard',
  toasts: [],

  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  setActiveNav: (v) => set({ activeNav: v }),

  addToast: (toast) => {
    const id = Math.random().toString(36).slice(2)
    set(s => ({ toasts: [...s.toasts, { ...toast, id }] }))
    setTimeout(() => {
      set(s => ({ toasts: s.toasts.filter(t => t.id !== id) }))
    }, 5000)
  },

  removeToast: (id) => set(s => ({ toasts: s.toasts.filter(t => t.id !== id) })),
}))
