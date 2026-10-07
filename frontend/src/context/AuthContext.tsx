'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { apiClient, setAccessToken } from '@/lib/api-client';
import {
  fetchCurrentUser,
  getApiErrorMessage,
  loginRequest,
  logoutRequest,
  registerRequest,
  type LoginInput,
  type RegisterInput,
} from '@/lib/auth-service';
import type { AuthUser } from '@/types/api';

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  initializing: boolean;
  error: string | null;
  login: (_input: LoginInput) => Promise<void>;
  register: (_input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Session restoration on mount: use the HttpOnly refresh cookie (if any)
  // to silently obtain a fresh access token, then load the current user.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const token = await apiClient.refreshAccessToken();
      if (cancelled) return;
      if (token) {
        try {
          const me = await fetchCurrentUser();
          if (!cancelled) setUser(me);
        } catch {
          if (!cancelled) setUser(null);
        }
      }
      if (!cancelled) setInitializing(false);
    })();

    const onExpired = () => setUser(null);
    window.addEventListener('campusxolve:session-expired', onExpired);
    return () => {
      cancelled = true;
      window.removeEventListener('campusxolve:session-expired', onExpired);
    };
  }, []);

  const login = useCallback(async (input: LoginInput) => {
    setLoading(true);
    setError(null);
    try {
      const { user: me } = await loginRequest(input);
      setUser(me);
    } catch (err) {
      setAccessToken(null);
      const message = getApiErrorMessage(err, 'Login failed. Please try again.');
      setError(message);
      throw new Error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    setLoading(true);
    setError(null);
    try {
      const { user: me } = await registerRequest(input);
      setUser(me);
    } catch (err) {
      setAccessToken(null);
      const message = getApiErrorMessage(err, 'Registration failed. Please try again.');
      setError(message);
      throw new Error(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setLoading(true);
    try {
      await logoutRequest();
    } finally {
      setUser(null);
      setLoading(false);
    }
  }, []);

  const refreshUser = useCallback(async () => {
    const me = await fetchCurrentUser();
    setUser(me);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, initializing, error, login, register, logout, refreshUser, clearError }),
    [user, loading, initializing, error, login, register, logout, refreshUser, clearError]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
