import {
  createContext,
  useState,
  useEffect,
  useRef,
  type ReactNode,
} from 'react';
import { useCoaching } from './useCoaching';

export interface NetworkStatusContextType {
  isOnline: boolean;
  isReconnecting: boolean;
}

const NetworkStatusContext = createContext<NetworkStatusContextType>({
  isOnline: true,
  isReconnecting: false,
});

export { NetworkStatusContext };

export function NetworkStatusProvider({ children }: { children: ReactNode }) {
  const [isOnline, setIsOnline] = useState(
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  );
  const { connectionStatus } = useCoaching();
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    const handleOnline = () => {
      // Debounce online recovery by 1 second to avoid flicker.
      debounceRef.current = setTimeout(() => {
        setIsOnline(true);
      }, 1000);
    };

    const handleOffline = () => {
      clearTimeout(debounceRef.current);
      setIsOnline(false);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      clearTimeout(debounceRef.current);
    };
  }, []);

  const isReconnecting = connectionStatus === 'reconnecting';

  return (
    <NetworkStatusContext.Provider value={{ isOnline, isReconnecting }}>
      {children}
    </NetworkStatusContext.Provider>
  );
}
