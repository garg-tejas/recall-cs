import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import type { ApiError } from '../api/client'
import {
  answerQuizSession,
  finishQuizSession,
  getTopics,
  skipQuizSession,
  startQuizSession,
} from '../api/quiz'
import type { QuizCard, QuizSessionAnswerResponse, SessionProgress } from '../api/types'
import PageHeader from '../components/layout/PageHeader'
import FeedbackPanel from '../components/review/FeedbackPanel'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import ProgressBar from '../components/ui/ProgressBar'
import StateMessage from '../components/ui/StateMessage'
import Textarea from '../components/ui/Textarea'
import type { ReviewSessionScopeState, ReviewSummaryState } from './reviewFlow'
import './review.css'

type VerdictBucket = 'correct' | 'partially_correct' | 'incorrect'

interface SessionAttemptSnapshot {
  score: number | null
  verdict: VerdictBucket
  shouldRemediate: boolean
  topic: string
}

interface PathPosition {
  index: number
  total: number
  label: string
}

function normalizeVerdictBucket(value: string | null | undefined): VerdictBucket {
  const normalized = (value || '').trim().toLowerCase()
  if (normalized.includes('partial')) return 'partially_correct'
  if (normalized.includes('correct')) return 'correct'
  return 'incorrect'
}

function clampLimit(value: number): number {
  return Math.max(1, Math.min(100, Math.round(value)))
}

function normalizeTopicToken(value: string | null | undefined): string {
  return (value || '').trim().toLowerCase()
}

function toTopicSlug(value: string): string {
  return value.replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
}

function uniqueTopics(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const ordered: string[] = []
  for (const value of values) {
    const raw = (value || '').trim()
    const normalized = normalizeTopicToken(raw)
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    ordered.push(raw)
  }
  return ordered
}

function reorderTopicsByPreferred(topics: string[], preferredTopic: string): string[] {
  if (!preferredTopic) return topics
  const preferred = topics.find((topic) => normalizeTopicToken(topic) === preferredTopic)
  if (!preferred) return topics
  return [preferred, ...topics.filter((topic) => normalizeTopicToken(topic) !== preferredTopic)]
}

