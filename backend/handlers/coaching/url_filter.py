"""Streaming markdown-link validator for coaching agent text output.

Nova Lite, even with strict prompt guidance, is prone to inventing URLs
when summarizing web_search results (saw two consecutive prod smoke-test
failures with hallucinated TechCrunch and LinkedIn URLs). This module
implements deterministic server-side stripping: any markdown link whose
URL is not in the allow-list built from actual web_search results gets
reduced to plain text.

Usage::

    allowed_urls: set[str] = set()
    filt = UrlFilter(send_fn=send_ws, allowed_urls=allowed_urls)

    # ... on AfterToolCallEvent for web_search, add real URLs to the set.
    allowed_urls.update(real_urls_from_tool_result)

    # ... in stream callback, feed deltas through the filter.
    filt.write(delta_text)

    # ... at end of stream.
    filt.flush()

The filter is "buffered pass-through": text is emitted immediately when
no partial link is being assembled. When it sees `[`, it buffers until
the link pattern completes (or is disproven), then validates and emits.

Markdown is flexible but we only target the one pattern the agent
actually uses: `[label](url)`. Labels may not contain `]`; URLs may not
contain `)` — the common Nova Lite output form. We are intentionally
conservative: anything we can't confidently parse as a link passes
through unchanged.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Set

_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")

_MAX_BUFFER = 4096
"""Safety cap: if a buffered `[` never completes within this many chars,
flush the buffer as plain text rather than leaking it at end-of-stream."""


class UrlFilter:
    """Stream-safe markdown link validator.

    Routes text to `send_fn` as `{"type": "delta", "text": str}`, the same
    envelope stream_callback already uses, so this is a drop-in wrapper.
    """

    def __init__(self, send_fn: Callable[[dict], Any], allowed_urls: Set[str]) -> None:
        self._send = send_fn
        self._allowed = allowed_urls
        self._buffer = ""
        self._output_parts: list[str] = []

    @property
    def filtered_output(self) -> str:
        """Full filtered text emitted so far (for the `done` payload)."""
        return "".join(self._output_parts)

    def write(self, chunk: str) -> None:
        """Feed the next streaming chunk through the filter."""
        if not chunk:
            return
        self._buffer += chunk
        self._drain()

    def flush(self) -> None:
        """Emit any trailing buffered text at end of stream."""
        if self._buffer:
            self._emit(self._buffer)
            self._buffer = ""

    # --- internal ---

    def _drain(self) -> None:
        """Emit everything that's no longer ambiguous.

        We walk the buffer, emitting safe prefixes until we hit either a
        complete `[label](url)` pattern (validate + emit) or an incomplete
        one (stop and wait for more chunks).
        """
        while self._buffer:
            idx = self._buffer.find("[")
            if idx == -1:
                # No pending link. Whole buffer is safe to emit.
                self._emit(self._buffer)
                self._buffer = ""
                return

            if idx > 0:
                # Plain text before the '[' is safe.
                self._emit(self._buffer[:idx])
                self._buffer = self._buffer[idx:]

            # Buffer now starts with '['. Try to match a complete link.
            m = _LINK_RE.match(self._buffer)
            if m:
                label, url = m.group(1), m.group(2)
                if self._is_allowed(url):
                    self._emit(m.group(0))
                else:
                    # Invented URL — drop the link, keep the label.
                    self._emit(f"[{label}]" if label else "")
                self._buffer = self._buffer[m.end():]
                continue

            # Not yet a complete link. Two cases:
            #  (a) It's actually just bracketed text like "[note]" with no
            #      '(' after ']' — once we see ']' + non-'(', emit as-is.
            #  (b) We're mid-link, waiting for more chunks.
            close = self._buffer.find("]")
            if close != -1 and close + 1 < len(self._buffer) and self._buffer[close + 1] != "(":
                # Case (a): bracketed non-link text. Emit through ']'.
                self._emit(self._buffer[: close + 1])
                self._buffer = self._buffer[close + 1:]
                continue

            # Case (b) or overflow: bail out of safety cap.
            if len(self._buffer) > _MAX_BUFFER:
                self._emit(self._buffer)
                self._buffer = ""
            return

    def _is_allowed(self, url: str) -> bool:
        """URL must appear verbatim in the allow-list.

        Callers populate the set from actual `results[].url` values. We
        compare strict equality because Nova Lite tends to invent plausible
        variants (trailing-slash, different path); we don't want to match
        those.
        """
        return url in self._allowed

    def _emit(self, text: str) -> None:
        if text:
            self._output_parts.append(text)
            self._send({"type": "delta", "text": text})
