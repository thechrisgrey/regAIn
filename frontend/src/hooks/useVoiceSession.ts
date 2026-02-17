import { useState, useRef, useCallback, useEffect } from 'react';
import { useAuth } from './useAuth';

function getVoiceWsUrl(): string | undefined {
  return import.meta.env.VITE_VOICE_WS_URL as string | undefined;
}
const SAMPLE_RATE = 16000;
const BUFFER_SIZE = 4096;

interface VoiceSessionState {
  isActive: boolean;
  error: string | null;
  fallbackToText: boolean;
}

/**
 * Convert Float32 audio samples to Int16 PCM.
 */
function float32ToInt16(float32: Float32Array): Int16Array {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const clamped = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return int16;
}

/**
 * Downsample audio from source sample rate to target sample rate.
 */
function downsample(buffer: Float32Array, sourceSampleRate: number, targetSampleRate: number): Float32Array {
  if (sourceSampleRate === targetSampleRate) return buffer;
  const ratio = sourceSampleRate / targetSampleRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    result[i] = buffer[Math.round(i * ratio)];
  }
  return result;
}

/**
 * Encode an Int16Array as a base64 string.
 */
function int16ToBase64(int16: Int16Array): string {
  const bytes = new Uint8Array(int16.buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Decode a base64 PCM string and play it through an AudioContext.
 */
function playPcmAudio(base64Audio: string, audioCtx: AudioContext): void {
  const binary = atob(base64Audio);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  const int16 = new Int16Array(bytes.buffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 0x8000;
  }

  const audioBuffer = audioCtx.createBuffer(1, float32.length, SAMPLE_RATE);
  audioBuffer.getChannelData(0).set(float32);
  const source = audioCtx.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioCtx.destination);
  source.start();
}

export function useVoiceSession() {
  const { getToken } = useAuth();
  const [state, setState] = useState<VoiceSessionState>({
    isActive: false,
    error: null,
    fallbackToText: false,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);

  const cleanup = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const stopSession = useCallback(() => {
    cleanup();
    setState((prev) => ({ ...prev, isActive: false }));
  }, [cleanup]);

  const startSession = useCallback(async () => {
    const voiceWsUrl = getVoiceWsUrl();
    if (!voiceWsUrl) {
      setState({ isActive: false, error: 'Voice WebSocket URL not configured', fallbackToText: true });
      return;
    }

    setState({ isActive: false, error: null, fallbackToText: false });

    try {
      const token = await getToken();
      const ws = new WebSocket(`${voiceWsUrl}?token=${encodeURIComponent(token)}`);
      wsRef.current = ws;

      ws.onopen = async () => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          mediaStreamRef.current = stream;

          const audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
          audioCtxRef.current = audioCtx;

          const source = audioCtx.createMediaStreamSource(stream);
          // ScriptProcessorNode is deprecated but widely supported;
          // AudioWorklet would be the modern alternative.
          const processor = audioCtx.createScriptProcessor(BUFFER_SIZE, 1, 1);
          processorRef.current = processor;

          processor.onaudioprocess = (e: AudioProcessingEvent) => {
            if (ws.readyState !== WebSocket.OPEN) return;
            const input = e.inputBuffer.getChannelData(0);
            const downsampled = downsample(input, audioCtx.sampleRate, SAMPLE_RATE);
            const pcm = float32ToInt16(downsampled);
            const encoded = int16ToBase64(pcm);
            ws.send(JSON.stringify({ type: 'audio', data: encoded }));
          };

          source.connect(processor);
          processor.connect(audioCtx.destination);
          setState({ isActive: true, error: null, fallbackToText: false });
        } catch (micErr) {
          cleanup();
          setState({
            isActive: false,
            error: micErr instanceof Error ? micErr.message : 'Microphone access denied',
            fallbackToText: true,
          });
        }
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(event.data as string) as { type: string; data?: string };
          if (msg.type === 'audio' && msg.data && audioCtxRef.current) {
            playPcmAudio(msg.data, audioCtxRef.current);
          } else if (msg.type === 'fallback') {
            cleanup();
            setState({ isActive: false, error: null, fallbackToText: true });
          }
        } catch {
          // Non-JSON message — ignore
        }
      };

      ws.onerror = () => {
        cleanup();
        setState({ isActive: false, error: 'Voice connection error', fallbackToText: true });
      };

      ws.onclose = (event: CloseEvent) => {
        const wasActive = wsRef.current !== null;
        wsRef.current = null;
        if (wasActive) {
          cleanup();
          // Unexpected close → fallback
          if (event.code !== 1000) {
            setState({ isActive: false, error: null, fallbackToText: true });
          } else {
            setState((prev) => ({ ...prev, isActive: false }));
          }
        }
      };
    } catch (err) {
      cleanup();
      setState({
        isActive: false,
        error: err instanceof Error ? err.message : 'Failed to start voice session',
        fallbackToText: true,
      });
    }
  }, [getToken, cleanup]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  return {
    isActive: state.isActive,
    error: state.error,
    fallbackToText: state.fallbackToText,
    startSession,
    stopSession,
  };
}
