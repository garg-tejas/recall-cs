import type { FormEvent } from 'react'
import type { QuizCard } from '../../api/types'
import Button from '../ui/Button'
import Textarea from '../ui/Textarea'

export interface ReviewWorkspaceProps {
  card: QuizCard
  answer: string
  onAnswer: (value: string) => void
  submitted: boolean
  busy: boolean
  canSubmit: boolean
  onSubmit: (event: FormEvent) => void
  onDontKnow: () => void
  onSkip: () => void
  pathPosition?: { index: number; total: number; label: string } | null
}

export default function ReviewWorkspace({ card, answer, onAnswer, submitted, busy, canSubmit, onSubmit, onDontKnow, onSkip, pathPosition }: ReviewWorkspaceProps) {
  return <section className="review-workspace" aria-label="Question and response">
    <article className="review-question">
      <header className="review-question__meta"><span className="study-label">01 / Recall</span><span className="study-label">{card.topic}</span></header>
      {pathPosition ? <p className="review-question__path-position">Node {pathPosition.index + 1} / {pathPosition.total} · {pathPosition.label}</p> : null}
      <h2 className="review-question__text">{card.question}</h2>
      <p className="review-question__hint">Take a moment to retrieve the idea before writing. Precise reasoning matters more than length.</p>
    </article>
    <section className="review-compose">
      <header><span className="study-label">02 / Explain</span><span className="review-compose__count">{answer.length} characters</span></header>
      <form onSubmit={onSubmit} className="review-compose__form">
        <Textarea label="Your explanation" value={answer} onChange={(event) => onAnswer(event.target.value)} rows={8} required disabled={submitted || busy} placeholder="Start with the key idea. Add the mechanism, then an example or a trade-off…" />
        <div className="review-compose__actions">
          <Button type="submit" disabled={busy || submitted || !canSubmit || !answer.trim()} loading={busy} loadingLabel="Checking…">Check my answer</Button>
          <Button type="button" variant="secondary" disabled={busy || submitted || !canSubmit} onClick={onDontKnow}>I don't know yet</Button>
          <Button type="button" variant="ghost" disabled={busy || submitted || !canSubmit} onClick={onSkip}>Skip this card</Button>
        </div>
        <p className="review-compose__submitted-note" role="status">{submitted ? 'Answer recorded. Compare it with the reference and feedback alongside.' : 'Checking uses the configured grading model. “I don’t know” records a missed recall; skipping moves on.'}</p>
      </form>
    </section>
  </section>
}

export function ReviewNotes() {
  return <aside className="review-notebook" aria-label="Study guidance">
    <p className="study-label">03 / Check</p><h2>The margin is for reflection.</h2><p>Your reference answer and model feedback appear here after you respond.</p>
    <ol><li>State the central idea.</li><li>Explain why it works.</li><li>Name a limitation or trade-off.</li></ol>
    <div className="review-notebook__note"><span className="study-label">A note on feedback</span><p>A model score is a suggestion to inspect, not proof of mastery. Compare the explanation with the reference and any available source context.</p></div>
  </aside>
}
