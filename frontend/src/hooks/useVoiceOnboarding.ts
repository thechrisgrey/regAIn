import { useState, useRef, useCallback, useEffect } from 'react';
import { useAuth } from './useAuth';

const VOICE_WS_URL = import.meta.env.VITE_VOICE_WS_URL as string | undefined;
const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;
const CAPTURE_BUFFER_SIZE = 4096;
const PLAYBACK_BUFFER_SIZE = 4096;
const CHUNK_INTERVAL_MS = 100;

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

/** Resample using linear interpolation (higher quality than nearest-neighbor). */
function resampleAudio(
  input: Float32Array,
  inputRate: number,
  outputRate: number,
): Float32Array {
  if (inputRate === outputRate) return input;
  const ratio = inputRate / outputRate;
  const outputLength = Math.floor(input.length / ratio);
  const output = new Float32Array(outputLength);
  for (let i = 0; i < outputLength; i++) {
    const srcIndex = i * ratio;
    const index = Math.floor(srcIndex);
    const fraction = srcIndex - index;
    if (index + 1 < input.length) {
      output[i] = input[index] * (1 - fraction) + input[index + 1] * fraction;
    } else {
      output[i] = input[index];
    }
  }
  return output;
}

/** Convert float samples [-1,1] to PCM 16-bit. */
function floatTo16BitPCM(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return output;
}

