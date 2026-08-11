from cuoti.rich_text import render_web_rich_text


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
