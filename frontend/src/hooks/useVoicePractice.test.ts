import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// Mock useAuth before any imports
vi.mock('./useAuth', () => ({
  useAuth: vi.fn(() => ({
    getToken: vi.fn().mockResolvedValue('mock-token'),
  })),
}));

// --- WebSocket mock ---
class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  url: string;
  readyState = MockWebSocket.OPEN;
  onopen: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  send = vi.fn();
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED;
  });

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  simulateOpen() {
    this.onopen?.(new Event('open'));
  }
  simulateMessage(data: string) {
    this.onmessage?.(new MessageEvent('message', { data }));
  }
  simulateError() {
    this.onerror?.(new Event('error'));
  }
  simulateClose(code = 1000) {
    this.onclose?.(new CloseEvent('close', { code }));
  }
}

// --- AudioContext mock ---
const mockStop = vi.fn();
const mockGetUserMedia = vi.fn().mockResolvedValue({
  getTracks: () => [{ stop: mockStop }],
  getAudioTracks: () => [{ enabled: true, stop: mockStop }],
});

const mockConnect = vi.fn();
const mockDisconnect = vi.fn();
const mockProcessorNode = {
  connect: mockConnect,
  disconnect: mockDisconnect,
  onaudioprocess: null as ((e: unknown) => void) | null,
};

const mockSourceNode = { connect: vi.fn() };
const mockClose = vi.fn().mockResolvedValue(undefined);

function MockAudioContext() {
  return {
    sampleRate: 16000,
    createMediaStreamSource: vi.fn(() => mockSourceNode),
    createScriptProcessor: vi.fn(() => mockProcessorNode),
    destination: {},
    close: mockClose,
  };
}

// We need to dynamically import the hook so that the module-level const
// captures our env var value. Store the hook function after import.
let useVoicePractice: typeof import('./useVoicePractice').useVoicePractice;

