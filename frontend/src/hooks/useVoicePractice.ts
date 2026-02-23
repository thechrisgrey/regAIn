import { useState, useRef, useCallback, useEffect } from 'react';
import { useAuth } from './useAuth';
import type { VoicePracticeSessionType } from '../types';

const VOICE_PRACTICE_WS_URL = import.meta.env.VITE_VOICE_PRACTICE_WS_URL as string | undefined;
const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;
const CAPTURE_BUFFER_SIZE = 4096;
const PLAYBACK_BUFFER_SIZE = 4096;
const CHUNK_INTERVAL_MS = 100;

export type VoiceStatus = 'idle' | 'connecting' | 'active' | 'ending' | 'assessing' | 'error';

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
  sessionType: VoicePracticeSessionType | null;
}

// ---------------------------------------------------------------------------
// Audio helpers
// ---------------------------------------------------------------------------

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

function floatTo16BitPCM(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return output;
}

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

export function useVoicePractice() {
  const { getToken } = useAuth();
  const [state, setState] = useState<VoiceState>({
    status: 'idle',
    error: null,
    isMuted: false,
    isAgentSpeaking: false,
    transcript: [],
    sessionType: null,
  });

  // Refs -- WebSocket & lifecycle
  const wsRef = useRef<WebSocket | null>(null);
  const intentionalCloseRef = useRef(false);
  const stateRef = useRef<VoiceStatus>('idle');

  // Refs -- Capture
  const captureCtxRef = useRef<AudioContext | null>(null);
  const captureProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const mutedRef = useRef(false);

  // Refs -- Playback (continuous buffer approach)
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const playbackProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const playbackBufferRef = useRef<Float32Array>(new Float32Array(0));
  const readIndexRef = useRef(0);
  const writeIndexRef = useRef(0);

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
  // Playback -- continuous buffer with ScriptProcessorNode
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

        updateState({ isAgentSpeaking: true });
      } catch {
        // Invalid base64 -- ignore silently.
      }
    },
    [initPlayback, ensurePlaybackCapacity, updateState],
  );

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
  // Capture -- ScriptProcessorNode (intentional; best browser support)
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

      if (stateRef.current === 'active' && mutedRef.current) {
        audioBuffer.push(new Float32Array(inputData.length)); // silence
      } else if (stateRef.current === 'active') {
        audioBuffer.push(new Float32Array(inputData));
      } else {
        return;
      }

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
        wsRef.current.send(encoded);

        audioBuffer = [];
        lastSendTime = now;
      }
    };

    source.connect(processor);
    processor.connect(ctx.destination);
  }, []);

  // -----------------------------------------------------------------------
  // Auto-mute microphone while agent is speaking
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

  const startSession = useCallback(async (sessionType: VoicePracticeSessionType) => {
    if (!VOICE_PRACTICE_WS_URL) {
      setState({
        status: 'error',
        error: 'Voice practice is not available at this time.',
        isMuted: false,
        isAgentSpeaking: false,
        transcript: [],
        sessionType: null,
      });
      return;
    }

    setState((prev) => ({
      ...prev,
      status: 'connecting',
      error: null,
      transcript: [],
      sessionType,
    }));
    intentionalCloseRef.current = false;

    try {
      const token = await getToken();
      const ws = new WebSocket(
        `${VOICE_PRACTICE_WS_URL}?token=${encodeURIComponent(token)}&session_type=${encodeURIComponent(sessionType)}`,
      );
      wsRef.current = ws;

      ws.onopen = async () => {
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
            sessionType: null,
          });
        }
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(event.data as string) as Record<
            string,
            unknown
          >;

          switch (msg.type) {
            case 'audio': {
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
              clearPlaybackQueue();
              updateState({ isAgentSpeaking: false });
              break;

            case 'state': {
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
                sessionType: null,
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
                sessionType: null,
              });
              break;

            default:
              break;
          }
        } catch {
          // Non-JSON or malformed -- ignore.
        }
      };

      ws.onerror = () => {
        cleanup();
        setState({
          status: 'error',
          error: 'Voice connection error. Please try again.',
          isMuted: false,
          isAgentSpeaking: false,
          transcript: [],
          sessionType: null,
        });
      };

      ws.onclose = (event: CloseEvent) => {
        wsRef.current = null;
        if (!intentionalCloseRef.current) {
          cleanup();
          setState((prev) => {
            if (prev.status === 'ending' || prev.status === 'assessing') return prev;
            if (event.code === 1000) {
              // Normal close -- transition to assessing
              return {
                ...prev,
                status: 'assessing' as const,
                isAgentSpeaking: false,
              };
            }
            return {
              ...prev,
              status: 'error' as const,
              error: 'Voice connection was interrupted.',
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
        sessionType: null,
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
      status: 'assessing',
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
    sessionType: state.sessionType,
    startSession,
    stopSession,
    toggleMute,
    isAvailable:
      !!VOICE_PRACTICE_WS_URL &&
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices?.getUserMedia,
  };
}
