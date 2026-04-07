import { createContext, useRef, useCallback, type ReactNode } from 'react';

export type MutationEventType =
  | 'mission:completed'
  | 'mission:generated'
  | 'evidence:logged'
  | 'campaign:created'
  | 'resume:generated'
  | 'voice:session_completed'
  | 'scorecard:viewed'
  | 'profile:updated'
  | 'page:navigated';

export interface MutationEvent {
  type: MutationEventType;
  payload?: Record<string, unknown>;
}

export interface MutationBusContextType {
  emit: (event: MutationEvent) => void;
  subscribe: (type: MutationEventType, callback: () => void) => () => void;
}

const MutationBusContext = createContext<MutationBusContextType | undefined>(undefined);

export { MutationBusContext };

export function MutationBusProvider({ children }: { children: ReactNode }) {
  const listenersRef = useRef<Map<MutationEventType, Set<() => void>>>(new Map());

  const subscribe = useCallback((type: MutationEventType, callback: () => void) => {
    if (!listenersRef.current.has(type)) {
      listenersRef.current.set(type, new Set());
    }
    listenersRef.current.get(type)!.add(callback);
    return () => {
      listenersRef.current.get(type)?.delete(callback);
    };
  }, []);

  const emit = useCallback((event: MutationEvent) => {
    listenersRef.current.get(event.type)?.forEach((cb) => cb());
  }, []);

  return (
    <MutationBusContext.Provider value={{ emit, subscribe }}>
      {children}
    </MutationBusContext.Provider>
  );
}
