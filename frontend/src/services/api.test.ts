import { describe, it, expect, vi, afterEach, type Mock } from 'vitest';
import { api, ApiError } from './api';

const MOCK_TOKEN = 'test-jwt-token';

function mockFetchResponse(body: unknown, status = 200, ok = true) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: status === 200 ? 'OK' : 'Bad Request',
    json: () => Promise.resolve(body),
  });
}

function expectCalledWithEndpoint(
  fetchMock: Mock,
  endpoint: string,
  method: string,
) {
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining(endpoint),
    expect.objectContaining({ method }),
  );
}

describe('API service', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe('apiRequest authentication headers', () => {
    it('includes Authorization Bearer header in every request', async () => {
      globalThis.fetch = mockFetchResponse({ missions: [] });

      await api.missions.list(MOCK_TOKEN);

      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: `Bearer ${MOCK_TOKEN}`,
            'Content-Type': 'application/json',
          }),
        }),
      );
    });
  });

  describe('ApiError handling', () => {
    it('throws ApiError with statusCode on non-ok response', async () => {
      globalThis.fetch = mockFetchResponse({ error: 'Not found' }, 404, false);

      await expect(api.dashboard.get(MOCK_TOKEN)).rejects.toThrow(ApiError);

      try {
        await api.dashboard.get(MOCK_TOKEN);
      } catch (e) {
        expect(e).toBeInstanceOf(ApiError);
        expect((e as ApiError).statusCode).toBe(404);
        expect((e as ApiError).message).toBe('Not found');
      }
    });

    it('handles non-JSON error responses gracefully', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: () => Promise.reject(new Error('not json')),
      });

      await expect(api.dashboard.get(MOCK_TOKEN)).rejects.toThrow(ApiError);

      try {
        await api.dashboard.get(MOCK_TOKEN);
      } catch (e) {
        expect((e as ApiError).statusCode).toBe(500);
        expect((e as ApiError).message).toBe('Internal Server Error');
      }
    });
  });

  describe('typed API functions', () => {
    it('calls POST /onboarding for onboarding.create', async () => {
      const data = { email: 'test@example.com', firstName: 'Test', lastName: 'User', persona: 'veteran' as const, currentRole: 'QA Lead', targetRole: 'Engineer' };
      globalThis.fetch = mockFetchResponse({ userId: '123' });

      await api.onboarding.create(data, MOCK_TOKEN);

      expectCalledWithEndpoint(globalThis.fetch as unknown as Mock, '/onboarding', 'POST');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ body: JSON.stringify(data) }),
      );
    });

    it('calls GET /missions for missions.list', async () => {
      globalThis.fetch = mockFetchResponse({ missions: [] });

      await api.missions.list(MOCK_TOKEN);

      expectCalledWithEndpoint(globalThis.fetch as unknown as Mock, '/missions', 'GET');
    });

    it('calls POST /missions/{id}/complete for missions.complete', async () => {
      const data = { reflection: 'done', skillTags: ['python'] };
      globalThis.fetch = mockFetchResponse({ success: true });

      await api.missions.complete('m-1', data, MOCK_TOKEN);

      expectCalledWithEndpoint(globalThis.fetch as unknown as Mock, '/missions/m-1/complete', 'POST');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ body: JSON.stringify(data) }),
      );
    });

    it('calls GET /evidence for evidence.list', async () => {
      globalThis.fetch = mockFetchResponse({ evidence: [] });

      await api.evidence.list(MOCK_TOKEN);

      expectCalledWithEndpoint(globalThis.fetch as unknown as Mock, '/evidence', 'GET');
    });

    it('appends skill_tag query param when provided', async () => {
      globalThis.fetch = mockFetchResponse({ evidence: [] });

      await api.evidence.list(MOCK_TOKEN, 'python');

      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/evidence?skill_tag=python'),
        expect.any(Object),
      );
    });

    it('calls GET /dashboard for dashboard.get', async () => {
      globalThis.fetch = mockFetchResponse({ campaign: {} });

      await api.dashboard.get(MOCK_TOKEN);

      expectCalledWithEndpoint(globalThis.fetch as unknown as Mock, '/dashboard', 'GET');
    });

    it('calls POST /coaching/checkin for coaching.checkin', async () => {
      const data = { message: 'Hello coach', session_type: 'checkin' as const };
      globalThis.fetch = mockFetchResponse({ response: 'Hi there', userId: 'u-1' });

      await api.coaching.checkin(data, MOCK_TOKEN);

      expectCalledWithEndpoint(globalThis.fetch as unknown as Mock, '/coaching/checkin', 'POST');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ body: JSON.stringify(data) }),
      );
    });
  });
});
