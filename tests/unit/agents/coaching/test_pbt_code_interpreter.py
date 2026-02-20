"""Property-based tests for Code Interpreter output URL.

# Feature: agentcore-platform-integration, Property 13: Code interpreter output URL

**Validates: Requirements 13.3**

For any Code Interpreter execution that produces an output file, the system
SHALL return a response containing a valid presigned S3 URL pointing to the
generated file.

Strategy:
- Mock the bedrock-agentcore client (invoke_tool) to return simulated
  Code Interpreter responses with output_key, url, or stdout-only results.
- Mock the S3 client to return deterministic presigned URLs.
- Generate random Python code strings, session IDs, and S3 object keys.
- Verify: when Gateway returns output_key → presigned URL is generated.
- Verify: when Gateway returns url directly → it is passed through.
- Verify: when Gateway returns no output file → url is empty string.
- Verify: presigned URL contains expected bucket and key.
"""

import os
import sys
import types
from typing import Any
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub strands so tool_schemas.py (imported by gateway_client) can load
# ---------------------------------------------------------------------------
_strands_stub = types.ModuleType("strands")
_strands_stub.tool = lambda fn: fn  # type: ignore[attr-defined]
sys.modules.setdefault("strands", _strands_stub)

from hypothesis import given, settings, HealthCheck  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from backend.agents.coaching.gateway_client import GatewayToolClient  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_GATEWAY_ID = "regain-coaching-gateway"
TEST_JWT_TOKEN = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test.sig"
TEST_BUCKET = "regain-code-interpreter-output-563170906428"
TEST_REGION = "us-east-1"


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_id_alphabet = st.characters(whitelist_categories=("L", "N", "Pd"))

_session_id = st.text(min_size=1, max_size=40, alphabet=_id_alphabet)

_s3_object_key = st.builds(
    lambda prefix, name, ext: f"{prefix}/{name}.{ext}",
    st.text(min_size=1, max_size=20, alphabet=_id_alphabet),
    st.text(min_size=1, max_size=20, alphabet=_id_alphabet),
    st.sampled_from(["png", "jpg", "csv", "pdf"]),
)

_matplotlib_code = st.builds(
    lambda title, xlabel, ylabel: (
        "import matplotlib.pyplot as plt\n"
        f"plt.title('{title}')\n"
        f"plt.xlabel('{xlabel}')\n"
        f"plt.ylabel('{ylabel}')\n"
        "plt.plot([1, 2, 3], [4, 5, 6])\n"
        "plt.savefig('output.png')\n"
    ),
    st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N", "Zs"))),
    st.text(min_size=1, max_size=15, alphabet=st.characters(whitelist_categories=("L",))),
    st.text(min_size=1, max_size=15, alphabet=st.characters(whitelist_categories=("L",))),
)

_stdout_text = st.text(min_size=0, max_size=100)