function toPathTopicLabel(topicKey: string): string {
  const tail = topicKey.split(':').pop() || topicKey
  return tail
    .replace(/[-_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function resolvePathTopicIndex(currentTopic: string, orderedPathTopics: string[]): number {
  const topicToken = normalizeTopicToken(currentTopic)
  if (!topicToken || orderedPathTopics.length === 0) return -1
  const topicSlug = toTopicSlug(topicToken)

  for (let index = 0; index < orderedPathTopics.length; index += 1) {
    const candidate = normalizeTopicToken(orderedPathTopics[index])
    const candidateTail = candidate.split(':').pop() || candidate
    const candidateTailSpaced = candidateTail.replace(/[-_]+/g, ' ').trim()
    if (
      topicToken === candidate ||
      topicToken === candidateTail ||
      topicToken === candidateTailSpaced
    ) {
      return index
    }

    const candidateSlug = toTopicSlug(candidate)
    const candidateTailSlug = toTopicSlug(candidateTail)
    if (
      topicSlug.length > 0 &&
      (topicSlug === candidateSlug || topicSlug === candidateTailSlug)
    ) {
      return index
    }
  }

  return -1
}

export default function ReviewPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const routeState = (location.state as ReviewSessionScopeState | null) ?? null

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [currentCard, setCurrentCard] = useState<QuizCard | null>(null)
  const [progress, setProgress] = useState<SessionProgress | null>(null)
  const [displayedIndex, setDisplayedIndex] = useState(0)
  const [sessionAttempts, setSessionAttempts] = useState<SessionAttemptSnapshot[]>([])

  const [userAnswer, setUserAnswer] = useState('')
  const [attemptStartedAt, setAttemptStartedAt] = useState<number | null>(null)

  const [result, setResult] = useState<QuizSessionAnswerResponse | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const sessionIdRef = useRef<string | null>(null)
  const sessionClosedRef = useRef(false)

  const orderedTopics = useMemo(() => {
    const fromPath = uniqueTopics(routeState?.pathTopicsOrdered ?? [])
    const fromScope = uniqueTopics(routeState?.topics ?? [])
    const preferredTopic = normalizeTopicToken(routeState?.preferredTopic)

    const baseline = fromPath.length > 0 ? fromPath : fromScope
    return reorderTopicsByPreferred(baseline, preferredTopic)
  }, [routeState?.pathTopicsOrdered, routeState?.preferredTopic, routeState?.topics])

  const pathTopics = useMemo(() => {
    if (routeState?.source !== 'learning-path') return []
    const fromPath = uniqueTopics(routeState?.pathTopicsOrdered ?? [])
    const fallback = uniqueTopics(routeState?.topics ?? [])
    const preferredTopic = normalizeTopicToken(routeState?.preferredTopic)
    const baseline = fromPath.length > 0 ? fromPath : fallback
    return reorderTopicsByPreferred(baseline, preferredTopic)
  }, [
    routeState?.pathTopicsOrdered,
    routeState?.preferredTopic,
    routeState?.source,
    routeState?.topics,
  ])

  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  const buildSummaryState = useCallback((): ReviewSummaryState => {
    const correctCount = sessionAttempts.filter(
      (attempt) => attempt.verdict === 'correct',
    ).length
    const partialCount = sessionAttempts.filter(
      (attempt) => attempt.verdict === 'partially_correct',
    ).length
    const incorrectCount = sessionAttempts.filter(
      (attempt) => attempt.verdict === 'incorrect',
    ).length
    const remediationCount = sessionAttempts.filter((attempt) => attempt.shouldRemediate).length
    const scoredAttempts = sessionAttempts
      .map((attempt) => attempt.score)
      .filter((score): score is number => typeof score === 'number')

    return {
      answeredCount: sessionAttempts.length,
      totalCards: progress?.total ?? sessionAttempts.length,
      averageScore:
        scoredAttempts.length > 0
          ? scoredAttempts.reduce((sum, score) => sum + score, 0) / scoredAttempts.length
          : null,
      correctCount,
      partialCount,
      incorrectCount,
      remediationCount,
      topics: Array.from(new Set(sessionAttempts.map((attempt) => attempt.topic).filter(Boolean))),
    }
  }, [progress?.total, sessionAttempts])

  const finishAndNavigateBack = useCallback(() => {
    const activeSessionId = sessionIdRef.current
    if (!activeSessionId || sessionClosedRef.current) {
      navigate('/dashboard')
      return
    }
    sessionClosedRef.current = true
    void finishQuizSession(activeSessionId)
      .catch(() => undefined)
      .finally(() => {
        sessionIdRef.current = null
        setSessionId(null)
        navigate('/dashboard')
      })
  }, [navigate])

  const finishAndNavigateSummary = useCallback(() => {
    const summaryState = buildSummaryState()
    const activeSessionId = sessionIdRef.current
    if (!activeSessionId || sessionClosedRef.current) {
      navigate('/review/summary', { state: summaryState })
      return
    }
    sessionClosedRef.current = true
    void finishQuizSession(activeSessionId)
      .catch(() => undefined)
      .finally(() => {
        sessionIdRef.current = null
        setSessionId(null)
        navigate('/review/summary', { state: summaryState })
      })
  }, [buildSummaryState, navigate])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      setIsLoading(true)
      setError(null)
      setResult(null)
      setUserAnswer('')
      setSessionAttempts([])
      try {
        let topics: string[] | undefined =
          orderedTopics.length > 0 ? orderedTopics : undefined
        if (topics === undefined) {
          const topicsList = await getTopics()
          const names = (topicsList || []).map((t) => t.topic).filter(Boolean)
          topics = names.length > 0 ? names : undefined
        }
        const subject = routeState?.subject || undefined
        const requestedLimit = typeof routeState?.limit === 'number' ? clampLimit(routeState.limit) : 10
        const pathTopicsOrdered =
          orderedTopics.length > 0 ? orderedTopics : topics
        const data = await startQuizSession({
          limit: requestedLimit,
          topics,
          subject,
          path_topics_ordered: pathTopicsOrdered,
        })
        if (cancelled) return
        sessionClosedRef.current = false
        setSessionId(data.session_id)
        setProgress(data.progress)
        setDisplayedIndex(0)
        if (data.current_card) {
          setCurrentCard(data.current_card)
          setAttemptStartedAt(performance.now())
        } else {
          setCurrentCard(null)
          setAttemptStartedAt(null)
        }
      } catch (err) {
        if (cancelled) return
        const apiErr = err as ApiError
        setError(apiErr.detail || 'Failed to start review session')
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [orderedTopics, routeState?.limit, routeState?.subject])

  useEffect(() => {
    return () => {
      const activeSessionId = sessionIdRef.current
      if (!activeSessionId || sessionClosedRef.current) return
      sessionClosedRef.current = true
      void finishQuizSession(activeSessionId).catch(() => undefined)
    }
  }, [])

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!currentCard || !sessionId) return
    const trimmedAnswer = userAnswer.trim()
    if (!trimmedAnswer) {
      setError('Please enter an answer before submitting')
      return
    }
    setIsSubmitting(true)
    setError(null)
    try {
      const started = attemptStartedAt ?? performance.now()
      const responseTimeMs = Math.round(performance.now() - started)
      const res = await answerQuizSession(sessionId, {
        card_id: currentCard.card_id,
        user_answer: trimmedAnswer,
        response_time_ms: responseTimeMs,
      })
      const verdict = normalizeVerdictBucket(res.verdict)
      setResult(res)
      setProgress(res.progress)
      setSessionAttempts((previous) => [
        ...previous,
        {
          score: typeof res.model_score === 'number' ? res.model_score : null,
          verdict,
          shouldRemediate:
            typeof res.should_remediate === 'boolean'
              ? res.should_remediate
              : verdict !== 'correct',
          topic: currentCard.topic,
        },
      ])
    } catch (err) {
      const apiErr = err as ApiError
      setError(apiErr.detail || 'Failed to submit answer')
    } finally {
      setIsSubmitting(false)
    }
  }

  const onDontKnow = async () => {
    if (!currentCard || !sessionId) return
    setIsSubmitting(true)
    setError(null)
    try {
      const started = attemptStartedAt ?? performance.now()
      const responseTimeMs = Math.round(performance.now() - started)
      const res = await answerQuizSession(sessionId, {
        card_id: currentCard.card_id,
        user_answer: '',
        response_time_ms: responseTimeMs,
        action: 'dont_know',
      })
      const verdict = normalizeVerdictBucket(res.verdict)
      setResult(res)
      setProgress(res.progress)
      setSessionAttempts((previous) => [
        ...previous,
        {
          score: typeof res.model_score === 'number' ? res.model_score : null,
          verdict,
          shouldRemediate:
            typeof res.should_remediate === 'boolean'
              ? res.should_remediate
              : verdict !== 'correct',
          topic: currentCard.topic,
        },
      ])
    } catch (err) {
      const apiErr = err as ApiError
      setError(apiErr.detail || 'Failed to record answer')
    } finally {
      setIsSubmitting(false)
    }
  }

  const onSkip = async () => {
    if (!sessionId) return
    setIsSubmitting(true)
    setError(null)
    try {
      const res = await skipQuizSession(sessionId)
      setProgress(res.progress)
      if (res.next_card) {
        setCurrentCard(res.next_card)
        setDisplayedIndex((previous) => previous + 1)
        setUserAnswer('')
        setResult(null)
        setAttemptStartedAt(performance.now())
      } else {
        setCurrentCard(null)
        setResult(null)
      }
    } catch (err) {
      const apiErr = err as ApiError
      setError(apiErr.detail || 'Failed to skip card')
    } finally {
      setIsSubmitting(false)
    }
  }

  const goToNextCard = () => {
    if (!result?.next_card) {
      setCurrentCard(null)
      return
    }
    setCurrentCard(result.next_card)
    setDisplayedIndex((previous) => previous + 1)
    setUserAnswer('')
    setResult(null)
    setAttemptStartedAt(performance.now())
  }

  const noCards = !isLoading && !error && !currentCard && !result
  const hasScopedTopics = orderedTopics.length > 0
  const emptyStateTitle = hasScopedTopics
    ? 'No cards available for this selection'
    : 'No cards available right now'
  const emptyStateBody = hasScopedTopics
    ? 'Your current topic filter returned no cards. Try widening the scope or starting from all topics.'
    : 'There are no cards available right now. Return to the dashboard and try a different session scope.'

  const progressPercent = useMemo(() => {
    if (!progress || progress.total === 0) return 0
    if (progress.completed && !currentCard) return 100
    const stepsIntoRun = currentCard ? displayedIndex + 1 : displayedIndex
    return Math.round((stepsIntoRun / progress.total) * 100)
  }, [currentCard, displayedIndex, progress])

  const queueRemaining = useMemo(() => {
    if (!currentCard || !progress) return 0
    return Math.max(progress.total - displayedIndex - 1, 0)
  }, [currentCard, displayedIndex, progress])

  const hasMoreAfterCurrent = useMemo(() => Boolean(result?.next_card), [result])
  const totalCards = progress?.total ?? 0
  const pathPosition = useMemo<PathPosition | null>(() => {
    if (!currentCard || pathTopics.length === 0) return null
    const matchIndex = resolvePathTopicIndex(currentCard.topic, pathTopics)
    if (matchIndex < 0) return null
    const matchedTopic = pathTopics[matchIndex]
    return {
      index: matchIndex,
      total: pathTopics.length,
      label: toPathTopicLabel(matchedTopic),
    }
  }, [currentCard, pathTopics])

  return (
    <div className="review layout-stack layout-stack--lg">
      <PageHeader
        eyebrow="Session"
        title="Review workspace"
        subtitle={
          currentCard
            ? `Card ${displayedIndex + 1} of ${totalCards}`
            : 'No active card'
        }
        backHref="/dashboard"
        backLabel="Back to dashboard"
      />

      <section className="review-progress">
        <Card
          className="review-progress__card"
          kicker="Session progress"
          title={
            currentCard ? `${progressPercent}% through this run` : 'Ready for the next run'
          }
          subtitle={
            currentCard
              ? `${queueRemaining} cards remaining after this step`
              : 'Select new scope from dashboard when ready.'
          }
          actions={
            currentCard ? (
              <Badge tone={result ? 'success' : 'info'}>
                {result ? 'Answered' : 'In progress'}
              </Badge>
            ) : (
              <Badge tone="neutral">Idle</Badge>
            )
          }
        >
          <ProgressBar
            value={progressPercent}
            className="review-progress__bar"
            ariaLabel="Session progress"
          />
        </Card>
      </section>

      {isLoading ? (
        <StateMessage title="Loading review cards" tone="info">
          Preparing your next question set.
        </StateMessage>
      ) : null}

      {error ? (
        <StateMessage title="Review session error" tone="danger">
          {error}
        </StateMessage>
      ) : null}

      {noCards ? (
        <Card className="review-empty" tone="inset" padding="lg">
          <StateMessage title={emptyStateTitle} tone="warning">
            {emptyStateBody}
          </StateMessage>
          <div className="review-empty__actions">
            <Button type="button" onClick={finishAndNavigateBack}>
              Back to dashboard
            </Button>
          </div>
        </Card>
      ) : null}

      {!isLoading && !error && currentCard ? (
        <section className="review-workspace" key={`${currentCard.card_id}-${displayedIndex}`}>
          <Card
            className="review-question"
            tone="default"
            padding="lg"
            kicker={`Topic: ${currentCard.topic}`}
            title="Question"
          >
            {pathPosition ? (
              <p className="review-question__path-position">
                Node {pathPosition.index + 1} of {pathPosition.total}: {pathPosition.label}
              </p>
            ) : null}
            <p className="review-question__text">{currentCard.question}</p>
            <p className="review-question__hint">
              Explain your answer clearly. Use precise terms where possible.
            </p>
          </Card>

          <Card
            className="review-compose"
            tone="inset"
            padding="lg"
            kicker="Answer composer"
            title="Your response"
            subtitle={
              result
                ? 'Answer submitted. Review feedback and choose the next step below.'
                : 'Draft your response before submitting.'
            }
          >
            <form onSubmit={onSubmit} className="review-compose__form">
              <Textarea
                label="Your answer"
                value={userAnswer}
                onChange={(e) => setUserAnswer(e.target.value)}
                rows={9}
                required
                disabled={!!result}
              />

              <div className="review-compose__actions">
                <Button
                  type="submit"
                  disabled={isSubmitting || !!result || !sessionId}
                  loading={isSubmitting}
                  loadingLabel="Grading..."
                >
                  Submit answer
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  disabled={isSubmitting || !!result || !sessionId}
                  onClick={onDontKnow}
                >
                  Don&apos;t know
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={isSubmitting || !!result || !sessionId}
                  onClick={onSkip}
                >
                  Skip
                </Button>
              </div>

              {result ? (
                <p className="review-compose__submitted-note">
                  Submission locked. Use the feedback panel to continue.
                </p>
              ) : null}
            </form>
          </Card>
        </section>
      ) : null}

      {result ? (
        <FeedbackPanel
          result={result}
          hasMoreAfterCurrent={hasMoreAfterCurrent}
          onNextCard={goToNextCard}
          onFinishSession={finishAndNavigateSummary}
          onBackToDashboard={finishAndNavigateBack}
        />
      ) : null}
    </div>
  )
}
