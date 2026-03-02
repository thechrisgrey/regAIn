import type {
  OnboardingData,
  OnboardingResponse,
  MissionsResponse,
  CompleteData,
  CompleteResponse,
  GenerateResponse,
  EvidenceResponse,
  DashboardResponse,
  CoachingRequest,
  CoachingResponse,
  VoiceSessionsResponse,
  VoiceSessionDetailResponse,
  OnetSearchResponse,
  OnetCareerReport,
  AnalyticsResponse,
  SkillSuggestionsResponse,
} from '../types';
import type { ResumeResponse } from '../types/resume';

import { requestCache } from './cache';

const API_BASE_URL = import.meta.env.VITE_API_URL;
const REQUEST_TIMEOUT_MS = 30_000;
const DEFAULT_CACHE_TTL_MS = 30_000;
const MAX_RETRIES = 2;
const MUTATION_RETRY_DELAY_MS = 500;

export type ErrorKind = 'NOT_FOUND' | 'CONFLICT' | 'RATE_LIMITED' | 'TRANSIENT' | 'VALIDATION' | 'UNKNOWN';

interface ApiRequestOptions {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
}

export class ApiError extends Error {
  public readonly statusCode: number;
  public readonly errorKind: ErrorKind;

  constructor(message: string, statusCode: number, errorKind?: ErrorKind) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.errorKind = errorKind ?? 'UNKNOWN';
  }
}

async function apiRequest<T>(
  endpoint: string,
  options: ApiRequestOptions,
  token: string,
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  const doFetch = async (): Promise<T> => {
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: options.method,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          ...options.headers,
        },
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        throw new ApiError('Request timed out', 408);
      }
      throw err;
    }

    if (!response.ok) {
      const errorData = await response
        .json()
        .catch(() => ({ error: response.statusText }));
      const parsed = errorData as { error?: string; errorKind?: ErrorKind };
      throw new ApiError(
        parsed.error ?? 'Request failed',
        response.status,
        parsed.errorKind,
      );
    }

    return response.json() as Promise<T>;
  };

  try {
    // Retry on 5xx for GET requests only
    if (options.method === 'GET') {
      let lastError: unknown;
      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        try {
          return await doFetch();
        } catch (err) {
          lastError = err;
          if (err instanceof ApiError && (err.statusCode >= 500 || err.statusCode === 429) && attempt < MAX_RETRIES) {
            const delay = err.statusCode === 429 ? 1000 : (attempt + 1) * 100;
            await new Promise((r) => setTimeout(r, delay));
            continue;
          }
          throw err;
        }
      }
      throw lastError;
    }
    // Retry on 5xx/408 for POST/PUT mutations (1 retry, skip CONFLICT).
    if (options.method === 'POST' || options.method === 'PUT') {
      try {
        return await doFetch();
      } catch (err) {
        if (
          err instanceof ApiError &&
          (err.statusCode >= 500 || err.statusCode === 408 || err.statusCode === 429) &&
          err.errorKind !== 'CONFLICT'
        ) {
          const retryDelay = err.statusCode === 429 ? 1000 : MUTATION_RETRY_DELAY_MS;
          await new Promise((r) => setTimeout(r, retryDelay));
          return await doFetch();
        }
        throw err;
      }
    }
    return await doFetch();
  } finally {
    clearTimeout(timeoutId);
  }
}

function cachedGet<T>(endpoint: string, token: string, ttlMs = DEFAULT_CACHE_TTL_MS): Promise<T> {
  const key = endpoint;
  return requestCache.get<T>(key, () => apiRequest<T>(endpoint, { method: 'GET' }, token), ttlMs);
}

function invalidateCache(...prefixes: string[]): void {
  for (const prefix of prefixes) {
    requestCache.invalidate(prefix);
  }
}

export const api = {
  onboarding: {
    create: (data: OnboardingData, token: string) =>
      apiRequest<OnboardingResponse>(
        '/onboarding',
        { method: 'POST', body: data },
        token,
      ),
  },
  missions: {
    list: (token: string, limit?: number, cursor?: string) => {
      const params = new URLSearchParams();
      if (limit) params.set('limit', String(limit));
      if (cursor) params.set('cursor', cursor);
      const qs = params.toString();
      return cachedGet<MissionsResponse>(`/missions${qs ? `?${qs}` : ''}`, token);
    },
    complete: (missionId: string, data: CompleteData, token: string) =>
      apiRequest<CompleteResponse>(
        `/missions/${missionId}/complete`,
        { method: 'POST', body: data },
        token,
      ).then((res) => {
        invalidateCache('/missions', '/dashboard', '/evidence');
        return res;
      }),
    generate: (token: string) => {
      const idempotencyKey = crypto.randomUUID();
      return apiRequest<GenerateResponse>(
        '/missions/generate',
        { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey } },
        token,
      ).then((res) => {
        invalidateCache('/missions');
        return res;
      });
    },
  },
  evidence: {
    list: (token: string, skillTag?: string, limit?: number, cursor?: string) => {
      const params = new URLSearchParams();
      if (skillTag) params.set('skill_tag', skillTag);
      if (limit) params.set('limit', String(limit));
      if (cursor) params.set('cursor', cursor);
      const qs = params.toString();
      return cachedGet<EvidenceResponse>(`/evidence${qs ? `?${qs}` : ''}`, token);
    },
    suggestTags: (reflection: string, token: string) =>
      cachedGet<SkillSuggestionsResponse>(
        `/evidence/suggest-tags?reflection=${encodeURIComponent(reflection.slice(0, 500))}`,
        token,
        10_000,
      ),
  },
  dashboard: {
    get: (token: string) =>
      cachedGet<DashboardResponse>('/dashboard', token),
  },
  analytics: {
    get: (token: string) =>
      cachedGet<AnalyticsResponse>('/analytics', token, 60_000),
  },
  coaching: {
    checkin: (data: CoachingRequest, token: string) =>
      apiRequest<CoachingResponse>(
        '/coaching/checkin',
        { method: 'POST', body: data },
        token,
      ),
  },
  resume: {
    get: (token: string) =>
      apiRequest<ResumeResponse>(
        '/resume',
        { method: 'GET' },
        token,
      ),
    generate: (token: string) => {
      const idempotencyKey = crypto.randomUUID();
      return apiRequest<ResumeResponse>(
        '/resume/generate',
        { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey } },
        token,
      );
    },
  },
  voicePractice: {
    listSessions: (token: string) =>
      apiRequest<VoiceSessionsResponse>(
        '/voice-sessions',
        { method: 'GET' },
        token,
      ),
    getSession: (sessionId: string, token: string) =>
      apiRequest<VoiceSessionDetailResponse>(
        `/voice-sessions/${sessionId}`,
        { method: 'GET' },
        token,
      ),
  },
  profile: {
    delete: (token: string) =>
      apiRequest<{ status: string; deletionDate: string }>(
        '/profile',
        { method: 'DELETE' },
        token,
      ),
    recover: (token: string) =>
      apiRequest<{ status: string }>(
        '/profile/recover',
        { method: 'POST' },
        token,
      ),
  },
  onet: {
    search: (keyword: string, token: string) =>
      apiRequest<OnetSearchResponse>(
        `/onet/search?keyword=${encodeURIComponent(keyword)}`,
        { method: 'GET' },
        token,
      ),
    careerDetail: (socCode: string, token: string) =>
      apiRequest<OnetCareerReport>(
        `/onet/careers/${encodeURIComponent(socCode)}`,
        { method: 'GET' },
        token,
      ),
  },
};
