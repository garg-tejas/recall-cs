import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import type { ApiError } from '../api/client'
import { getStats, getTopics } from '../api/quiz'
import type { TopicStats } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import TopicScopeControls from '../components/dashboard/TopicScopeControls'
import TopicTable from '../components/dashboard/TopicTable'
import PageHeader from '../components/layout/PageHeader'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import StateMessage from '../components/ui/StateMessage'
import { usePageTitle } from '../hooks/usePageTitle'
import './dashboard.css'

interface MissionState {
  title: string
  description: string
  badgeTone: 'success' | 'warning' | 'danger'
  badgeLabel: string
}

export default function DashboardPage() {
  usePageTitle('Dashboard')
  const { user, clearSession } = useAuth()
  const navigate = useNavigate()

  const [topics, setTopics] = useState<TopicStats[]>([])
  const [availableTopics, setAvailableTopics] = useState<string[]>([])
  const [selectedTopics, setSelectedTopics] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadDashboard = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [stats, topicsList] = await Promise.all([getStats(), getTopics()])
      setTopics(stats.topics || [])
      const names = (topicsList || []).map((t) => t.topic).sort()
      setAvailableTopics(names)
      setSelectedTopics((prev) => (prev.length > 0 ? prev : names))
    } catch (err) {
      const apiErr = err as ApiError
      setError(apiErr.detail || 'Failed to load stats')
    } finally {
      setIsLoading(false)
      setHasLoadedOnce(true)
    }
  }, [])

  useEffect(() => {
    void loadDashboard()
  }, [loadDashboard])

  const hasAnyData = topics.length > 0 || availableTopics.length > 0
  const isInitialLoading = isLoading && !hasLoadedOnce
  const isRefreshing = isLoading && hasLoadedOnce
  const hasBlockingError = !isLoading && !!error && !hasAnyData

  const totals = useMemo(() => {
    const totalCards = topics.reduce((acc, t) => acc + (t.total || 0), 0)
    const learnedCards = topics.reduce((acc, t) => acc + (t.learned || 0), 0)
    const dueToday = topics.reduce((acc, t) => acc + (t.due_today || 0), 0)
    const overdue = topics.reduce((acc, t) => acc + (t.overdue || 0), 0)
    return { totalCards, learnedCards, dueToday, overdue }
  }, [topics])

  const completionRate = useMemo(() => {
    if (totals.totalCards === 0) return 0
    return Math.round((totals.learnedCards / totals.totalCards) * 100)
  }, [totals.learnedCards, totals.totalCards])

  const mission = useMemo<MissionState>(() => {
    if (totals.overdue > 0) {
      return {
        title: 'Recover the overdue queue',
        description: `${totals.overdue} cards have slipped. Prioritize a short cleanup sprint now.`,
        badgeTone: 'danger',
        badgeLabel: 'Critical',
      }
    }

    if (totals.dueToday > 0) {
      return {
        title: 'Finish today\'s review set',
        description: `${totals.dueToday} cards are due today. Keep your streak stable with one focused session.`,
        badgeTone: 'warning',
        badgeLabel: 'Active',
      }
    }

    return {
      title: 'Rhythm is on track',
      description: 'No immediate backlog. A light review pass can build buffer for tomorrow.',
      badgeTone: 'success',
      badgeLabel: 'Stable',
    }
  }, [totals.dueToday, totals.overdue])

  const selectionSummary =
    selectedTopics.length === availableTopics.length
      ? 'All topics selected'
      : `${selectedTopics.length} of ${availableTopics.length} topics selected`

  const dueTopicNames = useMemo(
    () =>
      topics
        .filter((topic) => topic.due_today + topic.overdue > 0)
        .map((topic) => topic.topic),
    [topics],
  )

  const startReview = useCallback(() => {
    navigate('/review/setup', {
      state: {
        topics: selectedTopics.length ? selectedTopics : null,
      },
    })
  }, [navigate, selectedTopics])

  const previewLearningPath = useCallback(() => {
    navigate('/review/path', {
      state: {
        topics: selectedTopics.length ? selectedTopics : null,
        limit: 10,
      },
    })
  }, [navigate, selectedTopics])

  if (isInitialLoading) {
    return (
      <div className="dashboard layout-stack layout-stack--lg">
        <PageHeader
          eyebrow="Signal Lab"
          title="Dashboard"
          subtitle="Preparing your review workspace..."
        />
        <DashboardLoadingState />
      </div>
    )
  }

  if (hasBlockingError) {
    return (
      <div className="dashboard layout-stack layout-stack--lg">
        <PageHeader
          eyebrow="Signal Lab"
          title="Dashboard"
          subtitle="We could not load your study workspace."
        />
        <Card className="dashboard-blocking-error" tone="default" padding="lg">
          <StateMessage title="Connection issue" tone="danger">
            {error}
          </StateMessage>
          <div className="dashboard-blocking-error__actions">
            <Button type="button" onClick={() => void loadDashboard()}>
              Retry loading
            </Button>
            <Button type="button" variant="ghost" onClick={clearSession}>
              Log out
            </Button>
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="dashboard layout-stack layout-stack--lg">
      <PageHeader
        eyebrow="Signal Lab"
        title="Dashboard"
        subtitle="Monitor your study rhythm and launch the next review sprint."
      />

      {isRefreshing ? (
        <p className="dashboard-status-line" role="status" aria-live="polite">
          Refreshing dashboard metrics...
        </p>
      ) : null}

      <section className="dashboard-hero">
        <Card
          tone="accent"
          padding="lg"
          className="dashboard-hero__mission"
          kicker="Daily mission"
          title={mission.title}
          subtitle={mission.description}
          actions={<Badge tone={mission.badgeTone}>{mission.badgeLabel}</Badge>}
        >
          <div className="dashboard-hero__mission-grid">
            <div className="dashboard-hero__metric">
              <span className="dashboard-hero__metric-label">Due now</span>
              <strong className="dashboard-hero__metric-value">
                {totals.dueToday + totals.overdue}
              </strong>
            </div>
            <div className="dashboard-hero__metric">
              <span className="dashboard-hero__metric-label">Completion</span>
              <strong className="dashboard-hero__metric-value">{completionRate}%</strong>
            </div>
            <div className="dashboard-hero__metric">
              <span className="dashboard-hero__metric-label">Topics in scope</span>
              <strong className="dashboard-hero__metric-value">{selectedTopics.length}</strong>
            </div>
          </div>
          <div className="dashboard-hero__actions">
            <Button type="button" size="lg" onClick={startReview}>
              Start review session
            </Button>
            <Button type="button" variant="secondary" onClick={previewLearningPath}>
              Preview learning path
            </Button>
            <Button type="button" variant="ghost" onClick={() => navigate('/tutor')}>
              AI Tutor
            </Button>
            <p className="dashboard-hero__hint">{selectionSummary}</p>
          </div>
        </Card>

        <Card
          tone="default"
          className="dashboard-hero__profile"
          kicker="Account overview"
          title={user?.username ?? 'Signed in'}
          subtitle={user?.email ?? 'Authenticated session'}
          actions={
            <div className="dashboard-profile__actions">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void loadDashboard()}
                disabled={isRefreshing}
              >
                Refresh
              </Button>
              <Button variant="ghost" size="sm" onClick={clearSession}>
                Log out
              </Button>
            </div>
          }
        >
          <div className="dashboard-hero__profile-body">
            <div
              className="dashboard-completion-ring"
              role="img"
              aria-label={`Completion rate ${completionRate}%`}
            >
              <div
                className="dashboard-completion-ring__dial"
                style={{
                  background: `conic-gradient(var(--accent-primary) ${completionRate}%, rgba(126, 157, 181, 0.24) ${completionRate}% 100%)`,
                }}
              />
              <div className="dashboard-completion-ring__core">
                <strong>{completionRate}%</strong>
                <span>completion</span>
              </div>
            </div>

            <dl className="dashboard-summary">
              <div className="dashboard-summary__item">
                <dt>Cards learned</dt>
                <dd>{totals.learnedCards}</dd>
              </div>
              <div className="dashboard-summary__item">
                <dt>Total cards</dt>
                <dd>{totals.totalCards}</dd>
              </div>
              <div className="dashboard-summary__item">
                <dt>Topics tracked</dt>
                <dd>{availableTopics.length}</dd>
              </div>
              <div className="dashboard-summary__item">
                <dt>Completion</dt>
                <dd>{completionRate}%</dd>
              </div>
            </dl>
          </div>
        </Card>
      </section>

      <section className="dashboard-stats" aria-label="Review statistics">
        <DashboardStat
          label="Total cards"
          value={totals.totalCards}
          detail={`${totals.learnedCards} learned`}
          tone="info"
        />
        <DashboardStat
          label="Due today"
          value={totals.dueToday}
          detail={totals.dueToday > 0 ? 'Ready in this cycle' : 'Nothing new due'}
          tone={totals.dueToday > 0 ? 'warning' : 'success'}
        />
        <DashboardStat
          label="Overdue"
          value={totals.overdue}
          detail={totals.overdue > 0 ? 'Needs catch-up' : 'Queue is clean'}
          tone={totals.overdue > 0 ? 'danger' : 'success'}
        />
      </section>

      <TopicScopeControls
        availableTopics={availableTopics}
        selectedTopics={selectedTopics}
        dueTopicNames={dueTopicNames}
        isBusy={isRefreshing}
        onToggleTopic={(topicName) => {
          setSelectedTopics((prev) =>
            prev.includes(topicName)
              ? prev.filter((topic) => topic !== topicName)
              : [...prev, topicName],
          )
        }}
        onSelectAll={() => setSelectedTopics(availableTopics)}
        onClearAll={() => setSelectedTopics([])}
        onSelectDueOnly={() =>
          setSelectedTopics(dueTopicNames.length > 0 ? dueTopicNames : availableTopics)
        }
        onStartReview={startReview}
      />

      <section className="dashboard-topics">
        <h2 className="dashboard-topics__title">By topic</h2>

        {error && hasAnyData ? (
          <div className="dashboard-inline-error">
            <StateMessage title="Could not refresh latest metrics" tone="warning">
              Showing the last successful snapshot. Retry when ready.
            </StateMessage>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void loadDashboard()}
              disabled={isRefreshing}
            >
              Retry
            </Button>
          </div>
        ) : null}

        {!error && topics.length === 0 ? (
          <div className="dashboard-empty-state">
            <div className="dashboard-empty-state__illustration" aria-hidden="true">
              <span className="dashboard-empty-state__glyph">◎</span>
              <div className="dashboard-empty-state__rings">
                <span /><span /><span />
              </div>
            </div>
            <div className="dashboard-empty-state__copy">
              <h3 className="dashboard-empty-state__title">Your review queue is empty</h3>
              <p className="dashboard-empty-state__detail">
                No cards have been loaded yet. Once the backend finishes seeding, your topics,
                due cards, and progress will appear here.
              </p>
            </div>
            <div className="dashboard-empty-state__actions">
              <Button
                type="button"
                variant="primary"
                size="md"
                onClick={() => navigate('/review/setup')}
              >
                Start your first review
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="md"
                onClick={() => void loadDashboard()}
                disabled={isRefreshing}
              >
                Refresh
              </Button>
            </div>
          </div>
        ) : null}

        {topics.length > 0 ? <TopicTable topics={topics} /> : null}
      </section>
    </div>
  )
}

