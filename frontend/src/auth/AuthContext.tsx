import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'

import { useAuth as useClerkAuth, useUser as useClerkUser } from '@clerk/react'

import { clerkLogin, getMe } from '../api/auth'
import { setAuthFailureHandler, tokenManager } from '../api/client'
import type { TokenResponse, UserOut } from '../api/types'

type AuthStatus = 'unknown' | 'authenticated' | 'unauthenticated'

export interface AuthContextValue {
  status: AuthStatus
  user: UserOut | null
  accessToken: string | null
  refreshToken: string | null
  setTokenPair: (tokens: TokenResponse) => void
  clearSession: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const ACCESS_KEY = 'csrag.access_token'
const REFRESH_KEY = 'csrag.refresh_token'

function readStoredToken(key: string): string | null {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStoredToken(key: string, value: string | null) {
  try {
    if (value === null) sessionStorage.removeItem(key)
    else sessionStorage.setItem(key, value)
  } catch {
    // ignore
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(() =>
    readStoredToken(ACCESS_KEY)
  )
  const [refreshToken, setRefreshToken] = useState<string | null>(() =>
    readStoredToken(REFRESH_KEY)
  )
  const [user, setUser] = useState<UserOut | null>(null)
  const [status, setStatus] = useState<AuthStatus>('unknown')

  const clerkAuth = useClerkAuth()
  const clerkUser = useClerkUser()
  const exchangeAttempted = useRef(false)

  const clearSession = () => {
    setAccessToken(null)
    setRefreshToken(null)
    setUser(null)
    setStatus('unauthenticated')
    tokenManager.clear()
    writeStoredToken(ACCESS_KEY, null)
    writeStoredToken(REFRESH_KEY, null)
  }

  const setTokenPair = (tokens: TokenResponse) => {
    setAccessToken(tokens.access_token)
    setRefreshToken(tokens.refresh_token)
    tokenManager.setTokens(tokens.access_token, tokens.refresh_token)
    writeStoredToken(ACCESS_KEY, tokens.access_token)
    writeStoredToken(REFRESH_KEY, tokens.refresh_token)
  }

  const refreshUser = async () => {
    if (!tokenManager.getAccessToken()) {
      setStatus('unauthenticated')
      setUser(null)
      return
    }
    const me = await getMe()
    setUser(me)
    setStatus('authenticated')
  }

  // On mount: ensure tokenManager has whatever we stored.
  useEffect(() => {
    if (accessToken && refreshToken) {
      tokenManager.setTokens(accessToken, refreshToken)
    } else {
      tokenManager.clear()
    }
  }, [accessToken, refreshToken])

  // On auth failure from API client: clear tokens.
  useEffect(() => {
    setAuthFailureHandler(() => {
      clearSession()
    })
  }, [])

  // Validate existing tokens by fetching /me whenever accessToken changes.
  useEffect(() => {
    let cancelled = false
    const run = async () => {
      if (!accessToken) {
        if (!cancelled) {
          setUser(null)
          // Only mark unauthenticated if Clerk has finished loading and user is not signed in.
          if (clerkAuth.isLoaded && !clerkAuth.isSignedIn) {
            setStatus('unauthenticated')
          }
        }
        return
      }
      tokenManager.setTokens(accessToken, refreshToken || '')
      try {
        const me = await getMe()
        if (cancelled) return
        setUser(me)
        setStatus('authenticated')
      } catch {
        if (cancelled) return
        // Stored token is invalid — clear it.
        clearSession()
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [accessToken])

  // Sync Clerk sign-in state with our backend tokens.
  useEffect(() => {
    let cancelled = false

    const run = async () => {
      if (!clerkAuth.isLoaded) return

      if (clerkAuth.isSignedIn) {
        // If we already have backend tokens, nothing to do.
        if (accessToken) return

        // Avoid duplicate exchange attempts.
        if (exchangeAttempted.current) return
        exchangeAttempted.current = true

        const email = clerkUser.user?.primaryEmailAddress?.emailAddress
        const username = clerkUser.user?.username || email?.split('@')[0] || 'user'
        const clerkUserId = clerkUser.user?.id

        if (!email || !clerkUserId) {
          if (!cancelled) setStatus('unauthenticated')
          return
        }

        try {
          const tokens = await clerkLogin({
            clerk_user_id: clerkUserId,
            email,
            username,
          })
          if (cancelled) return
          setTokenPair(tokens)
          // /me will be fetched by the accessToken effect above.
        } catch {
          if (cancelled) return
          setStatus('unauthenticated')
        }
      } else {
        // Clerk says user is signed out — clear our session too.
        exchangeAttempted.current = false
        if (accessToken) {
          clearSession()
        } else if (status !== 'unauthenticated') {
          setStatus('unauthenticated')
        }
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [clerkAuth.isLoaded, clerkAuth.isSignedIn, accessToken])

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      accessToken,
      refreshToken,
      setTokenPair,
      clearSession,
      refreshUser,
    }),
    [status, user, accessToken, refreshToken]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}
