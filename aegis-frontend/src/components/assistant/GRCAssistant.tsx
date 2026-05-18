/**
 * GRCAssistant — collapsible right-rail panel that renders the GRC Assistant
 * chat UI. Consumes AssistantProvider context. Rendered once in Layout.
 *
 * Keyboard: Cmd+K / Ctrl+K toggles the panel.
 */
import React, { useEffect, useRef, useState, useCallback } from 'react'
import { Bot, X, RotateCcw, Send } from 'lucide-react'
import { Spinner, LiveDot } from '@/components/ui'
import { useAssistant } from './AssistantProvider'
import { ChangeCard } from './ChangeCard'
import type { AssistantMessage, AssistantChangeProposal } from '@/types'

const PANEL_WIDTH = 360

export const GRCAssistant: React.FC = () => {
  const {
    isOpen, toggleOpen,
    messages, proposals,
    sendMessage, resetSession,
    applyChange, rejectChange,
    isConnected, isThinking,
  } = useAssistant()

  const [draft, setDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Keyboard shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        toggleOpen()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [toggleOpen])

  // Scroll to bottom on new message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, proposals])

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) setTimeout(() => inputRef.current?.focus(), 80)
  }, [isOpen])

  const submit = useCallback(() => {
    const text = draft.trim()
    if (!text || !isConnected) return
    sendMessage(text)
    setDraft('')
  }, [draft, isConnected, sendMessage])

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  // Build a unified timeline (messages + pending proposal cards interleaved)
  const proposalsByChangeId = Object.fromEntries(proposals.map(p => [p.change_id, p]))

  return (
    <>
      {/* Toggle button — always visible */}
      <button
        data-testid="assistant-toggle"
        onClick={toggleOpen}
        title="GRC Assistant (⌘K)"
        style={{
          position: 'fixed', bottom: 20, right: isOpen ? PANEL_WIDTH + 12 : 20,
          width: 40, height: 40, borderRadius: '50%', zIndex: 300,
          background: isConnected ? 'var(--accent)' : 'var(--bg3)',
          border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 2px 12px rgba(0,0,0,.4)', transition: 'right .2s ease',
          color: 'white',
        }}
      >
        <Bot size={18} />
      </button>

      {/* Panel */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: PANEL_WIDTH, zIndex: 250,
        background: 'var(--bg1)', borderLeft: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        transform: isOpen ? 'translateX(0)' : `translateX(${PANEL_WIDTH}px)`,
        transition: 'transform .2s ease',
      }}>
        {/* Header */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <Bot size={14} style={{ color: 'var(--accent2)' }} />
          <span style={{ fontSize: 13, fontWeight: 500, flex: 1 }}>GRC Assistant</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            {isConnected
              ? <><LiveDot /><span style={{ fontSize: 10, color: 'var(--text3)' }}>connected</span></>
              : <span style={{ fontSize: 10, color: 'var(--text3)' }}>connecting…</span>
            }
          </div>
          <button className="btn btn-ghost btn-sm" onClick={resetSession} title="New session" style={{ padding: '3px 6px' }}>
            <RotateCcw size={12} />
          </button>
          <button className="btn btn-ghost btn-sm" onClick={toggleOpen} style={{ padding: '3px 6px' }}>
            <X size={12} />
          </button>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {messages.length === 0 && (
            <div style={{ color: 'var(--text3)', fontSize: 12, textAlign: 'center', marginTop: 40, lineHeight: 1.6 }}>
              Ask me anything about your company profile, risks, or controls.
              <br />
              <span style={{ fontSize: 10 }}>I can propose changes — you approve before anything saves.</span>
            </div>
          )}

          {messages.map((msg, i) => {
            const nextMsg = messages[i + 1]
            const proposalAfter = !nextMsg && proposals.filter(p => p.status === 'pending_approval')

            return (
              <React.Fragment key={i}>
                <MessageBubble message={msg} />
                {/* Show pending proposals after the last assistant message */}
                {msg.role === 'assistant' && Array.isArray(proposalAfter) && proposalAfter.length > 0 && (proposalAfter as AssistantChangeProposal[]).map(p => (
                  <ChangeCard
                    key={p.change_id}
                    proposal={p}
                    onApprove={() => applyChange(p.change_id)}
                    onReject={() => rejectChange(p.change_id)}
                  />
                ))}
              </React.Fragment>
            )
          })}

          {isThinking && <ThinkingIndicator />}
          <div ref={bottomRef} />
        </div>

        {/* Session reset banner — always shown per PRD §3.5.6 */}
        <div
          data-testid="assistant-session-banner"
          style={{ padding: '4px 14px', fontSize: 9, color: 'var(--text3)', borderTop: '1px solid var(--border)', textAlign: 'center' }}
        >
          Conversations reset between sessions. I won't remember our previous chats.
        </div>

        {/* Input */}
        <div style={{ padding: '10px 12px', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end' }}>
            <textarea
              ref={inputRef}
              data-testid="assistant-input"
              rows={2}
              className="input"
              style={{ flex: 1, resize: 'none', fontSize: 12, padding: '6px 9px', lineHeight: 1.4 }}
              placeholder={isConnected ? 'Ask or instruct… (Enter to send)' : 'Connecting…'}
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              disabled={!isConnected}
            />
            <button
              data-testid="assistant-send"
              className="btn btn-primary btn-sm"
              onClick={submit}
              disabled={!draft.trim() || !isConnected}
              style={{ alignSelf: 'flex-end', padding: '6px 10px' }}
            >
              <Send size={12} />
            </button>
          </div>
          <div style={{ fontSize: 9, color: 'var(--text3)', marginTop: 4 }}>
            ⌘K to toggle · Enter to send · Shift+Enter for new line
          </div>
        </div>
      </div>
    </>
  )
}

const MessageBubble: React.FC<{ message: AssistantMessage }> = ({ message }) => {
  const isUser = message.role === 'user'
  return (
    <div data-testid={`assistant-message-${message.role}`} style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
      <div style={{
        maxWidth: '85%', padding: '7px 10px', borderRadius: isUser ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
        background: isUser ? 'var(--accent)' : 'var(--bg2)',
        border: isUser ? 'none' : '1px solid var(--border)',
        fontSize: 12, lineHeight: 1.5, color: isUser ? 'white' : 'var(--text)',
        whiteSpace: 'pre-wrap', wordBreak: 'break-word',
      }}>
        {message.content}
        <div style={{ fontSize: 9, color: isUser ? 'rgba(255,255,255,.5)' : 'var(--text3)', marginTop: 3, textAlign: 'right' }}>
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  )
}

const ThinkingIndicator: React.FC = () => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
    <Spinner size={12} />
    <span style={{ fontSize: 11, color: 'var(--text3)' }}>Thinking…</span>
  </div>
)
