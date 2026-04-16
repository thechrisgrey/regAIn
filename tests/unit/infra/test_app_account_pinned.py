"""Guard against cross-account drift in the CDK app entry point.

**Why this test exists:** The CDK CLI auto-populates CDK_DEFAULT_ACCOUNT from
whatever credentials it resolves. If infra/app.py reads that env var, an
expired SSO session silently sends deploys to the wrong account (the
long-lived IAM user in 205930636302 wired up through ~/.aws/credentials).

This test parses infra/app.py as AST and asserts that the production account
and region are hardcoded string literals — not dynamic function calls like
os.environ.get(...). Any regression that reintroduces env-driven account
resolution will fail this test before reaching deploy.
"""

from __future__ import annotations

import ast
from pathlib import Path


EXPECTED_ACCOUNT = "563170906428"
EXPECTED_REGION = "us-east-1"
APP_PY = Path(__file__).resolve().parents[3] / "infra" / "app.py"


def _find_assignment(module: ast.Module, target_name: str) -> ast.Assign:
    """Return the first top-level `target_name = ...` assignment."""
    for node in module.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == target_name:
                return node
    raise AssertionError(f"No top-level assignment to {target_name} found in app.py")


def _assert_string_literal(node: ast.Assign, expected: str) -> None:
    """Assert RHS of `node` is a plain string literal equal to `expected`."""
    rhs = node.value
    assert isinstance(rhs, ast.Constant), (
        f"_ACCOUNT/_REGION must be a string literal (ast.Constant), got {type(rhs).__name__}. "
        "Do NOT use os.environ.get() or any dynamic expression — the CDK CLI "
        "auto-populates CDK_DEFAULT_ACCOUNT, which causes silent cross-account deploys."
    )
    assert isinstance(rhs.value, str), f"Expected string literal, got {type(rhs.value).__name__}"
    assert rhs.value == expected, f"Expected '{expected}', got '{rhs.value}'"


class TestAppPyAccountPinned:
    """Enforce that infra/app.py pins account and region to production."""

    def test_app_py_exists(self) -> None:
        assert APP_PY.exists(), f"infra/app.py not found at {APP_PY}"

    def test_account_is_hardcoded_to_production(self) -> None:
        """_ACCOUNT must be a string literal '563170906428' (no env lookup)."""
        module = ast.parse(APP_PY.read_text())
        node = _find_assignment(module, "_ACCOUNT")
        _assert_string_literal(node, EXPECTED_ACCOUNT)

    def test_region_is_hardcoded(self) -> None:
        """_REGION must be a string literal 'us-east-1' (no env lookup)."""
        module = ast.parse(APP_PY.read_text())
        node = _find_assignment(module, "_REGION")
        _assert_string_literal(node, EXPECTED_REGION)

    def test_no_dynamic_account_resolution(self) -> None:
        """Neither _ACCOUNT nor _REGION may be assigned from a function call.

        Walks the module AST and verifies that any assignment targeting
        _ACCOUNT or _REGION has an ast.Constant RHS, not an ast.Call (which
        would indicate os.environ.get, os.getenv, or similar dynamic lookup).
        """
        module = ast.parse(APP_PY.read_text())
        guarded = {"_ACCOUNT", "_REGION"}
        for node in module.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in guarded:
                    assert not isinstance(node.value, ast.Call), (
                        f"{target.id} must not be assigned from a function call. "
                        "Dynamic env var lookups silently reroute deploys to the "
                        "wrong account when SSO credentials expire. Use a string literal."
                    )
