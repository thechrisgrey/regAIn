"""Shared async Nova Sonic bidirectional streaming client.

Encapsulates the event-based protocol for Amazon Nova 2 Sonic,
providing a clean callback-based interface for voice handlers.
Uses the experimental aws_sdk_bedrock_runtime Python SDK.

Both the coaching voice handler and voice practice handler use
this module instead of duplicating the complex event logic.
"""

import asyncio
import inspect
import json
import logging
import os
import threading
import uuid
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = "amazon.nova-2-sonic-v1:0"
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
VOICE_ID = "matthew"

# Module-level event loop running in a daemon thread.
# Lambda WebSocket connections are sticky to instances, so this
# loop persists across invocations for the same instance.
_event_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_thread: Optional[threading.Thread] = None
_loop_lock = threading.Lock()


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    """Get or create the module-level asyncio event loop.

    Creates a daemon thread running asyncio.run_forever() if one
    does not already exist. Safe to call from any thread.

    Returns:
        The shared asyncio event loop.
    """
    global _event_loop, _loop_thread
    with _loop_lock:
        if _event_loop is not None and _event_loop.is_running():
            return _event_loop

        _event_loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(
            target=_event_loop.run_forever,
            daemon=True,
        )
        _loop_thread.start()
        return _event_loop


def run_async(coro, timeout: float = 30.0):
    """Schedule a coroutine on the shared event loop and block until done.

    Args:
        coro: An awaitable coroutine.
        timeout: Maximum seconds to wait for the result.

    Returns:
        The coroutine's return value.
    """
    loop = ensure_event_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def build_tool_specs(
    tool_functions: list,
    exclude_params: Optional[set[str]] = None,
) -> list[dict]:
    """Build Nova Sonic toolSpec entries from tool function signatures.

    Inspects each function's signature and docstring to generate a
    properly formatted toolSpec with inputSchema for Nova Sonic.

    Args:
        tool_functions: List of @tool decorated functions.
        exclude_params: Parameter names to exclude from the schema
            (default: {"user_id"} since it's injected by the handler).

    Returns:
        List of toolSpec dicts ready for the promptStart toolConfiguration.
    """
    exclude = exclude_params or {"user_id"}
    specs = []

    for func in tool_functions:
        name = getattr(func, "__name__", str(func))
        doc = getattr(func, "__doc__", "") or ""
        description = doc.split("\n")[0].strip() or name

        # Get the real signature, handling wrapped decorators.
        try:
            sig = inspect.signature(func)
        except (ValueError, TypeError):
            wrapped = getattr(func, "__wrapped__", func)
            sig = inspect.signature(wrapped)

        properties: dict[str, dict] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name in exclude:
                continue

            prop: dict[str, Any] = {"description": f"The {param_name} parameter"}
            annotation = param.annotation

            if annotation != inspect.Parameter.empty:
                origin = getattr(annotation, "__origin__", None)
                if annotation is str:
                    prop["type"] = "string"
                elif annotation is int:
                    prop["type"] = "integer"
                elif annotation is float:
                    prop["type"] = "number"
                elif annotation is bool:
                    prop["type"] = "boolean"
                elif annotation is list or origin is list:
                    prop["type"] = "array"
                elif annotation is dict or origin is dict:
                    prop["type"] = "object"
                else:
                    prop["type"] = "string"
            else:
                prop["type"] = "string"

            properties[param_name] = prop

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        specs.append({
            "toolSpec": {
                "name": name,
                "description": description,
                "inputSchema": {
                    "json": json.dumps({
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    })
                },
            }
        })

    return specs


