import {
  createContext,
  useState,
  useCallback,
  useRef,
  useContext,
  useEffect,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';

interface Toast {
  id: string;
  message: string;
  variant: 'default' | 'success' | 'error';
  action?: { label: string; onClick: () => void };
  duration: number;
  dismissing: boolean;
}

type ToastOptions = {
  message: string;
  variant?: 'default' | 'success' | 'error';
  action?: { label: string; onClick: () => void };
  duration?: number;
};

interface ToastContextType {
  toast: (options: ToastOptions) => string;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    // Clear auto-dismiss timer.
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }

    // Trigger exit animation.
    setToasts(prev => prev.map(t => (t.id === id ? { ...t, dismissing: true } : t)));

    // Remove after animation completes.
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 200);
  }, []);

  const toast = useCallback(
    (options: ToastOptions): string => {
      const id = crypto.randomUUID();
      const duration = options.duration ?? 5000;

      const newToast: Toast = {
        id,
        message: options.message,
        variant: options.variant ?? 'default',
        action: options.action,
        duration,
        dismissing: false,
      };

      setToasts(prev => [...prev, newToast]);

      // Auto-dismiss timer.
      const timer = setTimeout(() => {
        dismiss(id);
      }, duration);
      timersRef.current.set(id, timer);

      return id;
    },
    [dismiss],
  );

  // Cleanup all timers on unmount.
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach(t => clearTimeout(t));
      timers.clear();
    };
  }, []);

  return (
    <ToastContext.Provider value={{ toast, dismiss }}>
      {children}
      <ToastContainer toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Container (portal to body)
// ---------------------------------------------------------------------------

const VARIANT_CLASSES: Record<Toast['variant'], string> = {
  default: 'bg-surface-1 border-neutral-200/80 text-neutral-700',
  success: 'bg-success-50 border-success-100 text-success-700',
  error: 'bg-error-50 border-error-100 text-error-700',
};

function ToastContainer({
  toasts,
  dismiss,
}: {
  toasts: Toast[];
  dismiss: (id: string) => void;
}) {
  if (toasts.length === 0) return null;

  return createPortal(
    <div className="fixed bottom-6 right-6 z-50 flex flex-col-reverse gap-2 pointer-events-none">
      {toasts.map(t => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-center gap-3 rounded-[var(--radius-button)] border px-4 py-3 shadow-elevated text-sm max-w-sm ${
            VARIANT_CLASSES[t.variant]
          } ${t.dismissing ? 'animate-toast-out' : 'animate-toast-in'}`}
        >
          <span className="flex-1">{t.message}</span>

          {t.action && (
            <button
              type="button"
              onClick={() => {
                t.action!.onClick();
                dismiss(t.id);
              }}
              className="ml-2 font-medium underline underline-offset-2 hover:no-underline whitespace-nowrap"
            >
              {t.action.label}
            </button>
          )}

          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => dismiss(t.id)}
            className="text-neutral-400 hover:text-neutral-600 transition-colors shrink-0"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ))}
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast must be used within ToastProvider');
  return context;
}
