import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  createConversation,
  deleteConversation,
  getConversation,
  getConversations,
  tutorChatStream,
} from '../api/tutor'
import type {
  ChatMessageOut,
  ChunkSummary,
  ConversationOut,
  CreateConversationRequest,
} from '../api/types'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { StateMessage } from '../components/ui/StateMessage'
import './tutor.css'

interface StreamingMessage {
  role: 'assistant'
  content: string
  citations: { index: number; chunk_id: string; snippet: string }[]
  chunks: ChunkSummary[]
}

const SUBJECT_OPTIONS = [
  { value: '', label: 'All subjects' },
  { value: 'os', label: 'Operating Systems' },
  { value: 'dbms', label: 'DBMS' },
  { value: 'cn', label: 'Computer Networks' },
]

export default function TutorPage() {
  const navigate = useNavigate()
  const [conversations, setConversations] = useState<ConversationOut[]>([])
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessageOut[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedSubject, setSelectedSubject] = useState('')
  const [streamingMsg, setStreamingMsg] = useState<StreamingMessage | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)

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
    try {
      const data = await getConversation(id)
      setMessages(data.messages || [])
      setSelectedSubject(data.subject || '')
    } catch (err) {
      setError('Failed to load conversation')
    }
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingMsg])

  const handleNewChat = useCallback(async () => {
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
    } catch (err) {
      setError('Failed to create conversation')
    }
  }, [selectedSubject, loadConversations])

  const handleSelectConversation = useCallback(
    async (id: number) => {
      setActiveConversationId(id)
      setStreamingMsg(null)
      setError(null)
      await loadMessages(id)
    },
    [loadMessages]
  )

  const handleDeleteConversation = useCallback(
    async (id: number, e: React.MouseEvent) => {
      e.stopPropagation()
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
    [activeConversationId, loadConversations]
  )

  const handleSend = useCallback(async () => {
    const trimmed = input.trim()
    if (!trimmed || isStreaming) return

    setInput('')
    setError(null)
    setIsLoading(true)
    setIsStreaming(true)

    // Optimistically add user message
    const userMsg: ChatMessageOut = {
      id: Date.now(),
      role: 'user',
      content: trimmed,
      citations: [],
      chunks: [],
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMsg])

    const streamMsg: StreamingMessage = {
      role: 'assistant',
      content: '',
      citations: [],
      chunks: [],
    }
    setStreamingMsg(streamMsg)

    try {
      await tutorChatStream(
        {
          query: trimmed,
          conversation_id: activeConversationId,
          subject: selectedSubject || undefined,
        },
        (token) => {
          setStreamingMsg((prev) =>
            prev ? { ...prev, content: prev.content + token } : null
          )
        },
        (citations, chunks, conversationId) => {
          setStreamingMsg((prev) => {
            if (!prev) return null
            return {
              ...prev,
              citations,
              chunks,
            }
          })
          if (conversationId && !activeConversationId) {
            setActiveConversationId(conversationId)
          }
          setIsStreaming(false)
          setIsLoading(false)
          void loadConversations()
        },
        (errorMsg) => {
          setError(errorMsg)
          setIsStreaming(false)
          setIsLoading(false)
        }
      )

      // Move streaming message into messages list
      setMessages((prev) => {
        const assistantMsg: ChatMessageOut = {
          id: Date.now() + 1,
          role: 'assistant',
          content: streamMsg.content,
          citations: streamMsg.citations,
          chunks: streamMsg.chunks,
          created_at: new Date().toISOString(),
        }
        return [...prev, assistantMsg]
      })
      setStreamingMsg(null)
    } catch (err) {
      setError((err as Error).message || 'Chat failed')
      setIsStreaming(false)
      setIsLoading(false)
      setStreamingMsg(null)
    }
  }, [input, isStreaming, activeConversationId, selectedSubject, loadConversations])

  const allMessages = useMemo(() => {
    if (!streamingMsg) return messages
    const assistantMsg: ChatMessageOut = {
      id: Date.now(),
      role: 'assistant',
      content: streamingMsg.content,
      citations: streamingMsg.citations,
      chunks: streamingMsg.chunks,
      created_at: new Date().toISOString(),
    }
    return [...messages, assistantMsg]
  }, [messages, streamingMsg])

  return (
    <div className="tutor-page">
      <aside className="tutor-sidebar">
        <div className="tutor-sidebar__header">
          <h2>Conversations</h2>
          <Button type="button" size="sm" onClick={handleNewChat}>
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
              onClick={() => void handleSelectConversation(conv.id)}
            >
              <span className="tutor-sidebar__title">
                {conv.title || 'Untitled'}
              </span>
              <span className="tutor-sidebar__meta">
                {conv.subject?.toUpperCase() || 'General'} · {conv.message_count} msgs
              </span>
              <button
                className="tutor-sidebar__delete"
                onClick={(e) => void handleDeleteConversation(conv.id, e)}
                title="Delete"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </aside>

      <main className="tutor-main">
        <PageHeader
          eyebrow="AI Tutor"
          title="Study Assistant"
          subtitle="Ask anything about OS, DBMS, or Computer Networks. Grounded in your textbook."
          backHref="/dashboard"
          backLabel="Back to dashboard"
        />

        <div className="tutor-scope">
          <label>Scope:</label>
          <select
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
                <p className="tutor-message__content">{msg.content}</p>
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
