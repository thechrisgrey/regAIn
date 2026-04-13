import { useState, useMemo, useCallback } from 'react';
import { useCalendar } from '../hooks/useCalendar';
import type { CalendarEntry } from '../types';

type ViewMode = 'year' | 'month' | 'week' | 'day';

const VIEW_OPTIONS: ViewMode[] = ['year', 'month', 'week', 'day'];

function formatMonthYear(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
}

function formatDayHeader(date: Date): string {
  return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
}

function getMonthRange(date: Date): { start: string; end: string } {
  const y = date.getFullYear();
  const m = date.getMonth();
  const start = new Date(y, m, 1);
  const end = new Date(y, m + 1, 0);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

function getWeekRange(date: Date): { start: string; end: string } {
  const d = new Date(date);
  d.setDate(d.getDate() - d.getDay());
  const start = d.toISOString().slice(0, 10);
  d.setDate(d.getDate() + 6);
  const end = d.toISOString().slice(0, 10);
  return { start, end };
}

function getDayRange(date: Date): { start: string; end: string } {
  const s = date.toISOString().slice(0, 10);
  return { start: s, end: s };
}

function getDateRange(view: ViewMode, date: Date): { start: string; end: string } {
  switch (view) {
    case 'year':
      return { start: `${date.getFullYear()}-01-01`, end: `${date.getFullYear()}-12-31` };
    case 'month':
      return getMonthRange(date);
    case 'week':
      return getWeekRange(date);
    case 'day':
      return getDayRange(date);
  }
}

function isToday(dateStr: string): boolean {
  return dateStr === new Date().toISOString().slice(0, 10);
}

function getEntriesByDate(entries: CalendarEntry[]): Record<string, CalendarEntry[]> {
  const map: Record<string, CalendarEntry[]> = {};
  for (const entry of entries) {
    const d = entry.date;
    if (!map[d]) map[d] = [];
    map[d].push(entry);
  }
  return map;
}

// --- Entry Pill ---

function EntryPill({ entry }: { entry: CalendarEntry }) {
  const isAgent = entry.author === 'agent';
  return (
    <div
      className={`mt-1 truncate rounded-[4px] px-1.5 py-0.5 text-[10px] leading-tight ${
        isAgent
          ? 'border-l-2 border-accent-400 bg-accent-50 text-accent-600'
          : 'border-l-2 border-primary-500 bg-primary-100 text-primary-700'
      }`}
    >
      {entry.content}
    </div>
  );
}

// --- Month Grid ---

function MonthGrid({
  currentDate,
  entriesByDate,
  onDayClick,
}: {
  currentDate: Date;
  entriesByDate: Record<string, CalendarEntry[]>;
  onDayClick: (date: Date) => void;
}) {
  const weeks = useMemo(() => {
    const y = currentDate.getFullYear();
    const m = currentDate.getMonth();
    const firstDay = new Date(y, m, 1);
    const lastDay = new Date(y, m + 1, 0);
    const startOffset = firstDay.getDay();

    const days: { date: Date; inMonth: boolean }[] = [];

    // Previous month fill
    for (let i = startOffset - 1; i >= 0; i--) {
      const d = new Date(y, m, -i);
      days.push({ date: d, inMonth: false });
    }
    // Current month
    for (let d = 1; d <= lastDay.getDate(); d++) {
      days.push({ date: new Date(y, m, d), inMonth: true });
    }
    // Next month fill to complete the grid
    while (days.length % 7 !== 0) {
      const last = days[days.length - 1].date;
      const next = new Date(last);
      next.setDate(next.getDate() + 1);
      days.push({ date: next, inMonth: false });
    }

    // Split into weeks
    const result: { date: Date; inMonth: boolean }[][] = [];
    for (let i = 0; i < days.length; i += 7) {
      result.push(days.slice(i, i + 7));
    }
    return result;
  }, [currentDate]);

  const dayHeaders = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  return (
    <div>
      {/* Day headers */}
      <div className="grid grid-cols-7 gap-px mb-px">
        {dayHeaders.map((d) => (
          <div key={d} className="py-2 text-center text-[11px] font-semibold uppercase tracking-[0.1em] text-neutral-400">
            {d}
          </div>
        ))}
      </div>

      {/* Week rows */}
      <div className="grid grid-cols-7 gap-px bg-neutral-200/60">
        {weeks.flat().map(({ date, inMonth }) => {
          const dateStr = date.toISOString().slice(0, 10);
          const dayEntries = entriesByDate[dateStr] || [];
          const today = isToday(dateStr);
          const dayNum = date.getDate();

          return (
            <button
              key={dateStr}
              type="button"
              onClick={() => onDayClick(date)}
              className={`min-h-[90px] p-1.5 text-left transition-colors hover:bg-primary-50 ${
                inMonth ? 'bg-surface-1' : 'bg-surface-3'
              }`}
            >
              {today ? (
                <span className="inline-flex h-[22px] w-[22px] items-center justify-center rounded-full bg-primary-500 text-[12px] font-semibold text-white">
                  {dayNum}
                </span>
              ) : (
                <span className={`text-[12px] font-medium ${inMonth ? 'text-neutral-800' : 'text-neutral-300'}`}>
                  {dayNum}
                </span>
              )}
              {dayEntries.slice(0, 2).map((entry) => (
                <EntryPill key={entry.dateEntryId} entry={entry} />
              ))}
              {dayEntries.length > 2 && (
                <span className="mt-0.5 block text-[9px] text-neutral-400">
                  +{dayEntries.length - 2} more
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Legend */}
      <div className="mt-3 flex gap-4 text-[11px] text-neutral-500">
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-3 rounded-sm border-l-2 border-primary-500 bg-primary-100" />
          Your entries
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-3 rounded-sm border-l-2 border-accent-400 bg-accent-50" />
          Agent entries
        </div>
      </div>
    </div>
  );
}

// --- Placeholder views (Task 11 and 12 fill these in) ---

function WeekStrip({ currentDate, entriesByDate, onDayClick }: {
  currentDate: Date;
  entriesByDate: Record<string, CalendarEntry[]>;
  onDayClick: (date: Date) => void;
}) {
  return <div className="py-8 text-center text-sm text-neutral-400">Week view -- coming next</div>;
}

function DayDetail({ currentDate, entries, onCreateEntry, onUpdateEntry, onDeleteEntry }: {
  currentDate: Date;
  entries: CalendarEntry[];
  onCreateEntry: (date: string, category: string, content: string) => Promise<void>;
  onUpdateEntry: (dateEntryId: string, content: string) => Promise<void>;
  onDeleteEntry: (dateEntryId: string) => Promise<void>;
}) {
  return <div className="py-8 text-center text-sm text-neutral-400">Day view -- coming next</div>;
}

function YearHeatmap({ currentDate, heatmapData, fetchHeatmap, onDayClick }: {
  currentDate: Date;
  heatmapData: Record<string, number> | null;
  fetchHeatmap: (year: string) => Promise<void>;
  onDayClick: (date: Date) => void;
}) {
  return <div className="py-8 text-center text-sm text-neutral-400">Year view -- coming next</div>;
}

// --- Page Root ---

export default function CalendarPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('month');
  const [currentDate, setCurrentDate] = useState(new Date());

  const { start, end } = getDateRange(viewMode, currentDate);

  const {
    entries,
    loading,
    error,
    createEntry,
    updateEntry,
    deleteEntry,
    heatmapData,
    fetchHeatmap,
  } = useCalendar(start, end);

  const entriesByDate = useMemo(() => getEntriesByDate(entries), [entries]);

  const navigatePrev = useCallback(() => {
    setCurrentDate((d) => {
      const next = new Date(d);
      switch (viewMode) {
        case 'year': next.setFullYear(next.getFullYear() - 1); break;
        case 'month': next.setMonth(next.getMonth() - 1); break;
        case 'week': next.setDate(next.getDate() - 7); break;
        case 'day': next.setDate(next.getDate() - 1); break;
      }
      return next;
    });
  }, [viewMode]);

  const navigateNext = useCallback(() => {
    setCurrentDate((d) => {
      const next = new Date(d);
      switch (viewMode) {
        case 'year': next.setFullYear(next.getFullYear() + 1); break;
        case 'month': next.setMonth(next.getMonth() + 1); break;
        case 'week': next.setDate(next.getDate() + 7); break;
        case 'day': next.setDate(next.getDate() + 1); break;
      }
      return next;
    });
  }, [viewMode]);

  const goToday = useCallback(() => setCurrentDate(new Date()), []);

  const handleDayClick = useCallback((date: Date) => {
    setCurrentDate(date);
    setViewMode('day');
  }, []);

  // Header subtitle
  const headerText = viewMode === 'day'
    ? formatDayHeader(currentDate)
    : viewMode === 'year'
      ? String(currentDate.getFullYear())
      : formatMonthYear(currentDate);

  const dayEntries = entries.filter((e) => e.date === currentDate.toISOString().slice(0, 10));
  const taskCount = dayEntries.filter((e) => e.category === 'task').length;
  const noteCount = dayEntries.filter((e) => e.category === 'note').length;

  return (
    <div className="animate-fade-in">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">Calendar</h1>
          <p className="text-sm text-neutral-500">Plan, track, and reflect on your career journey</p>
        </div>

        {/* View switcher */}
        <div className="flex overflow-hidden rounded-[var(--radius-button)] border border-neutral-200">
          {VIEW_OPTIONS.map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setViewMode(v)}
              className={`px-3 py-1.5 text-[12px] capitalize transition-colors ${
                v === viewMode
                  ? 'bg-primary-500 font-medium text-white'
                  : 'bg-surface-1 text-neutral-500 hover:bg-surface-2'
              }`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {/* Navigation */}
      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={navigatePrev}
          className="rounded-[var(--radius-button)] border border-neutral-200 px-2 py-1 text-sm text-neutral-600 hover:bg-surface-2 transition-colors"
          aria-label="Previous"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
        </button>
        <span className="min-w-[160px] text-center text-base font-semibold text-neutral-800">
          {headerText}
        </span>
        <button
          type="button"
          onClick={navigateNext}
          className="rounded-[var(--radius-button)] border border-neutral-200 px-2 py-1 text-sm text-neutral-600 hover:bg-surface-2 transition-colors"
          aria-label="Next"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
          </svg>
        </button>
        <button
          type="button"
          onClick={goToday}
          className="rounded-[var(--radius-button)] border border-neutral-200 px-2.5 py-1 text-[12px] text-neutral-600 hover:bg-surface-2 transition-colors"
        >
          Today
        </button>
        {viewMode === 'day' && (
          <span className="text-[12px] text-neutral-400">
            {taskCount} task{taskCount !== 1 ? 's' : ''}, {noteCount} note{noteCount !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div className="mt-4 rounded-[var(--radius-card)] border border-error-200 bg-error-50 px-4 py-3 text-sm text-error-700">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="mt-8 flex justify-center">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary-200 border-t-primary-500" />
        </div>
      )}

      {/* Views */}
      {!loading && (
        <div className="mt-4">
          {viewMode === 'month' && (
            <MonthGrid
              currentDate={currentDate}
              entriesByDate={entriesByDate}
              onDayClick={handleDayClick}
            />
          )}
          {viewMode === 'week' && (
            <WeekStrip
              currentDate={currentDate}
              entriesByDate={entriesByDate}
              onDayClick={handleDayClick}
            />
          )}
          {viewMode === 'day' && (
            <DayDetail
              currentDate={currentDate}
              entries={dayEntries}
              onCreateEntry={createEntry}
              onUpdateEntry={updateEntry}
              onDeleteEntry={deleteEntry}
            />
          )}
          {viewMode === 'year' && (
            <YearHeatmap
              currentDate={currentDate}
              heatmapData={heatmapData}
              fetchHeatmap={fetchHeatmap}
              onDayClick={handleDayClick}
            />
          )}
        </div>
      )}
    </div>
  );
}
