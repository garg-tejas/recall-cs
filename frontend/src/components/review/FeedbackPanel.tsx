import { useMemo } from 'react'

import type { QuizSessionAnswerResponse } from '../../api/types'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import Card from '../ui/Card'
import ProgressBar from '../ui/ProgressBar'
import { verdictBucket } from '../../lib/verdict'

interface FeedbackPanelProps {
  result: QuizSessionAnswerResponse
  hasMoreAfterCurrent: boolean
  onNextCard: () => void
  onFinishSession: () => void
  onBackToDashboard: () => void
}

type FeedbackTone = 'info' | 'success' | 'warning' | 'danger'

function normalizeLabel(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export default function FeedbackPanel({
  result,
  hasMoreAfterCurrent,
  onNextCard,
  onFinishSession,
  onBackToDashboard,
}: FeedbackPanelProps) {
  const normalizedVerdict = (result.verdict || 'n/a').toLowerCase()
  const shouldRemediate = useMemo(() => {
    if (typeof result.should_remediate === 'boolean') {
      return result.should_remediate
    }
    return verdictBucket(result.verdict) === 'incorrect' || verdictBucket(result.verdict) === 'partially_correct'
  }, [normalizedVerdict, result.should_remediate])

  const conceptSummary = useMemo(() => {
    const text = (result.concept_summary || '').trim()
    if (text) return text
    return 'No concept summary was returned. Compare your explanation with the reference answer.'
  }, [result.concept_summary])

  const whereYouMissed = useMemo(() => {
    const points = result.where_you_missed || []
    return points
      .map((point) => point.trim())
      .filter(Boolean)
      .slice(0, 3)
  }, [result.where_you_missed])

  const verdictTone = useMemo<FeedbackTone>(() => {
    if (normalizedVerdict.includes('dont_know') || normalizedVerdict.includes("don't_know")) return 'warning'
    if (normalizedVerdict.includes('grading_error') || normalizedVerdict.includes('error')) return 'info'
    if (normalizedVerdict.includes('incorrect')) return 'danger'
    if (normalizedVerdict.includes('partial')) return 'warning'
    if (normalizedVerdict.includes('correct')) return 'success'
    return 'info'
  }, [normalizedVerdict])

  const scoreLabel = useMemo(() => {
    if (verdictBucket(result.verdict) === 'ungraded') return 'Unavailable'
    if (typeof result.model_score !== 'number' || !Number.isFinite(result.model_score) || result.model_score < 0 || result.model_score > 5) return 'Unavailable'
    return `${result.model_score}/5`
  }, [result.model_score, result.verdict])

  const scorePercent = useMemo(() => {
    if (typeof result.model_score !== 'number') return 0
    return Math.max(0, Math.min(100, Math.round((result.model_score / 5) * 100)))
  }, [result.model_score])

  const verdictLabel = useMemo(() => normalizeLabel(result.verdict || 'n/a'), [result.verdict])

  const nextDueLabel = useMemo(() => {
    if (!result.next_due_at) return null
    const parsed = new Date(result.next_due_at)
    if (Number.isNaN(parsed.getTime())) return result.next_due_at
    return parsed.toLocaleString()
  }, [result.next_due_at])

  return (
    <Card
      className="review-feedback-panel"
      tone="default"
      padding="lg"
      kicker="Feedback"
      title={normalizedVerdict.includes('grading_error') ? 'Check the reference.' : 'Compare your reasoning.'}
      subtitle="Model feedback is a study aid. Inspect the reference before continuing."
      actions={<Badge tone={verdictTone}>{verdictLabel}</Badge>}
    >
      <div className="review-feedback-panel__score">
        <div className="review-feedback-panel__score-meta">
          <span>Model score</span>
          <strong>{scoreLabel}</strong>
        </div>
        {scoreLabel !== 'Unavailable' ? <ProgressBar
          value={scorePercent}
          className="review-feedback-panel__score-bar"
          ariaLabel="Model score"
        /> : null}
      </div>

      {normalizedVerdict.includes('dont_know') ? (
        <section className="review-feedback-panel__section">
          <h4>Skipped — failed recall</h4>
          <p>This card has been recorded as a missed recall. Review the reference answer below to reinforce the concept.</p>
        </section>
      ) : null}

      {normalizedVerdict.includes('grading_error') ? (
        <section className="review-feedback-panel__section">
          <h4>Grading unavailable</h4>
          <p>We could not grade your answer automatically this time. Please review the reference answer below and self-assess.</p>
        </section>
      ) : null}

      {shouldRemediate ? (
        <section className="review-feedback-panel__section">
          <h4>Concept in brief</h4>
          <p>{conceptSummary}</p>
        </section>
      ) : null}

      {shouldRemediate ? (
        <section className="review-feedback-panel__section">
          <h4>Where your answer missed</h4>
          {whereYouMissed.length > 0 ? (
            <ul className="review-feedback-panel__list">
              {whereYouMissed.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          ) : (
            <p>No specific gaps were returned. Compare your explanation with the reference answer.</p>
          )}
        </section>
      ) : null}

      <section className="review-feedback-panel__section review-feedback-panel__section--reference">
        <h4>Reference answer</h4>
        <p>{result.answer || 'No reference answer was returned.'}</p>
      </section>

      {result.show_source_context && result.explanation ? (
        <details className="review-feedback-panel__context">
          <summary>Inspect available source excerpt</summary>
          <span className="review-feedback-panel__source-id">{result.source_chunk_id ? `Source chunk / ${result.source_chunk_id}` : 'Source identifier not provided'}</span>
          <p className="review-feedback-panel__snippet">{result.explanation}</p>
        </details>
      ) : null}

      {nextDueLabel ? (
        <p className="review-feedback-panel__next-due">
          Next review scheduled at {nextDueLabel}
        </p>
      ) : null}

      <div className="review-feedback-panel__actions">
        {hasMoreAfterCurrent ? (
          <Button type="button" onClick={onNextCard}>
            Continue to next card
          </Button>
        ) : (
          <Button type="button" onClick={onFinishSession}>
            Finish session
          </Button>
        )}
        <Button type="button" variant="ghost" onClick={onBackToDashboard}>
          Back to dashboard
        </Button>
      </div>
    </Card>
  )
}
