// Development-only fixture entry; not imported by main.tsx or built as a production input.
import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { StudyFrame } from './components/layout/AppShell'
import { LandingReadingView } from './routes/LandingPage'
import ReviewWorkspace, { ReviewNotes } from './components/review/ReviewWorkspace'
import FeedbackPanel from './components/review/FeedbackPanel'
import PageHeader from './components/layout/PageHeader'
import StateMessage from './components/ui/StateMessage'
import type { QuizCard, QuizSessionAnswerResponse } from './api/types'
import './index.css'
import './routes/review.css'
import './design-preview.css'

// Defensive deny-all fetch adapter. None of the mounted fixture views invokes API/auth hooks.
globalThis.fetch = async () => { throw new Error('Isolated UI fixture: network operations are disabled.') }
const fixtureCard: QuizCard = { card_id: 1, topic: 'Operating systems / Memory', question: 'What does paging solve, and what does it leave behind?' }
const fixtureResult: QuizSessionAnswerResponse = {
  answer: 'Paging maps fixed-size virtual pages to physical frames. Non-contiguous frames avoid external fragmentation, while unused space within an allocated frame can still cause internal fragmentation.',
  explanation: 'Illustrative source excerpt: fixed-sized pages may be placed in any available frame. The last page of a process need not fill its frame.',
  source_chunk_id: 'ui-fixture / paging / 001', show_source_context: true, model_score: 3, verdict: 'partially_correct', should_remediate: true,
  concept_summary: 'Separate free space between allocations from unused space within an allocation.', where_you_missed: ['Explain why non-contiguous physical frames remove the need for one large contiguous free block.'],
  progress: { current_index: 1, total: 3, completed: false },
}
function Preview() {
  const { pathname } = useLocation()
  const [mode, setMode] = useState('question')
  const [answer, setAnswer] = useState('Paging uses fixed-size frames, so a process does not need one continuous allocation.')
  const [notice, setNotice] = useState('')
  const feedback = ['feedback', 'incorrect', 'dont-know', 'grading-error', 'source-missing'].includes(mode)
  const result = { ...fixtureResult,
    ...(mode === 'incorrect' ? { verdict: 'incorrect', model_score: 1 } : {}),
    ...(mode === 'dont-know' ? { verdict: 'dont_know', model_score: 0 } : {}),
    ...(mode === 'grading-error' ? { verdict: 'grading_error', model_score: null, should_remediate: false } : {}),
    ...(mode === 'source-missing' ? { explanation: null, source_chunk_id: null, show_source_context: false } : {}),
  }
  const reset = () => { setMode('question'); setNotice('Fixture action only. Nothing was saved.') }
  return <><div className="fixture-notice"><strong>ISOLATED UI FIXTURES</strong><span>Synthetic records and feedback. No backend, Clerk, or model calls.</span><label>State <select value={mode} onChange={(event) => { setMode(event.target.value); setNotice('') }}>{['question', 'feedback', 'incorrect', 'dont-know', 'grading-error', 'source-missing', 'loading', 'error', 'empty', 'long-text'].map((value) => <option key={value}>{value}</option>)}</select></label></div><StudyFrame width="wide" account={<span>UI preview</span>}>
    {pathname === '/' ? <LandingReadingView /> : <div className="review reading-sheet layout-stack layout-stack--lg"><PageHeader eyebrow="Illustrative session / no result is saved" title="One question at a time." subtitle="Fixture card 1 of 3" backHref="/" backLabel="Back to introduction" />
      {notice && <p role="status" className="study-label">{notice}</p>}
      {mode === 'loading' ? <StateMessage tone="info" title="Loading review cards">Preparing your next question set.</StateMessage>
        : mode === 'empty' ? <StateMessage tone="warning" title="No cards available for this selection">Widen the topic scope or return to your study desk.</StateMessage>
        : <>{mode === 'error' && <StateMessage title="The answer could not be checked" tone="danger">Your explanation remains below. Retry when the connection is available.</StateMessage>}<div className="review-desk"><ReviewWorkspace card={mode === 'long-text' ? { ...fixtureCard, question: `${fixtureCard.question} Explain the distinction between virtual address translation, allocation granularity, fragmentation, and locality without assuming contiguous physical memory.` } : fixtureCard} answer={answer} onAnswer={setAnswer} submitted={feedback} busy={false} canSubmit onSubmit={(event) => { event.preventDefault(); setMode('feedback') }} onDontKnow={() => setMode('dont-know')} onSkip={reset} />{feedback ? <FeedbackPanel result={result} hasMoreAfterCurrent onNextCard={reset} onFinishSession={reset} onBackToDashboard={reset} /> : <ReviewNotes />}</div></>}
    </div>}
  </StudyFrame></>
}
if (import.meta.env.DEV) createRoot(document.getElementById('root')!).render(<React.StrictMode><MemoryRouter><Preview /></MemoryRouter></React.StrictMode>)
