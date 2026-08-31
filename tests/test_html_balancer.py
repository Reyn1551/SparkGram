"""
Unit Tests for Stateful Stack HTML Balancer and Safe Chunker.
"""
import pytest
from sparkgram.formatters.html_balancer import HTMLTagBalancer


def test_balance_unclosed_single_tag():
    raw = "<b>Hello world"
    balanced = HTMLTagBalancer.balance_html_chunk(raw)
    assert balanced == "<b>Hello world</b>"


def test_balance_unclosed_nested_tags():
    raw = "<blockquote><b><code>def test():"
    balanced = HTMLTagBalancer.balance_html_chunk(raw)
    assert balanced == "<blockquote><b><code>def test():</code></b></blockquote>"


def test_balance_already_closed_tags():
    raw = "<b>Bold</b> and <i>Italic</i>"
    balanced = HTMLTagBalancer.balance_html_chunk(raw)
    assert balanced == "<b>Bold</b> and <i>Italic</i>"


def test_split_into_safe_chunks_small():
    raw = "<b>Hello</b> world"
    chunks = HTMLTagBalancer.split_into_safe_chunks(raw, max_chars=100)
    assert len(chunks) == 1
    assert chunks[0] == "<b>Hello</b> world"


def test_split_into_safe_chunks_multipage():
    # Long text with bold tag across split
    raw = "<b>" + ("Lorem ipsum dolor sit amet. \n\n" * 50) + "</b>"
    chunks = HTMLTagBalancer.split_into_safe_chunks(raw, max_chars=500)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 600
        # Verify each chunk is self-contained with no unclosed tags
        unclosed = HTMLTagBalancer.get_unclosed_tags(chunk)
        assert len(unclosed) == 0


def test_strip_html_tags():
    raw = "<b>Bold</b> & <code>Code</code>"
    plain = HTMLTagBalancer.strip_html_tags(raw)
    assert plain == "Bold & Code"
