import { useState, useRef, useEffect, type FormEvent } from 'react';
import { useCoaching } from '../hooks/useCoaching';
import { useVoiceSession } from '../hooks/useVoiceSession';
import { Button } from '../components/ui';

const SESSION_TYPES = [
  { value: 'onboarding', label: 'Onboarding' },
  { value: 'checkin', label: 'Check-in' },
  { value: 'general', label: 'General' },
] as const;

export default function CoachingPage() {
  const { messages, loading, error, sendMessage } = useCoaching();
  const { isActive: voiceActive, error: voiceError, fallbackToText, startSession, stopSession } = useVoiceSession();

  const [input, setInput] = useState('');
  const [sessionType, setSessionType] = useState('checkin');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    setInput('');
    void sendMessage(trimmed, sessionType);
  };

  const toggleVoice = () => {
    if (voiceActive) {
      stopSession();
    } else {
      void startSession();
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)] animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-neutral-200">
        <h1 className="text-2xl font-bold text-neutral-900">Coaching</h1>
        <div className="flex items-center gap-2">
          <label htmlFor="session-type" className="text-sm text-neutral-600">
            Session:
          </label>
          <select
            id="session-type"
            value={sessionType}
            onChange={(e) => setSessionType(e.target.value)}
            className="rounded-[var(--radius-button)] border border-neutral-200 bg-white px-3 py-1.5 text-sm text-neutral-700 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20"
          >
            {SESSION_TYPES.map(({ value, label }) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Message History */}
      <div className="flex-1 overflow-y-auto py-4 space-y-3" role="log" aria-label="Coaching conversation">
        {messages.length === 0 && (
          <p className="text-center text-neutral-400 mt-12">
            Start a conversation with your coaching agent.
          </p>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[75%] px-4 py-2 text-sm whitespace-pre-wrap animate-scale-in ${
                msg.role === 'user'
                  ? 'bg-primary-500 text-white rounded-2xl rounded-br-sm'
                  : 'bg-surface-3 text-neutral-900 rounded-2xl rounded-bl-sm'
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-surface-3 text-neutral-500 rounded-2xl rounded-bl-sm px-4 py-3 text-sm flex items-center gap-1.5">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-neutral-400 animate-pulse" />
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-neutral-400 animate-pulse" style={{ animationDelay: '150ms' }} />
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-neutral-400 animate-pulse" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Voice / Error Notices */}
      {voiceError && (
        <p className="text-sm text-error-600 px-1 pb-1" role="alert">{voiceError}</p>
      )}
      {fallbackToText && !voiceError && (
        <p className="text-sm text-warning-600 px-1 pb-1" role="status">
          Voice unavailable — using text mode.
        </p>
      )}
      {error && (
        <p className="text-sm text-error-600 px-1 pb-1" role="alert">{error}</p>
      )}

      {/* Input Area */}
      <form onSubmit={handleSubmit} className="flex items-center gap-2 pt-3 border-t border-neutral-200">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          disabled={loading}
          aria-label="Coaching message"
          className="flex-1 rounded-[var(--radius-card)] border border-neutral-200 px-4 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 disabled:opacity-50"
        />
        <Button
          type="submit"
          disabled={loading || !input.trim()}
          aria-label="Send message"
        >
          Send
        </Button>
        <button
          type="button"
          onClick={toggleVoice}
          aria-label={voiceActive ? 'Stop voice session' : 'Start voice session'}
          className={`rounded-[var(--radius-card)] px-3 py-2 text-sm font-medium transition-colors duration-150 ${
            voiceActive
              ? 'bg-error-500 text-white hover:bg-error-600 animate-pulse'
              : 'bg-neutral-100 text-neutral-700 hover:bg-neutral-200'
          }`}
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 00-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z" clipRule="evenodd" />
          </svg>
        </button>
      </form>
    </div>
  );
}
