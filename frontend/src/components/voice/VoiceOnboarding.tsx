import { useEffect, useRef } from 'react';
import { useVoiceOnboarding } from '../../hooks/useVoiceOnboarding';
import VoiceIndicator from './VoiceIndicator';
import { Button } from '../ui';

interface VoiceOnboardingProps {
  onSessionEnd: () => void;
  onError: () => void;
}

export default function VoiceOnboarding({
  onSessionEnd,
  onError,
}: VoiceOnboardingProps) {
  const {
    status,
    error,
    isMuted,
    isAgentSpeaking,
    transcript,
    startSession,
    stopSession,
    toggleMute,
  } = useVoiceOnboarding();

  const endingHandledRef = useRef(false);

  // Start voice session on mount.
  useEffect(() => {
    void startSession();
  }, [startSession]);

  // When the session reaches "ending" state, notify the parent once.
  useEffect(() => {
    if (status === 'ending' && !endingHandledRef.current) {
      endingHandledRef.current = true;
      onSessionEnd();
    }
  }, [status, onSessionEnd]);

  const indicatorState = (() => {
    if (status === 'connecting') return 'connecting' as const;
    if (status === 'active' && isAgentSpeaking) return 'speaking' as const;
    return 'listening' as const;
  })();

  const statusText = (() => {
    if (status === 'connecting') return 'Connecting...';
    if (status === 'active' && isAgentSpeaking) return 'Coach is speaking...';
    if (status === 'active' && isMuted) return 'Microphone muted';
    if (status === 'active') return 'Listening...';
    if (status === 'ending') return 'Checking your profile...';
    return '';
  })();

  // -------------------------------------------------------------------
  // Error state
  // -------------------------------------------------------------------

  if (status === 'error') {
    return (
      <div className="flex flex-col items-center justify-center py-12 animate-fade-in">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-error-100">
          <svg
            className="h-6 w-6 text-error-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
            />
          </svg>
        </div>
        <p className="mt-4 text-base font-medium text-error-700">
          Voice session unavailable
        </p>
        <p className="mt-1 text-sm text-neutral-500 text-center max-w-sm">
          {error}
        </p>
        <Button variant="secondary" onClick={onError} className="mt-6">
          Continue with form
        </Button>
      </div>
    );
  }

  // -------------------------------------------------------------------
  // Ending state — loading spinner while parent checks profile
  // -------------------------------------------------------------------

  if (status === 'ending') {
    return (
      <div className="flex flex-col items-center justify-center py-16 animate-fade-in">
        <div className="h-10 w-10 animate-spin rounded-full border-[3px] border-neutral-200 border-t-primary-500" />
        <p className="mt-6 text-sm font-medium text-neutral-600">
          {statusText}
        </p>
      </div>
    );
  }

  // -------------------------------------------------------------------
  // Active / connecting state
  // -------------------------------------------------------------------

  return (
    <div className="flex flex-col items-center py-8 animate-fade-in">
      {/* Visual indicator */}
      <VoiceIndicator state={indicatorState} />

      {/* Status label */}
      <p className="mt-6 text-sm font-medium text-neutral-600" role="status">
        {statusText}
      </p>

      {/* Transcript — shown if the backend sends text events */}
      {transcript.length > 0 && (
        <div className="mt-6 w-full max-w-md space-y-2 max-h-48 overflow-y-auto">
          {transcript.map((entry, i) => (
            <div
              key={i}
              className={`text-sm px-3 py-1.5 rounded-lg ${
                entry.role === 'user'
                  ? 'ml-auto bg-primary-100 text-primary-800 max-w-[80%] text-right'
                  : 'mr-auto bg-surface-3 text-neutral-700 max-w-[80%]'
              }`}
            >
              {entry.text}
            </div>
          ))}
        </div>
      )}

      {/* Controls */}
      {status === 'active' && (
        <div className="mt-8 flex items-center gap-3">
          {/* Mute toggle */}
          <button
            type="button"
            onClick={toggleMute}
            aria-label={isMuted ? 'Unmute microphone' : 'Mute microphone'}
            className={`rounded-full p-3 transition-colors duration-150 ${
              isMuted
                ? 'bg-warning-100 text-warning-600 hover:bg-warning-200'
                : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200'
            }`}
          >
            {isMuted ? (
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M17.25 9.75L19.5 12m0 0l2.25 2.25M19.5 12l2.25-2.25M19.5 12l-2.25 2.25m-10.5-6l4.72-4.72a.75.75 0 011.28.531V19.94a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.009 9.009 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.756 3.63 8.25 4.51 8.25H6.75z"
                />
              </svg>
            ) : (
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
                />
              </svg>
            )}
          </button>

          {/* End session */}
          <Button variant="destructive" onClick={stopSession}>
            End conversation
          </Button>
        </div>
      )}

      {status === 'connecting' && (
        <p className="mt-4 text-xs text-neutral-400">
          Requesting microphone access...
        </p>
      )}
    </div>
  );
}
