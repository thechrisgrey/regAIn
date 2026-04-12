# Calendar Feature — Design Spec

## Overview

A monthly calendar page at `/calendar` where users can create and manage daily notes and tasks. The coaching agent also has read/write access, enabling proactive scheduling (e.g., mission reminders, coaching observations) and reactive scheduling (user asks the agent to add something). Users can delete agent entries; the agent cannot delete user entries.

## Views

Four view modes, switchable via a segmented control in the page header. Default is **Month**.

### Month View (Default)
- 7-column CSS grid, 5–6 week rows
- Day cells show date number + truncated entry pills (max 2–3 visible, overflow hidden)
- Entry pills color-coded by author: cocoa/primary left border for user, mauve/accent left border for agent
- Previous/next month days rendered with muted background and text
- Today indicator: filled primary-500 circle on the date number
- Clicking a day navigates to Day view for that date
- Bottom legend: "Your entries" (cocoa) and "Agent entries" (mauve)

### Week View
- 7 card columns, one per day, with more vertical space than month cells
- Each card shows: day name (uppercase label), date number, entry pills
- Overflow entries show "+N more" link
- Today's card has a primary border accent and filled date circle
- Clicking a card navigates to Day view

### Day View
- Full detail view for a single date
- Two sections with SectionLabel-style headers: **Tasks** and **Notes**
- Each section has a "+ Add task" / "+ Add note" button that opens an inline text input
- Entry cards show: content text, author label ("You" or "Agent"), timestamp
- User entries: edit + delete icons
- Agent entries: delete icon only (user can dismiss, cannot edit)
- Agent entries are write-once (not editable by anyone after creation)
- Prev/next arrows navigate between days
- Subtitle shows dynamic entry count ("2 tasks, 1 note")

