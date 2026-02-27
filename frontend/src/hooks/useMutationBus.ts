import { useContext, useEffect } from 'react';
import { MutationBusContext, type MutationBusContextType, type MutationEventType } from './MutationBusContext';

export type { MutationEventType };

export function useMutationBus(): MutationBusContextType {
  const context = useContext(MutationBusContext);
  if (!context) {
    throw new Error('useMutationBus must be used within MutationBusProvider');
  }
  return context;
}

export function useOnMutation(type: MutationEventType, callback: () => void) {
  const { subscribe } = useMutationBus();
  useEffect(() => subscribe(type, callback), [subscribe, type, callback]);
}
