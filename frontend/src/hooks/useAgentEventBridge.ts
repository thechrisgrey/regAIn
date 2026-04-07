import { useEffect, useRef, useCallback } from 'react';
import { useOnMutation, type MutationEventType } from './useMutationBus';

const DEDUP_WINDOW_MS = 5_000;
const BATCH_DEBOUNCE_MS = 2_000;

interface ActionEvent {
  action: MutationEventType;
  payload?: Record<string, unknown>;
  timestamp: number;
}

/**
 * Bridges MutationBus events to the coaching WebSocket as action_events.
 * Handles deduplication (same action+payload within 5s) and batching
 * (3+ events within 2s are combined into a single message).
 */
export function useAgentEventBridge(
  sendWs: ((data: Record<string, unknown>) => void) | null,
  getToken: () => Promise<string>,
) {
  const lastEventRef = useRef<{ key: string; time: number }>({ key: '', time: 0 });
  const batchRef = useRef<ActionEvent[]>([]);
  const batchTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const flush = useCallback(async () => {
    batchTimerRef.current = undefined;
    const events = batchRef.current;
    batchRef.current = [];

    if (!events.length || !sendWs) return;

    const token = await getToken();

    if (events.length >= 3) {
      sendWs({
        type: 'action_event',
        action: 'batch',
        payload: { events: events.map(e => ({ action: e.action, payload: e.payload })) },
        token,
      });
    } else {
      for (const e of events) {
        sendWs({
          type: 'action_event',
          action: e.action,
          payload: e.payload || {},
          token,
        });
      }
    }
  }, [sendWs, getToken]);

  const enqueue = useCallback((action: MutationEventType, payload?: Record<string, unknown>) => {
    const now = Date.now();
    const key = `${action}:${JSON.stringify(payload || {})}`;

    if (lastEventRef.current.key === key && now - lastEventRef.current.time < DEDUP_WINDOW_MS) {
      return;
    }
    lastEventRef.current = { key, time: now };

    batchRef.current.push({ action, payload, timestamp: now });

    clearTimeout(batchTimerRef.current);
    batchTimerRef.current = setTimeout(flush, BATCH_DEBOUNCE_MS);
  }, [flush]);

  // Subscribe to all action-relevant MutationBus events.
  // These are stable string literals, so the hook call order is fixed.
  useOnMutation('mission:completed', useCallback(() => enqueue('mission:completed'), [enqueue]));
  useOnMutation('mission:generated', useCallback(() => enqueue('mission:generated'), [enqueue]));
  useOnMutation('evidence:logged', useCallback(() => enqueue('evidence:logged'), [enqueue]));
  useOnMutation('campaign:created', useCallback(() => enqueue('campaign:created'), [enqueue]));
  useOnMutation('resume:generated', useCallback(() => enqueue('resume:generated'), [enqueue]));
  useOnMutation('voice:session_completed', useCallback(() => enqueue('voice:session_completed'), [enqueue]));
  useOnMutation('scorecard:viewed', useCallback(() => enqueue('scorecard:viewed'), [enqueue]));
  useOnMutation('profile:updated', useCallback(() => enqueue('profile:updated'), [enqueue]));
  useOnMutation('page:navigated', useCallback(() => enqueue('page:navigated'), [enqueue]));

  useEffect(() => {
    return () => {
      clearTimeout(batchTimerRef.current);
    };
  }, []);
}