_direct_url = st.builds(
    lambda key: f"https://{TEST_BUCKET}.s3.amazonaws.com/{key}?X-Amz-Signature=abc123",
    _s3_object_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_presigned_url(bucket: str, key: str) -> str:
    """Build a deterministic presigned URL for testing."""
    return (
        f"https://{bucket}.s3.{TEST_REGION}.amazonaws.com/{key}"
        f"?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=3600"
    )


def _create_client(gateway_response: dict[str, Any]) -> tuple[GatewayToolClient, MagicMock]:
    """Create a GatewayToolClient with a mocked agentcore client.

    The agentcore client's invoke_tool is mocked to return the given
    gateway_response. Returns the client and a mock S3 client that
    should be patched into boto3.client calls during execute_code.

    Args:
        gateway_response: The response dict that invoke_tool should return.

    Returns:
        Tuple of (client, mock_s3_client).
    """
    mock_agentcore = MagicMock()
    mock_agentcore.invoke_tool.return_value = {
        "output": gateway_response,
    }

    client = GatewayToolClient(TEST_GATEWAY_ID, TEST_JWT_TOKEN)
    client.client = mock_agentcore

    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.side_effect = lambda method, Params, ExpiresIn: (
        _make_presigned_url(Params["Bucket"], Params["Key"])
    )

    return client, mock_s3


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestCodeInterpreterOutputURL:
    """Property 13: Code interpreter output URL.

    For random Code Interpreter executions that produce output files,
    verify presigned S3 URL in response.
    """

    @given(
        code=_matplotlib_code,
        session_id=_session_id,
        object_key=_s3_object_key,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_output_key_produces_presigned_url(
        self,
        code: str,
        session_id: str,
        object_key: str,
    ) -> None:
        """When Gateway returns an output_key, execute_code SHALL return a
        presigned S3 URL containing the expected bucket and key.

        # Feature: agentcore-platform-integration, Property 13: Code interpreter output URL
        **Validates: Requirements 13.3**
        """
        gateway_response = {
            "output_key": object_key,
            "execution_status": "success",
            "stdout": "",
            "stderr": "",
        }

        client, mock_s3 = _create_client(gateway_response)

        with patch.dict(os.environ, {
            "CODE_INTERPRETER_BUCKET": TEST_BUCKET,
            "AWS_REGION": TEST_REGION,
        }):
            with patch(
                "backend.agents.coaching.gateway_client.boto3.client",
                return_value=mock_s3,
            ):
                result = client.execute_code(code, session_id)

        assert result.get("url"), (
            f"Expected presigned URL for output_key={object_key!r}, "
            f"got result: {result}"
        )

        url = result["url"]
        assert TEST_BUCKET in url, (
            f"Presigned URL does not contain bucket {TEST_BUCKET!r}: {url}"
        )
        assert object_key in url, (
            f"Presigned URL does not contain key {object_key!r}: {url}"
        )
        assert result.get("execution_status") == "success"
        assert "output_key" not in result

    @given(
        code=_matplotlib_code,
        session_id=_session_id,
        direct_url=_direct_url,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_direct_url_is_passed_through(
        self,
        code: str,
        session_id: str,
        direct_url: str,
    ) -> None:
        """When Gateway returns a url directly (no output_key), execute_code
        SHALL pass it through unchanged.

        # Feature: agentcore-platform-integration, Property 13: Code interpreter output URL
        **Validates: Requirements 13.3**
        """
        gateway_response = {
            "url": direct_url,
            "execution_status": "success",
            "stdout": "",
            "stderr": "",
        }

        client, _ = _create_client(gateway_response)
        result = client.execute_code(code, session_id)

        assert result.get("url") == direct_url, (
            f"Expected direct URL {direct_url!r} to pass through, "
            f"got: {result.get('url')!r}"
        )
        assert result.get("execution_status") == "success"

    @given(
        code=_matplotlib_code,
        session_id=_session_id,
        stdout=_stdout_text,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_stdout_only_response_has_empty_url(
        self,
        code: str,
        session_id: str,
        stdout: str,
    ) -> None:
        """When Gateway returns no output file (stdout-only), execute_code
        SHALL return an empty string for url.

        # Feature: agentcore-platform-integration, Property 13: Code interpreter output URL
        **Validates: Requirements 13.3**
        """
        gateway_response = {
            "execution_status": "success",
            "stdout": stdout,
            "stderr": "",
        }

        client, _ = _create_client(gateway_response)
        result = client.execute_code(code, session_id)

        assert result.get("url") == "", (
            f"Expected empty URL for stdout-only response, "
            f"got: {result.get('url')!r}"
        )
        assert result.get("stdout") == stdout
        assert result.get("execution_status") == "success"

    @given(
        code=_matplotlib_code,
        session_id=_session_id,
        object_key=_s3_object_key,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_presigned_url_uses_correct_bucket_from_env(
        self,
        code: str,
        session_id: str,
        object_key: str,
    ) -> None:
        """The presigned URL SHALL be generated using the bucket from the
        CODE_INTERPRETER_BUCKET environment variable.

        # Feature: agentcore-platform-integration, Property 13: Code interpreter output URL
        **Validates: Requirements 13.3**
        """
        custom_bucket = "custom-test-bucket-12345"

        gateway_response = {
            "output_key": object_key,
            "execution_status": "success",
            "stdout": "",
            "stderr": "",
        }

        client, mock_s3 = _create_client(gateway_response)

        with patch.dict(os.environ, {
            "CODE_INTERPRETER_BUCKET": custom_bucket,
            "AWS_REGION": TEST_REGION,
        }):
            with patch(
                "backend.agents.coaching.gateway_client.boto3.client",
                return_value=mock_s3,
            ):
                result = client.execute_code(code, session_id)

        assert custom_bucket in result.get("url", ""), (
            f"Presigned URL should use bucket {custom_bucket!r}, "
            f"got: {result.get('url')!r}"
        )

    @given(
        code=_matplotlib_code,
        session_id=_session_id,
        object_key=_s3_object_key,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_s3_generate_presigned_url_called_with_correct_params(
        self,
        code: str,
        session_id: str,
        object_key: str,
    ) -> None:
        """When generating a presigned URL, the S3 client SHALL be called
        with get_object, the correct bucket, key, and 3600s expiry.

        # Feature: agentcore-platform-integration, Property 13: Code interpreter output URL
        **Validates: Requirements 13.3**
        """
        gateway_response = {
            "output_key": object_key,
            "execution_status": "success",
            "stdout": "",
            "stderr": "",
        }

        client, mock_s3 = _create_client(gateway_response)

        with patch.dict(os.environ, {
            "CODE_INTERPRETER_BUCKET": TEST_BUCKET,
            "AWS_REGION": TEST_REGION,
        }):
            with patch(
                "backend.agents.coaching.gateway_client.boto3.client",
                return_value=mock_s3,
            ):
                client.execute_code(code, session_id)

        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": TEST_BUCKET, "Key": object_key},
            ExpiresIn=3600,
        )
