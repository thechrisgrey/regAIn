# Three-Panel Layout Redesign

**Date:** 2026-04-10
**Status:** Draft
**Scope:** Desktop layout only. Mobile unchanged. Voice practice pages unchanged.

## Problem

The coaching chat is the core differentiator of REGAIN -- persistent, personalized AI coaching with memory across sessions. But the current UI buries it behind a floating button in the bottom-right corner that opens a 400px modal. Users may not discover it, and even when they do, the modal competes with page content rather than complementing it.

## Solution

Replace the current sidebar + floating modal layout with a three-panel grid:

```
| Nav ~10vw | Page Content (1fr) | Chat ~40vw |
```

The chat panel is a first-class layout column, always visible by default, with a toggle to collapse it when the user needs full-width content.

## Layout Grid

### CSS Grid Structure

The root layout uses CSS grid with three named columns:

```css
.layout {
  display: grid;
  grid-template-columns: var(--nav-w) 1fr var(--chat-w);
  min-height: 100vh;
}
```

### Column Sizing

- **Nav:** `--nav-w: clamp(64px, 10vw, 88px)` -- scales with viewport, never too narrow for icons+labels or too wide to waste space.
- **Chat (open):** `--chat-w: 40vw`
- **Chat (closed):** `--chat-w: 0px`
- **Content:** `1fr` -- automatically absorbs freed space when chat collapses.

### Toggle Animation

```css
.layout {
  transition: grid-template-columns 300ms ease;
}

.chat-panel {
  overflow: hidden; /* prevents content flash during collapse */
}
```

### Persistence

Chat open/close state is stored in `localStorage` (`regain-chat-open`). Defaults to open on first visit.

## Sidebar Navigation

### Visual Design

Keeps the warm chocolate gradient (`#3B2D27` to `#261C18`). Shrinks from `w-60` (240px) to `clamp(64px, 10vw, 88px)`.

### Nav Item Layout

Each item is a vertical stack, centered horizontally:
- `NavIcon` SVG: 20px
- Label text: 10px, `tracking-wide`, `text-neutral-400` (inactive) or `text-accent-400` (active)
- Gap: 2px between icon and label

Active item retains the left 3px `accent-400` indicator bar with `animate-glow-pulse`.

### Logo

At 64-88px width, the full `regain-type.png` script logo won't be legible. Two options to evaluate during implementation:
1. Scale the existing PNG to fit (may be too small to read but still recognizable as a brand mark).
2. Replace with a text "R." in the same cursive font (General Sans italic or a custom lettermark).

Use whichever is more legible at the actual rendered size. Add `title="Regain"` for accessibility.

### Item Order (top to bottom)

1. Dashboard
2. Missions
3. Evidence
4. Voice
5. Resume
6. *(flex spacer)*
7. Profile (bottom-anchored)

## Chat Panel

### Design Principles

Minimal chrome. No header bar. The panel is a flex column filling full viewport height.

### Structure (top to bottom)

1. **Connection status indicator** -- 2px top border spanning the panel width.
   - `primary-500` (#916D65): connected
   - `warning-400`: reconnecting
   - `neutral-300`: disconnected
2. **Messages area** (`flex-1 overflow-y-auto`) -- scrollable conversation.
   - Assistant messages: left-aligned, `surface-2` background, rounded bubbles.
   - User messages: right-aligned, `primary-500` background, white text, rounded bubbles.
   - Same bubble styling as current CoachModal.
3. **Tool activity feed** -- `AgentActivityFeed` component renders inline when agent is working. Fades out after completion (existing behavior).
4. **Input area** (bottom-pinned, `border-t border-neutral-200`) -- text input with `chat-input-glow` focus ring. Send button right-aligned inside the input.

### State Management

Zero changes to `CoachingContext.tsx`. All WebSocket logic, message persistence (sessionStorage), streaming state, and tool steps remain as-is. The new `ChatPanel` component consumes the same context the current `CoachModal` does.

## Drawer Handle

A persistent visual element between the content and chat columns.

### Appearance

- Width: 3px strip
- Background: `neutral-200`
- Grab indicator: short (30px) `accent-400` bar centered vertically
- Cursor: `pointer` (not `col-resize` -- it's a toggle, not a drag handle)

### Behavior

- Click toggles chat panel open/closed
- Hover: grab indicator brightens slightly (opacity transition)
- Always visible regardless of chat state
- When chat is closed, the handle sits on the right edge of the content area

## Voice Practice Exception

Voice practice routes (`/voice-practice`, `/voice-practice/:id`) render outside the three-panel grid. They keep their current full-screen layout with the AudioVisualizer orb.

`Layout.tsx` checks the current route path. If it matches a voice practice route, render the full-screen layout (no sidebar, no chat panel). Otherwise, render the three-panel grid.

## Component Changes

### New Components

| Component | Purpose |
|-----------|---------|
| `ChatPanel.tsx` | Grid-embedded chat panel. Extracts message list + input from CoachModal. Consumes CoachingContext. |
| `Sidebar.tsx` | Extracted from Layout.tsx. Icon+label stacked nav at narrow width. |
| `DrawerHandle.tsx` | 3px toggle strip between content and chat columns. |

### Modified Components

| Component | Change |
|-----------|--------|
| `Layout.tsx` | Rewrite from flex to CSS grid. Compose Sidebar + content Outlet + DrawerHandle + ChatPanel. Add voice route detection for full-screen fallback. localStorage chat toggle state. |

### Removed Components

| Component | Reason |
|-----------|--------|
| `CoachModal.tsx` | Replaced entirely by ChatPanel in the grid. |
| `CoachingPage.tsx` | Currently redirects to /dashboard. No longer needed since chat is always accessible in the layout. |

### Unchanged Components

| Component | Notes |
|-----------|-------|
| `CoachingContext.tsx` | Zero changes. All WebSocket + state logic stays. |
| `AgentActivityFeed` | Rendered inside ChatPanel instead of CoachModal. Component itself unchanged. |
| All page components | Dashboard, Missions, Evidence, Profile, etc. render in the content column. No changes needed. |
| `App.tsx` routing | Remove CoachingPage route. Everything else stays. |

## CSS Token Additions

Add to `index.css` `@theme` block:

```css
--nav-w: clamp(64px, 10vw, 88px);
--chat-w-open: 40vw;
--chat-w-closed: 0px;
```

## Out of Scope

- Mobile layout changes (stays as-is)
- Voice practice layout changes (stays full-screen)
- CoachingContext refactoring (no state management changes)
- Backend changes (none required)
- Drag-to-resize functionality (fixed 50/40 split)
