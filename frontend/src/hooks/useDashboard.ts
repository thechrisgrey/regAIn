import { useSharedData } from './useSharedData';

export function useDashboard() {
  const { dashboard, refreshDashboard } = useSharedData();

  return {
    data: dashboard.data,
    loading: dashboard.loading,
    error: dashboard.error,
    fetchDashboard: refreshDashboard,
  };
}
