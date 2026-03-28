# Account Deletion Options

Give users the choice between immediate account deletion and a 30-day scheduled deletion with recovery window.

## Motivation

Currently `DELETE /profile` hard-deletes immediately. Users have no grace period, and the developer (who frequently recreates test accounts) needs fast deletion. The existing `soft_delete_user_account()` service method and `POST /profile/recover` endpoint are implemented but unwired. This feature connects the plumbing and exposes both paths in the UI.

## Decisions

| Question | Decision |
|----------|----------|
| How does the backend distinguish modes? | Request body `{"mode": "immediate"}` or `{"mode": "scheduled"}` on the existing `DELETE /profile` endpoint |
| UX flow | Stepped: type DELETE to confirm, then pick mode on a second panel with two cards |
| Recovery mechanism | Auto-show recovery banner in Layout when `deletedAt` is present on dashboard response |
| Extra friction after DELETE confirmation? | None — the DELETE input is the intent gate |

## Backend

### handler.py

The `DELETE /profile` handler reads `mode` from the request body:

- `{"mode": "immediate"}` calls `hard_delete_user_account(user_id)` (current behavior)
- `{"mode": "scheduled"}` calls `soft_delete_user_account(user_id)` (existing method, currently unwired)
- Missing or invalid `mode` returns 400 with `error_kind="VALIDATION"`

No new endpoints. No infrastructure changes. The existing `POST /profile/recover` endpoint and the scheduled cleanup Lambda remain unchanged.

### Response shapes

Immediate:
```json
{"status": "deleted", "deleted": {"user_profiles": 1, "campaigns": 2, ...}}
```

Scheduled:
```json
{"status": "scheduled", "deletionDate": "2026-04-25T12:00:00+00:00"}
```

### Dashboard service

`DashboardService.get_dashboard()` already reads the user profile to get the username. It needs to pass through `deletedAt` and `deletionScheduledFor` fields (if present) in the response so the frontend can detect a soft-deleted state and render the recovery banner.

Add to the dashboard response shape:
```json
{
  "campaign": {...},
  "stats": {...},
  "deletedAt": "2026-03-26T12:00:00+00:00",
  "deletionScheduledFor": "2026-04-25T12:00:00+00:00"
}
```

These fields are only present when the account is soft-deleted. The frontend checks for their existence.

## Frontend

### API layer (api.ts)

Update `api.profile.delete` to accept a mode parameter:

```typescript
delete: (token: string, mode: 'immediate' | 'scheduled' = 'immediate') =>
  apiRequest<{ status: string; deletionDate?: string; deleted?: Record<string, number> }>(
    '/profile',
    { method: 'DELETE', body: JSON.stringify({ mode }) },
    token,
  )
```

Default is `immediate` for backward compatibility.

### DeleteAccount component (Profile.tsx)

Two-step flow replacing the current single-step confirmation:

**Step 1:** User clicks "Delete my account". Confirmation panel expands. User types DELETE. Button reads "Continue" and advances to step 2.

**Step 2:** The input and button are replaced by two side-by-side cards:

- **"Delete now"** -- destructive styling (error border/text). Subtitle: "Permanently erase all data immediately. This cannot be undone." Calls `api.profile.delete(token, 'immediate')`, signs out, navigates to `/login`.
- **"Schedule for later"** -- neutral styling. Subtitle: "Data kept 30 days. Recover anytime by signing back in." Calls `api.profile.delete(token, 'scheduled')`, signs out, navigates to `/login`.

A "Cancel" link resets to the initial unexpanded state.

Both cards disable during the async call (reuse existing `deleting` state). Error display remains below the section label as it is today.

### Recovery banner (Layout.tsx)

When the dashboard response contains `deletedAt`, Layout renders a fixed banner above the main content (inside layout, outside sidebar):

> Your account is scheduled for deletion on [formatted date]. **Recover account**

Clicking "Recover account" calls `api.profile.recover(token)`, clears the banner state, and re-fetches dashboard data to confirm recovery.

The banner uses `bg-warning-50 border-warning-200` with `text-warning-700` text and a `text-primary-600 font-medium` recover link, consistent with the existing design system.

## Testing

### Backend

- **handler.py unit test:** Verify `mode=immediate` routes to `hard_delete_user_account`, `mode=scheduled` routes to `soft_delete_user_account`, missing/invalid mode returns 400.
- **Existing integration tests:** All `TestCascadeDeletion` tests remain valid (they test `hard_delete_user_account` directly, not the handler).
- **New integration test:** Soft delete sets `deletedAt` and `deletionScheduledFor` on the profile row, then `recover_user_account` removes them.
- **Dashboard service test:** Verify `deletedAt`/`deletionScheduledFor` are included in response when present, absent when not.

### Frontend

- **Profile.test.tsx:** Test two-step flow: type DELETE, click Continue, verify two mode cards appear. Click "Delete now" and verify `api.profile.delete(token, 'immediate')` called. Repeat for "Schedule for later" with `'scheduled'`.
- **api-service.smoke.test.ts:** Already passes (backward-compatible function signature).
- **Recovery banner test:** Mock dashboard response with `deletedAt` field, verify banner renders in Layout, click "Recover account", verify `api.profile.recover` called and banner disappears on re-fetch.

## Edge Cases

- **Refresh mid-step-2:** State resets to step 1 (local `useState`, no persistence needed).
- **Scheduled deletion + re-login within 30 days:** Banner appears, user can recover. After 30 days the existing cleanup Lambda hard-deletes.
- **Double-click:** Both cards disable during async via existing `deleting` state.
- **Soft-deleted user with stripped PII:** After recovery, `firstName`/`lastName`/`email` are `[deleted]`. User will need to re-enter via onboarding-style flow. This is existing behavior documented in `recover_user_account()` — out of scope for this feature.

## Files Changed

| File | Change |
|------|--------|
| `backend/handlers/profile/handler.py` | Read `mode` from body, route to hard/soft delete |
| `backend/handlers/dashboard/service.py` | Pass through `deletedAt`/`deletionScheduledFor` in response |
| `frontend/src/services/api.ts` | Add `mode` parameter to `api.profile.delete` |
| `frontend/src/pages/Profile.tsx` | Two-step deletion flow in `DeleteAccount` component |
| `frontend/src/components/Layout.tsx` | Recovery banner when `deletedAt` present |
| `frontend/src/hooks/useDashboard.ts` | Expose `deletedAt`/`deletionScheduledFor` from dashboard data |
| `tests/unit/handlers/test_profile_handler.py` | New: handler routing tests for mode parameter |
| `tests/integration/test_cascade_deletion.py` | New: soft delete + recover integration test |
| `frontend/src/pages/Profile.test.tsx` | Update: two-step flow tests |
| `frontend/src/components/Layout.test.tsx` | New/update: recovery banner tests |

## Out of Scope

- Post-recovery re-onboarding for stripped PII fields (existing limitation)
- Email notifications for scheduled deletion
- Admin-initiated deletion