beforeEach(async () => {
  MockWebSocket.instances = [];
  vi.stubGlobal('WebSocket', MockWebSocket);
  vi.stubGlobal('AudioContext', MockAudioContext);
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia: mockGetUserMedia },
    writable: true,
    configurable: true,
  });

  // Set env var, reset modules, and re-import so the module-level const sees it
  import.meta.env.VITE_VOICE_PRACTICE_WS_URL = 'wss://test-voice-practice.example.com/prod';
  vi.resetModules();
  const mod = await import('./useVoicePractice');
  useVoicePractice = mod.useVoicePractice;
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('useVoicePractice', () => {
  describe('initial state', () => {
    it('initializes with idle status', () => {
      const { result } = renderHook(() => useVoicePractice());
      expect(result.current.status).toBe('idle');
    });

    it('initializes with null error', () => {
      const { result } = renderHook(() => useVoicePractice());
      expect(result.current.error).toBeNull();
    });

    it('initializes with muted false and speaking false', () => {
      const { result } = renderHook(() => useVoicePractice());
      expect(result.current.isMuted).toBe(false);
      expect(result.current.isAgentSpeaking).toBe(false);
    });

    it('initializes with empty transcript', () => {
      const { result } = renderHook(() => useVoicePractice());
      expect(result.current.transcript).toEqual([]);
    });
  });

  describe('startSession', () => {
    it('sets error when env var is missing', async () => {
      // Re-import without env var
      delete import.meta.env.VITE_VOICE_PRACTICE_WS_URL;
      vi.resetModules();
      const mod = await import('./useVoicePractice');
      const useVoicePracticeNoEnv = mod.useVoicePractice;

      const { result } = renderHook(() => useVoicePracticeNoEnv());

      await act(async () => {
        await result.current.startSession('interview');
      });

      expect(result.current.status).toBe('error');
      expect(result.current.error).toBe('Voice practice is not available at this time.');
    });

    it('transitions to connecting', async () => {
      const { result } = renderHook(() => useVoicePractice());

      await act(async () => {
        result.current.startSession('interview');
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(result.current.status).toBe('connecting');
    });

    it('creates WebSocket without token in URL and sends auth message', async () => {
      const { result } = renderHook(() => useVoicePractice());

      await act(async () => {
        result.current.startSession('interview');
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(MockWebSocket.instances).toHaveLength(1);
      // Token should NOT be in URL (first-message auth).
      expect(MockWebSocket.instances[0].url).not.toContain('token=');
      // session_type should still be in query params.
      expect(MockWebSocket.instances[0].url).toContain('session_type=interview');

      // Simulate onopen — hook should send auth message.
      await act(async () => {
        MockWebSocket.instances[0].simulateOpen();
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(MockWebSocket.instances[0].send).toHaveBeenCalledWith(
        expect.stringContaining('"type":"auth"'),
      );
    });

    it('transitions to active after auth_success and mic acquired', async () => {
      const { result } = renderHook(() => useVoicePractice());

      await act(async () => {
        result.current.startSession('interview');
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateOpen();
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'auth_success' }),
        );
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.status).toBe('active');
      expect(mockGetUserMedia).toHaveBeenCalled();
    });

    it('stores sessionType', async () => {
      const { result } = renderHook(() => useVoicePractice());

      await act(async () => {
        result.current.startSession('mission_discussion');
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(result.current.sessionType).toBe('mission_discussion');
    });

    it('requests microphone access after auth_success', async () => {
      const { result } = renderHook(() => useVoicePractice());

      await act(async () => {
        result.current.startSession('interview');
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateOpen();
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'auth_success' }),
        );
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(mockGetUserMedia).toHaveBeenCalledWith(
        expect.objectContaining({ audio: expect.any(Object) }),
      );
    });
  });

  describe('message handling', () => {
    async function startActiveSession() {
      const hookResult = renderHook(() => useVoicePractice());

      await act(async () => {
        hookResult.result.current.startSession('interview');
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateOpen();
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'auth_success' }),
        );
        await new Promise((r) => setTimeout(r, 50));
      });

      return hookResult;
    }

    it('accumulates transcript entries', async () => {
      const { result } = await startActiveSession();

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'transcript', text: 'Hello', role: 'assistant' }),
        );
      });

      expect(result.current.transcript).toHaveLength(1);
      expect(result.current.transcript[0]).toEqual({ role: 'assistant', text: 'Hello' });
    });

    it('merges consecutive same-role transcript chunks', async () => {
      const { result } = await startActiveSession();

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'transcript', text: 'Hello ', role: 'assistant' }),
        );
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'transcript', text: 'world', role: 'assistant' }),
        );
      });

      expect(result.current.transcript).toHaveLength(1);
      expect(result.current.transcript[0].text).toBe('Hello world');
    });

    it('creates new entry for different role', async () => {
      const { result } = await startActiveSession();

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'transcript', text: 'Hi', role: 'assistant' }),
        );
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'transcript', text: 'Hello', role: 'user' }),
        );
      });

      expect(result.current.transcript).toHaveLength(2);
      expect(result.current.transcript[0].role).toBe('assistant');
      expect(result.current.transcript[1].role).toBe('user');
    });

    it('handles clear_audio message', async () => {
      const { result } = await startActiveSession();

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'clear_audio' }),
        );
      });

      expect(result.current.isAgentSpeaking).toBe(false);
    });

    it('handles fallback message', async () => {
      const { result } = await startActiveSession();

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'fallback', message: 'Service unavailable' }),
        );
      });

      expect(result.current.status).toBe('error');
      expect(result.current.error).toBe('Service unavailable');
    });

    it('handles session_ended message', async () => {
      const { result } = await startActiveSession();

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'session_ended' }),
        );
      });

      expect(result.current.status).toBe('ending');
    });
  });

  describe('stopSession', () => {
    it('transitions to assessing and cleans up', async () => {
      const { result } = renderHook(() => useVoicePractice());

      await act(async () => {
        result.current.startSession('interview');
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateOpen();
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'auth_success' }),
        );
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.status).toBe('active');

      await act(async () => {
        result.current.stopSession();
      });

      expect(result.current.status).toBe('assessing');
      expect(result.current.isAgentSpeaking).toBe(false);
    });
  });

  describe('toggleMute', () => {
    it('toggles mute state', async () => {
      const { result } = renderHook(() => useVoicePractice());

      await act(async () => {
        result.current.startSession('interview');
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateOpen();
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.isMuted).toBe(false);

      await act(async () => {
        result.current.toggleMute();
      });

      expect(result.current.isMuted).toBe(true);

      await act(async () => {
        result.current.toggleMute();
      });

      expect(result.current.isMuted).toBe(false);
    });
  });

  describe('error handling', () => {
    it('sets error on WebSocket error', async () => {
      const { result } = renderHook(() => useVoicePractice());

      await act(async () => {
        result.current.startSession('interview');
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateError();
      });

      expect(result.current.status).toBe('error');
      expect(result.current.error).toBe('Voice connection error. Please try again.');
    });

    it('sets error on unexpected WebSocket close', async () => {
      const { result } = renderHook(() => useVoicePractice());

      await act(async () => {
        result.current.startSession('interview');
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateOpen();
        await new Promise((r) => setTimeout(r, 50));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateClose(1006);
      });

      expect(result.current.status).toBe('error');
      expect(result.current.error).toBe('Voice connection was interrupted.');
    });
  });
});
