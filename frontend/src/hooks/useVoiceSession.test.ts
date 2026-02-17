import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useVoiceSession } from './useVoiceSession';

// Mock useAuth
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
    createBuffer: vi.fn(() => ({ getChannelData: () => new Float32Array(0) })),
    createBufferSource: vi.fn(() => ({
      buffer: null,
      connect: vi.fn(),
      start: vi.fn(),
    })),
  };
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal('WebSocket', MockWebSocket);
  vi.stubGlobal('AudioContext', MockAudioContext);
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia: mockGetUserMedia },
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe('useVoiceSession', () => {
  it('initializes with default state', () => {
    const { result } = renderHook(() => useVoiceSession());

    expect(result.current.isActive).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.fallbackToText).toBe(false);
  });

  it('falls back when VITE_VOICE_WS_URL is not configured', async () => {
    // env var is not set in test environment, so startSession should fallback
    const { result } = renderHook(() => useVoiceSession());

    await act(async () => {
      await result.current.startSession();
    });

    expect(result.current.isActive).toBe(false);
    expect(result.current.fallbackToText).toBe(true);
    expect(result.current.error).toBe('Voice WebSocket URL not configured');
  });

  it('establishes WebSocket and audio capture on startSession', async () => {
    import.meta.env.VITE_VOICE_WS_URL = 'wss://test.example.com/prod';

    const { result } = renderHook(() => useVoiceSession());

    await act(async () => {
      result.current.startSession();
      await new Promise((r) => setTimeout(r, 10));
    });

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain('wss://test.example.com/prod?token=');

    // Simulate WebSocket open → triggers async audio setup (getUserMedia)
    await act(async () => {
      MockWebSocket.instances[0].simulateOpen();
      // getUserMedia is async — need to flush microtasks
      await new Promise((r) => setTimeout(r, 50));
    });

    expect(mockGetUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(result.current.isActive).toBe(true);
    expect(result.current.error).toBeNull();

    delete import.meta.env.VITE_VOICE_WS_URL;
  });

  it('sets fallbackToText on WebSocket error', async () => {
    import.meta.env.VITE_VOICE_WS_URL = 'wss://test.example.com/prod';

    const { result } = renderHook(() => useVoiceSession());

    await act(async () => {
      result.current.startSession();
      await new Promise((r) => setTimeout(r, 10));
    });

    await act(async () => {
      MockWebSocket.instances[0].simulateError();
    });

    expect(result.current.isActive).toBe(false);
    expect(result.current.fallbackToText).toBe(true);

    delete import.meta.env.VITE_VOICE_WS_URL;
  });

  it('handles fallback message from server', async () => {
    import.meta.env.VITE_VOICE_WS_URL = 'wss://test.example.com/prod';

    const { result } = renderHook(() => useVoiceSession());

    await act(async () => {
      result.current.startSession();
      await new Promise((r) => setTimeout(r, 10));
    });

    await act(async () => {
      MockWebSocket.instances[0].simulateOpen();
      await new Promise((r) => setTimeout(r, 10));
    });

    await act(async () => {
      MockWebSocket.instances[0].simulateMessage(JSON.stringify({ type: 'fallback' }));
    });

    expect(result.current.isActive).toBe(false);
    expect(result.current.fallbackToText).toBe(true);

    delete import.meta.env.VITE_VOICE_WS_URL;
  });

  it('cleans up resources on stopSession', async () => {
    import.meta.env.VITE_VOICE_WS_URL = 'wss://test.example.com/prod';

    const { result } = renderHook(() => useVoiceSession());

    await act(async () => {
      result.current.startSession();
      await new Promise((r) => setTimeout(r, 10));
    });

    await act(async () => {
      MockWebSocket.instances[0].simulateOpen();
      await new Promise((r) => setTimeout(r, 50));
    });

    expect(result.current.isActive).toBe(true);

    await act(async () => {
      result.current.stopSession();
    });

    expect(result.current.isActive).toBe(false);
    expect(mockClose).toHaveBeenCalled();
    expect(mockStop).toHaveBeenCalled();

    delete import.meta.env.VITE_VOICE_WS_URL;
  });

  it('sets fallbackToText on unexpected WebSocket close', async () => {
    import.meta.env.VITE_VOICE_WS_URL = 'wss://test.example.com/prod';

    const { result } = renderHook(() => useVoiceSession());

    await act(async () => {
      result.current.startSession();
      await new Promise((r) => setTimeout(r, 10));
    });

    await act(async () => {
      MockWebSocket.instances[0].simulateOpen();
      await new Promise((r) => setTimeout(r, 10));
    });

    // Unexpected close (code !== 1000)
    await act(async () => {
      MockWebSocket.instances[0].simulateClose(1006);
    });

    expect(result.current.isActive).toBe(false);
    expect(result.current.fallbackToText).toBe(true);

    delete import.meta.env.VITE_VOICE_WS_URL;
  });
});
