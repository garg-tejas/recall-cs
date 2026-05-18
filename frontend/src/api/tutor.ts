/**
 * Tutor API endpoints.
 */

import { apiRequest } from './client'
import type {
  ConversationDetailOut,
  ConversationListResponse,
  CreateConversationRequest,
  TutorChatRequest,
  TutorChatResponse,
} from './types'

export async function getConversations(): Promise<ConversationListResponse> {
  return apiRequest<ConversationListResponse>('/api/tutor/conversations', {
    method: 'GET',
  })
}

export async function createConversation(
  data: CreateConversationRequest
): Promise<ConversationDetailOut> {
  return apiRequest<ConversationDetailOut>('/api/tutor/conversations', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getConversation(id: number): Promise<ConversationDetailOut> {
  return apiRequest<ConversationDetailOut>(`/api/tutor/conversations/${id}`, {
    method: 'GET',
  })
}

export async function deleteConversation(id: number): Promise<void> {
  await apiRequest<void>(`/api/tutor/conversations/${id}`, {
    method: 'DELETE',
  })
}

export async function tutorChat(data: TutorChatRequest): Promise<TutorChatResponse> {
  return apiRequest<TutorChatResponse>('/api/tutor/chat', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function tutorChatStream(
  data: TutorChatRequest,
  onToken: (token: string) => void,
  onDone: (citations: unknown[], chunksUsed: unknown[], conversationId: number) => void,
  onError: (error: string) => void
): Promise<void> {
  const accessToken = localStorage.getItem('access_token')
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`
  }

  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/tutor/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('No response body')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        const event = line.slice(7)
        const dataLine = lines[lines.indexOf(line) + 1]
        if (dataLine?.startsWith('data: ')) {
          const data = dataLine.slice(6)
          if (event === 'token') {
            try {
              const parsed = JSON.parse(data)
              onToken(parsed.token || '')
            } catch {
              onToken(data)
            }
          } else if (event === 'done') {
            try {
              const parsed = JSON.parse(data)
              onDone(parsed.citations || [], parsed.chunks_used || [], parsed.conversation_id)
            } catch {
              onDone([], [], 0)
            }
          } else if (event === 'error') {
            onError(data)
          }
        }
      }
    }
  }
}
