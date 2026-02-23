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
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">Voice Practice</h1>
        <p className="mt-1 text-sm text-neutral-500">Sharpen your interview skills with AI-powered practice sessions</p>
      </div>

      {voiceError && (
        <p className="text-sm text-error-600 mb-4" role="alert">{voiceError}</p>
      )}

      {/* Mode selection cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        <Card hoverable className="p-6 animate-fade-in-up" style={{ animationDelay: '0ms' }}>
          <div className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-button)] bg-primary-50 ring-1 ring-primary-100 mb-4">
            <svg className="h-5 w-5 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 0 1-.825-.242m9.345-8.334a2.126 2.126 0 0 0-.476-.095 48.64 48.64 0 0 0-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0 0 11.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
            </svg>
          </div>
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
          <div className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-button)] bg-info-50 ring-1 ring-info-100 mb-4">
            <svg className="h-5 w-5 text-info-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3v11.25A2.25 2.25 0 0 0 6 16.5h2.25M3.75 3h-1.5m1.5 0h16.5m0 0h1.5m-1.5 0v11.25A2.25 2.25 0 0 1 18 16.5h-2.25m-7.5 0h7.5m-7.5 0-1 3m8.5-3 1 3m0 0 .5 1.5m-.5-1.5h-9.5m0 0-.5 1.5m.75-9 3-3 2.148 2.148A12.061 12.061 0 0 1 16.5 7.605" />
            </svg>
          </div>
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
      <div className="section-divider mb-6" />
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
