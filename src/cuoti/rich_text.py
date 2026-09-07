from __future__ import annotations

import html
import re
from dataclasses import dataclass


FENCED_CODE_RE = re.compile(
    r"^```(?P<language>[A-Za-z0-9_+-]*)[ \t]*\n(?P<code>.*?)^```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
DISPLAY_MATH_RE = re.compile(r"\$\$(?P<math>.*?)\$\$", re.DOTALL)


@dataclass(frozen=True)
class RichSegment:
    kind: str
    text: str
    language: str = ""


def _normalize_text_display_math_spacing(value: str) -> str:
    """Collapse blank lines immediately outside display math delimiters."""
    matches = list(DISPLAY_MATH_RE.finditer(value))
    if not matches:
        return value

    parts: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        gap = value[cursor:match.start()]
        if index:
            gap = re.sub(r"^[ \t]*\n(?:[ \t]*\n)+", "\n", gap)
        gap = re.sub(r"\n(?:[ \t]*\n)+[ \t]*$", "\n", gap)
        parts.extend([gap, match.group(0)])
        cursor = match.end()

    tail = value[cursor:]
    tail = re.sub(r"^[ \t]*\n(?:[ \t]*\n)+", "\n", tail)
    parts.append(tail)
    return "".join(parts)


def normalize_rich_text_spacing(value: str) -> str:
    """Normalize display-math spacing without touching fenced code blocks.

    Stored Markdown keeps exactly one line break around a standalone formula;
    decorative empty lines are removed. Code samples remain byte-for-byte
    equivalent apart from normalizing platform newline characters.
    """
    normalized = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    parts: list[str] = []
    cursor = 0
    for match in FENCED_CODE_RE.finditer(normalized):
        parts.append(_normalize_text_display_math_spacing(normalized[cursor:match.start()]))
        parts.append(match.group(0))
        cursor = match.end()
    parts.append(_normalize_text_display_math_spacing(normalized[cursor:]))
    return "".join(parts)


def split_rich_text(value: str) -> list[RichSegment]:
    """拆分 Markdown 三反引号代码块；其余内容交给公式渲染器。"""
    normalized = normalize_rich_text_spacing(value)
    segments: list[RichSegment] = []
    cursor = 0
    for match in FENCED_CODE_RE.finditer(normalized):
        if match.start() > cursor:
            segments.append(RichSegment("text", normalized[cursor:match.start()]))
        segments.append(RichSegment("code", match.group("code"), match.group("language")))
        cursor = match.end()
    if cursor < len(normalized):
        segments.append(RichSegment("text", normalized[cursor:]))
    return segments or [RichSegment("text", normalized)]


def code_block_html(code: str, language: str = "") -> str:
    safe_language = re.sub(r"[^A-Za-z0-9_+-]", "", language)
    class_name = f' class="language-{safe_language}"' if safe_language else ""
    return f"<pre><code{class_name}>{html.escape(code.rstrip())}</code></pre>"


def text_with_display_math_html(value: str) -> str:
    """转义普通文本，同时保持跨行公式为一个连续文本节点供 KaTeX 处理。"""
    rendered: list[str] = []
    cursor = 0
    for match in DISPLAY_MATH_RE.finditer(value):
        before = value[cursor:match.start()].rstrip("\n")
        rendered.append(html.escape(before).replace("\n", "<br>"))
        math = html.escape(match.group("math").strip())
        rendered.append(f'<div class="display-math">$${math}$$</div>')
        cursor = match.end()
    rendered.append(html.escape(value[cursor:].lstrip("\n")).replace("\n", "<br>"))
    return "".join(rendered)


def render_web_rich_text(value: str) -> str:
    """安全渲染网页文本：正文全部转义，仅将围栏内容变为代码块。"""
    rendered: list[str] = []
    for segment in split_rich_text(value):
        if segment.kind == "code":
            rendered.append(code_block_html(segment.text, segment.language))
        else:
            rendered.append(text_with_display_math_html(segment.text))
    return "".join(rendered)
