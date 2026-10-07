import { AxiosError } from 'axios';
import { apiClient, setAccessToken } from './api-client';
import { API_ENDPOINTS } from './api-config';
import type { ApiErrorBody, AuthUser, RegisterResponse, TokenResponse, UserRole } from '@/types/api';

export interface LoginInput {
  email: string;
  password: string;
}

export interface RegisterInput {
  full_name: string;
  email: string;
  password: string;
  role: Extract<UserRole, 'REPORTER' | 'SOLVER'>;
}

/** Extract a human-readable message from a failed API call. */
export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof AxiosError) {
    if (!error.response) {
      return 'Cannot reach the backend. Make sure it is running on http://localhost:8000.';
    }
    const body = error.response.data as ApiErrorBody | undefined;
    const detail = body?.detail;
    if (typeof detail === 'string' && detail.length > 0) {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      if (typeof first === 'string') return first;
      if (first?.msg) return first.msg;
    }
    if (error.response.status === 401) return 'Invalid email or password.';
  }
  return fallback;
}

export async function loginRequest(input: LoginInput): Promise<{ token: TokenResponse; user: AuthUser }> {
  const token = await apiClient.post<TokenResponse>(API_ENDPOINTS.auth.login, input);
  setAccessToken(token.access_token);
  const user = await apiClient.get<AuthUser>(API_ENDPOINTS.auth.me);
  return { token, user };
}

export async function registerRequest(input: RegisterInput): Promise<{ response: RegisterResponse; user: AuthUser }> {
  const response = await apiClient.post<RegisterResponse>(API_ENDPOINTS.auth.register, input);
  setAccessToken(response.access_token);
  return { response, user: response.user };
}

export async function logoutRequest(): Promise<void> {
  try {
    await apiClient.post(API_ENDPOINTS.auth.logout, {});
  } catch {
    // Logout is best-effort: the session may already be expired.
  } finally {
    setAccessToken(null);
  }
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  return apiClient.get<AuthUser>(API_ENDPOINTS.auth.me);
}
