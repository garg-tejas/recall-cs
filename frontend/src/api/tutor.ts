/**
 * Tutor API endpoints.
 */

import { apiRequest, tokenManager } from './client'
import { readTutorStream } from '../lib/tutor-stream'
import type { TutorStreamCompletion } from '../lib/tutor-stream'
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
  signal?: AbortSignal,
): Promise<TutorStreamCompletion> {
  const accessToken = tokenManager.getAccessToken()
  const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'text/event-stream' }
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/tutor/chat/stream`, {
    method: 'POST', headers, body: JSON.stringify(data), signal,
  })
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(typeof errorData.detail === 'string' ? errorData.detail : `HTTP ${response.status}`)
  }
  if (!response.headers.get('content-type')?.toLowerCase().includes('text/event-stream')) {
    await response.body?.cancel().catch(() => undefined)
    throw new Error('Tutor returned an unexpected response format')
  }
  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')
  return readTutorStream(reader, onToken)
}
