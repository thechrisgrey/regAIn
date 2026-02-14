import { useState, useCallback } from 'react';
import { useAuth } from './useAuth';
import { api } from '../services/api';
import type { OnboardingData, OnboardingResponse } from '../types';

export function useOnboarding() {
  const { getToken } = useAuth();
  const [data, setData] = useState<OnboardingResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submitOnboarding = useCallback(
    async (onboardingData: OnboardingData) => {
      setLoading(true);
      setError(null);
      try {
        const token = await getToken();
        const result = await api.onboarding.create(onboardingData, token);
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setLoading(false);
      }
    },
    [getToken],
  );

  return { data, loading, error, submitOnboarding };
}
