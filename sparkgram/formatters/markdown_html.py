"""
Markdown to Telegram HTML Converter for SparkGram.
Transforms standard markdown, diffs, thinking blocks, and tables into clean,
highly aesthetic Telegram HTML entities optimized for mobile & desktop readability.
"""
import re
import html
from typing import List, Optional

from .html_balancer import HTMLTagBalancer


def escape_html_text(text: str) -> str:
    """Escapes special characters &, <, > for Telegram HTML mode."""
    if not text:
        return ""
    return html.escape(str(text), quote=False)


def md_to_telegram_html(md: str, enable_expandable_blockquotes: bool = True) -> str:
    """Converts standard Markdown into aesthetically formatted Telegram HTML."""
    if not md:
        return ""

    bq_tag_open = "<blockquote expandable>" if enable_expandable_blockquotes else "<blockquote>"

    # 1. Format <thinking> ... </thinking> blocks into expandable reasoning cards
    def thinking_replacer(match):
        inner = match.group(1).strip()
        escaped_inner = html.escape(inner, quote=False)
        return f"{bq_tag_open}\n💭 <b>Reasoning Trace:</b>\n{escaped_inner}\n</blockquote>"

    text = re.sub(r"<thinking>([\s\S]*?)</thinking>", thinking_replacer, md, flags=re.IGNORECASE)

    # 2. Protect and beautify code blocks with language indicators
    code_blocks: List[str] = []

    def code_block_replacer(match):
        lang = (match.group(1) or "").strip().lower()
        code_content = match.group(2)
        escaped_code = html.escape(code_content)
        
        # If language is diff or patch, wrap cleanly
        if lang in ("diff", "patch") or code_content.startswith(("diff --git", "--- a/", "+++ b/")):
            tag = f'<pre><code class="language-diff">{escaped_code}</code></pre>'
        elif lang:
            tag = f'<pre><code class="language-{html.escape(lang)}">{escaped_code}</code></pre>'
        else:
            tag = f"<pre><code>{escaped_code}</code></pre>"
            
        code_blocks.append(tag)
        return f"\x00CB{len(code_blocks)-1}\x00"

    # Match ```lang\ncode\n```
    text = re.sub(r"```([a-zA-Z0-9_-]*)\n?([\s\S]*?)```", code_block_replacer, text)

    # 3. Protect inline code `...`
    inline_codes: List[str] = []

    def inline_code_replacer(match):
        code_content = match.group(1)
        escaped_code = html.escape(code_content)
        inline_codes.append(f"<code>{escaped_code}</code>")
        return f"\x00IC{len(inline_codes)-1}\x00"

    text = re.sub(r"`([^`\n]+)`", inline_code_replacer, text)

    # 4. Blockquotes before escaping: > text -> blockquote placeholder
    blockquotes: List[str] = []

    def blockquote_replacer(match):
        bq_lines = match.group(0).splitlines()
        cleaned_lines = [re.sub(r"^>\s?", "", line) for line in bq_lines]
        inner_text = "\n".join(cleaned_lines)
        escaped_inner = html.escape(inner_text, quote=False)
        tag = f"{bq_tag_open}\n{escaped_inner}\n</blockquote>"
        blockquotes.append(tag)
        return f"\x00BQ{len(blockquotes)-1}\x00"

    text = re.sub(r"(?:^>[^\n]*\n?)+", blockquote_replacer, text, flags=re.MULTILINE)

    # 5. Escape remaining HTML in text
    text = html.escape(text, quote=False)

    # 6. Headers: # Header -> ✨ <b>Header</b>
    def header_replacer(match):
        level = len(match.group(1))
        content = match.group(2).strip()
        icon = "✨ " if level <= 2 else "🔹 "
        return f"\n{icon}<b>{content}</b>\n"

    text = re.sub(r"^(#{1,6})\s+(.+)$", header_replacer, text, flags=re.MULTILINE)

    # 7. Unordered Lists: * item / - item -> • item
    text = re.sub(r"^[ \t]*[-*+]\s+(.+)$", r"• \1", text, flags=re.MULTILINE)

    # 8. Bold: **text** or __text__ -> <b>text</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\b__(.+?)__\b", r"<b>\1</b>", text)

    # 9. Italic: *text* or _text_ -> <i>text</i>
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", text)

    # 10. Strikethrough: ~~text~~ -> <s>text</s>
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # 11. Links: [text](url) -> <a href="url">text</a>
    def link_replacer(match):
        link_text = match.group(1)
        link_url = match.group(2)
        return f'<a href="{html.escape(link_url)}">{link_text}</a>'

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", link_replacer, text)

    # 12. Restore blockquotes
    for idx, bq_tag in enumerate(blockquotes):
        text = text.replace(f"\x00BQ{idx}\x00", bq_tag)

    # 13. Restore inline code
    for idx, code_tag in enumerate(inline_codes):
        text = text.replace(f"\x00IC{idx}\x00", code_tag)

    # 14. Restore code blocks
    for idx, block_tag in enumerate(code_blocks):
        text = text.replace(f"\x00CB{idx}\x00", block_tag)

    # 15. Normalize excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return text


def split_markdown_into_html_chunks(md: str, header_html: str = "", max_chars: int = 3800) -> List[str]:
    """Converts Markdown to balanced Telegram HTML chunks under max_chars limit."""
    full_html = md_to_telegram_html(md)
    if header_html:
        full_html = f"{header_html}\n\n{full_html}"
    return HTMLTagBalancer.split_into_safe_chunks(full_html, max_chars=max_chars)
