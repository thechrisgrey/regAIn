import { useState, useRef, useCallback, useEffect } from 'react';
import { useAuth } from './useAuth';

const VOICE_WS_URL = import.meta.env.VITE_VOICE_WS_URL as string | undefined;
const SAMPLE_RATE = 16000;
const BUFFER_SIZE = 4096;

export type VoiceStatus = 'idle' | 'connecting' | 'active' | 'ending' | 'error';

export interface TranscriptEntry {
  role: 'user' | 'assistant';
  text: string;
}

interface VoiceState {
  status: VoiceStatus;
  error: string | null;
  isMuted: boolean;
  isAgentSpeaking: boolean;
  transcript: TranscriptEntry[];
}

// ---------------------------------------------------------------------------
// Audio helpers
// ---------------------------------------------------------------------------

function float32ToInt16(float32: Float32Array): Int16Array {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const clamped = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return int16;
}

function downsample(
  buffer: Float32Array,
  sourceSampleRate: number,
  targetSampleRate: number,
): Float32Array {
  if (sourceSampleRate === targetSampleRate) return buffer;
  const ratio = sourceSampleRate / targetSampleRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  for (let i = 0; i < newLength; i++) {
    result[i] = buffer[Math.round(i * ratio)];
  }
  return result;
}

function int16ToBase64(int16: Int16Array): string {
  const bytes = new Uint8Array(int16.buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useVoiceOnboarding() {
  const { getToken } = useAuth();
  const [state, setState] = useState<VoiceState>({
    status: 'idle',
    error: null,
    isMuted: false,
    isAgentSpeaking: false,
    transcript: [],
  });

  const wsRef = useRef<WebSocket | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const mutedRef = useRef(false);
  const nextPlayTimeRef = useRef(0);
  const agentSpeakingTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );

  // -----------------------------------------------------------------------
  // Cleanup
  // -----------------------------------------------------------------------

  const cleanup = useCallback(() => {
    clearTimeout(agentSpeakingTimerRef.current);

    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (captureCtxRef.current) {
      captureCtxRef.current.close().catch(() => {});
      captureCtxRef.current = null;
    }
    if (playbackCtxRef.current) {
      playbackCtxRef.current.close().catch(() => {});
      playbackCtxRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Send audio to backend (raw base64 PCM — matches backend protocol)
  // -----------------------------------------------------------------------

  const sendAudio = useCallback(
    (float32Data: Float32Array, sourceSampleRate: number) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
      if (mutedRef.current) return;

      const downsampled = downsample(float32Data, sourceSampleRate, SAMPLE_RATE);
      const pcm = float32ToInt16(downsampled);
      const encoded = int16ToBase64(pcm);
      wsRef.current.send(encoded);
    },
    [],
  );

  // -----------------------------------------------------------------------
  // Playback — queued for gapless audio
  // -----------------------------------------------------------------------

  const playAudio = useCallback((base64Audio: string) => {
    const ctx = playbackCtxRef.current;
    if (!ctx) return;

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

    const audioBuffer = ctx.createBuffer(1, float32.length, SAMPLE_RATE);
    audioBuffer.getChannelData(0).set(float32);

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);

    const startTime = Math.max(ctx.currentTime, nextPlayTimeRef.current);
    source.start(startTime);
    nextPlayTimeRef.current = startTime + audioBuffer.duration;

    // Mark agent as speaking while audio is playing.
    setState((prev) => ({ ...prev, isAgentSpeaking: true }));
    clearTimeout(agentSpeakingTimerRef.current);
    agentSpeakingTimerRef.current = setTimeout(() => {
      setState((prev) => ({ ...prev, isAgentSpeaking: false }));
    }, 1500);
  }, []);

  // -----------------------------------------------------------------------
  // Audio capture setup (AudioWorklet → ScriptProcessorNode fallback)
  // -----------------------------------------------------------------------

  const setupAudioCapture = useCallback(
    async (ws: WebSocket) => {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const audioCtx = new AudioContext();
      captureCtxRef.current = audioCtx;

      const sourceNode = audioCtx.createMediaStreamSource(stream);
      const nativeSampleRate = audioCtx.sampleRate;

      try {
        await audioCtx.audioWorklet.addModule('/audio-capture-processor.js');
        const workletNode = new AudioWorkletNode(audioCtx, 'audio-capture-processor');
        workletNodeRef.current = workletNode;

        workletNode.port.onmessage = (event: MessageEvent) => {
          sendAudio(event.data as Float32Array, nativeSampleRate);
        };

        sourceNode.connect(workletNode);

        // Keep the worklet in the active audio graph without audible output.
        const silentGain = audioCtx.createGain();
        silentGain.gain.value = 0;
        workletNode.connect(silentGain);
        silentGain.connect(audioCtx.destination);
      } catch {
        // AudioWorklet unavailable — fall back to ScriptProcessorNode.
        console.warn(
          'AudioWorklet not supported, falling back to ScriptProcessorNode',
        );
        const processor = audioCtx.createScriptProcessor(BUFFER_SIZE, 1, 1);
        processorRef.current = processor;

        processor.onaudioprocess = (e: AudioProcessingEvent) => {
          if (ws.readyState !== WebSocket.OPEN) return;
          sendAudio(new Float32Array(e.inputBuffer.getChannelData(0)), nativeSampleRate);
        };

        sourceNode.connect(processor);
        processor.connect(audioCtx.destination);
      }

      // Separate playback context at the target sample rate.
      playbackCtxRef.current = new AudioContext({ sampleRate: SAMPLE_RATE });
      nextPlayTimeRef.current = 0;
    },
    [sendAudio],
  );

  // -----------------------------------------------------------------------
  // Session lifecycle
  // -----------------------------------------------------------------------

  const startSession = useCallback(async () => {
    if (!VOICE_WS_URL) {
      setState({
        status: 'error',
        error: 'Voice is not available. Please use the form to complete onboarding.',
        isMuted: false,
        isAgentSpeaking: false,
        transcript: [],
      });
      return;
    }

    setState((prev) => ({ ...prev, status: 'connecting', error: null }));

    try {
      const token = await getToken();
      const ws = new WebSocket(
        `${VOICE_WS_URL}?token=${encodeURIComponent(token)}`,
      );
      wsRef.current = ws;

      ws.onopen = async () => {
        try {
          await setupAudioCapture(ws);
          setState((prev) => ({ ...prev, status: 'active' }));
        } catch (err) {
          cleanup();
          setState({
            status: 'error',
            error:
              err instanceof Error
                ? err.message
                : 'Microphone access denied',
            isMuted: false,
            isAgentSpeaking: false,
            transcript: [],
          });
        }
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(event.data as string) as Record<string, unknown>;

          if (msg.type === 'audio' && typeof msg.data === 'string') {
            playAudio(msg.data);
          } else if (msg.type === 'fallback') {
            cleanup();
            setState({
              status: 'error',
              error:
                typeof msg.message === 'string'
                  ? msg.message
                  : 'Voice session could not be established.',
              isMuted: false,
              isAgentSpeaking: false,
              transcript: [],
            });
          } else if (msg.type === 'transcript' && typeof msg.text === 'string') {
            const role =
              msg.role === 'user' ? ('user' as const) : ('assistant' as const);
            setState((prev) => ({
              ...prev,
              transcript: [
                ...prev.transcript,
                { role, text: msg.text as string },
              ],
            }));
          }
        } catch {
          // Non-JSON or malformed — ignore.
        }
      };

      ws.onerror = () => {
        cleanup();
        setState({
          status: 'error',
          error: 'Voice connection error. Please try again or use the form.',
          isMuted: false,
          isAgentSpeaking: false,
          transcript: [],
        });
      };

      ws.onclose = (event: CloseEvent) => {
        const wasConnected = wsRef.current !== null;
        wsRef.current = null;
        if (wasConnected) {
          cleanup();
          setState((prev) => {
            if (prev.status === 'ending') return prev;
            if (event.code !== 1000) {
              return {
                ...prev,
                status: 'error' as const,
                error: 'Voice connection was interrupted.',
                isAgentSpeaking: false,
              };
            }
            return { ...prev, status: 'ending' as const, isAgentSpeaking: false };
          });
        }
      };
    } catch (err) {
      cleanup();
      setState({
        status: 'error',
        error:
          err instanceof Error
            ? err.message
            : 'Failed to start voice session',
        isMuted: false,
        isAgentSpeaking: false,
        transcript: [],
      });
    }
  }, [getToken, setupAudioCapture, playAudio, cleanup]);

  const stopSession = useCallback(() => {
    setState((prev) => ({
      ...prev,
      status: 'ending',
      isAgentSpeaking: false,
    }));
    cleanup();
  }, [cleanup]);

  const toggleMute = useCallback(() => {
    mutedRef.current = !mutedRef.current;
    setState((prev) => ({ ...prev, isMuted: !prev.isMuted }));

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getAudioTracks().forEach((track) => {
        track.enabled = !mutedRef.current;
      });
    }
  }, []);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  return {
    status: state.status,
    error: state.error,
    isMuted: state.isMuted,
    isAgentSpeaking: state.isAgentSpeaking,
    transcript: state.transcript,
    startSession,
    stopSession,
    toggleMute,
    isAvailable:
      !!VOICE_WS_URL &&
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices?.getUserMedia,
  };
}