interface DashboardStatProps {
  label: string
  value: number
  detail: string
  tone: 'info' | 'success' | 'warning' | 'danger'
}

function DashboardStat({ label, value, detail, tone }: DashboardStatProps) {
  return (
    <article className={`dashboard-stat dashboard-stat--${tone}`}>
      <div className="dashboard-stat__head">
        <p className="dashboard-stat__label">{label}</p>
        <span className="dashboard-stat__icon" aria-hidden="true" />
      </div>
      <p className="dashboard-stat__value">{value}</p>
      <p className="dashboard-stat__detail">{detail}</p>
    </article>
  )
}

function DashboardLoadingState() {
  return (
    <div className="dashboard-loading" aria-hidden="true">
      <div className="dashboard-loading__hero">
        <span className="dashboard-loading__block dashboard-loading__block--lg" />
        <span className="dashboard-loading__block dashboard-loading__block--sm" />
      </div>
      <div className="dashboard-loading__stats">
        <span className="dashboard-loading__block dashboard-loading__block--md" />
        <span className="dashboard-loading__block dashboard-loading__block--md" />
        <span className="dashboard-loading__block dashboard-loading__block--md" />
      </div>
      <div className="dashboard-loading__scope">
        <span className="dashboard-loading__block dashboard-loading__block--sm" />
        <span className="dashboard-loading__block dashboard-loading__block--sm" />
        <span className="dashboard-loading__block dashboard-loading__block--sm" />
      </div>
      <span className="dashboard-loading__block dashboard-loading__block--table" />
    </div>
  )
}
