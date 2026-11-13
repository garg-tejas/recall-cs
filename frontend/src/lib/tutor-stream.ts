import type { CitationOut, ChunkSummary, ChatMessageOut } from '../api/types.ts'

export interface SseEvent { event: string; data: string }

/** Incremental SSE framing. A blank line, not a network chunk, ends an event. */
export class SseParser {
  private line = ''
  private event = ''
  private data: string[] = []
  private skipLf = false
  private size = 0
  private firstCharacter = true
  private readonly onEvent: (event: SseEvent) => void
  private readonly maxEventCharacters: number

  constructor(onEvent: (event: SseEvent) => void, maxEventCharacters = 1_048_576) {
    this.onEvent = onEvent
    this.maxEventCharacters = maxEventCharacters
  }

  push(text: string) {
    for (const character of text) {
      if (this.firstCharacter) {
        this.firstCharacter = false
        if (character === '\uFEFF') continue
      }
      if (this.skipLf) {
        this.skipLf = false
        if (character === '\n') continue
      }
      if (character === '\r' || character === '\n') {
        this.processLine()
        this.skipLf = character === '\r'
      } else {
        this.line += character
        this.size += 1
        if (this.size > this.maxEventCharacters) throw new Error('Tutor event exceeded the maximum supported size')
      }
    }
  }

  private processLine() {
    const line = this.line
    this.line = ''
    if (!line) {
      const event = { event: this.event || 'message', data: this.data.join('\n') }
      const hasData = this.data.length > 0
      this.event = ''
      this.data = []
      this.size = 0
      if (hasData) this.onEvent(event)
      return
    }
    if (line.startsWith(':')) return
    const colon = line.indexOf(':')
    const field = colon < 0 ? line : line.slice(0, colon)
    let value = colon < 0 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') this.event = value
    if (field === 'data') this.data.push(value)
  }
}

export interface TutorStreamCompletion {
  content: string
  citations: CitationOut[]
  chunks: ChunkSummary[]
  conversationId: number | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function parseJson(data: string): unknown {
  try { return JSON.parse(data) } catch { throw new Error('Tutor returned malformed event data') }
}

function completionMetadata(value: unknown): Omit<TutorStreamCompletion, 'content'> {
  if (!isRecord(value) || !Array.isArray(value.citations) || !Array.isArray(value.chunks_used)) throw new Error('Tutor completion metadata is incomplete')
  const citations = value.citations.map((item: unknown) => {
    if (!isRecord(item) || !Number.isSafeInteger(item.index) || (item.index as number) < 0 || typeof item.chunk_id !== 'string' || typeof item.snippet !== 'string') throw new Error('Tutor returned an invalid citation')
    return { index: item.index as number, chunk_id: item.chunk_id, snippet: item.snippet }
  })
  const chunks = value.chunks_used.map((item: unknown) => {
    if (!isRecord(item) || typeof item.id !== 'string' || typeof item.header_path !== 'string' || typeof item.snippet !== 'string') throw new Error('Tutor returned an invalid source chunk')
    return { id: item.id, header_path: item.header_path, snippet: item.snippet }
  })
  const conversationId = value.conversation_id
  if (conversationId !== null && (typeof conversationId !== 'number' || !Number.isSafeInteger(conversationId) || conversationId <= 0)) throw new Error('Tutor returned an invalid conversation identifier')
  return { citations, chunks, conversationId }
}

function eventError(data: string): Error {
  try {
    const payload: unknown = JSON.parse(data)
    if (isRecord(payload) && typeof payload.detail === 'string') return new Error(payload.detail)
    if (isRecord(payload) && typeof payload.message === 'string') return new Error(payload.message)
    if (typeof payload === 'string') return new Error(payload)
  } catch { /* Legacy plaintext errors remain readable. */ }
  return new Error(data || 'Tutor generation failed')
}

/** Reads one reply. Only a validated done event makes it a completed answer. */
export async function readTutorStream(reader: ReadableStreamDefaultReader<Uint8Array>, onToken: (token: string) => void): Promise<TutorStreamCompletion> {
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let content = ''
  let completion: TutorStreamCompletion | null = null
  let failure: Error | null = null
  let terminal = false
  let exhausted = false
  const parser = new SseParser(({ event, data }) => {
    if (terminal) return
    if (event === 'error') { terminal = true; failure = eventError(data); return }
    if (event === 'token') {
      const payload = parseJson(data)
      if (!isRecord(payload) || typeof payload.token !== 'string') throw new Error('Tutor returned an invalid answer token')
      content += payload.token
      onToken(payload.token)
    } else if (event === 'done') {
      const metadata = completionMetadata(parseJson(data))
      if (!content.trim()) throw new Error('Tutor completed without answer text')
      completion = { content, ...metadata }
      terminal = true
    }
  })
  try {
    while (!terminal) {
      const { done, value } = await reader.read()
      if (done) {
        exhausted = true
        parser.push(decoder.decode())
        break
      }
      parser.push(decoder.decode(value, { stream: true }))
    }
    if (failure) throw failure
    if (!completion) throw new Error('Tutor stream ended before completion. Any received text is incomplete.')
    return completion
  } finally {
    if (!exhausted) await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}

export function createTutorReply(id: number, createdAt: string): ChatMessageOut {
  return { id, role: 'assistant', content: '', citations: [], chunks: [], created_at: createdAt }
}

export function appendTutorToken(reply: ChatMessageOut, token: string): ChatMessageOut {
  return { ...reply, content: reply.content + token }
}

export function finalizeTutorReply(reply: ChatMessageOut, completion: TutorStreamCompletion): ChatMessageOut {
  return { ...reply, content: completion.content, citations: completion.citations, chunks: completion.chunks }
}
