import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import type { ApiError } from '../api/client'
import { getStats, getTopics } from '../api/quiz'
import PageHeader from '../components/layout/PageHeader'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import Input from '../components/ui/Input'
import StateMessage from '../components/ui/StateMessage'
import type { ReviewSessionScopeState } from './reviewFlow'
import { usePageTitle } from '../hooks/usePageTitle'
import './review-setup.css'

const SUBJECT_OPTIONS = [
  { key: 'os', label: 'Operating Systems' },
  { key: 'dbms', label: 'DBMS' },
  { key: 'cn', label: 'Computer Networks' },
] as const

function clampLimit(value: number) {
  return Math.max(1, Math.min(100, Math.round(value)))
}

export default function ReviewSetupPage() {
  usePageTitle('Review Setup')
  const navigate = useNavigate()
  const location = useLocation()
  const routeState = (location.state as ReviewSessionScopeState | null) ?? null

  const [availableTopics, setAvailableTopics] = useState<string[]>([])
  const [dueTopicNames, setDueTopicNames] = useState<string[]>([])
  const [selectedTopics, setSelectedTopics] = useState<string[]>([])
  const [selectedSubject, setSelectedSubject] = useState<string>('')
  const [limit, setLimit] = useState<number>(10)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [stats, topics] = await Promise.all([getStats(), getTopics()])
      const names = (topics || []).map((entry) => entry.topic).sort()
      const dueNames = (stats.topics || [])
        .filter((topic) => topic.due_today + topic.overdue > 0)
        .map((topic) => topic.topic)

      const selectedFromRoute = (routeState?.topics || []).filter((name) =>
        names.includes(name),
      )
      const nextSelectedTopics =
        selectedFromRoute.length > 0
          ? selectedFromRoute
          : names.length > 0
            ? names
            : []

      setAvailableTopics(names)
      setDueTopicNames(dueNames)
      setSelectedTopics(nextSelectedTopics)
      setSelectedSubject((routeState?.subject || '').trim().toLowerCase())
      if (typeof routeState?.limit === 'number') {
        setLimit(clampLimit(routeState.limit))
      }
    } catch (err) {
      const apiErr = err as ApiError
      setError(apiErr.detail || 'Failed to prepare review setup')
    } finally {
      setIsLoading(false)
    }
  }, [routeState?.limit, routeState?.subject, routeState?.topics])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const selectedSummary = useMemo(() => {
    if (availableTopics.length === 0) return 'No topics available yet'
    if (selectedTopics.length === availableTopics.length) return 'All topics selected'
    return `${selectedTopics.length} of ${availableTopics.length} topics selected`
  }, [availableTopics.length, selectedTopics.length])

  const canStart = selectedTopics.length > 0 || selectedSubject.length > 0

  return (
    <div className="review-setup layout-stack layout-stack--lg">
      <PageHeader
        eyebrow="Session"
        title="Review setup"
        subtitle="Tune the next sprint before entering the question workspace."
        backHref="/dashboard"
        backLabel="Back to dashboard"
      />

      {isLoading ? (
        <StateMessage title="Loading setup" tone="info">
          Pulling latest topic scope and due signals.
        </StateMessage>
      ) : null}

      {error ? (
        <Card tone="default" className="review-setup__error" padding="md">
          <StateMessage title="Setup unavailable" tone="danger">
            {error}
          </StateMessage>
          <Button type="button" variant="secondary" onClick={() => void loadData()}>
            Retry loading
          </Button>
        </Card>
      ) : null}

      {!isLoading && !error ? (
        <>
          <section className="review-setup__grid">
            <Card
              tone="accent"
              padding="lg"
              className="review-setup__mission"
              kicker="Session scope"
              title="Calibrate this run"
              subtitle="Use tighter scope for targeted remediation, or broaden scope for maintenance rounds."
              actions={<Badge tone={dueTopicNames.length > 0 ? 'warning' : 'success'}>{dueTopicNames.length} due topics</Badge>}
            >
              <div className="review-setup__stats">
                <article className="review-setup__stat">
                  <span>Selected topics</span>
                  <strong>{selectedTopics.length}</strong>
                </article>
                <article className="review-setup__stat">
                  <span>Question limit</span>
                  <strong>{limit}</strong>
                </article>
                <article className="review-setup__stat">
                  <span>Subject focus</span>
                  <strong>{selectedSubject || 'all'}</strong>
                </article>
              </div>
              <p className="review-setup__hint">{selectedSummary}</p>
            </Card>

            <Card
              tone="default"
              padding="lg"
              className="review-setup__tuning"
              kicker="Tuning"
              title="Session controls"
              subtitle="Set answer count and optional subject bias."
            >
              <div className="review-setup__limit-row">
                <Input
                  label="Question limit"
                  type="number"
                  min={1}
                  max={100}
                  value={String(limit)}
                  onChange={(event) => {
                    const nextValue = Number(event.target.value || 1)
                    setLimit(clampLimit(Number.isFinite(nextValue) ? nextValue : 1))
                  }}
                  hint="Allowed range: 1 to 100 cards in this session."
                />
              </div>

              <div className="review-setup__subject-row">
                <p className="review-setup__label">Subject focus</p>
                <div className="review-setup__subjects">
                  <button
                    type="button"
                    className={`review-setup__subject${selectedSubject.length === 0 ? ' review-setup__subject--active' : ''}`}
                    onClick={() => setSelectedSubject('')}
                  >
                    All subjects
                  </button>
                  {SUBJECT_OPTIONS.map((subject) => (
                    <button
                      key={subject.key}
                      type="button"
                      className={`review-setup__subject${selectedSubject === subject.key ? ' review-setup__subject--active' : ''}`}
                      onClick={() => setSelectedSubject(subject.key)}
                    >
                      {subject.label}
                    </button>
                  ))}
                </div>
              </div>
            </Card>
          </section>

          <Card
            tone="default"
            padding="lg"
            className="review-setup__topics"
            kicker="Topic scope"
            title="Refine selection"
            subtitle="Choose the topics to include in this session run."
            actions={<Badge tone="info">{selectedSummary}</Badge>}
          >
            <div className="review-setup__topic-actions">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setSelectedTopics(availableTopics)}
                disabled={availableTopics.length === 0}
              >
                Select all
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setSelectedTopics([])}
                disabled={availableTopics.length === 0}
              >
                Clear all
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => setSelectedTopics(dueTopicNames)}
                disabled={dueTopicNames.length === 0}
              >
                Due only
              </Button>
            </div>

            {availableTopics.length > 0 ? (
              <div className="review-setup__chips">
                {availableTopics.map((topicName) => {
                  const isSelected = selectedTopics.includes(topicName)
                  const isDue = dueTopicNames.includes(topicName)
                  return (
                    <button
                      key={topicName}
                      type="button"
                      className={`review-setup__chip${isSelected ? ' review-setup__chip--active' : ''}`}
                      onClick={() => {
                        setSelectedTopics((previous) =>
                          previous.includes(topicName)
                            ? previous.filter((item) => item !== topicName)
                            : [...previous, topicName],
                        )
                      }}
                    >
                      <span className="review-setup__chip-title">{topicName}</span>
                      {isDue ? <Badge tone="warning">due</Badge> : null}
                    </button>
                  )
                })}
              </div>
            ) : (
              <StateMessage title="No topics available" tone="warning">
                Seed cards first to enable setup controls.
              </StateMessage>
            )}
          </Card>

          <section className="review-setup__footer">
            <Button type="button" variant="ghost" onClick={() => navigate('/dashboard')}>
              Cancel
            </Button>
            <Button
              type="button"
              size="lg"
              disabled={!canStart}
              onClick={() =>
                navigate('/review/path', {
                  state: {
                    topics: selectedTopics.length > 0 ? selectedTopics : null,
                    subject: selectedSubject || null,
                    limit,
                  },
                })
              }
            >
              Preview learning path
            </Button>
          </section>
        </>
      ) : null}
    </div>
  )
}
