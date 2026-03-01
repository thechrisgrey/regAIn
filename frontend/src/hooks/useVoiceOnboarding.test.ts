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

// VITE_VOICE_WS_URL is already set in .env, so the module-level const
// captures the real value. We use vi.resetModules() + dynamic import
// to ensure the module sees our test value.
let useVoiceOnboarding: typeof import('./useVoiceOnboarding').useVoiceOnboarding;

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
  import.meta.env.VITE_VOICE_WS_URL = 'wss://test-voice.example.com/prod';
  vi.resetModules();
  const mod = await import('./useVoiceOnboarding');
  useVoiceOnboarding = mod.useVoiceOnboarding;
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('useVoiceOnboarding', () => {
  describe('initial state', () => {
    it('initializes with idle status', () => {
      const { result } = renderHook(() => useVoiceOnboarding());
      expect(result.current.status).toBe('idle');
    });

    it('initializes with null error', () => {
      const { result } = renderHook(() => useVoiceOnboarding());
      expect(result.current.error).toBeNull();
    });

    it('initializes with muted false and speaking false', () => {
      const { result } = renderHook(() => useVoiceOnboarding());
      expect(result.current.isMuted).toBe(false);
      expect(result.current.isAgentSpeaking).toBe(false);
    });

    it('initializes with empty transcript', () => {
      const { result } = renderHook(() => useVoiceOnboarding());
      expect(result.current.transcript).toEqual([]);
    });
  });

  describe('startSession', () => {
    it('transitions to connecting', async () => {
      const { result } = renderHook(() => useVoiceOnboarding());

      await act(async () => {
        result.current.startSession();
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(result.current.status).toBe('connecting');
    });

    it('creates WebSocket with token', async () => {
      const { result } = renderHook(() => useVoiceOnboarding());

      await act(async () => {
        result.current.startSession();
        await new Promise((r) => setTimeout(r, 10));
      });

      expect(MockWebSocket.instances).toHaveLength(1);
      expect(MockWebSocket.instances[0].url).toContain('token=');
    });

    it('transitions to active after open', async () => {
      const { result } = renderHook(() => useVoiceOnboarding());

      await act(async () => {
        result.current.startSession();
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateOpen();
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.status).toBe('active');
      expect(mockGetUserMedia).toHaveBeenCalled();
    });

    it('requests microphone access', async () => {
      const { result } = renderHook(() => useVoiceOnboarding());

      await act(async () => {
        result.current.startSession();
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateOpen();
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(mockGetUserMedia).toHaveBeenCalledWith(
        expect.objectContaining({ audio: expect.any(Object) }),
      );
    });
  });

  describe('message handling', () => {
    async function startActiveSession() {
      const hookResult = renderHook(() => useVoiceOnboarding());

      await act(async () => {
        hookResult.result.current.startSession();
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateOpen();
        await new Promise((r) => setTimeout(r, 50));
      });

      return hookResult;
    }

    it('accumulates user transcript', async () => {
      const { result } = await startActiveSession();

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'transcript', text: 'I want to switch careers', role: 'user' }),
        );
      });

      expect(result.current.transcript).toHaveLength(1);
      expect(result.current.transcript[0]).toEqual({ role: 'user', text: 'I want to switch careers' });
    });

    it('accumulates assistant transcript', async () => {
      const { result } = await startActiveSession();

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'transcript', text: 'Tell me more', role: 'assistant' }),
        );
      });

      expect(result.current.transcript).toHaveLength(1);
      expect(result.current.transcript[0]).toEqual({ role: 'assistant', text: 'Tell me more' });
    });

    it('merges consecutive same-role chunks', async () => {
      const { result } = await startActiveSession();

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'transcript', text: 'Part one ', role: 'assistant' }),
        );
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateMessage(
          JSON.stringify({ type: 'transcript', text: 'part two', role: 'assistant' }),
        );
      });

      expect(result.current.transcript).toHaveLength(1);
      expect(result.current.transcript[0].text).toBe('Part one part two');
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
          JSON.stringify({ type: 'fallback', message: 'Unable to establish voice' }),
        );
      });

      expect(result.current.status).toBe('error');
      expect(result.current.error).toBe('Unable to establish voice');
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
    it('closes WebSocket and transitions to ending', async () => {
      const { result } = renderHook(() => useVoiceOnboarding());

      await act(async () => {
        result.current.startSession();
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateOpen();
        await new Promise((r) => setTimeout(r, 50));
      });

      expect(result.current.status).toBe('active');

      await act(async () => {
        result.current.stopSession();
      });

      expect(result.current.status).toBe('ending');
      expect(result.current.isAgentSpeaking).toBe(false);
    });
  });

  describe('toggleMute', () => {
    it('toggles mute state', async () => {
      const { result } = renderHook(() => useVoiceOnboarding());

      await act(async () => {
        result.current.startSession();
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
      const { result } = renderHook(() => useVoiceOnboarding());

      await act(async () => {
        result.current.startSession();
        await new Promise((r) => setTimeout(r, 10));
      });

      await act(async () => {
        MockWebSocket.instances[0].simulateError();
      });

      expect(result.current.status).toBe('error');
      expect(result.current.error).toBe('Voice connection error. Please try again or use the form.');
    });

    it('sets error on unexpected WebSocket close', async () => {
      const { result } = renderHook(() => useVoiceOnboarding());

      await act(async () => {
        result.current.startSession();
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
