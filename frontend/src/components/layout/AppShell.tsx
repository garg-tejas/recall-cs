import type { ReactNode } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { UserButton, useAuth as useClerkAuth } from '@clerk/react'

import { cx } from '../ui/cx'

type ShellMode = 'workspace' | 'auth' | 'plain'
type ShellWidth = 'narrow' | 'content' | 'wide'

export interface AppShellProps {
  mode?: ShellMode
  width?: ShellWidth
  children?: ReactNode
}

export default function AppShell({
  mode = 'workspace',
  width = 'content',
  children,
}: AppShellProps) {
  const location = useLocation()
  const breadcrumb = resolveBreadcrumbLabel(location.pathname)
  const clerkAuth = useClerkAuth()

  return (
    <div className={cx('app-shell', `app-shell--${mode}`)}>
      <div className="app-shell__orb app-shell__orb--a" aria-hidden="true" />
      <div className="app-shell__orb app-shell__orb--b" aria-hidden="true" />
      {mode === 'workspace' ? (
        <header className={cx('app-shell__nav', `app-shell__nav--${width}`)}>
          <Link to="/" className="app-shell__brand">
            <span className="app-shell__brand-mark" aria-hidden="true" />
            Signal Lab
          </Link>
          <p className="app-shell__crumb" aria-live="polite">
            {breadcrumb}
          </p>
          {clerkAuth.isSignedIn ? (
            <div className="app-shell__user">
              <UserButton />
            </div>
          ) : null}
        </header>
      ) : null}
      <main className={cx('app-shell__content', `app-shell__content--${width}`)}>
        {children ?? <Outlet />}
      </main>
    </div>
  )
}

function resolveBreadcrumbLabel(pathname: string): string {
  const labelByPathname: Record<string, string> = {
    '/': 'Landing',
    '/dashboard': 'Dashboard',
    '/review/setup': 'Review Setup',
    '/review/path': 'Learning Path',
    '/review': 'Review Workspace',
    '/review/summary': 'Session Summary',
    '/login': 'Login',
    '/signup': 'Signup',
    '/tutor': 'AI Tutor',
  }

  if (labelByPathname[pathname]) return labelByPathname[pathname]
  if (pathname.startsWith('/review')) return 'Review'
  return 'Workspace'
}
