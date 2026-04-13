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
  | 'page:navigated'
  | 'calendar:updated';

export interface MutationEvent {
  type: MutationEventType;
  payload?: Record<string, unknown>;
}

export type PageSnapshot = Record<string, unknown>;

export interface MutationBusContextType {
  emit: (event: MutationEvent) => void;
  subscribe: (type: MutationEventType, callback: () => void) => () => void;
  setPageSnapshot: (snapshot: PageSnapshot) => void;
  getPageSnapshot: () => PageSnapshot | null;
}

const MutationBusContext = createContext<MutationBusContextType | undefined>(undefined);

export { MutationBusContext };

export function MutationBusProvider({ children }: { children: ReactNode }) {
  const listenersRef = useRef<Map<MutationEventType, Set<() => void>>>(new Map());
  const pageSnapshotRef = useRef<PageSnapshot | null>(null);

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

  const setPageSnapshot = useCallback((snapshot: PageSnapshot) => {
    pageSnapshotRef.current = snapshot;
  }, []);

  const getPageSnapshot = useCallback((): PageSnapshot | null => {
    return pageSnapshotRef.current;
  }, []);

  return (
    <MutationBusContext.Provider value={{ emit, subscribe, setPageSnapshot, getPageSnapshot }}>
      {children}
    </MutationBusContext.Provider>
  );
}
