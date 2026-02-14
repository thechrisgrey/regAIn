import type {
  OnboardingData,
  OnboardingResponse,
  MissionsResponse,
  CompleteData,
  CompleteResponse,
  EvidenceResponse,
  DashboardResponse,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL;

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
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: options.method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...options.headers,
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

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
    list: (token: string) =>
      apiRequest<MissionsResponse>(
        '/missions',
        { method: 'GET' },
        token,
      ),
    complete: (missionId: string, data: CompleteData, token: string) =>
      apiRequest<CompleteResponse>(
        `/missions/${missionId}/complete`,
        { method: 'POST', body: data },
        token,
      ),
  },
  evidence: {
    list: (token: string, skillTag?: string) =>
      apiRequest<EvidenceResponse>(
        `/evidence${skillTag ? `?skill_tag=${skillTag}` : ''}`,
        { method: 'GET' },
        token,
      ),
  },
  dashboard: {
    get: (token: string) =>
      apiRequest<DashboardResponse>(
        '/dashboard',
        { method: 'GET' },
        token,
      ),
  },
};
