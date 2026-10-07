import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { API_CONFIG, API_ENDPOINTS } from './api-config';

// Short-lived access token lives in memory only. The long-lived refresh
// token lives in a secure HttpOnly cookie managed by the backend and is
// never stored in localStorage.
let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

interface RetryableRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

class ApiClient {
  private client: AxiosInstance;
  private refreshPromise: Promise<string | null> | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: API_CONFIG.baseUrl,
      timeout: API_CONFIG.timeout,
      withCredentials: true, // send the HttpOnly refresh cookie
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.client.interceptors.request.use(
      (config: InternalAxiosRequestConfig) => {
        if (accessToken) {
          config.headers.set('Authorization', `Bearer ${accessToken}`);
        }
        return config;
      },
      (error: AxiosError) => Promise.reject(error)
    );

    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError) => {
        const originalRequest = error.config as RetryableRequestConfig | undefined;
        if (!error.response || !originalRequest) {
          if (error.code === 'ECONNREFUSED' || error.code === 'ERR_NETWORK') {
            console.warn('Backend unavailable:', error.message);
          }
          return Promise.reject(error);
        }

        const status = error.response.status;
        const url = originalRequest.url || '';
        const isAuthEndpoint =
          url.includes('/auth/login') || url.includes('/auth/register') || url.includes('/auth/refresh');

        // Automatic access-token refresh: exactly one retry, never for the
        // auth endpoints themselves (avoids infinite refresh loops).
        if (status === 401 && !originalRequest._retry && !isAuthEndpoint) {
          originalRequest._retry = true;
          const refreshed = await this.refreshAccessToken();
          if (refreshed) {
            originalRequest.headers.set('Authorization', `Bearer ${refreshed}`);
            return this.client.request(originalRequest);
          }
          setAccessToken(null);
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('campusxolve:session-expired'));
          }
        }
        return Promise.reject(error);
      }
    );
  }

  /** Single-flight refresh using the HttpOnly cookie. Returns the new token or null. */
  async refreshAccessToken(): Promise<string | null> {
    if (this.refreshPromise) {
      return this.refreshPromise;
    }
    this.refreshPromise = (async () => {
      try {
        const response = await axios.post<{ access_token: string }>(
          `${API_CONFIG.baseUrl}${API_ENDPOINTS.auth.refresh}`,
          {},
          { withCredentials: true, timeout: API_CONFIG.timeout }
        );
        const token = response.data.access_token;
        setAccessToken(token);
        return token;
      } catch {
        setAccessToken(null);
        return null;
      } finally {
        this.refreshPromise = null;
      }
    })();
    return this.refreshPromise;
  }

  get instance(): AxiosInstance {
    return this.client;
  }

  async get<T>(url: string): Promise<T> {
    const response = await this.client.get<T>(url);
    return response.data;
  }

  async post<T>(url: string, data?: unknown): Promise<T> {
    const response = await this.client.post<T>(url, data);
    return response.data;
  }

  async patch<T>(url: string, data?: unknown): Promise<T> {
    const response = await this.client.patch<T>(url, data);
    return response.data;
  }

  async delete<T>(url: string): Promise<T> {
    const response = await this.client.delete<T>(url);
    return response.data;
  }
}

export const apiClient = new ApiClient();
