"""Property test for thin handler pattern.

**Property 10: Thin Handler Pattern**
**Validates: Requirements 6.12**

Verifies that every Lambda handler follows the pattern:
validate input → call service module → return response,
with no business logic in the handler itself.

The property is: *For any* Lambda handler module, the handler file
must import a service class, must NOT import DynamoDB/boto3 directly,
and the lambda_handler function must delegate to the service module.
"""

import re
from pathlib import Path

from hypothesis import given, settings, strategies as st

# Project root: regAIn/ (three levels up from this test file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# All handler files that must follow the thin handler pattern
HANDLER_FILES = {
    "onboarding": _PROJECT_ROOT / "backend" / "handlers" / "onboarding" / "handler.py",
    "missions": _PROJECT_ROOT / "backend" / "handlers" / "missions" / "handler.py",
    "evidence": _PROJECT_ROOT / "backend" / "handlers" / "evidence" / "handler.py",
    "coaching": _PROJECT_ROOT / "backend" / "handlers" / "coaching" / "handler.py",
    "dashboard": _PROJECT_ROOT / "backend" / "handlers" / "dashboard" / "handler.py",
}

# Imports that indicate business logic leaking into the handler
FORBIDDEN_IMPORT_PATTERNS = [
    r"^\s*import\s+boto3",
    r"^\s*from\s+boto3",
    r"from\s+backend\.handlers\.shared\.dynamodb\s+import",
]

# Strategy: pick any handler name from the list
handler_strategy = st.sampled_from(list(HANDLER_FILES.keys()))


def _read_source(handler_name: str) -> str:
    """Read the source code for a handler file."""
    return HANDLER_FILES[handler_name].read_text()


def _get_import_lines(source: str) -> list[str]:
    """Extract all import lines from source code."""
    return [
        line for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]


@given(handler_name=handler_strategy)
@settings(max_examples=100)
def test_handler_imports_service_not_dynamodb(handler_name: str) -> None:
    """For any handler module, it must import its service module
    and must NOT import boto3 or the DynamoDB data access layer directly.

    This ensures handlers delegate business logic to service modules.
    """
    source = _read_source(handler_name)
    import_lines = _get_import_lines(source)
    import_text = "\n".join(import_lines)

    # Must import from its own service module
    service_pattern = rf"from\s+backend\.handlers\.{handler_name}\.service\s+import"
    assert re.search(service_pattern, import_text), (
        f"{handler_name}/handler.py does not import from its service module"
    )

    # Must NOT import forbidden business-logic modules
    for pattern in FORBIDDEN_IMPORT_PATTERNS:
        match = re.search(pattern, import_text, re.MULTILINE)
        assert match is None, (
            f"{handler_name}/handler.py imports forbidden module: {match.group()}. "
            "Handlers must delegate to service modules, not access DynamoDB directly."
        )


@given(handler_name=handler_strategy)
@settings(max_examples=100)
def test_handler_delegates_to_service(handler_name: str) -> None:
    """For any handler module, the lambda_handler function must instantiate
    a service class and call a method on it — confirming delegation.
    """
    source = _read_source(handler_name)

    # Verify lambda_handler function exists
    assert re.search(r"^def\s+lambda_handler\s*\(", source, re.MULTILINE), (
        f"{handler_name}/handler.py does not define a lambda_handler function"
    )

    # Extract the lambda_handler function body (everything after its def until
    # the next top-level def or end of file)
    handler_match = re.search(
        r"^def\s+lambda_handler\s*\([^)]*\)[^:]*:(.*?)(?=\n(?:def |class )|\Z)",
        source,
        re.DOTALL | re.MULTILINE,
    )
    assert handler_match, (
        f"{handler_name}/handler.py: could not extract lambda_handler body"
    )
    handler_body = handler_match.group(1)

    # Must instantiate a Service class (e.g. OnboardingService(), MissionsService())
    assert re.search(r"\w+Service\s*\(", handler_body), (
        f"{handler_name}/handler.py: lambda_handler does not instantiate a Service class. "
        "Handlers must delegate to a service module."
    )

    # Must call a method on the service instance (e.g. service.create_profile(...))
    assert re.search(r"service\.\w+\(", handler_body), (
        f"{handler_name}/handler.py: lambda_handler does not call a method on the service. "
        "Handlers must delegate business logic to the service module."
    )


@given(handler_name=handler_strategy)
@settings(max_examples=100)
def test_handler_returns_formatted_response(handler_name: str) -> None:
    """For any handler module, it must import and use response helpers
    (success_response / error_response) from the shared responses module.

    This ensures handlers use consistent API response formatting.
    """
    source = _read_source(handler_name)
    import_lines = _get_import_lines(source)
    import_text = "\n".join(import_lines)

    assert re.search(r"from\s+backend\.handlers\.shared\.responses\s+import", import_text), (
        f"{handler_name}/handler.py does not import from shared responses module. "
        "Handlers must use shared response helpers for consistent API responses."
    )

    # Verify both success_response and error_response are used in the handler
    assert "success_response" in source, (
        f"{handler_name}/handler.py does not use success_response"
    )
    assert "error_response" in source, (
        f"{handler_name}/handler.py does not use error_response"
    )
