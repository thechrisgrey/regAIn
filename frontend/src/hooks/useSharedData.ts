import { useContext } from 'react';
import { DataContext, type DataContextType } from './DataContext';

export type { DataContextType };

export function useSharedData(): DataContextType {
  const context = useContext(DataContext);
  if (!context) {
    throw new Error('useSharedData must be used within DataProvider');
  }
  return context;
}
