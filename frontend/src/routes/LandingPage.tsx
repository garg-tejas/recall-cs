import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Card from '../components/ui/Card'
import { usePageTitle } from '../hooks/usePageTitle'
import './landing.css'

interface LandingStep {
  title: string
  detail: string
  icon: string
}

interface LandingCta {
  primaryLabel: string
  primaryTarget: string
  secondaryLabel: string
  secondaryTarget: string
  supportLabel: string
  supportTarget: string
}

const workflowSteps: LandingStep[] = [
  {
    icon: '⊹',
    title: 'Capture weak spots',
    detail: 'Spin up a focused card set by topic so each session attacks what is slipping now.',
  },
  {
    icon: '◎',
    title: 'Get instant feedback',
    detail: 'Score quality, see concise guidance, and close each card with a clear next action.',
  },
  {
    icon: '⟳',
    title: 'Lock retention rhythm',
    detail: 'Track due and overdue load so daily review stays short, consistent, and compounding.',
  },
]

export default function LandingPage() {
  usePageTitle('')
  const { status, user } = useAuth()
  const navigate = useNavigate()

  const cta = useMemo<LandingCta>(() => {
    if (status === 'authenticated') {
      return {
        primaryLabel: 'Open dashboard',
        primaryTarget: '/dashboard',
        secondaryLabel: 'Resume review',
        secondaryTarget: '/review',
        supportLabel: 'Jump into review',
        supportTarget: '/review',
      }
    }

    return {
      primaryLabel: 'Start for free',
      primaryTarget: '/signup',
      secondaryLabel: 'I already have an account',
      secondaryTarget: '/login',
      supportLabel: 'Log in to continue',
      supportTarget: '/login',
    }
  }, [status])

  return (
    <div className="landing layout-stack layout-stack--lg">
      <section className="landing-hero" aria-label="Product overview">
        <div className="landing-hero__glow landing-hero__glow--a" aria-hidden="true" />
        <div className="landing-hero__glow landing-hero__glow--b" aria-hidden="true" />

        <header className="landing-hero__topbar">
          <p className="landing-hero__mode">
            <span className="landing-hero__brand-mark" aria-hidden="true" />
            Recall.cs workflow
          </p>
          <div className="landing-hero__topbar-actions">
            <Badge tone={status === 'authenticated' ? 'success' : 'info'}>
              {status === 'authenticated'
                ? `Signed in as ${user?.username ?? 'member'}`
                : 'Built for consistent recall'}
            </Badge>
          </div>
        </header>

        <div className="landing-hero__content">
          <div className="landing-hero__copy">
            <p className="landing-hero__eyebrow">Memory training, not random quizzes</p>
            <h1 className="landing-hero__title">
              Give your study loop a control room with clear next moves.
            </h1>
            <p className="landing-hero__subtitle">
              Recall.cs helps you review what matters now, score every response, and keep
              retention climbing with short daily sprints.
            </p>

            <div className="landing-hero__actions">
              <Button
                size="lg"
                onClick={() => navigate(cta.primaryTarget)}
              >
                {cta.primaryLabel}
              </Button>
              <Button
                size="lg"
                variant="ghost"
                onClick={() => navigate(cta.secondaryTarget)}
              >
                {cta.secondaryLabel}
              </Button>
            </div>

            <ul className="landing-hero__proof-list">
              <li>Topic-scoped review sessions</li>
              <li>Actionable per-answer feedback</li>
              <li>Daily due and overdue tracking</li>
            </ul>
          </div>

          <div className="landing-hero__preview" aria-label="Product preview">
            <div className="landing-hero__preview-topbar">
              <span className="landing-hero__preview-pill">OS · Memory Management</span>
              <span className="landing-hero__preview-count">Card 3 / 12</span>
            </div>
            <div className="landing-hero__preview-question">
              <p className="landing-hero__preview-label">Question</p>
              <p className="landing-hero__preview-text">
                Explain the difference between internal and external fragmentation. Which does paging solve?
              </p>
            </div>
            <div className="landing-hero__preview-answer">
              <p className="landing-hero__preview-label">Answer</p>
              <p className="landing-hero__preview-text landing-hero__preview-text--muted">
                Internal fragmentation is wasted space inside allocated blocks. External is free space scattered in unusable chunks. Paging eliminates external fragmentation by using fixed-size frames.
              </p>
            </div>
            <div className="landing-hero__preview-feedback">
              <div className="landing-hero__preview-score">
                <span className="landing-hero__preview-score-value">4</span>
                <span className="landing-hero__preview-score-max">/ 5</span>
                <span className="landing-hero__preview-score-label">Good recall</span>
              </div>
              <p className="landing-hero__preview-hint">
                Mention that paging introduces internal fragmentation in the last frame.
              </p>
            </div>
            <div className="landing-hero__preview-actions">
              <span className="landing-hero__preview-btn">Next card →</span>
              <span className="landing-hero__preview-meta">Due again in 4 days</span>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-workflow" aria-label="How it works">
        {workflowSteps.map((step, index) => (
          <div
            key={step.title}
            className={`landing-workflow__card landing-workflow__card--${index}`}
          >
            <div className="landing-workflow__icon" aria-hidden="true">{step.icon}</div>
            <p className="landing-workflow__kicker">Step {index + 1}</p>
            <h3 className="landing-workflow__title">{step.title}</h3>
            <p className="landing-workflow__detail">{step.detail}</p>
          </div>
        ))}
      </section>

      <section className="landing-final-cta" aria-label="Call to action">
        <h2>Ready to make review sessions feel deliberate?</h2>
        <p>
          Start with your current topics and run one focused loop today.
        </p>
        <div className="landing-final-cta__actions">
          <Button size="lg" onClick={() => navigate(cta.primaryTarget)}>
            {cta.primaryLabel}
          </Button>
          <Button size="lg" variant="secondary" onClick={() => navigate(cta.supportTarget)}>
            {cta.supportLabel}
          </Button>
        </div>
      </section>
    </div>
  )
}
