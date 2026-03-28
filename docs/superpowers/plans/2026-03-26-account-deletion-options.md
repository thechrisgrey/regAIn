# Account Deletion Options Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give users a choice between immediate account deletion and 30-day scheduled deletion with an in-app recovery banner.

**Architecture:** The existing `DELETE /profile` endpoint gains a `mode` body parameter (`immediate` | `scheduled`) that routes to the existing `hard_delete_user_account()` or `soft_delete_user_account()` methods. The dashboard service adds a profile read to surface `deletedAt`/`deletionScheduledFor` fields. The frontend Profile page gets a two-step deletion flow, and Layout gets a recovery banner.

**Tech Stack:** Python 3.12 (Lambda), React 19, TypeScript, Tailwind v4, Vitest, pytest

**Spec:** `docs/superpowers/specs/2026-03-26-account-deletion-options-design.md`

---

### Task 1: Backend — Profile handler mode routing

**Files:**
- Modify: `backend/handlers/profile/handler.py`
- Create: `tests/unit/handlers/test_profile_handler.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/handlers/test_profile_handler.py
"""Unit tests for profile handler mode routing."""

from unittest.mock import MagicMock, patch

import pytest

from backend.handlers.profile.handler import lambda_handler


def _make_event(method="DELETE", resource="/profile", body=None, user_id="user-123"):
    """Build a minimal API Gateway event."""
    event = {
        "httpMethod": method,
        "resource": resource,
        "body": body,
        "requestContext": {
            "authorizer": {"claims": {"sub": user_id}},
            "requestId": "test-req",
        },
    }
    return event


class TestDeleteModeRouting:
    """Verify DELETE /profile routes to correct service method based on mode."""

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_immediate_mode_calls_hard_delete(self, MockService):
        service = MockService.return_value
        service.hard_delete_user_account.return_value = {
            "status": "deleted",
            "deleted": {"user_profiles": 1},
        }

        event = _make_event(body='{"mode": "immediate"}')
        result = lambda_handler(event, None)

        service.hard_delete_user_account.assert_called_once_with("user-123")
        assert result["statusCode"] == 200

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_scheduled_mode_calls_soft_delete(self, MockService):
        service = MockService.return_value
        service.soft_delete_user_account.return_value = {
            "status": "scheduled",
            "deletionDate": "2026-04-25T00:00:00+00:00",
        }

        event = _make_event(body='{"mode": "scheduled"}')
        result = lambda_handler(event, None)

        service.soft_delete_user_account.assert_called_once_with("user-123")
        assert result["statusCode"] == 200

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_missing_mode_returns_400(self, MockService):
        event = _make_event(body='{}')
        result = lambda_handler(event, None)

        assert result["statusCode"] == 400
        service = MockService.return_value
        service.hard_delete_user_account.assert_not_called()
        service.soft_delete_user_account.assert_not_called()

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_invalid_mode_returns_400(self, MockService):
        event = _make_event(body='{"mode": "invalid"}')
        result = lambda_handler(event, None)

        assert result["statusCode"] == 400

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_no_body_returns_400(self, MockService):
        event = _make_event(body=None)
        result = lambda_handler(event, None)

        assert result["statusCode"] == 400

    @patch("backend.handlers.profile.handler.ProfileService")
    def test_recover_endpoint_unchanged(self, MockService):
        service = MockService.return_value
        service.recover_user_account.return_value = {"status": "recovered"}

        event = _make_event(method="POST", resource="/profile/recover")
        result = lambda_handler(event, None)

        service.recover_user_account.assert_called_once_with("user-123")
        assert result["statusCode"] == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/handlers/test_profile_handler.py -v`
Expected: FAIL — handler currently ignores the body and always calls `hard_delete_user_account`

- [ ] **Step 3: Implement the handler changes**

Replace the DELETE branch in `backend/handlers/profile/handler.py`:

```python
"""Profile Lambda handler.

Thin handler that extracts the user identity, delegates to
ProfileService, and returns a formatted response.
"""

import json
import logging
from typing import Any, Dict

from backend.handlers.shared.auth import get_user_id
from backend.handlers.shared.responses import error_response, success_response
from backend.handlers.shared.structured_log import get_logger
from backend.handlers.profile.service import ProfileService

logger = logging.getLogger(__name__)

_VALID_MODES = {"immediate", "scheduled"}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle profile requests (DELETE /profile, POST /profile/recover).

    Args:
        event: API Gateway event.
        context: Lambda context.

    Returns:
        API Gateway-compatible response.
    """
    slog = get_logger(event, __name__)
    user_id = get_user_id(event)
    if not user_id:
        return error_response("Unauthorized", 401)

    http_method = event.get("httpMethod", "")
    resource = event.get("resource", "")

    try:
        service = ProfileService()

        if http_method == "POST" and resource == "/profile/recover":
            result = service.recover_user_account(user_id)
            return success_response(result)

        if http_method == "DELETE":
            raw_body = event.get("body")
            if not raw_body:
                return error_response(
                    "Missing required field: mode", 400, error_kind="VALIDATION",
                )
            try:
                body = json.loads(raw_body)
            except (json.JSONDecodeError, TypeError):
                return error_response(
                    "Invalid JSON body", 400, error_kind="VALIDATION",
                )

            mode = body.get("mode")
            if mode not in _VALID_MODES:
                return error_response(
                    "Invalid mode. Must be 'immediate' or 'scheduled'",
                    400,
                    error_kind="VALIDATION",
                )

            if mode == "immediate":
                result = service.hard_delete_user_account(user_id)
            else:
                result = service.soft_delete_user_account(user_id)
            return success_response(result)

        return error_response("Not found", 404)
    except Exception:
        slog.exception("Profile handler failed for user %s", user_id)
        return error_response("Internal server error", 500)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/handlers/test_profile_handler.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/handlers/profile/handler.py tests/unit/handlers/test_profile_handler.py
git commit -m "feat: add mode parameter to DELETE /profile handler

Routes 'immediate' to hard_delete_user_account and 'scheduled' to
soft_delete_user_account. Returns 400 for missing or invalid mode."
```

---

### Task 2: Backend — Dashboard service surfaces deletedAt

**Files:**
- Modify: `backend/handlers/dashboard/service.py`
- Create: `tests/unit/handlers/test_dashboard_deletion_fields.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/handlers/test_dashboard_deletion_fields.py
"""Tests for deletedAt/deletionScheduledFor passthrough in dashboard response."""

from unittest.mock import MagicMock

import pytest

from backend.handlers.dashboard.service import DashboardService


def _make_db_client(profile=None, campaigns=None, missions=None, evidence=None):
    """Build a mock DynamoDBClient."""
    db = MagicMock()
    db.get_item.return_value = profile
    db.query_all.side_effect = lambda table, *a, **kw: {
        "campaigns": campaigns or [],
        "mission_history": missions or [],
        "evidence_vault": evidence or [],
    }.get(table, [])
    return db


class TestDashboardDeletionFields:
    """Verify deletedAt/deletionScheduledFor appear in dashboard response."""

    def test_includes_deletion_fields_when_soft_deleted(self):
        profile = {
            "userId": "u1",
            "deletedAt": "2026-03-26T12:00:00+00:00",
            "deletionScheduledFor": "2026-04-25T12:00:00+00:00",
        }
        db = _make_db_client(profile=profile)
        service = DashboardService(db_client=db)

        result = service.get_dashboard("u1")

        assert result["deletedAt"] == "2026-03-26T12:00:00+00:00"
        assert result["deletionScheduledFor"] == "2026-04-25T12:00:00+00:00"

    def test_omits_deletion_fields_when_not_deleted(self):
        profile = {"userId": "u1", "name": "Jane"}
        db = _make_db_client(profile=profile)
        service = DashboardService(db_client=db)

        result = service.get_dashboard("u1")

        assert "deletedAt" not in result
        assert "deletionScheduledFor" not in result

    def test_omits_deletion_fields_when_profile_not_found(self):
        db = _make_db_client(profile=None)
        service = DashboardService(db_client=db)

        result = service.get_dashboard("u1")

        assert "deletedAt" not in result
        assert "deletionScheduledFor" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/unit/handlers/test_dashboard_deletion_fields.py -v`
Expected: FAIL — `get_dashboard` doesn't read the profile or return deletion fields

- [ ] **Step 3: Implement the dashboard service changes**

Modify `backend/handlers/dashboard/service.py` to add a profile read inside the existing `ThreadPoolExecutor` and pass through deletion fields:

```python
"""Dashboard service module.

Contains business logic for aggregating campaign statistics.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List

from boto3.dynamodb.conditions import Key

from backend.handlers.shared.dynamodb import DynamoDBClient

logger = logging.getLogger(__name__)

_QUERY_TIMEOUT_SECONDS = 8


class DashboardService:
    """Handles dashboard aggregation business logic."""

    def __init__(self, db_client: DynamoDBClient | None = None) -> None:
        self.db = db_client or DynamoDBClient()

    def get_dashboard(self, user_id: str) -> Dict[str, Any]:
        """Aggregate campaign progress and statistics for a user.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            Dict with campaign info, stats, and optional deletion fields.
        """
        key_condition = Key("userId").eq(user_id)

        with ThreadPoolExecutor(max_workers=4) as executor:
            profile_future = executor.submit(
                self.db.get_item, "user_profiles", {"userId": user_id}
            )
            campaigns_future = executor.submit(
                self.db.query_all, "campaigns", key_condition
            )
            missions_future = executor.submit(
                self.db.query_all, "mission_history", key_condition
            )
            evidence_future = executor.submit(
                self.db.query_all, "evidence_vault", key_condition
            )

            try:
                profile = profile_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
                campaigns = campaigns_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
                missions = missions_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
                evidence = evidence_future.result(timeout=_QUERY_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                logger.error("Dashboard query timed out after %ds", _QUERY_TIMEOUT_SECONDS)
                raise

        active_campaign = next(
            (c for c in campaigns if c.get("status") == "active"), None
        )
        completed = [m for m in missions if m.get("status") == "completed"]

        result: Dict[str, Any] = {
            "campaign": active_campaign,
            "stats": {
                "missionsCompleted": len(completed),
                "missionsTotal": len(missions),
                "evidenceCount": len(evidence),
                "currentPhase": active_campaign.get("phase") if active_campaign else None,
            },
        }

        if profile:
            deleted_at = profile.get("deletedAt")
            deletion_scheduled = profile.get("deletionScheduledFor")
            if deleted_at:
                result["deletedAt"] = deleted_at
            if deletion_scheduled:
                result["deletionScheduledFor"] = deletion_scheduled

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/unit/handlers/test_dashboard_deletion_fields.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Run existing dashboard tests to verify no regressions**

Run: `.venv/bin/pytest tests/ -k dashboard -v`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add backend/handlers/dashboard/service.py tests/unit/handlers/test_dashboard_deletion_fields.py
git commit -m "feat: surface deletedAt in dashboard response

Adds a profile read to the dashboard service (parallel with existing
queries) and passes through deletedAt/deletionScheduledFor when present."
```

---

### Task 3: Backend — Integration test for soft delete + recover cycle

**Files:**
- Modify: `tests/integration/test_cascade_deletion.py`

- [ ] **Step 1: Write the integration tests**

Add a new test class at the end of `tests/integration/test_cascade_deletion.py`:

```python
class TestSoftDeleteAndRecoverCycle:
    """Tests for soft delete → recover flow via ProfileService."""

    def test_soft_delete_sets_deletion_markers(self, integration_tables):
        """soft_delete_user_account sets deletedAt and deletionScheduledFor."""
        db = DynamoDBClient()
        user_id = f"soft-del-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.soft_delete_user_account(user_id)

        assert result["status"] == "scheduled"
        assert "deletionDate" in result

        profile = db.get_item("user_profiles", {"userId": user_id})
        assert profile is not None
        assert "deletedAt" in profile
        assert "deletionScheduledFor" in profile
        assert profile["firstName"] == "[deleted]"
        assert profile["lastName"] == "[deleted]"

    def test_recover_clears_deletion_markers(self, integration_tables):
        """recover_user_account removes deletedAt and deletionScheduledFor."""
        db = DynamoDBClient()
        user_id = f"recover-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        service.soft_delete_user_account(user_id)

        result = service.recover_user_account(user_id)
        assert result["status"] == "recovered"

        profile = db.get_item("user_profiles", {"userId": user_id})
        assert profile is not None
        assert "deletedAt" not in profile
        assert "deletionScheduledFor" not in profile

    def test_recover_non_deleted_account_returns_not_deleted(self, integration_tables):
        """recover on an active account returns not_deleted status."""
        db = DynamoDBClient()
        user_id = f"no-del-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        result = service.recover_user_account(user_id)

        assert result["status"] == "not_deleted"

    def test_data_preserved_after_soft_delete(self, integration_tables):
        """Soft delete does NOT remove campaigns, missions, or evidence."""
        from boto3.dynamodb.conditions import Key

        db = DynamoDBClient()
        user_id = f"soft-keep-{uuid.uuid4().hex[:8]}"
        _seed_full_user(db, user_id)

        service = _make_profile_service(db)
        service.soft_delete_user_account(user_id)

        assert len(db.query_all("campaigns", Key("userId").eq(user_id))) == 2
        assert len(db.query_all("mission_history", Key("userId").eq(user_id))) == 5
        assert len(db.query_all("evidence_vault", Key("userId").eq(user_id))) == 3
        assert len(db.query_all("voice_sessions", Key("userId").eq(user_id))) == 2
```

