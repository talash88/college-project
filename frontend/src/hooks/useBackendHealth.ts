'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/lib/api-client';
import { HealthResponse, BackendStatus } from '@/types/api';

export function useBackendHealth(): BackendStatus & { refetch: () => void } {
  const [status, setStatus] = useState<BackendStatus>({
    connected: false,
    loading: true,
    error: null,
    data: null,
  });

  const fetchHealth = useCallback(async () => {
    setStatus((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await apiClient.get<HealthResponse>('/api/v1/health');
      setStatus({
        connected: true,
        loading: false,
        error: null,
        data,
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setStatus({
        connected: false,
        loading: false,
        error: errorMessage,
        data: null,
      });
    }
  }, []);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  return { ...status, refetch: fetchHealth };
}