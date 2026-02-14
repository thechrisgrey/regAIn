import { describe, it, expect, vi, afterEach } from 'vitest';
import * as fc from 'fast-check';
import { api } from './api';

/**
 * Property 12: API Request Authentication
 *
 * For all API client functions in the frontend service layer,
 * each function should include the Authorization header with the JWT token.
 *
 * Validates: Requirements 7.8
 */

function mockFetch() {
  const calls: RequestInit[] = [];
  globalThis.fetch = vi.fn((_url: string | URL | Request, init?: RequestInit) => {
    if (init) calls.push(init);
    return Promise.resolve({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: () => Promise.resolve({}),
    } as Response);
  });
  return calls;
}

/** Non-empty string arbitrary for JWT-like tokens. */
const arbToken = fc.string({ minLength: 1 });

describe('Property 12: API Request Authentication', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('onboarding.create includes Authorization: Bearer {token}', async () => {
    await fc.assert(
      fc.asyncProperty(arbToken, async (token) => {
        const calls = mockFetch();
        await api.onboarding.create(
          { email: 'a@b.c', name: 'X', persona: 'veteran', targetRole: 'Dev' },
          token,
        );
        expect(calls).toHaveLength(1);
        const headers = calls[0].headers as Record<string, string>;
        expect(headers['Authorization']).toBe(`Bearer ${token}`);
      }),
      { numRuns: 100 },
    );
  });

  it('missions.list includes Authorization: Bearer {token}', async () => {
    await fc.assert(
      fc.asyncProperty(arbToken, async (token) => {
        const calls = mockFetch();
        await api.missions.list(token);
        expect(calls).toHaveLength(1);
        const headers = calls[0].headers as Record<string, string>;
        expect(headers['Authorization']).toBe(`Bearer ${token}`);
      }),
      { numRuns: 100 },
    );
  });

  it('missions.complete includes Authorization: Bearer {token}', async () => {
    await fc.assert(
      fc.asyncProperty(arbToken, async (token) => {
        const calls = mockFetch();
        await api.missions.complete(
          'mission-1',
          { reflection: 'done', skillTags: [] },
          token,
        );
        expect(calls).toHaveLength(1);
        const headers = calls[0].headers as Record<string, string>;
        expect(headers['Authorization']).toBe(`Bearer ${token}`);
      }),
      { numRuns: 100 },
    );
  });

  it('evidence.list includes Authorization: Bearer {token}', async () => {
    await fc.assert(
      fc.asyncProperty(arbToken, async (token) => {
        const calls = mockFetch();
        await api.evidence.list(token);
        expect(calls).toHaveLength(1);
        const headers = calls[0].headers as Record<string, string>;
        expect(headers['Authorization']).toBe(`Bearer ${token}`);
      }),
      { numRuns: 100 },
    );
  });

  it('evidence.list with skillTag includes Authorization: Bearer {token}', async () => {
    await fc.assert(
      fc.asyncProperty(arbToken, fc.string({ minLength: 1 }), async (token, skillTag) => {
        const calls = mockFetch();
        await api.evidence.list(token, skillTag);
        expect(calls).toHaveLength(1);
        const headers = calls[0].headers as Record<string, string>;
        expect(headers['Authorization']).toBe(`Bearer ${token}`);
      }),
      { numRuns: 100 },
    );
  });

  it('dashboard.get includes Authorization: Bearer {token}', async () => {
    await fc.assert(
      fc.asyncProperty(arbToken, async (token) => {
        const calls = mockFetch();
        await api.dashboard.get(token);
        expect(calls).toHaveLength(1);
        const headers = calls[0].headers as Record<string, string>;
        expect(headers['Authorization']).toBe(`Bearer ${token}`);
      }),
      { numRuns: 100 },
    );
  });
});