- [ ] **Step 2: Run the integration tests**

Run: `.venv/bin/pytest tests/integration/test_cascade_deletion.py::TestSoftDeleteAndRecoverCycle -v`
Expected: All 4 tests PASS (these test existing service methods that already work)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_cascade_deletion.py
git commit -m "test: add integration tests for soft delete + recover cycle"
```

---

### Task 4: Frontend — Update API layer and types

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Update the DashboardResponse type**

In `frontend/src/types/index.ts`, add the optional deletion fields to `DashboardResponse`:

```typescript
export interface DashboardResponse {
  campaign: Campaign;
  stats: {
    missionsCompleted: number;
    evidenceCount: number;
    currentPhase: Campaign['phase'];
  };
  deletedAt?: string;
  deletionScheduledFor?: string;
}
```

- [ ] **Step 2: Update api.profile.delete signature**

In `frontend/src/services/api.ts`, change the `profile.delete` method:

From:
```typescript
  profile: {
    delete: (token: string) =>
      apiRequest<{ status: string; deletionDate: string }>(
        '/profile',
        { method: 'DELETE' },
        token,
      ),
```

To:
```typescript
  profile: {
    delete: (token: string, mode: 'immediate' | 'scheduled' = 'immediate') =>
      apiRequest<{ status: string; deletionDate?: string; deleted?: Record<string, number> }>(
        '/profile',
        { method: 'DELETE', body: { mode } },
        token,
      ),
```

- [ ] **Step 3: Run existing smoke tests to verify backward compatibility**

Run: `cd frontend && npx vitest --run src/__smoke__/api-service.smoke.test.ts`
Expected: PASS — `typeof api.profile.delete === 'function'` still holds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/api.ts frontend/src/types/index.ts
git commit -m "feat: add mode param to api.profile.delete and deletion fields to DashboardResponse"
```

---

### Task 5: Frontend — Two-step deletion flow in Profile

**Files:**
- Modify: `frontend/src/pages/Profile.tsx`
- Modify: `frontend/src/pages/Profile.test.tsx`

- [ ] **Step 1: Write the failing tests**

Update `frontend/src/pages/Profile.test.tsx` — replace the existing delete-related tests and add step-2 tests. First, update the mock to match the new signature:

```typescript
// In the vi.mock('../services/api') block, change to:
vi.mock('../services/api', () => ({
  api: {
    profile: {
      delete: vi.fn().mockResolvedValue({ status: 'deleted' }),
    },
  },
}));
```

Then add these new tests inside the existing `describe('Profile')` block, replacing `it('shows delete confirmation input when clicking delete'...)` and `it('cancel button hides delete confirmation'...)`:

```typescript
  it('shows delete confirmation input when clicking delete', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    expect(screen.getByText('Type DELETE to confirm')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
  });

  it('continue button advances to step 2 after typing DELETE', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    fireEvent.change(screen.getByPlaceholderText('DELETE'), { target: { value: 'DELETE' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByText('Delete now')).toBeInTheDocument();
    expect(screen.getByText('Schedule for later')).toBeInTheDocument();
    expect(screen.queryByText('Type DELETE to confirm')).not.toBeInTheDocument();
  });

  it('delete now calls api.profile.delete with immediate mode', async () => {
    const { api: mockApi } = await import('../services/api');
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    fireEvent.change(screen.getByPlaceholderText('DELETE'), { target: { value: 'DELETE' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.click(screen.getByText('Delete now'));
    expect(mockApi.profile.delete).toHaveBeenCalledWith('mock-token', 'immediate');
  });

  it('schedule for later calls api.profile.delete with scheduled mode', async () => {
    const { api: mockApi } = await import('../services/api');
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    fireEvent.change(screen.getByPlaceholderText('DELETE'), { target: { value: 'DELETE' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    fireEvent.click(screen.getByText('Schedule for later'));
    expect(mockApi.profile.delete).toHaveBeenCalledWith('mock-token', 'scheduled');
  });

  it('cancel button hides delete confirmation from step 1', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    expect(screen.getByText('Type DELETE to confirm')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.queryByText('Type DELETE to confirm')).not.toBeInTheDocument();
  });

  it('cancel button resets from step 2 back to initial state', () => {
    mockedUseDashboard.mockReturnValue({
      data: { campaign: MOCK_CAMPAIGN, stats: MOCK_STATS },
      loading: false,
      error: null,
      fetchDashboard: mockFetchDashboard,
    });
    renderPage();
    fireEvent.click(screen.getByText('Delete my account'));
    fireEvent.change(screen.getByPlaceholderText('DELETE'), { target: { value: 'DELETE' } });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByText('Delete now')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Cancel'));
    expect(screen.queryByText('Delete now')).not.toBeInTheDocument();
    expect(screen.getByText('Delete my account')).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest --run src/pages/Profile.test.tsx`
Expected: FAIL — "Continue" button doesn't exist, step 2 cards don't exist

- [ ] **Step 3: Implement the two-step DeleteAccount component**

Replace the `DeleteAccount` function in `frontend/src/pages/Profile.tsx` (lines 376-463):

```tsx
function DeleteAccount({
  getToken,
  signOut,
}: {
  getToken: () => Promise<string>;
  signOut: () => Promise<void>;
}) {
  const navigate = useNavigate();
  const [step, setStep] = useState<'idle' | 'confirm' | 'choose'>('idle');
  const [confirmText, setConfirmText] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const handleDelete = useCallback(async (mode: 'immediate' | 'scheduled') => {
    setDeleting(true);
    setDeleteError('');
    try {
      const token = await getToken();
      await api.profile.delete(token, mode);
      await signOut();
      navigate('/login');
    } catch (err) {
      setDeleteError(
        err instanceof Error ? err.message : 'Failed to delete account',
      );
      setDeleting(false);
    }
  }, [getToken, signOut, navigate]);

  const reset = useCallback(() => {
    setStep('idle');
    setConfirmText('');
    setDeleteError('');
  }, []);

  return (
    <Card className="p-6">
      <SectionLabel>Account</SectionLabel>

      <div className="mt-5 border-t border-neutral-100 pt-5">
        <p className="text-sm font-medium text-neutral-900">Delete account</p>
        <p className="mt-1.5 text-sm leading-relaxed text-neutral-500">
          Permanently delete your account and all associated data.
        </p>

        {deleteError && (
          <p className="mt-3 text-sm text-error-600">{deleteError}</p>
        )}

        {step === 'idle' && (
          <button
            onClick={() => setStep('confirm')}
            className="mt-4 text-sm font-medium text-error-600 hover:text-error-700 transition-colors"
          >
            Delete my account
          </button>
        )}

        {step === 'confirm' && (
          <div className="mt-4 space-y-3">
            <Input
              label="Type DELETE to confirm"
              placeholder="DELETE"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              autoComplete="off"
            />
            <div className="flex items-center gap-3">
              <Button
                variant="destructive"
                size="sm"
                disabled={confirmText !== 'DELETE'}
                onClick={() => setStep('choose')}
              >
                Continue
              </Button>
              <button
                onClick={reset}
                className="text-sm text-neutral-500 hover:text-neutral-700 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {step === 'choose' && (
          <div className="mt-4 space-y-3">
            <p className="text-sm font-medium text-neutral-700">
              How would you like to proceed?
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <button
                disabled={deleting}
                onClick={() => void handleDelete('immediate')}
                className="rounded-[var(--radius-card)] border border-error-200 bg-error-50/50 p-4 text-left transition-colors hover:bg-error-50 disabled:opacity-50"
              >
                <p className="text-sm font-semibold text-error-700">Delete now</p>
                <p className="mt-1 text-xs leading-relaxed text-neutral-500">
                  Permanently erase all data immediately. This cannot be undone.
                </p>
              </button>
              <button
                disabled={deleting}
                onClick={() => void handleDelete('scheduled')}
                className="rounded-[var(--radius-card)] border border-neutral-200 bg-surface-1 p-4 text-left transition-colors hover:bg-surface-2 disabled:opacity-50"
              >
                <p className="text-sm font-semibold text-neutral-700">Schedule for later</p>
                <p className="mt-1 text-xs leading-relaxed text-neutral-500">
                  Data kept 30 days. Recover anytime by signing back in.
                </p>
              </button>
            </div>
            <button
              onClick={reset}
              className="text-sm text-neutral-500 hover:text-neutral-700 transition-colors"
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    </Card>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest --run src/pages/Profile.test.tsx`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Profile.tsx frontend/src/pages/Profile.test.tsx
git commit -m "feat: two-step deletion flow with immediate/scheduled options

Step 1: type DELETE to confirm. Step 2: choose between 'Delete now'
(immediate) and 'Schedule for later' (30-day hold)."
```

---

### Task 6: Frontend — Recovery banner in Layout

**Files:**
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/components/Layout.test.tsx`

- [ ] **Step 1: Write the failing tests**

Add to `frontend/src/components/Layout.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Layout from './Layout';

const mockGetToken = vi.fn().mockResolvedValue('mock-token');
const mockRefreshDashboard = vi.fn();

vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    user: { username: 'test-user' },
    signOut: vi.fn(),
    loading: false,
    getToken: mockGetToken,
  })),
}));

vi.mock('../services/api', () => ({
  cachedGet: vi.fn(),
  api: {
    profile: {
      recover: vi.fn().mockResolvedValue({ status: 'recovered' }),
    },
  },
}));

vi.mock('../hooks/useSharedData', () => ({
  useSharedData: vi.fn(() => ({
    dashboard: {
      data: null,
      loading: false,
      error: null,
    },
    refreshDashboard: mockRefreshDashboard,
  })),
}));

import { useSharedData } from '../hooks/useSharedData';
const mockedUseSharedData = vi.mocked(useSharedData);

function renderLayout() {
  return render(
    <MemoryRouter>
      <Layout />
    </MemoryRouter>,
  );
}

describe('Layout navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedUseSharedData.mockReturnValue({
      dashboard: { data: null, loading: false, error: null },
      refreshDashboard: mockRefreshDashboard,
    } as ReturnType<typeof useSharedData>);
  });

  it('includes Resume nav item between Evidence and Profile (Req 9.1)', () => {
    renderLayout();

    const nav = screen.getByRole('navigation');
    const links = Array.from(nav.querySelectorAll('a'));
    const labels = links.map(link => link.textContent?.trim());

    expect(labels).toContain('Resume');

    const evidenceIdx = labels.indexOf('Evidence');
    const resumeIdx = labels.indexOf('Resume');
    const profileIdx = labels.indexOf('Profile');

    expect(evidenceIdx).toBeLessThan(resumeIdx);
    expect(resumeIdx).toBeLessThan(profileIdx);
  });
});

describe('Recovery banner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not show banner when account is not deleted', () => {
    mockedUseSharedData.mockReturnValue({
      dashboard: {
        data: { campaign: null, stats: { missionsCompleted: 0, evidenceCount: 0, currentPhase: null } },
        loading: false,
        error: null,
      },
      refreshDashboard: mockRefreshDashboard,
    } as unknown as ReturnType<typeof useSharedData>);
    renderLayout();
    expect(screen.queryByText('Recover account')).not.toBeInTheDocument();
  });

  it('shows recovery banner when deletedAt is present', () => {
    mockedUseSharedData.mockReturnValue({
      dashboard: {
        data: {
          campaign: null,
          stats: { missionsCompleted: 0, evidenceCount: 0, currentPhase: null },
          deletedAt: '2026-03-26T12:00:00+00:00',
          deletionScheduledFor: '2026-04-25T12:00:00+00:00',
        },
        loading: false,
        error: null,
      },
      refreshDashboard: mockRefreshDashboard,
    } as unknown as ReturnType<typeof useSharedData>);
    renderLayout();
    expect(screen.getByText('Recover account')).toBeInTheDocument();
    expect(screen.getByText(/scheduled for deletion/)).toBeInTheDocument();
  });

  it('calls api.profile.recover when recover link is clicked', async () => {
    const { api: mockApi } = await import('../services/api');
    mockedUseSharedData.mockReturnValue({
      dashboard: {
        data: {
          campaign: null,
          stats: { missionsCompleted: 0, evidenceCount: 0, currentPhase: null },
          deletedAt: '2026-03-26T12:00:00+00:00',
          deletionScheduledFor: '2026-04-25T12:00:00+00:00',
        },
        loading: false,
        error: null,
      },
      refreshDashboard: mockRefreshDashboard,
    } as unknown as ReturnType<typeof useSharedData>);
    renderLayout();
    fireEvent.click(screen.getByText('Recover account'));
    await waitFor(() => {
      expect(mockApi.profile.recover).toHaveBeenCalledWith('mock-token');
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest --run src/components/Layout.test.tsx`
Expected: FAIL — Layout doesn't read dashboard data or render a banner

- [ ] **Step 3: Implement the recovery banner in Layout**

Modify `frontend/src/components/Layout.tsx`. Add imports and the banner component:

Add to the imports at the top:

```typescript
import { Suspense, useState, useEffect, useCallback } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useSharedData } from '../hooks/useSharedData';
import { api, cachedGet } from '../services/api';
import NavIcon from './ui/NavIcon';
import ErrorBoundary from './ErrorBoundary';
import RouteLoader from './RouteLoader';
import ConnectionBanner from './ConnectionBanner';
```

Add this component before the `Layout` function:

```tsx
function RecoveryBanner() {
  const { getToken } = useAuth();
  const { dashboard, refreshDashboard } = useSharedData();
  const [recovering, setRecovering] = useState(false);

  const deletedAt = dashboard.data?.deletedAt;
  const deletionScheduledFor = dashboard.data?.deletionScheduledFor;

  if (!deletedAt) return null;

  const formattedDate = deletionScheduledFor
    ? new Date(deletionScheduledFor).toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      })
    : 'soon';

  const handleRecover = async () => {
    setRecovering(true);
    try {
      const token = await getToken();
      await api.profile.recover(token);
      await refreshDashboard();
    } catch {
      setRecovering(false);
    }
  };

  return (
    <div className="mb-4 rounded-[var(--radius-card)] border border-warning-200 bg-warning-50 px-4 py-3">
      <p className="text-sm text-warning-700">
        Your account is scheduled for deletion on {formattedDate}.{' '}
        <button
          onClick={() => void handleRecover()}
          disabled={recovering}
          className="font-medium text-primary-600 hover:text-primary-700 transition-colors disabled:opacity-50"
        >
          {recovering ? 'Recovering...' : 'Recover account'}
        </button>
      </p>
    </div>
  );
}
```

Then in the `Layout` function, add `<RecoveryBanner />` right after `<ConnectionBanner />` inside the `<main>` content area:

```tsx
      <main className="flex-1 overflow-y-auto bg-surface-2 pt-[60px] md:pt-0">
        <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 sm:py-8">
          <ConnectionBanner />
          <RecoveryBanner />
          <ErrorBoundary>
            <Suspense fallback={<RouteLoader />}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </div>
      </main>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest --run src/components/Layout.test.tsx`
Expected: All tests PASS

- [ ] **Step 5: Run the full frontend test suite**

Run: `cd frontend && npx vitest --run`
Expected: All tests PASS — no regressions

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Layout.tsx frontend/src/components/Layout.test.tsx
git commit -m "feat: add recovery banner for soft-deleted accounts

Shows a warning banner in Layout when the dashboard response contains
deletedAt. Clicking 'Recover account' calls POST /profile/recover and
refreshes the dashboard data."
```

---

### Task 7: Full integration verification

- [ ] **Step 1: Run the full backend test suite**

Run: `.venv/bin/pytest tests/integration/ -x -q -v`
Expected: All integration tests PASS (~30 tests)

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npx vitest --run`
Expected: All tests PASS

- [ ] **Step 3: Build the frontend to check for type errors**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no type errors

- [ ] **Step 4: Run ESLint**

Run: `cd frontend && npm run lint`
Expected: No lint errors

- [ ] **Step 5: Final commit with any fixes if needed**

Only if previous steps revealed issues. Otherwise, this task is complete.