class NovaSonicSession:
    """Manages a single Nova Sonic bidirectional streaming session.

    Handles the full event protocol: session initialization, audio
    streaming, tool use, and response processing via callbacks.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        region: Optional[str] = None,
    ):
        self.model_id = model_id or os.environ.get(
            "NOVA_SONIC_MODEL_ID", DEFAULT_MODEL_ID
        )
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.is_active = False
        self.prompt_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())

        # Callbacks set during start().
        self._on_audio: Optional[Callable[[str], None]] = None
        self._on_transcript: Optional[Callable[[str, str], None]] = None
        self._on_tool_use: Optional[Callable[[str, str, dict], Any]] = None
        self._on_state: Optional[Callable[[str], None]] = None

        # Internal stream state.
        self._stream: Any = None
        self._response_task: Optional[asyncio.Task] = None
        self._current_role = ""
        self._is_speculative = False
        self._tool_use_content: dict = {}
        self._tool_name = ""
        self._tool_use_id = ""

    async def start(
        self,
        system_prompt: str,
        on_audio: Callable[[str], None],
        on_transcript: Callable[[str, str], None],
        tool_specs: Optional[list[dict]] = None,
        on_tool_use: Optional[Callable[[str, str, dict], Any]] = None,
        on_state: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Initialize the Nova Sonic stream and begin processing.

        Sends sessionStart, promptStart, system prompt, and opens the
        audio input channel. Launches a background task to read responses.

        Args:
            system_prompt: System instructions for the AI.
            on_audio: Callback(base64_audio) for audio output chunks.
            on_transcript: Callback(role, text) for ASR and assistant text.
            tool_specs: List of toolSpec dicts from build_tool_specs().
                Empty or None to disable tools.
            on_tool_use: Callback(tool_name, tool_use_id, args_dict) -> result.
                Required if tool_specs is non-empty.
            on_state: Optional callback(state_str) for state changes
                ("speaking", "listening", "interrupted").
        """
        from aws_sdk_bedrock_runtime.client import (
            BedrockRuntimeClient,
            InvokeModelWithBidirectionalStreamOperationInput,
        )
        from aws_sdk_bedrock_runtime.config import (
            Config,
            HTTPAuthSchemeResolver,
            SigV4AuthScheme,
        )
        from smithy_aws_core.identity import EnvironmentCredentialsResolver

        self._on_audio = on_audio
        self._on_transcript = on_transcript
        self._on_tool_use = on_tool_use
        self._on_state = on_state

        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
            auth_scheme_resolver=HTTPAuthSchemeResolver(),
            auth_schemes={
                "aws.auth#sigv4": SigV4AuthScheme(service="bedrock")
            },
        )
        client = BedrockRuntimeClient(config=config)

        self._stream = await client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(
                model_id=self.model_id
            )
        )
        self.is_active = True

        # Send the initialization sequence.
        await self._send_session_start()
        await self._send_prompt_start(tool_specs or [])
        await self._send_system_prompt(system_prompt)
        await self._start_audio_input()

        # Start processing responses in the background.
        self._response_task = asyncio.create_task(self._process_responses())

    async def send_audio(self, audio_base64: str) -> None:
        """Send a chunk of audio to Nova Sonic.

        Args:
            audio_base64: Base64-encoded PCM 16-bit mono 16kHz audio.
        """
        if not self.is_active or not self._stream:
            return

        event = json.dumps({
            "event": {
                "audioInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "content": audio_base64,
                }
            }
        })
        await self._send_raw_event(event)

    async def send_tool_result(
        self, tool_use_id: str, result: Any
    ) -> None:
        """Send a tool execution result back to Nova Sonic.

        Follows the protocol: contentStart(TOOL) -> toolResult -> contentEnd.

        Args:
            tool_use_id: The toolUseId from the original toolUse event.
            result: Tool result (will be JSON-serialized if dict/list).
        """
        content_name = str(uuid.uuid4())

        # contentStart (TOOL)
        await self._send_raw_event(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "interactive": False,
                    "type": "TOOL",
                    "role": "TOOL",
                    "toolResultInputConfiguration": {
                        "toolUseId": tool_use_id,
                        "type": "TEXT",
                        "textInputConfiguration": {
                            "mediaType": "text/plain",
                        },
                    },
                }
            }
        }))

        # toolResult
        result_str = (
            json.dumps(result) if isinstance(result, (dict, list)) else str(result)
        )
        await self._send_raw_event(json.dumps({
            "event": {
                "toolResult": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "content": result_str,
                }
            }
        }))

        # contentEnd
        await self._send_raw_event(json.dumps({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                }
            }
        }))

    async def close(self) -> None:
        """Gracefully close the Nova Sonic session.

        Sends contentEnd (audio), promptEnd, sessionEnd, then closes
        the input stream and cancels the response processing task.
        """
        if not self.is_active:
            return

        self.is_active = False

        if self._stream:
            try:
                # Close audio input content.
                await self._send_raw_event(json.dumps({
                    "event": {
                        "contentEnd": {
                            "promptName": self.prompt_name,
                            "contentName": self.audio_content_name,
                        }
                    }
                }))
                # Prompt end.
                await self._send_raw_event(json.dumps({
                    "event": {
                        "promptEnd": {
                            "promptName": self.prompt_name,
                        }
                    }
                }))
                # Session end.
                await self._send_raw_event(json.dumps({
                    "event": {
                        "sessionEnd": {}
                    }
                }))
            except Exception:
                logger.warning("Error sending session close events")

            try:
                await self._stream.input_stream.close()
            except Exception:
                logger.warning("Error closing Nova Sonic input stream")

        if self._response_task and not self._response_task.done():
            self._response_task.cancel()
            try:
                await self._response_task
            except (asyncio.CancelledError, Exception):
                pass

    # ------------------------------------------------------------------
    # Internal: event sending
    # ------------------------------------------------------------------

    async def _send_raw_event(self, event_json: str) -> None:
        """Send a raw JSON event string to the stream."""
        from aws_sdk_bedrock_runtime.models import (
            BidirectionalInputPayloadPart,
            InvokeModelWithBidirectionalStreamInputChunk,
        )

        if not self._stream or not self.is_active:
            return

        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(
                bytes_=event_json.encode("utf-8")
            )
        )
        await self._stream.input_stream.send(chunk)

    async def _send_session_start(self) -> None:
        await self._send_raw_event(json.dumps({
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.7,
                    },
                }
            }
        }))

    async def _send_prompt_start(self, tool_specs: list[dict]) -> None:
        prompt_start: dict = {
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "textOutputConfiguration": {
                        "mediaType": "text/plain",
                    },
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": OUTPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": VOICE_ID,
                        "encoding": "base64",
                        "audioType": "SPEECH",
                    },
                }
            }
        }

        if tool_specs:
            prompt_start["event"]["promptStart"]["toolUseOutputConfiguration"] = {
                "mediaType": "application/json",
            }
            prompt_start["event"]["promptStart"]["toolConfiguration"] = {
                "tools": tool_specs,
            }

        await self._send_raw_event(json.dumps(prompt_start))

    async def _send_system_prompt(self, system_prompt: str) -> None:
        content_name = str(uuid.uuid4())

        # contentStart (SYSTEM TEXT)
        await self._send_raw_event(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "type": "TEXT",
                    "interactive": False,
                    "role": "SYSTEM",
                    "textInputConfiguration": {
                        "mediaType": "text/plain",
                    },
                }
            }
        }))

        # textInput
        await self._send_raw_event(json.dumps({
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "content": system_prompt,
                }
            }
        }))

        # contentEnd
        await self._send_raw_event(json.dumps({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                }
            }
        }))

    async def _start_audio_input(self) -> None:
        """Open the audio input content block for user speech."""
        await self._send_raw_event(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": INPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "audioType": "SPEECH",
                        "encoding": "base64",
                    },
                }
            }
        }))

    # ------------------------------------------------------------------
    # Internal: response processing
    # ------------------------------------------------------------------

    async def _process_responses(self) -> None:
        """Read output events from the stream and dispatch to callbacks."""
        while self.is_active:
            try:
                output = await self._stream.await_output()
                result = await output[1].receive()
                if not result.value or not result.value.bytes_:
                    continue

                response_data = result.value.bytes_.decode("utf-8")
                json_data = json.loads(response_data)

                if "event" not in json_data:
                    continue

                event = json_data["event"]

                if "contentStart" in event:
                    self._handle_content_start(event["contentStart"])
                elif "textOutput" in event:
                    self._handle_text_output(event["textOutput"])
                elif "audioOutput" in event:
                    self._handle_audio_output(event["audioOutput"])
                elif "toolUse" in event:
                    self._handle_tool_use_event(event["toolUse"])
                elif "contentEnd" in event:
                    content_end = event["contentEnd"]
                    stop_reason = content_end.get("stopReason", "")
                    if content_end.get("type") == "TOOL":
                        await self._execute_tool()
                    elif stop_reason == "END_TURN":
                        if self._on_state:
                            self._on_state("listening")
                elif "completionEnd" in event:
                    logger.info("Nova Sonic completion ended")

            except StopAsyncIteration:
                logger.info("Nova Sonic stream ended")
                break
            except asyncio.CancelledError:
                break
            except Exception:
                if self.is_active:
                    logger.exception("Error processing Nova Sonic response")
                break

    def _handle_content_start(self, data: dict) -> None:
        self._current_role = data.get("role", "")

        additional = data.get("additionalModelFields", "")
        if additional:
            try:
                fields = (
                    json.loads(additional)
                    if isinstance(additional, str)
                    else additional
                )
                self._is_speculative = (
                    fields.get("generationStage") == "SPECULATIVE"
                )
            except (json.JSONDecodeError, AttributeError):
                self._is_speculative = False
        else:
            self._is_speculative = False

        # USER contentStart during playback = barge-in.
        # Fire "interrupted" so handler sends clear_audio to the browser.
        if self._current_role == "USER" and self._on_state:
            self._on_state("interrupted")

    def _handle_text_output(self, data: dict) -> None:
        content = data.get("content", "")
        if not content:
            return

        # Barge-in interrupt signal.
        stripped = content.strip()
        if '"interrupted"' in stripped and "true" in stripped:
            if self._on_state:
                self._on_state("interrupted")
            return

        if self._current_role == "USER":
            if self._on_transcript:
                self._on_transcript("user", content)
        elif self._current_role == "ASSISTANT" and self._is_speculative:
            # SPECULATIVE generation stage for ASSISTANT = text preview
            # of what is being spoken. This IS the assistant transcript.
            if self._on_transcript:
                self._on_transcript("assistant", content)
            if self._on_state:
                self._on_state("speaking")

    def _handle_audio_output(self, data: dict) -> None:
        content = data.get("content", "")
        if content and self._on_audio:
            self._on_audio(content)

    def _handle_tool_use_event(self, data: dict) -> None:
        self._tool_use_content = data
        self._tool_name = data.get("toolName", "")
        self._tool_use_id = data.get("toolUseId", "")

    async def _execute_tool(self) -> None:
        """Execute a tool and send the result back to Nova Sonic."""
        if not self._tool_name or not self._on_tool_use:
            return

        tool_name = self._tool_name
        tool_use_id = self._tool_use_id
        tool_content = self._tool_use_content

        # Reset state before execution.
        self._tool_name = ""
        self._tool_use_id = ""
        self._tool_use_content = {}

        try:
            content_str = tool_content.get("content", "{}")
            args = (
                json.loads(content_str)
                if isinstance(content_str, str)
                else content_str
            )

            # Run the sync tool function in an executor to avoid
            # blocking the event loop during DynamoDB calls.
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: self._on_tool_use(tool_name, tool_use_id, args)
            )

            await self.send_tool_result(tool_use_id, result)
        except Exception:
            logger.exception("Tool execution failed for %s", tool_name)
            await self.send_tool_result(
                tool_use_id,
                {"error": f"Tool {tool_name} execution failed"},
            )
