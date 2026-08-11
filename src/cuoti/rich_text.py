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


def split_rich_text(value: str) -> list[RichSegment]:
    """拆分 Markdown 三反引号代码块；其余内容交给公式渲染器。"""
    normalized = (value or "").replace("\r\n", "\n").replace("\r", "\n")
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
        rendered.append(html.escape(value[cursor:match.start()]).replace("\n", "<br>"))
        math = html.escape(match.group("math").strip())
        rendered.append(f'<div class="display-math">$${math}$$</div>')
        cursor = match.end()
    rendered.append(html.escape(value[cursor:]).replace("\n", "<br>"))
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
