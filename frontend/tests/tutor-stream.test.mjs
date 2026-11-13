import assert from 'node:assert/strict'
import test from 'node:test'
import { SseParser, readTutorStream, createTutorReply, appendTutorToken, finalizeTutorReply } from '../src/lib/tutor-stream.ts'

const metadata = { citations: [{ index: 1, chunk_id: 'os:42', snippet: 'Paging uses fixed-size frames.' }], chunks_used: [{ id: 'os:42', header_path: 'Memory / Paging', snippet: 'Paging uses fixed-size frames.' }], conversation_id: 7 }
const event = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`
const transcript = event('token', { token: 'Paging café ' }) + event('token', { token: 'uses frames. [1]' }) + event('done', metadata)

function readerFor(chunks) {
  let position = 0
  const state = { cancelled: false, released: false }
  return {
    state,
    async read() { return position < chunks.length ? { value: chunks[position++], done: false } : { done: true } },
    async cancel() { state.cancelled = true },
    releaseLock() { state.released = true },
  }
}

test('every byte boundary preserves UTF-8 text and terminal citations', async () => {
  const bytes = new TextEncoder().encode(transcript)
  for (let boundary = 0; boundary <= bytes.length; boundary += 1) {
    const reader = readerFor([bytes.slice(0, boundary), bytes.slice(boundary)])
    const tokens = []
    const result = await readTutorStream(reader, token => tokens.push(token))
    assert.equal(result.content, 'Paging café uses frames. [1]')
    assert.equal(tokens.join(''), result.content)
    assert.deepEqual(result.citations, metadata.citations)
    assert.deepEqual(result.chunks, metadata.chunks_used)
    assert.equal(result.conversationId, 7)
    assert.equal(reader.state.released, true)
  }
})

test('single-byte network chunks and CRLF separators remain valid', async () => {
  const bytes = new TextEncoder().encode(transcript.replaceAll('\n', '\r\n'))
  const result = await readTutorStream(readerFor(Array.from(bytes, byte => Uint8Array.of(byte))), () => {})
  assert.equal(result.content, 'Paging café uses frames. [1]')
})

test('SSE comments, BOM, multiline data and non-data fields follow event framing', () => {
  const received = []
  const parser = new SseParser(value => received.push(value))
  for (const character of '\uFEFF: heartbeat\revent: note\rid: unused\rdata: first\rdata:second\r\r') parser.push(character)
  assert.deepEqual(received, [{ event: 'note', data: 'first\nsecond' }])
})

test('stable reply identity and final content retain citations and source chunks', async () => {
  const original = createTutorReply(-2, '2026-10-26T00:00:00Z')
  let reply = original
  const completion = await readTutorStream(readerFor([new TextEncoder().encode(transcript)]), token => { reply = appendTutorToken(reply, token) })
  const finished = finalizeTutorReply(reply, completion)
  assert.equal(finished.id, original.id)
  assert.equal(finished.created_at, original.created_at)
  assert.equal(original.content, '')
  assert.equal(finished.content, completion.content)
  assert.deepEqual(finished.citations, metadata.citations)
  assert.deepEqual(finished.chunks, metadata.chunks_used)
})

test('a fallback reply can complete without a persisted conversation', async () => {
  const text = event('token', { token: 'No supporting source found.' }) + event('done', { citations: [], chunks_used: [], conversation_id: null })
  const result = await readTutorStream(readerFor([new TextEncoder().encode(text)]), () => {})
  assert.equal(result.conversationId, null)
})

test('provider error preserves partial callbacks but never returns a completed reply', async () => {
  const text = event('token', { token: 'Partial' }) + event('error', { detail: 'Provider unavailable' })
  const reader = readerFor([new TextEncoder().encode(text)])
  const tokens = []
  await assert.rejects(readTutorStream(reader, token => tokens.push(token)), /Provider unavailable/)
  assert.deepEqual(tokens, ['Partial'])
  assert.equal(reader.state.cancelled, true)
  assert.equal(reader.state.released, true)
})

test('EOF or a nonterminated done frame cannot turn partial output into success', async () => {
  for (const text of [event('token', { token: 'Partial' }), transcript.slice(0, -1)]) {
    await assert.rejects(readTutorStream(readerFor([new TextEncoder().encode(text)]), () => {}), /ended before completion/)
  }
})

test('malformed data, invalid metadata, empty output and invalid UTF-8 reject and release', async () => {
  const cases = [
    new TextEncoder().encode('event: token\ndata: {bad}\n\n'),
    new TextEncoder().encode(event('token', { token: 'Answer' }) + event('done', {})),
    new TextEncoder().encode(event('token', { token: 'Answer' }) + event('done', { ...metadata, conversation_id: -4 })),
    new TextEncoder().encode(event('token', { token: 'Answer' }) + event('done', { ...metadata, citations: [{ index: 1 }] })),
    new TextEncoder().encode(event('done', metadata)),
    Uint8Array.of(0xff),
  ]
  for (const bytes of cases) {
    const reader = readerFor([bytes])
    await assert.rejects(readTutorStream(reader, () => {}))
    assert.equal(reader.state.cancelled, true)
    assert.equal(reader.state.released, true)
  }
})

test('terminal event stops further token delivery and cancels the reader', async () => {
  const reader = readerFor([new TextEncoder().encode(transcript + event('token', { token: 'ignored' }))])
  const tokens = []
  const result = await readTutorStream(reader, token => tokens.push(token))
  assert.equal(tokens.join(''), result.content)
  assert.equal(reader.state.cancelled, true)
})

test('oversized event framing rejects before unbounded buffering', () => {
  const parser = new SseParser(() => {}, 16)
  assert.throws(() => parser.push('data: ' + 'x'.repeat(17)), /maximum supported size/)
})

test('transport rejection still cancels and releases the reader', async () => {
  const reader = readerFor([])
  reader.read = async () => { throw new Error('Connection lost') }
  await assert.rejects(readTutorStream(reader, () => {}), /Connection lost/)
  assert.equal(reader.state.cancelled, true)
  assert.equal(reader.state.released, true)
})
