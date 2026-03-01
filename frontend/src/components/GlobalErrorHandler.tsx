import { useEffect, useRef } from 'react';
import { useToast } from './ui';

/**
 * Catches unhandled promise rejections and shows an error toast.
 * Debounces repeat errors within 5 seconds. Ignores AbortError
 * (fetch cancellation) to avoid spurious notifications.
 *
 * Renders nothing — mount inside ToastProvider.
 */
export default function GlobalErrorHandler() {
  const { toast } = useToast();
  const lastErrorTime = useRef(0);

  useEffect(() => {
    function handler(event: PromiseRejectionEvent) {
      // Ignore fetch cancellation (AbortController)
      const reason = event.reason;
      if (
        reason instanceof DOMException &&
        reason.name === 'AbortError'
      ) {
        return;
      }

      // Debounce: skip repeat errors within 5 seconds
      const now = Date.now();
      if (now - lastErrorTime.current < 5_000) {
        return;
      }
      lastErrorTime.current = now;

      toast({
        message: 'Something went wrong. Please try again.',
        variant: 'error',
      });
    }

    window.addEventListener('unhandledrejection', handler);
    return () => window.removeEventListener('unhandledrejection', handler);
  }, [toast]);

  return null;
}
