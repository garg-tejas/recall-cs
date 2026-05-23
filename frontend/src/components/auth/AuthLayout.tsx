import type { ReactNode } from 'react'

interface AuthLayoutProps {
  mode: 'login' | 'signup'
  title: string
  subtitle: string
  children: ReactNode
  footer?: ReactNode
}

export default function AuthLayout({
  mode,
  title,
  subtitle,
  children,
  footer,
}: AuthLayoutProps) {
  const modeLabel = mode === 'login' ? 'Returning learner' : 'New learner'

  return (
    <section className={`auth-layout auth-layout--${mode}`}>
      <aside className="auth-layout__brand" aria-label="Recall.cs overview">
        <p className="auth-layout__eyebrow">Recall.cs</p>
        <h1 className="auth-layout__headline">Train recall like a high-signal system.</h1>
        <p className="auth-layout__description">
          Daily adaptive reviews across OS, DBMS, and CN with measurable progress.
        </p>
        <ul className="auth-layout__pillars">
          <li>Spaced repetition queue with due/overdue priorities</li>
          <li>LLM-assisted feedback to tighten conceptual answers</li>
          <li>Topic-level progress so weak areas are visible early</li>
        </ul>
      </aside>

      <div className="auth-layout__panel">
        <header className="auth-layout__header">
          <p className="auth-layout__mode">{modeLabel}</p>
          <h2 className="auth-layout__title">{title}</h2>
          <p className="auth-layout__subtitle">{subtitle}</p>
        </header>

        <div className="auth-layout__body">{children}</div>
        {footer ? <footer className="auth-layout__footer">{footer}</footer> : null}
      </div>
    </section>
  )
}
