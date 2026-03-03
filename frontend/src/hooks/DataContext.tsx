import {
  createContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react';
import { useAuth } from './useAuth';
import { useOnMutation } from './useMutationBus';
import { api } from '../services/api';
import type { DashboardResponse, Mission, Evidence } from '../types';

interface DataSlice<T> {
  data: T;
  loading: boolean;
  error: string | null;
}

export interface DataContextType {
  dashboard: DataSlice<DashboardResponse | null>;
  missions: DataSlice<Mission[]> & { dailyRemaining: number | null; dailyLimit: number | null };
  evidence: DataSlice<Evidence[]>;
  refreshDashboard: () => Promise<void>;
  refreshMissions: () => Promise<void>;
  refreshEvidence: () => Promise<void>;
}

const DataContext = createContext<DataContextType | undefined>(undefined);

export { DataContext };

export function DataProvider({ children }: { children: ReactNode }) {
  const { getToken } = useAuth();

  // Dashboard state
  const [dashboardData, setDashboardData] = useState<DashboardResponse | null>(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  // Missions state
  const [missionsData, setMissionsData] = useState<Mission[]>([]);
  const [missionsLoading, setMissionsLoading] = useState(false);
  const [missionsError, setMissionsError] = useState<string | null>(null);
  const [dailyRemaining, setDailyRemaining] = useState<number | null>(null);
  const [dailyLimit, setDailyLimit] = useState<number | null>(null);

  // Evidence state
  const [evidenceData, setEvidenceData] = useState<Evidence[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  const refreshDashboard = useCallback(async () => {
    setDashboardLoading(true);
    setDashboardError(null);
    try {
      const token = await getToken();
      const result = await api.dashboard.get(token);
      setDashboardData(result);
    } catch (err) {
      setDashboardError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setDashboardLoading(false);
    }
  }, [getToken]);

  const refreshMissions = useCallback(async () => {
    setMissionsLoading(true);
    setMissionsError(null);
    try {
      const token = await getToken();
      const result = await api.missions.list(token);
      setMissionsData(result.missions);
      setDailyRemaining(result.dailyRemaining);
      setDailyLimit(result.dailyLimit);
    } catch (err) {
      setMissionsError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setMissionsLoading(false);
    }
  }, [getToken]);

  const refreshEvidence = useCallback(async () => {
    setEvidenceLoading(true);
    setEvidenceError(null);
    try {
      const token = await getToken();
      const result = await api.evidence.list(token);
      setEvidenceData(result.evidence);
    } catch (err) {
      setEvidenceError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setEvidenceLoading(false);
    }
  }, [getToken]);

  // Fetch all data on mount
  useEffect(() => {
    void refreshDashboard();
    void refreshMissions();
    void refreshEvidence();
  }, [refreshDashboard, refreshMissions, refreshEvidence]);

  // Subscribe to mutation bus events for cross-page data freshness
  useOnMutation('mission:completed', () => {
    void refreshDashboard();
    void refreshMissions();
    void refreshEvidence();
  });

  useOnMutation('evidence:logged', () => {
    void refreshDashboard();
    void refreshEvidence();
  });

  return (
    <DataContext.Provider
      value={{
        dashboard: { data: dashboardData, loading: dashboardLoading, error: dashboardError },
        missions: { data: missionsData, loading: missionsLoading, error: missionsError, dailyRemaining, dailyLimit },
        evidence: { data: evidenceData, loading: evidenceLoading, error: evidenceError },
        refreshDashboard,
        refreshMissions,
        refreshEvidence,
      }}
    >
      {children}
    </DataContext.Provider>
  );
}
