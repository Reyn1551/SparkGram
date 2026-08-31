"""
Stateful Stack HTML Balancer and Safe Chunker for Telegram Bot API.
Ensures zero entity parsing errors (400 Bad Request: Can't find end tag) during streaming.
"""
import re
import html
from typing import List, Tuple, Set

# Valid Telegram HTML tags (opening and closing)
TELEGRAM_VALID_TAGS: Set[str] = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "span", "tg-spoiler", "a", "code", "pre", "blockquote", "expandable_quote"
}

# Regex to match any HTML tag
TAG_REGEX = re.compile(r"<(/)?([a-zA-Z0-9_-]+)(?:\s+[^>]*)?>")


class HTMLTagBalancer:
    """Tracks and balances open HTML tags across streaming message chunks."""

    @staticmethod
    def get_unclosed_tags(text: str) -> List[Tuple[str, str]]:
        """
        Parses text and returns a list of (tag_name, full_open_tag) for tags that are opened but not closed.
        Example: '<b>hello <code>world' -> [('b', '<b>'), ('code', '<code>')]
        """
        tag_stack: List[Tuple[str, str]] = []
        for match in TAG_REGEX.finditer(text):
            is_closing = bool(match.group(1))
            tag_name = match.group(2).lower()
            full_tag = match.group(0)

            if tag_name not in TELEGRAM_VALID_TAGS and not full_tag.startswith(("<a ", "<code ", "<span ")):
                continue

            if not is_closing:
                tag_stack.append((tag_name, full_tag))
            else:
                # Find matching opening tag from end of stack
                for i in range(len(tag_stack) - 1, -1, -1):
                    if tag_stack[i][0] == tag_name:
                        tag_stack.pop(i)
                        break
        return tag_stack

    @classmethod
    def balance_html_chunk(cls, chunk: str) -> str:
        """Appends closing tags for any unclosed tags in chunk."""
        unclosed = cls.get_unclosed_tags(chunk)
        if not unclosed:
            return chunk
        # Close in reverse order
        closing_tags = "".join(f"</{tag_name}>" for tag_name, _ in reversed(unclosed))
        return chunk + closing_tags

    @classmethod
    def split_into_safe_chunks(cls, full_html: str, max_chars: int = 3800) -> List[str]:
        """Splits full HTML into valid, self-contained, balanced chunks under max_chars."""
        if not full_html:
            return []
        if len(full_html) <= max_chars:
            return [cls.balance_html_chunk(full_html)]

        chunks: List[str] = []
        remaining = full_html
        inherited_open_tags: List[Tuple[str, str]] = []

        while remaining:
            # Re-open tags from previous chunk if any
            prefix = "".join(full_tag for _, full_tag in inherited_open_tags)
            available_length = max_chars - len(prefix) - 50  # Leave safety margin for closing tags
            
            if len(remaining) <= available_length:
                final_chunk = prefix + remaining
                chunks.append(cls.balance_html_chunk(final_chunk))
                break

            # Find best split boundary (paragraph \n\n, newline \n, or space)
            cut_idx = available_length
            best_cut = remaining.rfind("\n\n", 0, cut_idx)
            if best_cut == -1 or best_cut < cut_idx // 2:
                best_cut = remaining.rfind("\n", 0, cut_idx)
            if best_cut == -1 or best_cut < cut_idx // 2:
                best_cut = remaining.rfind(" ", 0, cut_idx)
            if best_cut != -1 and best_cut > cut_idx // 3:
                cut_idx = best_cut

            current_segment = remaining[:cut_idx]
            combined_segment = prefix + current_segment

            # Calculate open tags that need to be carried over
            inherited_open_tags = cls.get_unclosed_tags(combined_segment)
            balanced_chunk = cls.balance_html_chunk(combined_segment)
            chunks.append(balanced_chunk)

            remaining = remaining[cut_idx:].lstrip()

        return chunks

    @staticmethod
    def strip_html_tags(text: str) -> str:
        """Fallback helper to strip all HTML tags to pure plain text."""
        clean = TAG_REGEX.sub("", text)
        return html.unescape(clean)
