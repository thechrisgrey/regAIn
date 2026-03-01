import { useNetworkStatus } from '../hooks/useNetworkStatusHook';

export default function ConnectionBanner() {
  const { isOnline, isReconnecting } = useNetworkStatus();

  if (isOnline && !isReconnecting) {
    return null;
  }

  if (!isOnline) {
    return (
      <div
        role="status"
        className="mb-4 rounded-[var(--radius-button)] bg-warning-50 px-4 py-2 text-sm font-medium text-warning-700 animate-fade-in"
      >
        You are offline. Reconnecting when network is available.
      </div>
    );
  }

  // isReconnecting
  return (
    <div
      role="status"
      className="mb-4 rounded-[var(--radius-button)] bg-primary-50 px-4 py-2 text-sm font-medium text-primary-700 animate-fade-in"
    >
      <span className="inline-block animate-voice-pulse">Reconnecting...</span>
    </div>
  );
}
