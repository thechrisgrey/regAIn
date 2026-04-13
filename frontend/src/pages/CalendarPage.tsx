import { useState, useMemo, useCallback, useEffect } from 'react';
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
  const weekDays = useMemo(() => {
    const d = new Date(currentDate);
    d.setDate(d.getDate() - d.getDay());
    return Array.from({ length: 7 }, (_, i) => {
      const day = new Date(d);
      day.setDate(d.getDate() + i);
      return day;
    });
  }, [currentDate]);

  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  return (
    <div className="grid grid-cols-7 gap-3">
      {weekDays.map((day, i) => {
        const dateStr = day.toISOString().slice(0, 10);
        const dayEntries = entriesByDate[dateStr] || [];
        const today = isToday(dateStr);

        return (
          <button
            key={dateStr}
            type="button"
            onClick={() => onDayClick(day)}
            className={`rounded-[var(--radius-card)] border p-3 text-left transition-all duration-200 hover:shadow-card-hover hover:-translate-y-0.5 ${
              today ? 'border-primary-300 shadow-card' : 'border-neutral-200'
            }`}
          >
            <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-neutral-400">
              {dayNames[i]}
            </span>
            <div className="mt-0.5">
              {today ? (
                <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-primary-500 text-[13px] font-semibold text-white">
                  {day.getDate()}
                </span>
              ) : (
                <span className="text-[13px] font-medium text-neutral-800">{day.getDate()}</span>
              )}
            </div>
            <div className="mt-2 space-y-1">
              {dayEntries.slice(0, 3).map((entry) => (
                <EntryPill key={entry.dateEntryId} entry={entry} />
              ))}
              {dayEntries.length > 3 && (
                <span className="block text-[9px] text-neutral-400">+{dayEntries.length - 3} more</span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function DayDetail({ currentDate, entries, onCreateEntry, onUpdateEntry, onDeleteEntry }: {
  currentDate: Date;
  entries: CalendarEntry[];
  onCreateEntry: (date: string, category: string, content: string) => Promise<void>;
  onUpdateEntry: (dateEntryId: string, content: string) => Promise<void>;
  onDeleteEntry: (dateEntryId: string) => Promise<void>;
}) {
  const [addingCategory, setAddingCategory] = useState<'task' | 'note' | null>(null);
  const [newContent, setNewContent] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [saving, setSaving] = useState(false);

  const dateStr = currentDate.toISOString().slice(0, 10);
  const tasks = entries.filter((e) => e.category === 'task');
  const notes = entries.filter((e) => e.category === 'note');

  const handleAdd = async () => {
    if (!addingCategory || !newContent.trim()) return;
    setSaving(true);
    try {
      await onCreateEntry(dateStr, addingCategory, newContent.trim());
      setNewContent('');
      setAddingCategory(null);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async (dateEntryId: string) => {
    if (!editContent.trim()) return;
    setSaving(true);
    try {
      await onUpdateEntry(dateEntryId, editContent.trim());
      setEditingId(null);
      setEditContent('');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (dateEntryId: string) => {
    await onDeleteEntry(dateEntryId);
  };

  const startEdit = (entry: CalendarEntry) => {
    setEditingId(entry.dateEntryId);
    setEditContent(entry.content);
  };

  const renderEntryCard = (entry: CalendarEntry) => {
    const isAgent = entry.author === 'agent';
    const isEditing = editingId === entry.dateEntryId;

    return (
      <div
        key={entry.dateEntryId}
        className={`animate-fade-in-up rounded-[var(--radius-card)] border p-3 ${
          isAgent
            ? 'border-accent-200 border-l-[3px] border-l-accent-400'
            : 'border-neutral-200 border-l-[3px] border-l-primary-500'
        }`}
      >
        {isEditing ? (
          <div className="space-y-2">
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              className="w-full rounded-[var(--radius-button)] border border-neutral-200 bg-surface-1 px-3 py-2 text-sm text-neutral-800 focus:border-primary-300 focus:outline-none focus:ring-1 focus:ring-primary-300"
              rows={2}
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void handleUpdate(entry.dateEntryId)}
                disabled={saving}
                className="rounded-[var(--radius-button)] bg-primary-500 px-3 py-1 text-[11px] font-medium text-white hover:bg-primary-600 transition-colors disabled:opacity-50"
              >
                Save
              </button>
              <button
                type="button"
                onClick={() => { setEditingId(null); setEditContent(''); }}
                className="rounded-[var(--radius-button)] border border-neutral-200 px-3 py-1 text-[11px] text-neutral-600 hover:bg-surface-2 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-[13px] leading-relaxed text-neutral-800">{entry.content}</p>
              <p className={`mt-1 text-[10px] ${isAgent ? 'text-accent-500' : 'text-neutral-400'}`}>
                {isAgent ? 'Agent' : 'You'} &middot; {new Date(entry.createdAt).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}
              </p>
            </div>
            <div className="flex shrink-0 gap-1">
              {!isAgent && (
                <button
                  type="button"
                  onClick={() => startEdit(entry)}
                  className="rounded p-1 text-neutral-400 hover:text-neutral-600 transition-colors"
                  aria-label="Edit"
                >
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125" />
                  </svg>
                </button>
              )}
              <button
                type="button"
                onClick={() => void handleDelete(entry.dateEntryId)}
                className="rounded p-1 text-neutral-400 hover:text-error-500 transition-colors"
                aria-label="Delete"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                </svg>
              </button>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderSection = (label: string, items: CalendarEntry[], category: 'task' | 'note') => (
    <div className="mb-6">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-[0.15em] text-neutral-400/60">
          {label}
        </span>
        <button
          type="button"
          onClick={() => { setAddingCategory(category); setNewContent(''); }}
          className="rounded-[var(--radius-button)] border border-neutral-200 px-3 py-1 text-[11px] text-neutral-600 hover:bg-surface-2 transition-colors"
        >
          + Add {category}
        </button>
      </div>
      <div className="space-y-2">
        {items.map(renderEntryCard)}
      </div>
      {addingCategory === category && (
        <div className="mt-2 space-y-2 animate-fade-in">
          <textarea
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder={`Enter ${category}...`}
            className="w-full rounded-[var(--radius-button)] border border-neutral-200 bg-surface-1 px-3 py-2 text-sm text-neutral-800 placeholder:text-neutral-400 focus:border-primary-300 focus:outline-none focus:ring-1 focus:ring-primary-300"
            rows={2}
            autoFocus
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void handleAdd()}
              disabled={saving || !newContent.trim()}
              className="rounded-[var(--radius-button)] bg-primary-500 px-3 py-1 text-[11px] font-medium text-white hover:bg-primary-600 transition-colors disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Add'}
            </button>
            <button
              type="button"
              onClick={() => setAddingCategory(null)}
              className="rounded-[var(--radius-button)] border border-neutral-200 px-3 py-1 text-[11px] text-neutral-600 hover:bg-surface-2 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="max-w-[640px]">
      {renderSection('Tasks', tasks, 'task')}
      {renderSection('Notes', notes, 'note')}
      {entries.length === 0 && !addingCategory && (
        <div className="rounded-[var(--radius-card)] border border-dashed border-neutral-200 px-4 py-6 text-center text-[12px] text-neutral-400">
          Click "+ Add task" or "+ Add note" to create an entry, or ask your agent to schedule something here.
        </div>
      )}
    </div>
  );
}

function YearHeatmap({ currentDate, heatmapData, fetchHeatmap, onDayClick }: {
  currentDate: Date;
  heatmapData: Record<string, number> | null;
  fetchHeatmap: (year: string) => Promise<void>;
  onDayClick: (date: Date) => void;
}) {
  const year = currentDate.getFullYear();

  useEffect(() => {
    void fetchHeatmap(String(year));
  }, [year, fetchHeatmap]);

  const grid = useMemo(() => {
    const jan1 = new Date(year, 0, 1);
    const startOffset = jan1.getDay();
    const startDate = new Date(jan1);
    startDate.setDate(startDate.getDate() - startOffset);

    const weeks: { date: Date; dateStr: string }[][] = [];
    const d = new Date(startDate);

    for (let w = 0; w < 53; w++) {
      const week: { date: Date; dateStr: string }[] = [];
      for (let day = 0; day < 7; day++) {
        week.push({ date: new Date(d), dateStr: d.toISOString().slice(0, 10) });
        d.setDate(d.getDate() + 1);
      }
      weeks.push(week);
      if (d.getFullYear() > year && d.getDay() === 0) break;
    }
    return weeks;
  }, [year]);

  const getCellColor = (count: number): string => {
    if (count === 0) return 'bg-surface-3';
    if (count === 1) return 'bg-primary-100';
    if (count === 2) return 'bg-primary-200';
    if (count === 3) return 'bg-primary-300';
    return 'bg-primary-500';
  };

  const data = heatmapData || {};
  const totalEntries = Object.values(data).reduce((sum, c) => sum + c, 0);
  const now = new Date();
  const currentMonth = now.getFullYear() === year ? now.getMonth() : -1;
  const activeDaysThisMonth = Object.keys(data).filter((d) => {
    if (currentMonth < 0) return false;
    const date = new Date(d);
    return date.getMonth() === currentMonth;
  }).length;

  let streak = 0;
  const today = new Date();
  const check = new Date(today);
  while (data[check.toISOString().slice(0, 10)] && data[check.toISOString().slice(0, 10)] > 0) {
    streak++;
    check.setDate(check.getDate() - 1);
  }

  const monthLabels = useMemo(() => {
    const labels: { label: string; col: number; isCurrent: boolean }[] = [];
    const jan1 = new Date(year, 0, 1);
    const startOffset = jan1.getDay();
    const startDate = new Date(jan1);
    startDate.setDate(startDate.getDate() - startOffset);
    for (let m = 0; m < 12; m++) {
      const firstOfMonth = new Date(year, m, 1);
      const daysSinceStart = Math.floor((firstOfMonth.getTime() - startDate.getTime()) / 86400000);
      const col = Math.floor(daysSinceStart / 7);
      labels.push({
        label: firstOfMonth.toLocaleDateString('en-US', { month: 'short' }),
        col,
        isCurrent: currentMonth === m,
      });
    }
    return labels;
  }, [year, currentMonth]);

  const dayLabels = ['', 'Mon', '', 'Wed', '', 'Fri', ''];

  if (!heatmapData) {
    return (
      <div className="flex justify-center py-12">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary-200 border-t-primary-500" />
      </div>
    );
  }

  return (
    <div>
      {/* Month labels */}
      <div className="flex gap-0 overflow-x-auto pl-8">
        {monthLabels.map(({ label, col, isCurrent }) => (
          <span
            key={label}
            className={`text-[10px] ${isCurrent ? 'font-bold text-neutral-800' : 'text-neutral-400'}`}
            style={{ position: 'relative', left: `${col * 14}px`, width: 0, whiteSpace: 'nowrap' }}
          >
            {label}
          </span>
        ))}
      </div>

      {/* Grid */}
      <div className="mt-2 flex gap-0.5 overflow-x-auto">
        {/* Day labels */}
        <div className="flex flex-col gap-0.5 pr-1">
          {dayLabels.map((label, i) => (
            <div key={i} className="flex h-[12px] w-6 items-center justify-end text-[9px] text-neutral-400">
              {label}
            </div>
          ))}
        </div>

        {/* Week columns */}
        {grid.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-0.5">
            {week.map(({ date, dateStr }) => {
              const count = data[dateStr] || 0;
              const inYear = date.getFullYear() === year;
              return (
                <button
                  key={dateStr}
                  type="button"
                  onClick={() => inYear && onDayClick(date)}
                  className={`h-[12px] w-[12px] rounded-[2px] transition-colors ${
                    inYear ? getCellColor(count) : 'bg-transparent'
                  } ${inYear ? 'hover:ring-1 hover:ring-primary-400' : ''}`}
                  title={inYear ? `${dateStr}: ${count} entries` : ''}
                  disabled={!inYear}
                />
              );
            })}
          </div>
        ))}
      </div>

      {/* Stats */}
      <div className="mt-4 flex gap-6 text-[12px] text-neutral-500">
        <span>
          <span className="font-semibold text-neutral-800">{totalEntries}</span> entries this year
        </span>
        {currentMonth >= 0 && (
          <span>
            <span className="font-semibold text-neutral-800">{activeDaysThisMonth}</span> active days this month
          </span>
        )}
        <span>
          <span className="font-semibold text-neutral-800">{streak}</span> day streak
        </span>
      </div>

      {/* Legend */}
      <div className="mt-3 flex items-center gap-1 text-[10px] text-neutral-400">
        Less
        <span className="inline-block h-[10px] w-[10px] rounded-[2px] bg-surface-3" />
        <span className="inline-block h-[10px] w-[10px] rounded-[2px] bg-primary-100" />
        <span className="inline-block h-[10px] w-[10px] rounded-[2px] bg-primary-200" />
        <span className="inline-block h-[10px] w-[10px] rounded-[2px] bg-primary-300" />
        <span className="inline-block h-[10px] w-[10px] rounded-[2px] bg-primary-500" />
        More
      </div>
    </div>
  );
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
