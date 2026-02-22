import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useVoicePractice } from '../hooks/useVoicePractice';
import { useVoiceSessions } from '../hooks/useVoiceSessions';
import { Button, Card, Badge, SkeletonBlock } from '../components/ui';

const AudioVisualizer = lazy(() => import('../components/voice/AudioVisualizer'));
import type { VoicePracticeSessionType } from '../types';

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export default function VoicePracticePage() {
  const navigate = useNavigate();
  const {
    status,
    error: voiceError,
    isMuted,
    isAgentSpeaking,
    transcript,
    startSession,
    stopSession,
    toggleMute,
  } = useVoicePractice();

  const {
    sessions,
    loading: sessionsLoading,
    error: sessionsError,
    fetchSessions,
  } = useVoiceSessions();

  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const [initialSessionCount, setInitialSessionCount] = useState<number | null>(null);

  // Load sessions on mount
  useEffect(() => {
    void fetchSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript]);

  // Poll for completed session during assessing state
  useEffect(() => {
    if (status === 'assessing') {
      setInitialSessionCount(sessions.length);
      pollRef.current = setInterval(() => {
        void fetchSessions();
      }, 3000);
    } else {
      clearInterval(pollRef.current);
      setInitialSessionCount(null);
    }
    return () => clearInterval(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  // Navigate to new session when it appears during assessing
  useEffect(() => {
    if (status === 'assessing' && initialSessionCount !== null && sessions.length > initialSessionCount) {
      const newest = sessions.find((s) => s.status === 'completed');
      if (newest) {
        clearInterval(pollRef.current);
        navigate(`/voice-practice/${newest.sessionId}`);
      }
    }
  }, [sessions, status, initialSessionCount, navigate]);

  const handleStart = (type: VoicePracticeSessionType) => {
    void startSession(type);
  };

  // -----------------------------------------------------------------------
  // View 3: Assessing
  // -----------------------------------------------------------------------
  if (status === 'assessing') {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] animate-fade-in">
        <div className="h-12 w-12 rounded-full border-4 border-primary-200 border-t-primary-500 animate-spin mb-6" />
        <p className="text-lg font-medium text-neutral-900">
          Generating your assessment...
        </p>
        <p className="text-sm text-neutral-500 mt-2">
          This may take a moment.
        </p>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // View 2: Active Voice Session
  // -----------------------------------------------------------------------
  if (status === 'connecting' || status === 'active') {
    const statusText = status === 'connecting'
      ? 'Connecting...'
      : isMuted
        ? 'Muted'
        : isAgentSpeaking
          ? 'Coach speaking...'
          : 'Listening...';

    return (
      <div className="flex flex-col h-[calc(100vh-3rem)] animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-neutral-200">
          <h1 className="text-2xl font-bold text-neutral-900">Voice Practice</h1>
          <p className="text-sm text-neutral-600">{statusText}</p>
        </div>

        {/* Voice orb visualizer */}
        <Suspense fallback={<div className="h-40 w-40 mx-auto my-2 rounded-full bg-neutral-200 animate-pulse" />}>
          <AudioVisualizer
            state={
              status === 'connecting'
                ? 'connecting'
                : isMuted
                  ? 'muted'
                  : isAgentSpeaking
                    ? 'speaking'
                    : 'listening'
            }
            className="h-40 w-40 mx-auto my-2"
          />
        </Suspense>

        {/* Transcript panel */}
        <div className="flex-1 overflow-y-auto py-4 space-y-3" role="log" aria-label="Voice practice conversation">
          {transcript.length === 0 && status === 'active' && (
            <p className="text-center text-neutral-400 mt-8">
              Start speaking to begin the session.
            </p>
          )}
          {transcript.map((entry, i) => (
            <div
              key={i}
              className={`flex ${entry.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[75%] px-4 py-2 text-sm animate-scale-in ${
                  entry.role === 'user'
                    ? 'bg-primary-500 text-white rounded-2xl rounded-br-sm whitespace-pre-wrap'
                    : 'bg-surface-3 text-neutral-900 rounded-2xl rounded-bl-sm'
                }`}
              >
                {entry.text}
              </div>
            </div>
          ))}
          <div ref={transcriptEndRef} />
        </div>

        {/* Voice error */}
        {voiceError && (
          <p className="text-sm text-error-600 px-1 pb-1" role="alert">{voiceError}</p>
        )}

        {/* Controls bar */}
        <div className="flex items-center justify-center gap-3 pt-3 border-t border-neutral-200">
          <button
            type="button"
            onClick={toggleMute}
            aria-label={isMuted ? 'Unmute microphone' : 'Mute microphone'}
            className={`rounded-[var(--radius-card)] px-3 py-2 text-sm font-medium transition-colors duration-150 ${
              isMuted
                ? 'bg-warning-100 text-warning-700 hover:bg-warning-200'
                : 'bg-neutral-100 text-neutral-700 hover:bg-neutral-200'
            }`}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              {isMuted ? (
                <path fillRule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM12.293 7.293a1 1 0 011.414 0L15 8.586l1.293-1.293a1 1 0 111.414 1.414L16.414 10l1.293 1.293a1 1 0 01-1.414 1.414L15 11.414l-1.293 1.293a1 1 0 01-1.414-1.414L13.586 10l-1.293-1.293a1 1 0 010-1.414z" clipRule="evenodd" />
              ) : (
                <path fillRule="evenodd" d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 00-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z" clipRule="evenodd" />
              )}
            </svg>
          </button>
          <Button variant="destructive" onClick={stopSession}>
            End Session
          </Button>
        </div>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // View 1: Mode Selection + History (idle / ending / error)
  // -----------------------------------------------------------------------
  return (
    <div className="animate-fade-in">
      <h1 className="text-2xl font-bold text-neutral-900 mb-6">Voice Practice</h1>

      {voiceError && (
        <p className="text-sm text-error-600 mb-4" role="alert">{voiceError}</p>
      )}

      {/* Mode selection cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        <Card hoverable className="p-6 animate-fade-in-up" style={{ animationDelay: '0ms' }}>
          <h2 className="text-lg font-semibold text-neutral-900 mb-2">Mock Interview</h2>
          <p className="text-sm text-neutral-600 mb-4">
            Practice realistic interview scenarios for your target role. Receive
            real-time feedback on your responses, communication style, and
            technical depth.
          </p>
          <Button onClick={() => handleStart('interview')}>
            Start Interview
          </Button>
        </Card>

        <Card hoverable className="p-6 animate-fade-in-up" style={{ animationDelay: '80ms' }}>
          <h2 className="text-lg font-semibold text-neutral-900 mb-2">Mission Discussion</h2>
          <p className="text-sm text-neutral-600 mb-4">
            Talk through your recent missions and progress with your coaching
            agent. Get guidance on next steps and reflect on what you have
            learned.
          </p>
          <Button onClick={() => handleStart('mission_discussion')}>
            Start Discussion
          </Button>
        </Card>
      </div>

      {/* Session History */}
      <h2 className="text-lg font-semibold text-neutral-900 mb-3">Session History</h2>

      {sessionsError && (
        <p className="text-sm text-error-600 mb-3" role="alert">{sessionsError}</p>
      )}

      {sessionsLoading && sessions.length === 0 && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <SkeletonBlock key={i} className="h-20 w-full" style={{ animationDelay: `${i * 100}ms` }} />
          ))}
        </div>
      )}

      {!sessionsLoading && sessions.length === 0 && (
        <p className="text-sm text-neutral-500">
          Start your first voice practice session above.
        </p>
      )}

      {sessions.length > 0 && (
        <div className="space-y-3">
          {sessions.map((session, i) => (
            <Card
              key={session.sessionId}
              hoverable
              className="p-4 cursor-pointer animate-fade-in-up"
              style={{ animationDelay: `${i * 60}ms` }}
              onClick={() => navigate(`/voice-practice/${session.sessionId}`)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  navigate(`/voice-practice/${session.sessionId}`);
                }
              }}
            >
              <div className="flex items-center gap-4 flex-wrap">
                <span className="text-sm text-neutral-600">
                  {formatDate(session.createdAt)}
                </span>
                <Badge variant={session.sessionType === 'interview' ? 'primary' : 'info'}>
                  {session.sessionType === 'interview' ? 'Interview' : 'Mission Discussion'}
                </Badge>
                <span className="text-sm font-mono tabular-nums text-neutral-700">
                  {formatDuration(session.durationSeconds)}
                </span>
                <span className="text-sm font-mono tabular-nums text-neutral-900 font-semibold">
                  {session.overallScore}/10
                </span>
              </div>
              {session.assessmentSummary && (
                <p className="text-sm text-neutral-500 mt-2 line-clamp-2">
                  {session.assessmentSummary}
                </p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
