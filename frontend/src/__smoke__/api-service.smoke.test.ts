/**
 * Smoke: API service
 *
 * Verifies the api module exports the expected interface and that
 * basic request/response flows work. Does NOT test live backends --
 * all fetch calls are mocked.
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { api, ApiError, cachedGet } from '../services/api';
import { requestCache } from '../services/cache';

const MOCK_TOKEN = 'smoke-test-token';

function mockFetch(body: unknown, status = 200, ok = true) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    json: () => Promise.resolve(body),
  });
}

describe('Smoke: API service', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    requestCache.clear();
  });

  // -- Module shape --

  it('exports api object with all expected namespaces', () => {
    // Confirms the API surface matches what the app consumes
    expect(api).toBeTruthy();
    expect(api.onboarding).toBeTruthy();
    expect(api.missions).toBeTruthy();
    expect(api.evidence).toBeTruthy();
    expect(api.dashboard).toBeTruthy();
    expect(api.coaching).toBeTruthy();
    expect(api.resume).toBeTruthy();
    expect(api.voicePractice).toBeTruthy();
    expect(api.profile).toBeTruthy();
    expect(api.onet).toBeTruthy();
    expect(api.analytics).toBeTruthy();
  });

  it('exports ApiError class', () => {
    // ApiError is used throughout the app for typed error handling
    const err = new ApiError('test', 500);
    expect(err).toBeInstanceOf(Error);
    expect(err.statusCode).toBe(500);
    expect(err.message).toBe('test');
    expect(err.name).toBe('ApiError');
  });

  it('exports cachedGet function', () => {
    // cachedGet is used by Layout for prefetching and by api.dashboard/missions/evidence
    expect(typeof cachedGet).toBe('function');
  });

  // -- Basic request flow --

  it('dashboard.get sends GET with Authorization header', async () => {
    // Confirms the API client adds proper auth headers
    globalThis.fetch = mockFetch({ campaign: {}, stats: {} });

    await api.dashboard.get(MOCK_TOKEN);

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

  it('missions.list returns missions array', async () => {
    // Confirms a basic GET endpoint returns deserialized data
    globalThis.fetch = mockFetch({
      missions: [{ missionId: 'm-1', title: 'Test' }],
      nextCursor: null,
      dailyRemaining: 3,
      dailyLimit: 6,
    });

    const result = await api.missions.list(MOCK_TOKEN);
    expect(result.missions).toHaveLength(1);
    expect(result.missions[0].missionId).toBe('m-1');
  });

  it('throws ApiError on non-ok response', async () => {
    // The app depends on ApiError for error handling in hooks
    globalThis.fetch = mockFetch({ error: 'Not found' }, 404, false);

    await expect(api.dashboard.get(MOCK_TOKEN)).rejects.toThrow(ApiError);
  });

  // -- API namespaces have expected methods --

  it('missions namespace has list, complete, generate', () => {
    expect(typeof api.missions.list).toBe('function');
    expect(typeof api.missions.complete).toBe('function');
    expect(typeof api.missions.generate).toBe('function');
  });

  it('evidence namespace has list and suggestTags', () => {
    expect(typeof api.evidence.list).toBe('function');
    expect(typeof api.evidence.suggestTags).toBe('function');
  });

  it('profile namespace has delete and recover', () => {
    expect(typeof api.profile.delete).toBe('function');
    expect(typeof api.profile.recover).toBe('function');
  });

  it('onet namespace has search and careerDetail', () => {
    expect(typeof api.onet.search).toBe('function');
    expect(typeof api.onet.careerDetail).toBe('function');
  });
});
