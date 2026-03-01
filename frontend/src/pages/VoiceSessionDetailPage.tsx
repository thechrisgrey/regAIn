import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useVoiceSessions } from '../hooks/useVoiceSessions';
import { Button, Card, Badge, ProgressBar, SkeletonBlock } from '../components/ui';

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function scoreColor(score: number): string {
  if (score >= 7) return 'text-success-600';
  if (score >= 4) return 'text-warning-600';
  return 'text-error-600';
}

function scoreBarColor(score: number): string {
  if (score >= 7) return 'bg-success-500';
  if (score >= 4) return 'bg-warning-500';
  return 'bg-error-500';
}

export default function VoiceSessionDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { sessionDetail, loading, error, fetchSessionDetail } = useVoiceSessions();
  const [transcriptExpanded, setTranscriptExpanded] = useState(false);

  useEffect(() => {
    if (sessionId) {
      void fetchSessionDetail(sessionId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  if (loading && !sessionDetail) {
    return (
      <div className="animate-fade-in">
        <SkeletonBlock className="h-5 w-40 mb-6" />
        <SkeletonBlock className="h-8 w-64 mb-4" />
        <SkeletonBlock className="h-24 w-full mb-4" />
        <SkeletonBlock className="h-48 w-full mb-4" />
        <SkeletonBlock className="h-48 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="animate-fade-in">
        <Link to="/voice-practice" className="text-sm text-primary-500 hover:text-primary-600 transition-colors">
          Back to Voice Practice
        </Link>
        <p className="text-sm text-error-600 mt-4" role="alert">{error}</p>
      </div>
    );
  }

  if (!sessionDetail) return null;

  const { assessment } = sessionDetail;

  // Normalize transcript: backend may return a flat array or a { turns } object.
  const turns = Array.isArray(sessionDetail.transcript)
    ? sessionDetail.transcript
    : sessionDetail.transcript?.turns ?? [];

  return (
    <div className="animate-fade-in">
      {/* Back link */}
      <Link
        to="/voice-practice"
        className="inline-block text-sm text-primary-500 hover:text-primary-600 transition-colors mb-4"
      >
        Back to Voice Practice
      </Link>

      {/* Session metadata bar */}
      <div className="flex items-center gap-4 flex-wrap mb-4">
        <span className="text-sm text-neutral-600">
          {formatDate(sessionDetail.createdAt)}
        </span>
        <Badge variant={sessionDetail.sessionType === 'interview' ? 'primary' : 'info'}>
          {sessionDetail.sessionType === 'interview' ? 'Interview' : 'Mission Discussion'}
        </Badge>
        <span className="text-sm font-mono tabular-nums text-neutral-700">
          {formatDuration(sessionDetail.durationSeconds)}
        </span>
        <span className={`text-2xl font-bold font-mono tabular-nums ${scoreColor(sessionDetail.overallScore)}`}>
          {sessionDetail.overallScore}
          <span className="text-sm font-normal text-neutral-500">/10</span>
        </span>
      </div>

      {/* Assessment summary */}
      {assessment?.summary && (
        <p className="text-sm italic text-neutral-600 mb-6">
          {assessment.summary}
        </p>
      )}

      {/* Assessment sections */}
      {assessment?.sections && assessment.sections.length > 0 && (
        <div className="space-y-4 mb-6">
          {assessment.sections.map((section, i) => (
            <Card
              key={section.title}
              variant="elevated"
              className="p-5 animate-fade-in-up"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold text-neutral-900">{section.title}</h3>
                <span className={`text-sm font-mono tabular-nums font-semibold ${scoreColor(section.score)}`}>
                  {section.score}/10
                </span>
              </div>
              <ProgressBar
                value={section.score * 10}
                barClassName={scoreBarColor(section.score)}
                className="mb-3"
              />
              <p className="text-sm text-neutral-700 mb-3">{section.feedback}</p>
              {section.suggestions.length > 0 && (
                <ul className="list-disc list-inside text-sm text-neutral-600 space-y-1">
                  {section.suggestions.map((suggestion, j) => (
                    <li key={j}>{suggestion}</li>
                  ))}
                </ul>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* Strengths */}
      {assessment?.strengths && assessment.strengths.length > 0 && (
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-neutral-900 mb-2">Strengths</h3>
          <div className="flex flex-wrap gap-2">
            {assessment.strengths.map((s) => (
              <Badge key={s} variant="success">{s}</Badge>
            ))}
          </div>
        </div>
      )}

      {/* Areas for Improvement */}
      {assessment?.areasForImprovement && assessment.areasForImprovement.length > 0 && (
        <div className="mb-6">
          <h3 className="text-sm font-semibold text-neutral-900 mb-2">Areas for Improvement</h3>
          <div className="flex flex-wrap gap-2">
            {assessment.areasForImprovement.map((a) => (
              <Badge key={a} variant="warning">{a}</Badge>
            ))}
          </div>
        </div>
      )}

      {/* Full Transcript */}
      {turns.length > 0 && (
        <div className="border-t border-neutral-200 pt-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setTranscriptExpanded(!transcriptExpanded)}
          >
            {transcriptExpanded ? 'Hide Transcript' : 'Show Full Transcript'}
            <svg
              className={`h-4 w-4 transition-transform duration-200 ${transcriptExpanded ? 'rotate-180' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </Button>

          {transcriptExpanded && (
            <div className="mt-4 space-y-3">
              {turns.map((turn, i) => (
                <div
                  key={i}
                  className={`flex ${turn.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[90%] sm:max-w-[75%] px-4 py-2 text-sm ${
                      turn.role === 'user'
                        ? 'bg-primary-500 text-white rounded-2xl rounded-br-sm whitespace-pre-wrap'
                        : 'bg-surface-3 text-neutral-900 rounded-2xl rounded-bl-sm'
                    }`}
                  >
                    {turn.text}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
