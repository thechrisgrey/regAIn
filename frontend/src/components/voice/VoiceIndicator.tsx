interface VoiceIndicatorProps {
  state: 'listening' | 'speaking' | 'connecting';
}

export default function VoiceIndicator({ state }: VoiceIndicatorProps) {
  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: 160, height: 160 }}
      aria-hidden="true"
    >
      {/* Ripple rings — visible when the agent is speaking */}
      {state === 'speaking' && (
        <>
          <span
            className="absolute inset-0 rounded-full border border-accent-400/30 animate-voice-ripple"
          />
          <span
            className="absolute inset-0 rounded-full border border-accent-400/20 animate-voice-ripple"
            style={{ animationDelay: '0.6s' }}
          />
          <span
            className="absolute inset-0 rounded-full border border-accent-400/10 animate-voice-ripple"
            style={{ animationDelay: '1.2s' }}
          />
        </>
      )}

      {/* Breathing ring — visible when listening */}
      {state === 'listening' && (
        <span
          className="absolute rounded-full border border-accent-300/30 animate-voice-breathe"
          style={{ inset: '16px' }}
        />
      )}

      {/* Center circle */}
      <div
        className={`relative z-10 rounded-full transition-all duration-500 ${
          state === 'speaking'
            ? 'h-20 w-20 bg-primary-500 animate-voice-pulse'
            : state === 'listening'
              ? 'h-16 w-16 bg-primary-400 animate-voice-pulse'
              : 'h-14 w-14 bg-neutral-300 animate-pulse'
        }`}
        style={
          state === 'speaking'
            ? { boxShadow: '0 0 32px rgba(145, 109, 101, 0.3)' }
            : state === 'listening'
              ? { boxShadow: '0 0 20px rgba(191, 168, 197, 0.25)' }
              : undefined
        }
      />
    </div>
  );
}
