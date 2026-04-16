"""Stream-safe URL validation for coaching agent output.

The coaching agent's Nova Lite model hallucinates URLs when citing
web_search results (observed twice in prod smoke tests before this
was added). UrlFilter is the deterministic guard: it buffers just
enough to detect complete `[label](url)` patterns, then validates
URLs against the allow-list populated from actual Tavily results.

These tests cover: happy path (allowed URL passes), strip path
(invented URL reduced to label), streaming boundaries (links split
across chunks), and non-link bracketed text (must pass through).
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from backend.handlers.coaching.url_filter import UrlFilter


class _Sink:
    """Collect outbound messages for assertion.

    UrlFilter calls send_fn with `{"type": "delta", "text": ...}`
    envelopes; we reassemble the text stream here.
    """

    def __init__(self) -> None:
        self.messages: List[Dict[str, Any]] = []

    def __call__(self, msg: Dict[str, Any]) -> None:
        self.messages.append(msg)

    @property
    def text(self) -> str:
        return "".join(m.get("text", "") for m in self.messages if m.get("type") == "delta")


def _run(chunks: List[str], allowed: Set[str]) -> str:
    sink = _Sink()
    filt = UrlFilter(send_fn=sink, allowed_urls=allowed)
    for c in chunks:
        filt.write(c)
    filt.flush()
    return sink.text


class TestUrlFilter:
    def test_plain_text_passes_through_unchanged(self) -> None:
        result = _run(["hello ", "world"], allowed=set())
        assert result == "hello world"

    def test_allowed_url_link_emitted_as_is(self) -> None:
        allowed = {"https://example.com/real"}
        result = _run(
            ["See ", "[the article](https://example.com/real)", " for details."],
            allowed=allowed,
        )
        assert result == "See [the article](https://example.com/real) for details."

    def test_disallowed_url_link_reduced_to_label(self) -> None:
        # Nova Lite invented techcrunch.com — not in Tavily's results.
        allowed = {"https://example.com/real"}
        result = _run(
            ["See ", "[TechCrunch](https://techcrunch.com/fake-url)", " for details."],
            allowed=allowed,
        )
        assert result == "See [TechCrunch] for details."

    def test_link_split_across_chunks(self) -> None:
        """Boundaries should not leak an invalid URL.

        The model streams tokens; a single markdown link may span
        multiple callback invocations. The filter must buffer until
        it sees the complete pattern before deciding.
        """
        allowed: Set[str] = set()
        result = _run(
            ["See [Tech", "Crunch](https://tech", "crunch.com/fake)", " end."],
            allowed=allowed,
        )
        assert result == "See [TechCrunch] end."

    def test_multiple_links_mixed(self) -> None:
        allowed = {"https://good.example.com/a"}
        result = _run(
            [
                "First [good one](https://good.example.com/a), ",
                "then [bad one](https://bad.example.com/x).",
            ],
            allowed=allowed,
        )
        assert result == "First [good one](https://good.example.com/a), then [bad one]."

    def test_bracketed_non_link_text_passes_through(self) -> None:
        """Text like `[note]` or `[1]` is not a link and must not be stripped."""
        result = _run(["See [note] and [1] here."], allowed=set())
        assert result == "See [note] and [1] here."

    def test_empty_url_set_strips_all_links(self) -> None:
        # Before any web_search runs, allow-set is empty. Every link is
        # hallucinated by definition — strip them all.
        result = _run(["check [anywhere](https://anywhere.example.com)"], allowed=set())
        assert result == "check [anywhere]"

    def test_trailing_open_bracket_flushed_on_flush(self) -> None:
        """An unmatched '[' at end-of-stream must not be silently dropped."""
        result = _run(["text ending with [", "unclosed"], allowed=set())
        # We flush remaining buffer as-is.
        assert result == "text ending with [unclosed"

    def test_url_strict_equality_not_prefix_match(self) -> None:
        """A variant URL (trailing slash, different path) must NOT be allowed.

        Nova Lite often invents plausible variants — we require exact match
        to the Tavily-returned URL.
        """
        allowed = {"https://example.com/article"}
        # Trailing slash variant — strip.
        result = _run(["[A](https://example.com/article/)"], allowed=allowed)
        assert result == "[A]"
        # Exact match — pass.
        result2 = _run(["[B](https://example.com/article)"], allowed=allowed)
        assert result2 == "[B](https://example.com/article)"

    def test_flush_emits_trailing_plain_text(self) -> None:
        sink = _Sink()
        filt = UrlFilter(send_fn=sink, allowed_urls=set())
        filt.write("hello")
        # Before flush: already emitted (no pending '[').
        assert sink.text == "hello"
        filt.flush()
        # Flush is idempotent on empty buffer.
        assert sink.text == "hello"

    def test_allowed_urls_set_mutation_is_observed(self) -> None:
        """The filter holds a reference to the set; updates take effect.

        This is how stream_handler wires it: the set is populated from
        web_search results via AfterToolCallEvent, then deltas arrive
        after the model has digested the tool output.
        """
        sink = _Sink()
        allowed: Set[str] = set()
        filt = UrlFilter(send_fn=sink, allowed_urls=allowed)

        # First write with empty allow-set: URL stripped.
        filt.write("[a](https://example.com/1) ")
        assert sink.text == "[a] "

        # Now simulate web_search having populated the set.
        allowed.add("https://example.com/2")
        filt.write("[b](https://example.com/2)")
        filt.flush()
        assert sink.text == "[a] [b](https://example.com/2)"
