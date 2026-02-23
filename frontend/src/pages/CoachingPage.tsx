import { useState, useRef, useEffect, type FormEvent } from 'react';
import { useStreamingCoaching } from '../hooks/useStreamingCoaching';
import { useVoiceSession } from '../hooks/useVoiceSession';
import { Button, MarkdownMessage } from '../components/ui';

const SESSION_TYPES = [
  { value: 'onboarding', label: 'Onboarding' },
  { value: 'checkin', label: 'Check-in' },
  { value: 'general', label: 'General' },
] as const;

export default function CoachingPage() {
  const { messages, streaming, streamingText, thinking, thinkingLabel, error, sendMessage } = useStreamingCoaching();
  const { isActive: voiceActive, error: voiceError, fallbackToText, startSession, stopSession } = useVoiceSession();

  const [input, setInput] = useState('');
  const [sessionType, setSessionType] = useState('checkin');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingText]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || streaming) return;
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
      <div className="flex items-center justify-between pb-4 border-b border-neutral-100">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">Coaching</h1>
          <p className="mt-0.5 text-xs text-neutral-400">AI-powered career guidance</p>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="session-type" className="text-xs font-medium text-neutral-500">
            Session
          </label>
          <select
            id="session-type"
            value={sessionType}
            onChange={(e) => setSessionType(e.target.value)}
            className="rounded-[var(--radius-button)] border border-neutral-200/80 bg-surface-1 px-3 py-1.5 text-sm text-neutral-700 shadow-sm focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 transition-shadow"
          >
            {SESSION_TYPES.map(({ value, label }) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Message History */}
      <div className="flex-1 overflow-y-auto py-4 space-y-3" role="log" aria-label="Coaching conversation">
        {messages.length === 0 && !streaming && (
          <div className="flex flex-col items-center justify-center mt-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary-50 ring-1 ring-primary-100">
              <svg className="h-6 w-6 text-primary-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z" />
              </svg>
            </div>
            <p className="mt-4 text-sm font-medium text-neutral-700">
              Start a conversation with your coaching agent
            </p>
            <p className="mt-1 text-xs text-neutral-400">
              Ask about your campaign, get mission guidance, or discuss your career strategy
            </p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[75%] px-4 py-2 text-sm animate-scale-in ${
                msg.role === 'user'
                  ? 'bg-primary-500 text-white rounded-2xl rounded-br-sm whitespace-pre-wrap'
                  : 'bg-surface-3 text-neutral-900 rounded-2xl rounded-bl-sm'
              }`}
            >
              {msg.role === 'assistant' ? <MarkdownMessage content={msg.content} /> : msg.content}
            </div>
          </div>
        ))}

        {/* Streaming bubble — shows text as it arrives */}
        {streaming && streamingText && (
          <div className="flex justify-start">
            <div className="max-w-[75%] px-4 py-2 text-sm bg-surface-3 text-neutral-900 rounded-2xl rounded-bl-sm">
              <MarkdownMessage content={streamingText} />
              {thinking ? (
                <span className="block mt-2 text-xs text-neutral-400 italic animate-pulse">
                  {thinkingLabel || 'Thinking'}...
                </span>
              ) : (
                <span className="inline-block w-1.5 h-4 bg-primary-500 ml-0.5 animate-pulse align-text-bottom" />
              )}
            </div>
          </div>
        )}

        {/* Loading / thinking indicator — between send and first chunk */}
        {streaming && !streamingText && (
          <div className="flex justify-start">
            <div className="bg-surface-3 text-neutral-500 rounded-2xl rounded-bl-sm px-4 py-3 text-sm flex items-center gap-1.5">
              {thinking ? (
                <span className="text-xs text-neutral-500 italic animate-pulse">
                  {thinkingLabel || 'Thinking'}...
                </span>
              ) : (
                <>
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-neutral-400 animate-pulse" />
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-neutral-400 animate-pulse" style={{ animationDelay: '150ms' }} />
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-neutral-400 animate-pulse" style={{ animationDelay: '300ms' }} />
                </>
              )}
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
      <form onSubmit={handleSubmit} className="flex items-center gap-2 pt-3 border-t border-neutral-100">
        <div className="chat-input-glow flex-1 rounded-[var(--radius-card)] border border-neutral-200/80 bg-surface-1 transition-shadow">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message..."
            disabled={streaming}
            aria-label="Coaching message"
            className="w-full rounded-[var(--radius-card)] border-0 bg-transparent px-4 py-2.5 text-sm focus:outline-none disabled:opacity-50"
          />
        </div>
        <Button
          type="submit"
          disabled={streaming || !input.trim()}
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
