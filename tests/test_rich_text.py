from cuoti.rich_text import normalize_rich_text_spacing, render_web_rich_text


def test_web_rich_text_escapes_html_and_renders_fenced_code():
    rendered = render_web_rich_text(
        "解析<script>alert(1)</script>\n```c\nif (a < b && c > d) return;\n```"
    )

    assert "<script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert '<pre><code class="language-c">' in rendered
    assert "if (a &lt; b &amp;&amp; c &gt; d) return;" in rendered


def test_web_rich_text_renders_windows_newline_fenced_code():
    rendered = render_web_rich_text(
        "17 求时间复杂度：\r\n```c\r\nint sum=0;\r\nsum++;\r\n```"
    )

    assert '<pre><code class="language-c">' in rendered
    assert "int sum=0;\nsum++;" in rendered
    assert "```" not in rendered


def test_web_rich_text_keeps_multiline_display_math_contiguous_for_katex():
    rendered = render_web_rich_text(
        "先求梯度：\n$$\n\\nabla f=(2x, y)\n$$\n所以成立。"
    )

    assert '<div class="display-math">$$\\nabla f=(2x, y)$$</div>' in rendered
    assert "$$<br>" not in rendered
    assert "<br>$$" not in rendered


def test_display_math_has_no_surrounding_blank_lines_or_break_tags():
    source = "先说明。\n\n$$\nx^2+y^2=1\n$$\n\n继续说明。"

    normalized = normalize_rich_text_spacing(source)
    rendered = render_web_rich_text(source)

    assert normalized == "先说明。\n$$\nx^2+y^2=1\n$$\n继续说明。"
    assert "<br><div class=\"display-math\">" not in rendered
    assert "</div><br>" not in rendered
    assert rendered == '先说明。<div class="display-math">$$x^2+y^2=1$$</div>继续说明。'


def test_display_math_spacing_normalizer_preserves_fenced_code():
    source = "正文\n\n$$x$$\n\n```text\n上\n\n$$not-math$$\n\n下\n```"

    normalized = normalize_rich_text_spacing(source)

    assert normalized.startswith("正文\n$$x$$\n```text")
    assert "上\n\n$$not-math$$\n\n下" in normalized
