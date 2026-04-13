import { useState, useCallback, useEffect } from 'react';
import { useAuth } from './useAuth';
import { useMutationBus } from './useMutationBus';
import { api } from '../services/api';
import type { CalendarEntry } from '../types';

export function useCalendar(startDate: string, endDate: string) {
  const { getToken } = useAuth();
  const { emit } = useMutationBus();

  const [entries, setEntries] = useState<CalendarEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [heatmapData, setHeatmapData] = useState<Record<string, number> | null>(null);

  const fetchEntries = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const result = await api.calendar.list(startDate, endDate, token);
      setEntries(result.entries);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load calendar');
    } finally {
      setLoading(false);
    }
  }, [getToken, startDate, endDate]);

  useEffect(() => {
    void fetchEntries();
  }, [fetchEntries]);

  const createEntry = useCallback(
    async (date: string, category: string, content: string) => {
      const token = await getToken();
      // Optimistic update
      const tempId = `${date}#temp-${Date.now()}`;
      const optimistic: CalendarEntry = {
        dateEntryId: tempId,
        date,
        category: category as 'task' | 'note',
        author: 'user',
        content,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      setEntries((prev) => [...prev, optimistic]);

      try {
        const result = await api.calendar.create({ date, category, content }, token);
        // Replace temp entry with real one
        setEntries((prev) =>
          prev.map((e) =>
            e.dateEntryId === tempId ? { ...e, dateEntryId: result.dateEntryId } : e,
          ),
        );
        emit({ type: 'calendar:updated' });
      } catch (err) {
        // Rollback
        setEntries((prev) => prev.filter((e) => e.dateEntryId !== tempId));
        throw err;
      }
    },
    [getToken, emit],
  );

  const updateEntry = useCallback(
    async (dateEntryId: string, content: string) => {
      const token = await getToken();
      // Optimistic
      const original = entries.find((e) => e.dateEntryId === dateEntryId);
      setEntries((prev) =>
        prev.map((e) =>
          e.dateEntryId === dateEntryId
            ? { ...e, content, updatedAt: new Date().toISOString() }
            : e,
        ),
      );
      try {
        await api.calendar.update(dateEntryId, content, token);
        emit({ type: 'calendar:updated' });
      } catch (err) {
        // Rollback
        if (original) {
          setEntries((prev) =>
            prev.map((e) => (e.dateEntryId === dateEntryId ? original : e)),
          );
        }
        throw err;
      }
    },
    [getToken, entries, emit],
  );

  const deleteEntry = useCallback(
    async (dateEntryId: string) => {
      const token = await getToken();
      // Optimistic
      const original = entries.find((e) => e.dateEntryId === dateEntryId);
      setEntries((prev) => prev.filter((e) => e.dateEntryId !== dateEntryId));
      try {
        await api.calendar.delete(dateEntryId, token);
        emit({ type: 'calendar:updated' });
      } catch (err) {
        // Rollback
        if (original) {
          setEntries((prev) => [...prev, original]);
        }
        throw err;
      }
    },
    [getToken, entries, emit],
  );

  const fetchHeatmap = useCallback(
    async (year: string) => {
      const token = await getToken();
      const result = await api.calendar.heatmap(year, token);
      setHeatmapData(result.heatmap);
    },
    [getToken],
  );

  const refresh = useCallback(async () => {
    await fetchEntries();
  }, [fetchEntries]);

  return {
    entries,
    loading,
    error,
    createEntry,
    updateEntry,
    deleteEntry,
    heatmapData,
    fetchHeatmap,
    refresh,
  };
}