/** Convert an ArrayBuffer of PCM bytes to a base64 string. */
function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
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

  // Refs — WebSocket & lifecycle
  const wsRef = useRef<WebSocket | null>(null);
  const intentionalCloseRef = useRef(false);
  const stateRef = useRef<VoiceStatus>('idle');

  // Refs — Capture
  const captureCtxRef = useRef<AudioContext | null>(null);
  const captureProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mutedRef = useRef(false);

  // Refs — Playback (continuous buffer approach from elo)
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const playbackProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const playbackBufferRef = useRef<Float32Array>(new Float32Array(0));
  const readIndexRef = useRef(0);
  const writeIndexRef = useRef(0);

  // Keep stateRef in sync for use inside audio callbacks.
  useEffect(() => {
    stateRef.current = state.status;
  }, [state.status]);

  // -----------------------------------------------------------------------
  // State updater
  // -----------------------------------------------------------------------

  const updateState = useCallback(
    (patch: Partial<VoiceState>) => {
      setState((prev) => ({ ...prev, ...patch }));
    },
    [],
  );

  // -----------------------------------------------------------------------
  // Playback — continuous buffer with ScriptProcessorNode
  // -----------------------------------------------------------------------

  const ensurePlaybackCapacity = useCallback((additional: number) => {
    const buf = playbackBufferRef.current;
    const needed = writeIndexRef.current + additional;
    if (needed > buf.length) {
      const newSize = Math.max(buf.length * 2, needed + OUTPUT_SAMPLE_RATE);
      const newBuf = new Float32Array(newSize);
      newBuf.set(buf);
      playbackBufferRef.current = newBuf;
    }
  }, []);

  const compactPlaybackBuffer = useCallback(() => {
    const buf = playbackBufferRef.current;
    const ri = readIndexRef.current;
    const wi = writeIndexRef.current;
    const unread = wi - ri;
    if (ri > 0 && unread > 0) {
      buf.copyWithin(0, ri, wi);
      readIndexRef.current = 0;
      writeIndexRef.current = unread;
    } else if (unread <= 0) {
      readIndexRef.current = 0;
      writeIndexRef.current = 0;
    }
  }, []);

  const initPlayback = useCallback(() => {
    if (playbackCtxRef.current) return;

    const ctx = new AudioContext({ sampleRate: OUTPUT_SAMPLE_RATE });
    playbackCtxRef.current = ctx;

    const processor = ctx.createScriptProcessor(PLAYBACK_BUFFER_SIZE, 1, 1);
    playbackProcessorRef.current = processor;

    processor.onaudioprocess = (event: AudioProcessingEvent) => {
      const output = event.outputBuffer.getChannelData(0);
      const buf = playbackBufferRef.current;
      const ri = readIndexRef.current;
      const wi = writeIndexRef.current;
      const available = wi - ri;

      if (available >= output.length) {
        output.set(buf.subarray(ri, ri + output.length));
        readIndexRef.current = ri + output.length;
        // Compact periodically to prevent unbounded growth.
        if (readIndexRef.current > OUTPUT_SAMPLE_RATE * 2) {
          compactPlaybackBuffer();
        }
      } else if (available > 0) {
        output.set(buf.subarray(ri, wi));
        output.fill(0, available);
        readIndexRef.current = wi;
      } else {
        output.fill(0);
      }
    };

    processor.connect(ctx.destination);
  }, [compactPlaybackBuffer]);

  /** Queue decoded audio into the playback buffer. */
  const queueAudio = useCallback(
    (base64Audio: string) => {
      initPlayback();
      try {
        const binaryStr = atob(base64Audio);
        const bytes = new Uint8Array(binaryStr.length);
        for (let i = 0; i < binaryStr.length; i++) {
          bytes[i] = binaryStr.charCodeAt(i);
        }
        const pcm = new Int16Array(bytes.buffer);
        const floats = new Float32Array(pcm.length);
        for (let i = 0; i < pcm.length; i++) {
          floats[i] = pcm[i] / 32768.0;
        }

        ensurePlaybackCapacity(floats.length);
        playbackBufferRef.current.set(floats, writeIndexRef.current);
        writeIndexRef.current += floats.length;

        // Mark agent as speaking.
        updateState({ isAgentSpeaking: true });
      } catch {
        // Invalid base64 — ignore silently.
      }
    },
    [initPlayback, ensurePlaybackCapacity, updateState],
  );

  /** Immediately clear pending playback audio (barge-in). */
  const clearPlaybackQueue = useCallback(() => {
    readIndexRef.current = 0;
    writeIndexRef.current = 0;
    playbackBufferRef.current = new Float32Array(OUTPUT_SAMPLE_RATE * 2);
  }, []);

  const stopPlayback = useCallback(() => {
    readIndexRef.current = 0;
    writeIndexRef.current = 0;
    playbackBufferRef.current = new Float32Array(0);
    if (playbackProcessorRef.current) {
      playbackProcessorRef.current.disconnect();
      playbackProcessorRef.current = null;
    }
    if (playbackCtxRef.current) {
      playbackCtxRef.current.close().catch(() => {});
      playbackCtxRef.current = null;
    }
  }, []);

  // -----------------------------------------------------------------------
  // Capture — ScriptProcessorNode (intentional; best browser support)
  // -----------------------------------------------------------------------

  const stopCapture = useCallback(() => {
    if (captureProcessorRef.current) {
      captureProcessorRef.current.disconnect();
      captureProcessorRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (captureCtxRef.current) {
      captureCtxRef.current.close().catch(() => {});
      captureCtxRef.current = null;
    }
  }, []);

  const startCapture = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: { ideal: INPUT_SAMPLE_RATE },
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    mediaStreamRef.current = stream;

    const ctx = new AudioContext({ sampleRate: INPUT_SAMPLE_RATE });
    captureCtxRef.current = ctx;
    const nativeRate = ctx.sampleRate;

    const source = ctx.createMediaStreamSource(stream);
    const processor = ctx.createScriptProcessor(CAPTURE_BUFFER_SIZE, 1, 1);
    captureProcessorRef.current = processor;

    let audioBuffer: Float32Array[] = [];
    let lastSendTime = Date.now();

    processor.onaudioprocess = (event: AudioProcessingEvent) => {
      const inputData = event.inputBuffer.getChannelData(0);

      // Don't send audio while the agent is speaking (prevents feedback loop).
      // When muted, send silence to keep the Nova Sonic stream alive.
      if (stateRef.current === 'active' && mutedRef.current) {
        audioBuffer.push(new Float32Array(inputData.length)); // silence
      } else if (stateRef.current === 'active') {
        audioBuffer.push(new Float32Array(inputData));
      } else {
        return;
      }

      // Batch into ~100ms chunks for network efficiency.
      const now = Date.now();
      if (
        now - lastSendTime >= CHUNK_INTERVAL_MS &&
        wsRef.current?.readyState === WebSocket.OPEN
      ) {
        const totalLen = audioBuffer.reduce((s, a) => s + a.length, 0);
        const combined = new Float32Array(totalLen);
        let offset = 0;
        for (const arr of audioBuffer) {
          combined.set(arr, offset);
          offset += arr.length;
        }

        const resampled = resampleAudio(combined, nativeRate, INPUT_SAMPLE_RATE);
        const pcm = floatTo16BitPCM(resampled);
        const encoded = arrayBufferToBase64(pcm.buffer as ArrayBuffer);
        // Backend expects raw base64 PCM in event.body (not JSON-wrapped).
        wsRef.current.send(encoded);

        audioBuffer = [];
        lastSendTime = now;
      }
    };

    source.connect(processor);
    processor.connect(ctx.destination);
  }, []);

  // -----------------------------------------------------------------------
  // Auto-mute microphone while agent is speaking (prevents feedback loop)
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (state.isAgentSpeaking) {
      mutedRef.current = true;
      setState((prev) => (prev.isMuted ? prev : { ...prev, isMuted: true }));
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getAudioTracks().forEach((t) => {
          t.enabled = false;
        });
      }
    } else if (state.status === 'active') {
      mutedRef.current = false;
      setState((prev) => (!prev.isMuted ? prev : { ...prev, isMuted: false }));
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getAudioTracks().forEach((t) => {
          t.enabled = true;
        });
      }
    }
  }, [state.isAgentSpeaking, state.status]);

  // Detect when agent stops speaking (no audio queued for 1.5s).
  const speakingTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const resetSpeakingTimer = useCallback(() => {
    clearTimeout(speakingTimerRef.current);
    speakingTimerRef.current = setTimeout(() => {
      updateState({ isAgentSpeaking: false });
    }, 1500);
  }, [updateState]);

  // -----------------------------------------------------------------------
  // Cleanup
  // -----------------------------------------------------------------------

  const cleanup = useCallback(() => {
    clearTimeout(speakingTimerRef.current);
    stopCapture();
    stopPlayback();
    if (wsRef.current) {
      wsRef.current.close(1000, 'cleanup');
      wsRef.current = null;
    }
  }, [stopCapture, stopPlayback]);

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
    intentionalCloseRef.current = false;

    try {
      const token = await getToken();
      // Connect without token in URL — send auth as first message.
      const ws = new WebSocket(VOICE_WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        // Send auth as first WebSocket message instead of query param.
        ws.send(JSON.stringify({ type: 'auth', token }));
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(event.data as string) as Record<
            string,
            unknown
          >;

          switch (msg.type) {
            case 'auth_success':
              // Auth confirmed — start audio capture.
              void (async () => {
                try {
                  await startCapture();
                  setState((prev) => ({ ...prev, status: 'active' }));
                } catch (err) {
                  cleanup();
                  setState({
                    status: 'error',
                    error:
                      err instanceof Error ? err.message : 'Microphone access denied',
                    isMuted: false,
                    isAgentSpeaking: false,
                    transcript: [],
                  });
                }
              })();
              break;

            case 'audio': {
              // Backend sends: {"type": "audio", "data": "<base64>"}
              const audioData =
                typeof msg.data === 'string'
                  ? msg.data
                  : typeof (msg.data as Record<string, unknown>)?.content ===
                      'string'
                    ? ((msg.data as Record<string, unknown>).content as string)
                    : null;
              if (audioData) {
                queueAudio(audioData);
                resetSpeakingTimer();
              }
              break;
            }

            case 'clear_audio':
              // Barge-in: immediately stop pending playback.
              clearPlaybackQueue();
              updateState({ isAgentSpeaking: false });
              break;

            case 'state': {
              // State updates from backend (listening, thinking, speaking).
              const serverState = (msg.data as Record<string, unknown>)
                ?.state as string | undefined;
              if (serverState === 'speaking') {
                updateState({ isAgentSpeaking: true });
              } else if (
                serverState === 'listening' ||
                serverState === 'thinking'
              ) {
                updateState({ isAgentSpeaking: false });
              }
              break;
            }

            case 'transcript': {
              const data = msg.data as Record<string, unknown> | undefined;
              const text =
                typeof msg.text === 'string'
                  ? msg.text
                  : typeof data?.content === 'string'
                    ? (data.content as string)
                    : null;
              if (text) {
                const role =
                  (msg.role ?? data?.role) === 'user'
                    ? ('user' as const)
                    : ('assistant' as const);
                setState((prev) => {
                  const last = prev.transcript[prev.transcript.length - 1];
                  if (last && last.role === role) {
                    const updated = [...prev.transcript];
                    updated[updated.length - 1] = {
                      ...last,
                      text: last.text + text,
                    };
                    return { ...prev, transcript: updated };
                  }
                  return {
                    ...prev,
                    transcript: [...prev.transcript, { role, text }],
                  };
                });
              }
              break;
            }

            case 'fallback':
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
              break;

            case 'session_ended':
              intentionalCloseRef.current = true;
              cleanup();
              setState((prev) => ({
                ...prev,
                status: 'ending',
                isAgentSpeaking: false,
              }));
              break;

            case 'error':
              cleanup();
              setState({
                status: 'error',
                error:
                  typeof (msg.data as Record<string, unknown>)?.message ===
                  'string'
                    ? ((msg.data as Record<string, unknown>).message as string)
                    : 'Voice session error.',
                isMuted: false,
                isAgentSpeaking: false,
                transcript: [],
              });
              break;

            default:
              break;
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
        wsRef.current = null;
        if (!intentionalCloseRef.current) {
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
            return {
              ...prev,
              status: 'ending' as const,
              isAgentSpeaking: false,
            };
          });
        }
      };
    } catch (err) {
      cleanup();
      setState({
        status: 'error',
        error:
          err instanceof Error ? err.message : 'Failed to start voice session',
        isMuted: false,
        isAgentSpeaking: false,
        transcript: [],
      });
    }
  }, [
    getToken,
    startCapture,
    cleanup,
    queueAudio,
    clearPlaybackQueue,
    resetSpeakingTimer,
    updateState,
  ]);

  const stopSession = useCallback(() => {
    intentionalCloseRef.current = true;
    setState((prev) => ({
      ...prev,
      status: 'ending',
      isAgentSpeaking: false,
    }));
    cleanup();
  }, [cleanup]);

  const toggleMute = useCallback(() => {
    const newMuted = !mutedRef.current;
    mutedRef.current = newMuted;
    setState((prev) => ({ ...prev, isMuted: newMuted }));
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getAudioTracks().forEach((track) => {
        track.enabled = !newMuted;
      });
    }
  }, []);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      intentionalCloseRef.current = true;
      clearTimeout(speakingTimerRef.current);
      stopCapture();
      stopPlayback();
      if (wsRef.current) {
        wsRef.current.close(1000, 'Unmount cleanup');
        wsRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
