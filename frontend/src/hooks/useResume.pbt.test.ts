// Feature: agent-friendly-resume, Property 12 (frontend): API response contains required fields
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import fc from 'fast-check';
import { useResume } from './useResume';
import type { ResumeResponse } from '../types/resume';

vi.mock('./useAuth', () => ({
  useAuth: vi.fn(() => ({
    getToken: vi.fn().mockResolvedValue('mock-token'),
  })),
}));

vi.mock('../services/api', () => ({
  api: {
    resume: {
      get: vi.fn(),
      generate: vi.fn(),
    },
  },
}));

import { api } from '../services/api';
const mockedGet = vi.mocked(api.resume.get);
const mockedGenerate = vi.mocked(api.resume.generate);

// Arbitrary for generating valid ResumeResponse objects
const resumeResponseArb = fc.record({
  content: fc.string({ minLength: 1 }),
  generatedAt: fc.integer({ min: 946684800000, max: 4102444800000 }).map(ts => new Date(ts).toISOString()),
  version: fc.integer({ min: 1 }),
  downloadUrl: fc.webUrl(),
  frontmatter: fc.record({
    schema_version: fc.string({ minLength: 1 }),
    generated_at: fc.integer({ min: 946684800000, max: 4102444800000 }).map(ts => new Date(ts).toISOString()),
    regain_version: fc.string({ minLength: 1 }),
    name: fc.string({ minLength: 1 }),
    target_role: fc.string({ minLength: 1 }),
    transition_type: fc.string({ minLength: 1 }),
    skills: fc.array(
      fc.record({
        skill_name: fc.string({ minLength: 1 }),
        evidence_count: fc.nat(),
        strongest_evidence_summary: fc.string(),
        proficiency_indicator: fc.string({ minLength: 1 }),
      }),
    ),
    campaign_phase: fc.string({ minLength: 1 }),
    campaign_progress_pct: fc.integer({ min: 0, max: 100 }),
    market_alignment_score: fc.integer({ min: 0, max: 100 }),
    missions_completed: fc.nat(),
    evidence_items: fc.nat(),
    top_accomplishments: fc.array(fc.string({ minLength: 1 })),
  }),
}) as fc.Arbitrary<ResumeResponse>;


describe('useResume property tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('Property 12: fetchResume exposes all required fields from API response', async () => {
    await fc.assert(
      fc.asyncProperty(resumeResponseArb, async (mockResponse) => {
        mockedGet.mockResolvedValue(mockResponse);

        const { result } = renderHook(() => useResume());

        await act(async () => {
          await result.current.fetchResume();
        });

        const resume = result.current.resume;
        expect(resume).not.toBeNull();
        expect(resume!.content).toBe(mockResponse.content);
        expect(resume!.generatedAt).toBe(mockResponse.generatedAt);
        expect(resume!.version).toBe(mockResponse.version);
        expect(resume!.downloadUrl).toBe(mockResponse.downloadUrl);
      }),
      { numRuns: 50 },
    );
  });

  it('Property 12: regenerateResume exposes all required fields from API response', async () => {
    await fc.assert(
      fc.asyncProperty(resumeResponseArb, async (mockResponse) => {
        mockedGenerate.mockResolvedValue(mockResponse);

        const { result } = renderHook(() => useResume());

        await act(async () => {
          await result.current.regenerateResume();
        });

        const resume = result.current.resume;
        expect(resume).not.toBeNull();
        expect(resume!.content).toBe(mockResponse.content);
        expect(resume!.generatedAt).toBe(mockResponse.generatedAt);
        expect(resume!.version).toBe(mockResponse.version);
        expect(resume!.downloadUrl).toBe(mockResponse.downloadUrl);
      }),
      { numRuns: 50 },
    );
  });
});