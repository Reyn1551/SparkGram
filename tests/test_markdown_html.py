"""
Unit Tests for Markdown to Telegram HTML Converter.
"""
import pytest
from sparkgram.formatters.markdown_html import (
    escape_html_text,
    md_to_telegram_html,
    split_markdown_into_html_chunks,
)


def test_escape_html_text():
    assert escape_html_text("a < b & c > d") == "a &lt; b &amp; c &gt; d"


def test_md_to_telegram_html_basic():
    md = "# Title\n\n**bold** and *italic* and `code`"
    out = md_to_telegram_html(md)
    assert "<b>Title</b>" in out
    assert "<b>bold</b>" in out
    assert "<i>italic</i>" in out
    assert "<code>code</code>" in out


def test_md_to_telegram_html_code_block():
    md = "```python\ndef hello():\n    print('Hello <world> & all')\n```"
    out = md_to_telegram_html(md)
    assert '<pre><code class="language-python">' in out
    assert "&lt;world&gt; &amp; all" in out
    assert "</code></pre>" in out


def test_md_to_telegram_html_expandable_blockquote():
    md = "> line 1\n> line 2"
    out = md_to_telegram_html(md, enable_expandable_blockquotes=True)
    assert "<blockquote expandable>" in out
    assert "line 1\nline 2" in out
    assert "</blockquote>" in out


def test_split_markdown_into_html_chunks():
    md = "# Header\n\n" + ("Paragraph text with **bold** and `code`.\n\n" * 40)
    chunks = split_markdown_into_html_chunks(md, header_html="🚀 <b>Status</b>", max_chars=1000)
    assert len(chunks) >= 2
    assert "🚀 <b>Status</b>" in chunks[0]
    for chunk in chunks:
        assert len(chunk) <= 1200
