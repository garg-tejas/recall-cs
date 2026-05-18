/**
 * Auth API endpoints.
 */

import { apiRequest } from './client'
import type {
  ClerkLoginRequest,
  SignupRequest,
  LoginRequest,
  RefreshRequest,
  TokenResponse,
  UserOut,
} from './types'

export async function signup(data: SignupRequest): Promise<TokenResponse> {
  return apiRequest<TokenResponse>('/auth/signup', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function login(data: LoginRequest): Promise<TokenResponse> {
  return apiRequest<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function clerkLogin(data: ClerkLoginRequest): Promise<TokenResponse> {
  return apiRequest<TokenResponse>('/auth/clerk', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function refresh(data: RefreshRequest): Promise<TokenResponse> {
  return apiRequest<TokenResponse>('/auth/refresh', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getMe(): Promise<UserOut> {
  return apiRequest<UserOut>('/auth/me', {
    method: 'GET',
  })
}
