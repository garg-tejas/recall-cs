import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createConversation,
  deleteConversation,
  getConversation,
  getConversations,
  tutorChatStream,
} from '../api/tutor'
import type {
  ChatMessageOut,
  ConversationOut,
  CreateConversationRequest,
} from '../api/types'
import Button from '../components/ui/Button'
import StateMessage from '../components/ui/StateMessage'
import { usePageTitle } from '../hooks/usePageTitle'
import { appendTutorToken, createTutorReply, finalizeTutorReply } from '../lib/tutor-stream'
import './tutor.css'

type TutorMessage = ChatMessageOut & { incomplete?: boolean }

// Monotonic counter for stable message IDs during a session
let _msgIdCounter = 0
function nextMsgId(): number {
  return -(++_msgIdCounter)
}

const SUBJECT_OPTIONS = [
  { value: '', label: 'All subjects' },
  { value: 'os', label: 'Operating Systems' },
  { value: 'dbms', label: 'DBMS' },
  { value: 'cn', label: 'Computer Networks' },
]

export default function TutorPage() {
  usePageTitle('AI Tutor')
  const [conversations, setConversations] = useState<ConversationOut[]>([])
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null)
  const [messages, setMessages] = useState<TutorMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedSubject, setSelectedSubject] = useState('')
  const [streamingMsg, setStreamingMsg] = useState<ChatMessageOut | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const streamControllerRef = useRef<AbortController | null>(null)
  const conversationRequestRef = useRef(0)

  useEffect(() => () => {
    const controller = streamControllerRef.current
    streamControllerRef.current = null
    controller?.abort()
    conversationRequestRef.current += 1
  }, [])

  const loadConversations = useCallback(async () => {
    try {
      const data = await getConversations()
      setConversations(data.conversations || [])
    } catch {
      // silent fail
    }
  }, [])

  useEffect(() => {
    void loadConversations()
  }, [loadConversations])

  const loadMessages = useCallback(async (id: number) => {
    const request = ++conversationRequestRef.current
    setIsLoading(true)
    try {
      const data = await getConversation(id)
      if (request !== conversationRequestRef.current) return
      setMessages(data.messages || [])
      setSelectedSubject(data.subject || '')
    } catch {
      if (request === conversationRequestRef.current) setError('Failed to load conversation')
    } finally {
      if (request === conversationRequestRef.current) setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  }, [messages, streamingMsg])

  const handleNewChat = useCallback(async () => {
    if (streamControllerRef.current || isLoading) return
    setIsLoading(true)
    try {
      const payload: CreateConversationRequest = {
        subject: selectedSubject || undefined,
      }
      const conv = await createConversation(payload)
      setActiveConversationId(conv.id)
      setMessages([])
      setStreamingMsg(null)
      setError(null)
      await loadConversations()
    } catch {
      setError('Failed to create conversation')
    } finally {
      setIsLoading(false)
    }
  }, [selectedSubject, loadConversations, isLoading])

  const handleSelectConversation = useCallback(
    async (id: number) => {
      if (streamControllerRef.current || isLoading) return
      setActiveConversationId(id)
      setStreamingMsg(null)
      setError(null)
      await loadMessages(id)
    },
    [loadMessages, isLoading]
  )

  const handleDeleteConversation = useCallback(
    async (id: number, e: React.MouseEvent) => {
      e.stopPropagation()
      if (streamControllerRef.current || isLoading) return
      try {
        await deleteConversation(id)
        if (activeConversationId === id) {
          setActiveConversationId(null)
          setMessages([])
        }
        await loadConversations()
      } catch {
        setError('Failed to delete conversation')
      }
    },
    [activeConversationId, loadConversations, isLoading]
  )

  const handleSend = useCallback(async () => {
    const trimmed = input.trim()
    if (!trimmed || streamControllerRef.current || isLoading) return
    const controller = new AbortController()
    streamControllerRef.current = controller
    const stillCurrent = () => streamControllerRef.current === controller && !controller.signal.aborted
    setInput('')
    setError(null)
    setIsLoading(true)
    setIsStreaming(true)
    const createdAt = new Date().toISOString()
    const userMessage: TutorMessage = { id: nextMsgId(), role: 'user', content: trimmed, citations: [], chunks: [], created_at: createdAt }
    setMessages((previous) => [...previous, userMessage])
    let reply = createTutorReply(nextMsgId(), createdAt)
    setStreamingMsg(reply)
    try {
      const completion = await tutorChatStream({ query: trimmed, conversation_id: activeConversationId, subject: selectedSubject || undefined }, (token) => {
        if (!stillCurrent()) return
        reply = appendTutorToken(reply, token)
        setStreamingMsg(reply)
      }, controller.signal)
      if (!stillCurrent()) return
      const completedReply = finalizeTutorReply(reply, completion)
      setMessages((previous) => [...previous, completedReply])
      setStreamingMsg(null)
      if (completion.conversationId !== null && activeConversationId === null) setActiveConversationId(completion.conversationId)
      void loadConversations()
    } catch (failure) {
      if (!stillCurrent()) return
      setError(failure instanceof Error ? failure.message : 'Chat failed')
      if (reply.content) setMessages((previous) => [...previous, { ...reply, incomplete: true }])
      setStreamingMsg(null)
      setInput(trimmed)
    } finally {
      if (stillCurrent()) {
        streamControllerRef.current = null
        setIsStreaming(false)
        setIsLoading(false)
      }
    }
  }, [input, isLoading, activeConversationId, selectedSubject, loadConversations])

  const allMessages = useMemo<TutorMessage[]>(() => streamingMsg ? [...messages, streamingMsg] : messages, [messages, streamingMsg])

  return (
    <div className="tutor-page">
      <aside className="tutor-sidebar">
        <div className="tutor-sidebar__header">
          <h2>Conversations</h2>
          <Button type="button" size="sm" onClick={handleNewChat} disabled={isStreaming || isLoading}>
            + New
          </Button>
        </div>
        <div className="tutor-sidebar__list">
          {conversations.length === 0 && (
            <p className="tutor-sidebar__empty">No conversations yet</p>
          )}
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={`tutor-sidebar__item${
                activeConversationId === conv.id ? ' tutor-sidebar__item--active' : ''
              }`}
            >
              <button type="button" className="tutor-sidebar__select" disabled={isStreaming || isLoading} onClick={() => void handleSelectConversation(conv.id)} aria-current={activeConversationId === conv.id ? 'true' : undefined}>
              <span className="tutor-sidebar__title">
                {conv.title || 'Untitled'}
              </span>
              <span className="tutor-sidebar__meta">
                {conv.subject?.toUpperCase() || 'General'} · {conv.message_count} msgs
              </span>
              </button>
              <button
                type="button"
                disabled={isStreaming || isLoading}
                className="tutor-sidebar__delete"
                onClick={(e) => void handleDeleteConversation(conv.id, e)}
                title="Delete conversation"
                aria-label={`Delete ${conv.title || 'untitled conversation'}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </aside>

      <main className="tutor-main">
        <div className="tutor-header">
          <span className="tutor-header__eyebrow">AI Tutor</span>
          <h1 className="tutor-header__title">Study Assistant</h1>
          <p className="tutor-header__subtitle">Ask anything about OS, DBMS, or Computer Networks. Grounded in your textbook.</p>
        </div>

        <div className="tutor-scope">
          <label htmlFor="tutor-subject">Scope:</label>
          <select
            id="tutor-subject"
            value={selectedSubject}
            onChange={(e) => setSelectedSubject(e.target.value)}
            disabled={isStreaming || isLoading}
          >
            {SUBJECT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="tutor-chat">
          {allMessages.length === 0 && !isLoading && (
            <StateMessage title="Start a conversation" tone="info">
              Ask a technical question about Operating Systems, DBMS, or Computer Networks.
            </StateMessage>
          )}

          {allMessages.map((msg) => (
            <div
              key={msg.id}
              className={`tutor-message tutor-message--${msg.role}`}
            >
              <div className="tutor-message__bubble">
                {msg.incomplete ? <p className="tutor-message__incomplete">Incomplete response · request failed</p> : null}
                <p className="tutor-message__content">{msg.content || (msg === streamingMsg ? 'Waiting for the first token…' : '')}</p>
                {msg.citations && msg.citations.length > 0 && (
                  <details className="tutor-message__citations">
                    <summary>Sources ({msg.citations.length})</summary>
                    <ul>
                      {msg.citations.map((c) => (
                        <li key={c.index}>
                          <strong>[{c.index}]</strong> {c.chunk_id}
                          <p>{c.snippet}</p>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            </div>
          ))}

          {isLoading && !streamingMsg && (
            <div className="tutor-message tutor-message--assistant">
              <div className="tutor-message__bubble tutor-message__bubble--loading">
                <span className="tutor-typing">Thinking</span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {error && (
          <StateMessage title="Error" tone="danger">
            {error}
          </StateMessage>
        )}

        <form
          className="tutor-input"
          onSubmit={(e) => {
            e.preventDefault()
            void handleSend()
          }}
        >
          <input
            type="text"
            aria-label="Question for the study assistant"
            placeholder="Ask about OS, DBMS, CN..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isStreaming || isLoading}
          />
          <Button type="submit" disabled={isStreaming || isLoading || !input.trim()}>
            {isStreaming ? 'Streaming...' : 'Send'}
          </Button>
        </form>
      </main>
    </div>
  )
}
