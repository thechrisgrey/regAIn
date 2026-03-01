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
} from '../types';
import type { ResumeResponse } from '../types/resume';

import { requestCache } from './cache';

const API_BASE_URL = import.meta.env.VITE_API_URL;
const REQUEST_TIMEOUT_MS = 30_000;
const DEFAULT_CACHE_TTL_MS = 30_000;
const MAX_RETRIES = 2;

interface ApiRequestOptions {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  headers?: Record<string, string>;
}

export class ApiError extends Error {
  public readonly statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
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
      throw new ApiError(
        (errorData as { error?: string }).error ?? 'Request failed',
        response.status,
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
          if (err instanceof ApiError && err.statusCode >= 500 && attempt < MAX_RETRIES) {
            await new Promise((r) => setTimeout(r, (attempt + 1) * 100));
            continue;
          }
          throw err;
        }
      }
      throw lastError;
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
  },
  dashboard: {
    get: (token: string) =>
      cachedGet<DashboardResponse>('/dashboard', token),
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
