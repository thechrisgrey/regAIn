import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useOnboarding } from './useOnboarding';
import { api } from '../services/api';

vi.mock('./useAuth', () => ({
  useAuth: vi.fn(() => ({
    getToken: vi.fn().mockResolvedValue('mock-token'),
  })),
}));

vi.mock('../services/api', () => ({
  api: {
    onboarding: {
      create: vi.fn(),
    },
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

const sampleOnboardingData = {
  email: 'test@example.com',
  firstName: 'Jane',
  lastName: 'Doe',
  persona: 'veteran' as const,
  currentRole: 'QA Lead',
  targetRole: 'Software Engineer',
};

describe('useOnboarding', () => {
  describe('initial state', () => {
    it('initializes with null data, no loading, no error', () => {
      const { result } = renderHook(() => useOnboarding());

      expect(result.current.data).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
    });
  });

  describe('submitOnboarding', () => {
    it('calls API with correct data and token', async () => {
      const mockResponse = { userId: 'u1', campaignId: 'c1', profile: { userId: 'u1', email: 'test@example.com', name: 'Jane Doe', persona: 'veteran' as const, onboardingCompleted: true, createdAt: '2025-01-01' } };
      (api.onboarding.create as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const { result } = renderHook(() => useOnboarding());

      await act(async () => {
        await result.current.submitOnboarding(sampleOnboardingData);
      });

      expect(api.onboarding.create).toHaveBeenCalledWith(sampleOnboardingData, 'mock-token');
    });

    it('populates data on success', async () => {
      const mockResponse = { userId: 'u1', campaignId: 'c1', profile: { userId: 'u1', email: 'test@example.com', name: 'Jane Doe', persona: 'veteran' as const, onboardingCompleted: true, createdAt: '2025-01-01' } };
      (api.onboarding.create as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

      const { result } = renderHook(() => useOnboarding());

      await act(async () => {
        await result.current.submitOnboarding(sampleOnboardingData);
      });

      expect(result.current.data).toEqual(mockResponse);
      expect(result.current.error).toBeNull();
    });

    it('sets loading during submission', async () => {
      let resolveApi: (value: unknown) => void;
      (api.onboarding.create as ReturnType<typeof vi.fn>).mockImplementation(
        () => new Promise((resolve) => { resolveApi = resolve; }),
      );

      const { result } = renderHook(() => useOnboarding());

      let submitPromise: Promise<void>;
      await act(async () => {
        submitPromise = result.current.submitOnboarding(sampleOnboardingData);
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(result.current.loading).toBe(true);

      await act(async () => {
        resolveApi!({ userId: 'u1', campaignId: 'c1', profile: {} });
        await submitPromise!;
      });

      expect(result.current.loading).toBe(false);
    });

    it('handles API errors', async () => {
      (api.onboarding.create as ReturnType<typeof vi.fn>).mockRejectedValue(
        new Error('Validation failed'),
      );

      const { result } = renderHook(() => useOnboarding());

      await act(async () => {
        await result.current.submitOnboarding(sampleOnboardingData);
      });

      expect(result.current.error).toBe('Validation failed');
      expect(result.current.data).toBeNull();
      expect(result.current.loading).toBe(false);
    });

    it('resets error on subsequent success', async () => {
      (api.onboarding.create as ReturnType<typeof vi.fn>)
        .mockRejectedValueOnce(new Error('First failure'))
        .mockResolvedValueOnce({ userId: 'u1', campaignId: 'c1', profile: {} });

      const { result } = renderHook(() => useOnboarding());

      await act(async () => {
        await result.current.submitOnboarding(sampleOnboardingData);
      });
      expect(result.current.error).toBe('First failure');

      await act(async () => {
        await result.current.submitOnboarding(sampleOnboardingData);
      });
      expect(result.current.error).toBeNull();
    });

    it('passes token correctly to API', async () => {
      (api.onboarding.create as ReturnType<typeof vi.fn>).mockResolvedValue({ userId: 'u1', campaignId: 'c1', profile: {} });

      const { result } = renderHook(() => useOnboarding());

      await act(async () => {
        await result.current.submitOnboarding(sampleOnboardingData);
      });

      const calledToken = (api.onboarding.create as ReturnType<typeof vi.fn>).mock.calls[0][1];
      expect(calledToken).toBe('mock-token');
    });
  });
});
