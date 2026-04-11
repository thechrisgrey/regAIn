import { describe, it, expect } from 'vitest';

// ---------------------------------------------------------------------------
// Pure-logic mirrors of the formatting helpers in CoachModal.tsx.
// Testing these in isolation avoids pulling in WebSocket/Auth/Router context.
// ---------------------------------------------------------------------------

type PageSnapshot = Record<string, unknown>;

/** Mirror of CoachModal's buildPrefix() */
function buildPrefix(
  pageContext: string,
  getPageSnapshot: () => PageSnapshot | null,
): string {
  const snapshot = getPageSnapshot();
  if (snapshot) {
    return `[page_context: ${pageContext}] [page_data: ${JSON.stringify(snapshot)}]`;
  }
  return `[page_context: ${pageContext}]`;
}

/** Mirror of the user-message cleaning pipeline in CoachModal's visibleMessages */
function cleanUserMessage(raw: string): string {
  return raw
    .replace(/\[page_context:\s*\w+\]\s*/g, '')
    .replace(/\[page_data:\s*\{.*\}]\s*/g, '')
    .replace(/\[proactive_check\]\s*/g, '')
    .trim();
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ChatPanel snapshot formatting', () => {
  it('builds message with page_data when snapshot exists', () => {
    const snapshot: PageSnapshot = { page: 'missions', activeMissions: 2 };
    const result = buildPrefix('missions', () => snapshot);

    expect(result).toBe(
      '[page_context: missions] [page_data: {"page":"missions","activeMissions":2}]',
    );
  });

  it('builds message without page_data when no snapshot', () => {
    const result = buildPrefix('dashboard', () => null);

    expect(result).toBe('[page_context: dashboard]');
  });

  it('builds proactive check with page_data', () => {
    const snapshot: PageSnapshot = { page: 'evidence', skillCount: 5 };
    const prefix = buildPrefix('evidence', () => snapshot);
    const message = `${prefix} [proactive_check]`;

    expect(message).toBe(
      '[page_context: evidence] [page_data: {"page":"evidence","skillCount":5}] [proactive_check]',
    );
  });

  it('builds user message with page_data', () => {
    const snapshot: PageSnapshot = { page: 'dashboard', activeMissions: 3 };
    const prefix = buildPrefix('dashboard', () => snapshot);
    const message = `${prefix} How do I complete my mission?`;

    expect(message).toBe(
      '[page_context: dashboard] [page_data: {"page":"dashboard","activeMissions":3}] How do I complete my mission?',
    );
  });
});

describe('ChatPanel page_data stripping', () => {
  it('strips page_data from visible user messages', () => {
    const raw =
      '[page_context: missions] [page_data: {"page":"missions","activeMissions":2}] How do I complete this?';
    expect(cleanUserMessage(raw)).toBe('How do I complete this?');
  });

  it('strips page_data with nested objects', () => {
    const raw =
      '[page_context: missions] [page_data: {"page":"missions","primaryMission":{"title":"Lead a sprint","status":"in_progress"}}] Tell me about my mission';
    expect(cleanUserMessage(raw)).toBe('Tell me about my mission');
  });

  it('strips proactive check with page_data', () => {
    const raw =
      '[page_context: dashboard] [page_data: {"page":"dashboard","stats":{"completed":3}}] [proactive_check]';
    expect(cleanUserMessage(raw)).toBe('');
  });

  it('strips page_context without page_data (backward compat)', () => {
    const raw = '[page_context: dashboard] Hello coach';
    expect(cleanUserMessage(raw)).toBe('Hello coach');
  });

  it('handles message with only page_context and proactive_check', () => {
    const raw = '[page_context: evidence] [proactive_check]';
    expect(cleanUserMessage(raw)).toBe('');
  });
});
