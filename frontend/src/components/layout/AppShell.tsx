import type { ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { UserButton, useAuth as useClerkAuth } from '@clerk/react'
import { cx } from '../ui/cx'

type ShellMode = 'workspace' | 'auth' | 'plain'
type ShellWidth = 'narrow' | 'content' | 'wide'
export interface AppShellProps { mode?: ShellMode; width?: ShellWidth; children?: ReactNode }

export function StudyFrame({ mode = 'workspace', width = 'content', children, account }: AppShellProps & { account?: ReactNode }) {
  const location = useLocation()
  return <div className={cx('app-shell', `app-shell--${mode}`)}>
    <a className="study-skip" href="#study-content">Skip to study content</a>
    {mode === 'workspace' ? <header className="app-shell__nav">
      <Link to="/" className="app-shell__brand"><span className="app-shell__brand-mark" aria-hidden="true">r.</span><span>Recall.cs<small>A COMPUTER SCIENCE STUDY</small></span></Link>
      <nav className="study-nav" aria-label="Study navigation">
        <NavLink to="/dashboard">Study desk</NavLink>
        <NavLink to="/review/setup" className={location.pathname.startsWith('/review') ? 'active' : undefined}>Practice</NavLink>
        <NavLink to="/tutor">Ask the textbook</NavLink>
      </nav>
      <div className="app-shell__user">{account}</div>
    </header> : null}
    <main id="study-content" tabIndex={-1} className={cx('app-shell__content', `app-shell__content--${width}`)}>{children ?? <Outlet />}</main>
    {mode === 'workspace' ? <footer className="study-footer"><span>Recall.cs / Study with a reference.</span><span>Question → Recall → Check → Revisit</span></footer> : null}
  </div>
}

export default function AppShell(props: AppShellProps) {
  const { isSignedIn } = useClerkAuth()
  return <StudyFrame {...props} account={isSignedIn ? <UserButton /> : <Link to="/login">Sign in →</Link>} />
}
