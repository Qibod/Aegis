/**
 * AssistantProvider — manages the GRC Assistant WebSocket connection and
 * shared session state. Wrap the app (or Layout) with this to give all
 * descendant components access via useAssistant().
 *
 * Session semantics: one session per browser tab. The session ID is generated
 * here and sent with the auth message. The backend resets history on each
 * new connection (no cross-session memory).
 */
import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { createAssistantWS } from '@/api/client'
import { useAuthStore } from '@/store'
import type { AssistantMessage, AssistantChangeProposal } from '@/types'

interface AssistantCtx {
  isOpen: boolean
  toggleOpen: () => void
  messages: AssistantMessage[]
  proposals: AssistantChangeProposal[]
  sendMessage: (text: string) => void
  resetSession: () => void
  applyChange: (changeId: string) => void
  rejectChange: (changeId: string) => void
  isConnected: boolean
  isThinking: boolean
}

const Ctx = createContext<AssistantCtx | null>(null)

export function useAssistant(): AssistantCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAssistant must be used inside AssistantProvider')
  return ctx
}

export const AssistantProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { accessToken: token } = useAuthStore()

  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<AssistantMessage[]>([])
  const [proposals, setProposals] = useState<AssistantChangeProposal[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [isThinking, setIsThinking] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const tokenRef = useRef(token)
  tokenRef.current = token

  const connect = useCallback(() => {
    if (!tokenRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = createAssistantWS()
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'auth', token: tokenRef.current }))
    }

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.type === 'session_start') {
          setIsConnected(true)
          if (msg.reset_banner) {
            setMessages([{ role: 'assistant', content: msg.reset_banner, timestamp: new Date().toISOString() }])
          }
        } else if (msg.type === 'assistant_message') {
          setIsThinking(false)
          setMessages(prev => [...prev, { role: 'assistant', content: msg.content, timestamp: new Date().toISOString() }])
        } else if (msg.type === 'change_proposal') {
          setProposals(prev => [...prev, {
            change_id: msg.change_id,
            entity_type: msg.entity_type,
            field_name: msg.field_name,
            current_value: msg.current_value,
            proposed_value: msg.proposed_value,
            rationale: msg.rationale,
            status: 'pending_approval',
          }])
        } else if (msg.type === 'tool_result') {
          // intermediate tool result, keep thinking
        } else if (msg.type === 'error') {
          setIsThinking(false)
          setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${msg.detail}`, timestamp: new Date().toISOString() }])
        }
      } catch { /* ignore malformed frames */ }
    }

    ws.onerror = () => setIsConnected(false)
    ws.onclose = () => {
      setIsConnected(false)
      // attempt reconnect after 5s if token still valid
      setTimeout(() => { if (tokenRef.current) connect() }, 5000)
    }
  }, [])

  useEffect(() => {
    if (token) connect()
    return () => { wsRef.current?.close() }
  }, [token, connect])

  const sendMessage = useCallback((text: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    const msg: AssistantMessage = { role: 'user', content: text, timestamp: new Date().toISOString() }
    setMessages(prev => [...prev, msg])
    setIsThinking(true)
    wsRef.current.send(JSON.stringify({ type: 'message', content: text }))
  }, [])

  const resetSession = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({ type: 'new_session' }))
    setMessages([])
    setProposals([])
  }, [])

  const applyChange = useCallback((changeId: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({ type: 'apply_change', change_id: changeId }))
    setProposals(prev => prev.map(p => p.change_id === changeId ? { ...p, status: 'approved' } : p))
  }, [])

  const rejectChange = useCallback((changeId: string) => {
    setProposals(prev => prev.map(p => p.change_id === changeId ? { ...p, status: 'rejected' } : p))
  }, [])

  return (
    <Ctx.Provider value={{
      isOpen, toggleOpen: () => setIsOpen(o => !o),
      messages, proposals,
      sendMessage, resetSession,
      applyChange, rejectChange,
      isConnected, isThinking,
    }}>
      {children}
    </Ctx.Provider>
  )
}
