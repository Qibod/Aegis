import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/store'
import { Layout } from '@/components/layout/Layout'
import { LoginPage, RegisterPage } from '@/pages/Auth'
import { DashboardPage } from '@/pages/Dashboard'
import { RisksPage } from '@/pages/Risks'
import { CanvasPage } from '@/pages/Canvas'
import { RadarPage, PulsePage, AuditPage, ControlsPage, SettingsPage } from '@/pages/Other'
import { OnboardingPage } from '@/pages/Onboarding'
import { TimeMachinePage } from '@/pages/TimeMachine'
import { RegulatoryAgentPage } from '@/pages/RegulatoryAgent'
import { AuditReportPage } from '@/pages/AuditReport'
import { TerrainPage } from '@/pages/Terrain'
import { AuditCopilotPage } from '@/pages/AuditCopilot'
import { CompanyProfilePage } from '@/pages/CompanyProfile'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

// Protected route wrapper — also guards incomplete onboarding
const Protected: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, org } = useAuthStore()
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (org && !org.onboarding_complete) return <Navigate to="/onboarding" replace />
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/login"      element={<LoginPage />} />
          <Route path="/register"   element={<RegisterPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />

          {/* Protected */}
          <Route path="/" element={<Protected><DashboardPage /></Protected>} />
          <Route path="/radar"    element={<Protected><RadarPage /></Protected>} />
          <Route path="/risks"    element={<Protected><RisksPage /></Protected>} />
          <Route path="/controls" element={<Protected><ControlsPage /></Protected>} />
          <Route path="/canvas"   element={<Protected><CanvasPage /></Protected>} />
          <Route path="/audit"    element={<Protected><AuditPage /></Protected>} />
          <Route path="/pulse"    element={<Protected><PulsePage /></Protected>} />
          <Route path="/settings"     element={<Protected><SettingsPage /></Protected>} />
          <Route path="/time-machine"  element={<Protected><TimeMachinePage /></Protected>} />
          <Route path="/regulatory"    element={<Protected><RegulatoryAgentPage /></Protected>} />
          <Route path="/audit/reports/:reportId" element={<Protected><AuditReportPage /></Protected>} />
          <Route path="/terrain" element={<Protected><TerrainPage /></Protected>} />
          <Route path="/audit-copilot"     element={<Protected><AuditCopilotPage /></Protected>} />
          <Route path="/company-profile"  element={<Protected><CompanyProfilePage /></Protected>} />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
