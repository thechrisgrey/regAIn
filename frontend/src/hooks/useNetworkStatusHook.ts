import { useContext } from 'react';
import { NetworkStatusContext, type NetworkStatusContextType } from './useNetworkStatus';

export type { NetworkStatusContextType };

export function useNetworkStatus(): NetworkStatusContextType {
  return useContext(NetworkStatusContext);
}