### Year Heat-Map
- GitHub contributions style: 52 columns (weeks) x 7 rows (days)
- Cell color intensity uses the primary palette based on entry count per day:
  - 0 entries: `surface-3` (#F4EFED)
  - 1 entry: `primary-100` (#F0E9E7)
  - 2 entries: `primary-200` (#DFCFC9)
  - 3 entries: `primary-300` (#CBB3AB)
  - 4+ entries: `primary-500` (#916D65)
- Day labels on the left (Mon, Wed, Fri)
- Month labels across the top, current month bolded
- Prev/next arrows navigate years
- Stats row below the grid: total entries this year, active days this month, current streak
- Clicking any cell navigates to Day view for that date

## Entry Data Model

### Categories
- **task** — actionable items (from user or agent)
- **note** — observations, reflections, journal entries (from user or agent)

### Author Color Coding
- **User entries**: `primary-100` background, `primary-500` left border (cocoa tones)
- **Agent entries**: `accent-100` background, `accent-400` left border (mauve tones)
- Author label text: "You" for user, "Agent" for agent

### Permissions
| Action | User (REST API) | Agent (coaching tool) |
|--------|----------------|----------------------|
| Create | Yes (any category) | Yes (any category, `author="agent"`) |
| Read | Yes | Yes (via `read_calendar` tool) |
| Update | Own entries only | No |
| Delete | Any entry | No |

## DynamoDB Table: `RegainCalendarEntries`

| Field | Type | Description |
|-------|------|-------------|
| `userId` | String (PK) | Cognito user ID |
| `dateEntryId` | String (SK) | Composite: `YYYY-MM-DD#uuid` — date prefix enables range queries |
| `date` | String | ISO date `YYYY-MM-DD` (denormalized for easy reads) |
| `category` | String | `task` or `note` |
| `author` | String | `user` or `agent` |
| `content` | String | Plain text body |
| `createdAt` | String | ISO timestamp |
| `updatedAt` | String | ISO timestamp |

### Query Patterns
- **Month**: `begins_with(dateEntryId, "2026-04")` — single query, no GSI
- **Day**: `begins_with(dateEntryId, "2026-04-12")` — single query
- **Week**: SK `between("2026-04-06", "2026-04-13")` — single query
- **Year heat-map**: `begins_with(dateEntryId, "2026")` with projection on `dateEntryId` and `category` only — minimizes read cost
- No GSI required. All access is by `userId` partition + date-prefix sort key.

### PITR
Enabled, consistent with all other data tables.

## API Endpoints

New Lambda handler at `backend/handlers/calendar/handler.py`, following the thin handler + service pattern.

| Method | Resource | Body / Params | Action |
|--------|----------|---------------|--------|
| `GET` | `/calendar?start=YYYY-MM-DD&end=YYYY-MM-DD` | Query params | List entries in date range |
| `GET` | `/calendar/heatmap?year=YYYY` | Query param | Year heat-map counts (`{date: count}`) |
| `POST` | `/calendar` | `{date, category, content}` | Create entry (`author` always `"user"` via REST) |
| `PUT` | `/calendar/{dateEntryId}` | `{content}` | Update entry (user-authored only; returns 403 for agent entries) |
| `DELETE` | `/calendar/{dateEntryId}` | — | Delete entry (any author) |

### Service Layer: `backend/handlers/calendar/service.py`
- `CalendarService.list_entries(user_id, start, end)` — range query
- `CalendarService.create_entry(user_id, date, category, content, author)` — creates with UUID sort key
- `CalendarService.update_entry(user_id, date_entry_id, content)` — fetches entry first, returns 403 if `author != "user"` (agent entries are immutable)
- `CalendarService.delete_entry(user_id, date_entry_id)` — no author restriction from REST
- `CalendarService.get_heatmap(user_id, year)` — lightweight projected query returning `{date: count}` map

## Coaching Agent Integration

Two new tools added to `backend/agents/coaching/tools.py`:

### `read_calendar`
- **Args**: `user_id`, `start_date`, `end_date`
- **Returns**: List of entries in the date range
- **Use case**: Agent checks what's scheduled before suggesting new tasks, references calendar context in conversations

### `write_calendar_entry`
- **Args**: `user_id`, `date`, `category` (`task` or `note`), `content`
- **Returns**: `{success: true, entryId: "..."}`
- **Behavior**: Always sets `author="agent"`. No delete or update capability.
- **Use cases**:
  - After generating a mission: schedules a task on a suggested date
  - After a voice practice session: writes a coaching note with observations
  - When user asks: "Remind me to do X on Thursday"
  - Proactive progress tracking: "You've completed 3 missions this week"

## Frontend Architecture

### Route
- `/calendar` — lazy-loaded via `React.lazy()` in `App.tsx`
- View mode and selected date managed via component state (not URL params)

### Navigation
- **Desktop sidebar** (`Sidebar.tsx`): `{ to: '/calendar', label: 'Calendar', icon: 'calendar' }` — between Voice and Score
- **Mobile nav** (`Layout.tsx` `MOBILE_NAV_GROUPS`): Added to the "Act" group
- **NavIcon**: New `calendar` SVG icon in `NavIcon.tsx`

### Components

| Component | File | Responsibility |
|-----------|------|---------------|
| `CalendarPage` | `pages/CalendarPage.tsx` | Page root — view mode state, selected date, data orchestration |
| `CalendarHeader` | inline in CalendarPage | View switcher, prev/next nav, "Today" button |
| `MonthGrid` | inline in CalendarPage | 7-column CSS grid with day cells and entry pills |
| `WeekStrip` | inline in CalendarPage | 7 card columns with entry pills |
| `DayDetail` | inline in CalendarPage | Full entry list, grouped by Tasks/Notes, inline CRUD |
| `YearHeatmap` | inline in CalendarPage | 52x7 heat-map grid + stats row |
| `EntryPill` | inline in CalendarPage | Reusable pill with author color coding |

Components start inline in `CalendarPage.tsx`. Extract to separate files only if the page grows beyond ~400 lines.

### Hook: `useCalendar`

Located at `hooks/useCalendar.ts`:

```
useCalendar(startDate, endDate) → {
  entries: CalendarEntry[],
  loading: boolean,
  error: string | null,
  createEntry(date, category, content): Promise<void>,
  updateEntry(dateEntryId, content): Promise<void>,
  deleteEntry(dateEntryId): Promise<void>,
  heatmapData: Record<string, number> | null,
  fetchHeatmap(year): Promise<void>,
  refresh(): Promise<void>
}
```

- Fetches entries for the visible date range
- View mode changes update the range → hook refetches
- Optimistic updates for create/update/delete, rolls back on API failure
- MutationBus integration: emits `calendar:updated` after mutations

### API Service

Added to `frontend/src/services/api.ts`:

```typescript
calendar: {
  list: (token, start, end) => cachedGet(`/calendar?start=${start}&end=${end}`, token),
  create: (data, token) => apiRequest('/calendar', { method: 'POST', body: data }, token),
  update: (dateEntryId, data, token) => apiRequest(`/calendar/${dateEntryId}`, { method: 'PUT', body: data }, token),
  delete: (dateEntryId, token) => apiRequest(`/calendar/${dateEntryId}`, { method: 'DELETE' }, token),
  heatmap: (year, token) => cachedGet(`/calendar/heatmap?year=${year}`, token),
}
```

### MutationBus Integration
- `CalendarPage` registers a page snapshot via `setPageSnapshot` with current view, entry counts, and recent entries
- CRUD operations emit `calendar:updated` so other pages (dashboard) can react
- `useCalendar` subscribes to `calendar:updated` for cross-component freshness

### Types

Added to `frontend/src/types/index.ts`:

```typescript
interface CalendarEntry {
  dateEntryId: string;
  date: string;
  category: 'task' | 'note';
  author: 'user' | 'agent';
  content: string;
  createdAt: string;
  updatedAt: string;
}
```

## CDK Infrastructure

### DataStack Changes
- New `_create_calendar_entries_table()` method
- Table added to `self.tables["CalendarEntries"]` and stack outputs
- PITR enabled, on-demand billing
- Update `EXPECTED_TABLE_COUNT` in test files

### ApiStack Changes
- New Calendar Lambda handler
- Routes: `GET /calendar`, `POST /calendar`, `PUT /calendar/{dateEntryId}`, `DELETE /calendar/{dateEntryId}`, `GET /calendar/heatmap`
- Lambda gets read/write permissions on CalendarEntries table
- Update `EXPECTED_LAMBDA_COUNT` and `EXPECTED_METHOD_COUNT` in test files

### AgentStack Changes
- Calendar table read/write permissions added to coaching Lambda
- `CALENDAR_TABLE_NAME` env var added to coaching Lambda

## Profile Cascade Deletion

The profile Lambda's cascade deletion must include CalendarEntries. Add `delete_all_by_partition_key(calendar_table, userId)` alongside the existing 5-table cascade. Update `CALENDAR_TABLE_NAME` env var on the profile Lambda via ApiStack.

## Design System Compliance

- **Colors**: Only palette tokens (`primary-*`, `accent-*`, `surface-*`, `neutral-*`). No raw Tailwind colors.
- **Radii**: `--radius-card` for day cells/cards, `--radius-button` for buttons and pills
- **Shadows**: `--shadow-card` on week view cards, `--shadow-card-hover` on hover
- **Typography**: Page header uses `text-2xl font-semibold tracking-tight`. Section labels use `SectionLabel` pattern.
- **Animations**: `animate-fade-in` on page root, `animate-fade-in-up` on entry cards with staggered delays
- **No emojis** in any UI text
