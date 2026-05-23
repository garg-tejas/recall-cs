import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import PageHeader from '../components/layout/PageHeader'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import ProgressBar from '../components/ui/ProgressBar'
import StateMessage from '../components/ui/StateMessage'
import type { ReviewSummaryState } from './reviewFlow'
import { usePageTitle } from '../hooks/usePageTitle'
import './review-summary.css'

function isSummaryState(value: unknown): value is ReviewSummaryState {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<ReviewSummaryState>
  return (
    typeof candidate.answeredCount === 'number' &&
    typeof candidate.totalCards === 'number' &&
    typeof candidate.correctCount === 'number' &&
    typeof candidate.partialCount === 'number' &&
    typeof candidate.incorrectCount === 'number' &&
    typeof candidate.remediationCount === 'number' &&
    Array.isArray(candidate.topics)
  )
}

export default function ReviewSummaryPage() {
  usePageTitle('Session Summary')
  const location = useLocation()
  const navigate = useNavigate()

  const summary = isSummaryState(location.state) ? location.state : null

  const completionPercent = useMemo(() => {
    if (!summary || summary.totalCards <= 0) return 0
    return Math.round((summary.answeredCount / summary.totalCards) * 100)
  }, [summary])

  const averageScoreLabel = useMemo(() => {
    if (!summary || summary.averageScore === null) return 'N/A'
    return `${summary.averageScore.toFixed(1)}/5`
  }, [summary])

  const averageScorePercent = useMemo(() => {
    if (!summary || summary.averageScore === null) return 0
    return Math.max(0, Math.min(100, (summary.averageScore / 5) * 100))
  }, [summary])

  const scoreTone = useMemo<'success' | 'warning' | 'danger'>(() => {
    if (!summary || summary.averageScore === null) return 'warning'
    if (summary.averageScore >= 4) return 'success'
    if (summary.averageScore >= 3) return 'warning'
    return 'danger'
  }, [summary])

  if (!summary) {
    return (
      <div className="review-summary layout-stack layout-stack--lg">
        <PageHeader
          eyebrow="Session"
          title="Session summary"
          subtitle="No summary payload was found for this run."
          backHref="/dashboard"
          backLabel="Back to dashboard"
        />
        <Card tone="inset" padding="lg">
          <StateMessage title="Summary unavailable" tone="warning">
            Start a review session first, then return here after finishing.
          </StateMessage>
          <div className="review-summary__actions">
            <Button type="button" onClick={() => navigate('/review/setup')}>
              Start a session
            </Button>
            <Button type="button" variant="ghost" onClick={() => navigate('/dashboard')}>
              Back to dashboard
            </Button>
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="review-summary layout-stack layout-stack--lg">
      <PageHeader
        eyebrow="Session"
        title="Session summary"
        subtitle={`${summary.answeredCount} answers completed across ${summary.topics.length || 1} scope tracks.`}
        backHref="/dashboard"
        backLabel="Back to dashboard"
      />

      <Card
        tone="accent"
        padding="lg"
        className="review-summary__hero"
        kicker="Run outcome"
        title={`${completionPercent}% session completion`}
        subtitle="Use this signal to choose whether to deepen one topic or expand breadth next."
        actions={<Badge tone={scoreTone}>Avg score {averageScoreLabel}</Badge>}
      >
        <div
          className="review-summary__score-ring"
          role="img"
          aria-label={`Average score ${averageScoreLabel}`}
        >
          <div
            className="review-summary__score-ring-track"
            style={{
              background: `conic-gradient(var(--accent-primary) ${averageScorePercent}%, rgba(126, 157, 181, 0.24) ${averageScorePercent}% 100%)`,
            }}
          />
          <div className="review-summary__score-ring-core">
            <strong>{averageScoreLabel}</strong>
            <span>avg score</span>
          </div>
        </div>

        <div className="review-summary__hero-progress">
          <ProgressBar value={completionPercent} ariaLabel="Session completion" />
        </div>
        <div className="review-summary__hero-metrics">
          <article>
            <span>Correct</span>
            <strong>{summary.correctCount}</strong>
          </article>
          <article>
            <span>Partial</span>
            <strong>{summary.partialCount}</strong>
          </article>
          <article>
            <span>Incorrect</span>
            <strong>{summary.incorrectCount}</strong>
          </article>
          <article>
            <span>Need remediation</span>
            <strong>{summary.remediationCount}</strong>
          </article>
        </div>
      </Card>

      <section className="review-summary__grid">
        <Card
          tone="default"
          padding="lg"
          className="review-summary__scope"
          kicker="Scope replay"
          title="Topics reviewed"
          subtitle="Restart with the same scope or tune for a narrower follow-up."
        >
          <div className="review-summary__chips">
            {summary.topics.length > 0 ? (
              summary.topics.map((topic) => (
                <Badge key={topic} tone="info">
                  {topic}
                </Badge>
              ))
            ) : (
              <Badge tone="neutral">All topics</Badge>
            )}
          </div>
        </Card>

        <Card
          tone="default"
          padding="lg"
          className="review-summary__next"
          kicker="Next actions"
          title="Run the next checkpoint"
          subtitle="Continue momentum while feedback from this session is still fresh."
        >
          <div className="review-summary__actions">
            <Button
              type="button"
              onClick={() =>
                navigate('/review/setup', {
                  state: {
                    topics: summary.topics.length > 0 ? summary.topics : null,
                  },
                })
              }
            >
              Start another run
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() =>
                navigate('/review/path', {
                  state: {
                    topics: summary.topics.length > 0 ? summary.topics : null,
                  },
                })
              }
            >
              Preview learning path
            </Button>
            <Button type="button" variant="secondary" onClick={() => navigate('/dashboard')}>
              Return to dashboard
            </Button>
          </div>
        </Card>
      </section>
    </div>
  )
}
