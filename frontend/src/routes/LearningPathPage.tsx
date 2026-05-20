import { type CSSProperties, useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import type { ApiError } from '../api/client'
import { finishQuizSession, startQuizSession } from '../api/quiz'
import type { LearningPathNode, QuizCard, SessionProgress } from '../api/types'
import PageHeader from '../components/layout/PageHeader'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import StateMessage from '../components/ui/StateMessage'
import type { ReviewSessionScopeState } from './reviewFlow'
import './learning-path.css'

type SWOTBucket = 'strength' | 'weakness' | 'opportunity' | 'threat'
type PathStatus = 'completed' | 'current' | 'upcoming' | 'locked'
type GraphNodeStatus = 'completed' | 'current' | 'unlocked' | 'locked'

interface PathStageNode {
  node: LearningPathNode
  index: number
  status: PathStatus
  unresolvedPrerequisiteKeys: string[]
}

interface SubjectSWOTSummary {
  subject: string
  buckets: Record<SWOTBucket, LearningPathNode[]>
}

function clampLimit(value: number): number {
  return Math.max(1, Math.min(100, Math.round(value)))
}

function normalizeBucket(value: string): SWOTBucket {
  const normalized = value.trim().toLowerCase()
  if (normalized === 'strength') return 'strength'
  if (normalized === 'weakness') return 'weakness'
  if (normalized === 'threat') return 'threat'
  return 'opportunity'
}

function emptyBuckets(): Record<SWOTBucket, LearningPathNode[]> {
  return {
    strength: [],
    weakness: [],
    opportunity: [],
    threat: [],
  }
}

interface PathGraphProps {
  stageNodes: PathStageNode[]
  displayNameByTopicKey: Map<string, string>
  onSelectNode: (stage: PathStageNode) => void
}

function toGraphStatus(status: PathStatus): GraphNodeStatus {
  if (status === 'upcoming') return 'unlocked'
  return status
}

function graphStatusTone(
  status: GraphNodeStatus,
): 'neutral' | 'info' | 'success' | 'warning' {
  if (status === 'completed') return 'success'
  if (status === 'current') return 'info'
  if (status === 'unlocked') return 'warning'
  return 'neutral'
}

function graphStatusLabel(status: GraphNodeStatus): string {
  if (status === 'completed') return 'completed'
  if (status === 'current') return 'current'
  if (status === 'unlocked') return 'ready'
  return 'locked'
}

function swotTone(bucket: SWOTBucket): 'neutral' | 'info' | 'success' | 'warning' | 'danger' {
  if (bucket === 'strength') return 'success'
  if (bucket === 'weakness') return 'danger'
  if (bucket === 'threat') return 'warning'
  return 'info'
}

function toTopicLabel(topicKey: string): string {
  const tail = topicKey.split(':').pop() || topicKey
  return tail.replace(/[-_]/g, ' ')
}

function uniqueTopicKeys(topicKeys: string[]): string[] {
  const seen = new Set<string>()
  const ordered: string[] = []
  for (const topicKey of topicKeys) {
    const normalized = topicKey.trim().toLowerCase()
    if (!normalized || seen.has(normalized)) continue
    seen.add(normalized)
    ordered.push(normalized)
  }
  return ordered
}

function PathGraph({
  stageNodes,
  displayNameByTopicKey,
  onSelectNode,
}: PathGraphProps) {
  const rowHeight = 112
  const rowTopOffset = 56
  const leftX = 26
  const rightX = 74

  const connectors = useMemo(() => {
    const points = stageNodes.map((stage, index) => ({
      stage,
      x: index % 2 === 0 ? leftX : rightX,
      y: rowTopOffset + index * rowHeight,
    }))
    const height = points.length > 0 ? points[points.length - 1].y + rowTopOffset : 112
    const paths = points.slice(1).map((point, index) => {
      const previousPoint = points[index]
      const midY = (previousPoint.y + point.y) / 2
      const targetStatus = toGraphStatus(point.stage.status)
      let tone: 'locked' | 'progress' | 'complete' = 'progress'
      if (targetStatus === 'locked') {
        tone = 'locked'
      } else if (
        toGraphStatus(previousPoint.stage.status) === 'completed' &&
        targetStatus === 'completed'
      ) {
        tone = 'complete'
      }

      return {
        key: `${index}-${point.stage.node.topic_key}`,
        tone,
        d: `M ${previousPoint.x} ${previousPoint.y} C ${previousPoint.x} ${midY}, ${point.x} ${midY}, ${point.x} ${point.y}`,
      }
    })

    return { height, paths }
  }, [stageNodes])

  const completedIndex = useMemo(() => {
    for (let index = stageNodes.length - 1; index >= 0; index -= 1) {
      if (stageNodes[index].status === 'completed') return index
    }
    return -1
  }, [stageNodes])

  const graphStyle = useMemo(
    () =>
      ({
        '--graph-row-count': String(Math.max(stageNodes.length, 1)),
        '--graph-progress': String(
          stageNodes.length > 1
            ? Math.max(0, Math.min(1, completedIndex / (stageNodes.length - 1)))
            : 0,
        ),
      }) as CSSProperties,
    [completedIndex, stageNodes.length],
  )

  return (
    <div className="learning-path__graph" style={graphStyle}>
      <div className="learning-path__graph-atmosphere" aria-hidden="true" />
      <svg
        className="learning-path__graph-connectors"
        viewBox={`0 0 100 ${connectors.height}`}
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        {connectors.paths.map((connector) => (
          <path
            key={connector.key}
            d={connector.d}
            pathLength={1}
            className={`learning-path__graph-connector learning-path__graph-connector--${connector.tone}`}
          />
        ))}
      </svg>

      <ol className="learning-path__graph-list">
        {stageNodes.map((stage) => {
          const graphStatus = toGraphStatus(stage.status)
          const lane = stage.index % 2 === 0 ? 'left' : 'right'
          const isLocked = graphStatus === 'locked'
          const isActionable = !isLocked
          const prerequisiteLabels = stage.node.prerequisite_topic_keys.map(
            (topicKey) => displayNameByTopicKey.get(topicKey) || toTopicLabel(topicKey),
          )
          const unresolvedLabels = stage.unresolvedPrerequisiteKeys.map(
            (topicKey) => displayNameByTopicKey.get(topicKey) || toTopicLabel(topicKey),
          )
          const lockHintText =
            unresolvedLabels.length > 0
              ? `Requires: ${unresolvedLabels.join(', ')}`
              : undefined
          const bucket = normalizeBucket(stage.node.swot_bucket)
          const cardClassName = [
            'learning-path__graph-card',
            `learning-path__graph-card--${graphStatus}`,
            isActionable ? 'learning-path__graph-card--actionable' : '',
          ]
            .filter(Boolean)
            .join(' ')

          const cardBody = (
            <>
              <div className="learning-path__graph-card-head">
                <div>
                  <span className="learning-path__step-kicker">Step {stage.index + 1}</span>
                  <strong>{stage.node.display_name}</strong>
                </div>
                <Badge tone={graphStatusTone(graphStatus)}>{graphStatusLabel(graphStatus)}</Badge>
              </div>
              <div className="learning-path__graph-meta">
                <span>{stage.node.subject.toUpperCase()}</span>
                <span>Mastery {Math.round(stage.node.mastery_score)}</span>
                <span>Priority {stage.node.priority_score.toFixed(1)}</span>
                <span className={`learning-path__bucket learning-path__bucket--${bucket}`}>
                  {bucket}
                </span>
              </div>
              {prerequisiteLabels.length > 0 ? (
                <p className="learning-path__prereq-note">Requires: {prerequisiteLabels.join(', ')}</p>
              ) : null}
              {isLocked && unresolvedLabels.length > 0 ? (
                <p className="learning-path__lock-note">
                  Locked by pending prerequisites: {unresolvedLabels.join(', ')}
                </p>
              ) : null}
              {isActionable ? (
                <p className="learning-path__attempt-note">Start review from this node</p>
              ) : null}
            </>
          )

          return (
            <li
              key={`${stage.node.subject}:${stage.node.topic_key}:${stage.index}`}
              className={`learning-path__graph-row learning-path__graph-row--${lane}`}
              style={
                {
                  '--path-node-index': String(stage.index),
                } as CSSProperties
              }
            >
              <div
                className={`learning-path__graph-node learning-path__graph-node--${graphStatus}`}
                title={isLocked ? lockHintText : undefined}
                aria-label={`Step ${stage.index + 1}: ${stage.node.display_name} ${graphStatusLabel(graphStatus)} node`}
              >
                <span>{stage.index + 1}</span>
              </div>

              {isActionable ? (
                <button
                  type="button"
                  className={cardClassName}
                  onClick={() => onSelectNode(stage)}
                >
                  {cardBody}
                </button>
              ) : (
                <div className={cardClassName} title={lockHintText}>
                  {cardBody}
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export default function LearningPathPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const routeState = (location.state as ReviewSessionScopeState | null) ?? null

  const [pathNodes, setPathNodes] = useState<LearningPathNode[]>([])
  const [progress, setProgress] = useState<SessionProgress | null>(null)
  const [currentCard, setCurrentCard] = useState<QuizCard | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadPathPreview = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    const topics = routeState?.topics && routeState.topics.length ? routeState.topics : undefined
    const subject = (routeState?.subject || '').trim().toLowerCase() || undefined
    const limit = typeof routeState?.limit === 'number' ? clampLimit(routeState.limit) : 10

    try {
      const preview = await startQuizSession({ topics, subject, limit })
      setPathNodes(preview.path || [])
      setProgress(preview.progress)
      setCurrentCard(preview.current_card || null)
      // Path preview uses a temporary session only to fetch scoped path metadata.
      void finishQuizSession(preview.session_id).catch(() => undefined)
    } catch (err) {
      const apiErr = err as ApiError
      setError(apiErr.detail || 'Failed to load learning path preview')
    } finally {
      setIsLoading(false)
    }
  }, [routeState?.limit, routeState?.subject, routeState?.topics])

  useEffect(() => {
    void loadPathPreview()
  }, [loadPathPreview])

  const nextScopeState = useMemo<ReviewSessionScopeState>(
    () => ({
      topics: routeState?.topics && routeState.topics.length > 0 ? routeState.topics : null,
      subject: routeState?.subject || null,
      limit: typeof routeState?.limit === 'number' ? clampLimit(routeState.limit) : 10,
    }),
    [routeState?.limit, routeState?.subject, routeState?.topics],
  )

  const currentIndex = useMemo(() => {
    if (pathNodes.length === 0) return -1
    const pointer = progress?.completed ? pathNodes.length - 1 : progress?.current_index ?? 0
    return Math.max(0, Math.min(pathNodes.length - 1, pointer))
  }, [pathNodes.length, progress?.completed, progress?.current_index])

  const displayNameByTopicKey = useMemo(() => {
    const map = new Map<string, string>()
    for (const node of pathNodes) {
      map.set(node.topic_key, node.display_name)
    }
    return map
  }, [pathNodes])

  const stageNodes = useMemo<PathStageNode[]>(() => {
    if (pathNodes.length === 0) return []
    const completedKeys = new Set(
      pathNodes.slice(0, Math.max(0, currentIndex)).map((node) => node.topic_key),
    )
    return pathNodes.map((node, index) => {
      const prerequisites = node.prerequisite_topic_keys || []
      const unresolvedPrerequisiteKeys = prerequisites.filter(
        (topicKey) => !completedKeys.has(topicKey),
      )
      let status: PathStatus
      if (index < currentIndex) {
        status = 'completed'
      } else if (index === currentIndex) {
        status = 'current'
      } else if (unresolvedPrerequisiteKeys.length > 0) {
        status = 'locked'
      } else {
        status = 'upcoming'
      }
      return { node, index, status, unresolvedPrerequisiteKeys }
    })
  }, [currentIndex, pathNodes])

  const currentNode = useMemo(
    () => stageNodes.find((entry) => entry.status === 'current') ?? null,
    [stageNodes],
  )

  const pathSummary = useMemo(() => {
    const completed = stageNodes.filter((stage) => stage.status === 'completed').length
    const ready = stageNodes.filter((stage) => stage.status === 'upcoming').length
    const locked = stageNodes.filter((stage) => stage.status === 'locked').length
    const progressPercent =
      stageNodes.length > 0 ? Math.round((completed / stageNodes.length) * 100) : 0
    return { completed, ready, locked, progressPercent }
  }, [stageNodes])

  const subjectSummaries = useMemo<SubjectSWOTSummary[]>(() => {
    const bySubject = new Map<string, SubjectSWOTSummary>()
    for (const node of pathNodes) {
      const subjectKey = node.subject.toUpperCase()
      if (!bySubject.has(subjectKey)) {
        bySubject.set(subjectKey, {
          subject: subjectKey,
          buckets: emptyBuckets(),
        })
      }
      const summary = bySubject.get(subjectKey)
      if (!summary) continue
      const bucket = normalizeBucket(node.swot_bucket)
      summary.buckets[bucket].push(node)
    }
    return Array.from(bySubject.values()).map((summary) => ({
      ...summary,
      buckets: {
        strength: [...summary.buckets.strength].sort(
          (left, right) => right.priority_score - left.priority_score,
        ),
        weakness: [...summary.buckets.weakness].sort(
          (left, right) => right.priority_score - left.priority_score,
        ),
        opportunity: [...summary.buckets.opportunity].sort(
          (left, right) => right.priority_score - left.priority_score,
        ),
        threat: [...summary.buckets.threat].sort(
          (left, right) => right.priority_score - left.priority_score,
        ),
      },
    }))
  }, [pathNodes])

  const priorityQueue = useMemo(
    () => [...pathNodes].sort((left, right) => right.priority_score - left.priority_score),
    [pathNodes],
  )

  const orderedPathTopicKeys = useMemo(
    () => uniqueTopicKeys(pathNodes.map((node) => node.topic_key)),
    [pathNodes],
  )

  // Derive subject names from path nodes for the topics filter.
  // topics should be subject names (e.g. "cn") not topic_keys (e.g. "cn:core")
  // because the backend matches topics against Topic.name.
  const subjectsFromPath = useMemo(
    () => [...new Set(pathNodes.map((node) => node.subject).filter(Boolean))],
    [pathNodes],
  )

  const reviewScopeFromPath = useMemo<ReviewSessionScopeState>(
    () => ({
      ...nextScopeState,
      topics: subjectsFromPath.length > 0 ? subjectsFromPath : nextScopeState.topics ?? null,
      pathTopicsOrdered: orderedPathTopicKeys.length > 0 ? orderedPathTopicKeys : null,
      preferredTopic: null,
      source: 'learning-path',
    }),
    [nextScopeState, orderedPathTopicKeys, subjectsFromPath],
  )

  const launchNodeReview = useCallback(
    (stage: PathStageNode) => {
      if (stage.status === 'locked') return
      const preferredTopic = stage.node.topic_key.trim().toLowerCase()
      const orderedTopics =
        preferredTopic.length > 0
          ? [preferredTopic, ...orderedPathTopicKeys.filter((topicKey) => topicKey !== preferredTopic)]
          : orderedPathTopicKeys

      navigate('/review', {
        state: {
          ...reviewScopeFromPath,
          topics: reviewScopeFromPath.topics,
          pathTopicsOrdered: orderedTopics.length > 0 ? orderedTopics : null,
          preferredTopic: preferredTopic || null,
        },
      })
    },
    [navigate, orderedPathTopicKeys, reviewScopeFromPath],
  )

  return (
    <div className="learning-path layout-stack layout-stack--lg">
      <PageHeader
        eyebrow="Planning"
        title="Learning path preview"
        subtitle="Review current node, upcoming sequence, and SWOT posture before entering the question workspace."
        backHref="/review/setup"
        backLabel="Back to setup"
      />

      {isLoading ? (
        <StateMessage title="Loading path preview" tone="info">
          Building your path from current mastery and SWOT signals.
        </StateMessage>
      ) : null}

      {error ? (
        <Card tone="default" padding="md" className="learning-path__error">
          <StateMessage title="Path unavailable" tone="danger">
            {error}
          </StateMessage>
          <div className="learning-path__error-actions">
            <Button type="button" onClick={() => void loadPathPreview()}>
              Retry
            </Button>
            <Button type="button" variant="ghost" onClick={() => navigate('/review/setup')}>
              Back to setup
            </Button>
          </div>
        </Card>
      ) : null}

      {!isLoading && !error && pathNodes.length === 0 ? (
        <Card tone="inset" padding="lg">
          <StateMessage title="No path nodes available" tone="warning">
            No eligible nodes were generated for current scope. Try broader topics or remove subject filter.
          </StateMessage>
          <div className="learning-path__actions">
            <Button type="button" variant="secondary" onClick={() => navigate('/review/setup')}>
              Adjust setup
            </Button>
            <Button
              type="button"
              onClick={() =>
                navigate('/review', {
                  state: nextScopeState,
                })
              }
            >
              Start anyway
            </Button>
          </div>
        </Card>
      ) : null}

      {!isLoading && !error && pathNodes.length > 0 ? (
        <>
          <section className="learning-path__hero-grid">
            <Card
              tone="accent"
              padding="lg"
              className="learning-path__focus"
              kicker="Current node"
              title={currentNode ? currentNode.node.display_name : 'No active node'}
              subtitle={
                currentNode
                  ? `${currentNode.node.subject.toUpperCase()} | mastery ${Math.round(currentNode.node.mastery_score)}`
                  : 'Path generation did not return a current node.'
              }
              actions={
                currentNode ? (
                  <Badge tone={swotTone(normalizeBucket(currentNode.node.swot_bucket))}>
                    {currentNode.node.swot_bucket}
                  </Badge>
                ) : undefined
              }
            >
              <div className="learning-path__focus-orbit" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
              <div className="learning-path__focus-metrics">
                <article>
                  <span>Progress</span>
                  <strong>{pathSummary.progressPercent}%</strong>
                </article>
                <article>
                  <span>Ready next</span>
                  <strong>{pathSummary.ready}</strong>
                </article>
                <article>
                  <span>Locked</span>
                  <strong>{pathSummary.locked}</strong>
                </article>
              </div>
              <div className="learning-path__focus-metrics learning-path__focus-metrics--secondary">
                <article>
                  <span>Queue</span>
                  <strong>{pathNodes.length}</strong>
                </article>
                <article>
                  <span>Limit</span>
                  <strong>{nextScopeState.limit}</strong>
                </article>
                <article>
                  <span>Question</span>
                  <strong>{currentCard ? 'ready' : 'none'}</strong>
                </article>
              </div>
              {currentNode ? (
                <div className="learning-path__focus-action">
                  <p>
                    Start here to keep the review session aligned with prerequisite order and
                    current weakness signals.
                  </p>
                  <Button type="button" onClick={() => launchNodeReview(currentNode)}>
                    Review current node
                  </Button>
                </div>
              ) : null}
            </Card>

            <Card
              tone="default"
              padding="lg"
              className="learning-path__sequence"
              kicker="Path sequence"
              title="Adaptive route"
              subtitle="Follow the lit rail. Ready nodes can start a focused review; locked nodes expose unmet prerequisites."
            >
              <div className="learning-path__sequence-toolbar">
                <div className="learning-path__graph-legend" aria-hidden="true">
                  <Badge tone="success">completed</Badge>
                  <Badge tone="info">current</Badge>
                  <Badge tone="warning">ready</Badge>
                  <Badge tone="neutral">locked</Badge>
                </div>
                <span>{pathSummary.completed}/{pathNodes.length} completed</span>
              </div>
              <PathGraph
                stageNodes={stageNodes}
                displayNameByTopicKey={displayNameByTopicKey}
                onSelectNode={launchNodeReview}
              />
            </Card>
          </section>

          <section className="learning-path__swot">
            <h2>SWOT panels by subject</h2>
            <div className="learning-path__swot-grid">
              {subjectSummaries.map((summary) => (
                <Card
                  key={summary.subject}
                  tone="default"
                  padding="md"
                  className="learning-path__swot-card"
                  kicker={summary.subject}
                  title="Subject SWOT"
                >
                  <div className="learning-path__swot-counts">
                    <Badge tone="success">S {summary.buckets.strength.length}</Badge>
                    <Badge tone="danger">W {summary.buckets.weakness.length}</Badge>
                    <Badge tone="info">O {summary.buckets.opportunity.length}</Badge>
                    <Badge tone="warning">T {summary.buckets.threat.length}</Badge>
                  </div>
                  <dl className="learning-path__swot-topics">
                    <div>
                      <dt>Weakness focus</dt>
                      <dd>
                        {summary.buckets.weakness.slice(0, 3).map((node) => node.display_name).join(', ') ||
                          'No weakness nodes in current scope.'}
                      </dd>
                    </div>
                    <div>
                      <dt>Threat watch</dt>
                      <dd>
                        {summary.buckets.threat.slice(0, 3).map((node) => node.display_name).join(', ') ||
                          'No threat nodes in current scope.'}
                      </dd>
                    </div>
                  </dl>
                </Card>
              ))}
            </div>
          </section>

          <Card
            tone="default"
            padding="lg"
            className="learning-path__priority"
            kicker="Topic queue"
            title="Priority-ordered topics"
            subtitle="Higher scores appear first and should be addressed earlier in session."
          >
            <ul className="learning-path__priority-list">
              {priorityQueue.slice(0, 10).map((node) => {
                const bucket = normalizeBucket(node.swot_bucket)
                return (
                  <li key={`${node.subject}:${node.topic_key}`}>
                    <div>
                      <strong>{node.display_name}</strong>
                      <p>
                        {node.subject.toUpperCase()} | mastery {Math.round(node.mastery_score)}
                      </p>
                    </div>
                    <div className="learning-path__priority-meta">
                      <Badge tone={swotTone(bucket)}>{bucket}</Badge>
                      <span>{node.priority_score.toFixed(1)}</span>
                    </div>
                  </li>
                )
              })}
            </ul>
          </Card>

          <section className="learning-path__actions">
            <Button
              type="button"
              variant="ghost"
              onClick={() =>
                navigate('/review/setup', {
                  state: nextScopeState,
                })
              }
            >
              Back to setup
            </Button>
            <Button
              type="button"
              size="lg"
              onClick={() =>
                navigate('/review', {
                  state: reviewScopeFromPath,
                })
              }
            >
              Enter review workspace
            </Button>
          </section>
        </>
      ) : null}
    </div>
  )
}
