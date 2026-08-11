from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from jinja2 import Environment, FileSystemLoader, select_autoescape
from .config import Settings
from .models import QuestionRecord
from .rich_text import code_block_html, split_rich_text


FORMULA_RE = re.compile(r"\$\$(.+?)\$\$|(?<!\$)\$([^$\n]+?)\$(?!\$)", re.DOTALL)
SOLUTION_TYPE_MARKERS = ("解答", "应用", "计算", "证明", "简答", "论述", "写作", "翻译")


def pdf_image_paths(question: QuestionRecord, variant: str) -> list[str]:
    """Only explicitly approved clean figures may enter the practice PDF.

    The notebook variant is intentionally text-only so photographed pages with
    corrections or answers can never leak back into the exported notebook.
    """
    return list(question.practice_image_paths) if variant == "practice" else []


def is_solution_question(question: QuestionRecord) -> bool:
    """长解答类题在 PDF 中独占一整列。"""
    return any(marker in question.question_type for marker in SOLUTION_TYPE_MARKERS)


def _node_executable() -> str:
    executable = shutil.which("node")
    if not executable:
        raise RuntimeError("PDF 公式渲染需要 Node.js；请运行 ./scripts/setup.sh 检查环境。")
    return executable


def render_rich_many(texts: Iterable[str], settings: Settings) -> list[str]:
    values = list(texts)
    matches: list[re.Match[str]] = []
    for value in values:
        for segment in split_rich_text(value or ""):
            if segment.kind == "text":
                matches.extend(FORMULA_RE.finditer(segment.text))
    rendered_formulas: list[str] = []
    if matches:
        payload = {
            "formulas": [
                {"tex": (match.group(1) or match.group(2)).strip(), "display": bool(match.group(1))}
                for match in matches
            ]
        }
        script = settings.project_root / "scripts" / "katex_batch.mjs"
        result = subprocess.run(
            [_node_executable(), str(script)], input=json.dumps(payload), text=True,
            capture_output=True, check=True, cwd=settings.project_root,
        )
        rendered_formulas = json.loads(result.stdout)["rendered"]

    formula_index = 0
    outputs: list[str] = []
    for value in values:
        parts: list[str] = []
        for segment in split_rich_text(value or ""):
            if segment.kind == "code":
                parts.append(code_block_html(segment.text, segment.language))
                continue
            cursor = 0
            for match in FORMULA_RE.finditer(segment.text):
                parts.append(html.escape(segment.text[cursor:match.start()]).replace("\n", "<br>"))
                parts.append(rendered_formulas[formula_index])
                formula_index += 1
                cursor = match.end()
            parts.append(html.escape(segment.text[cursor:]).replace("\n", "<br>"))
        outputs.append("".join(parts))
    return outputs


def export_pdf(
    questions: list[QuestionRecord],
    variant: str,
    output: Path | None = None,
    settings: Settings | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
) -> Path:
    def progress(value: int, message: str) -> None:
        if progress_callback:
            progress_callback(value, message)

    # WeasyPrint 在 Apple Silicon Homebrew 上需要显式看到 Pango 动态库。
    # 放在函数内惰性导入，确保 OCR、建库和 Web 启动不被可选 PDF 环境阻塞。
    if sys.platform == "darwin" and Path("/opt/homebrew/lib").exists():
        fallback = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
        paths = [item for item in fallback.split(":") if item]
        if "/opt/homebrew/lib" not in paths:
            os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(["/opt/homebrew/lib", *paths])
    from weasyprint import HTML

    if variant not in {"practice", "notebook"}:
        raise ValueError("PDF 类型必须是 practice 或 notebook")
    if not questions:
        raise ValueError("当前筛选条件下没有可导出的错题")
    settings = settings or Settings.load()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = output or settings.pdf_output / f"错题_{'纯题重做版' if variant == 'practice' else '完整错题本版'}_{stamp}.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    progress(8, "正在整理题目与公式")

    text_fields: list[str] = []
    for q in questions:
        text_fields.extend([q.question_text, *q.options, q.wrong_answer, q.correct_answer, q.analysis, q.error_reason])
    rich_values = iter(render_rich_many(text_fields, settings))
    progress(35, "公式渲染完成，正在组装页面")
    prepared = []
    for index, q in enumerate(questions, start=1):
        prepared.append({
            "record": q,
            "is_solution": is_solution_question(q),
            "question": next(rich_values),
            "options": [next(rich_values) for _ in q.options],
            "wrong_answer": next(rich_values),
            "correct_answer": next(rich_values),
            "analysis": next(rich_values),
            "error_reason": next(rich_values),
            "images": [
                (settings.subject_root(q.subject) / path).resolve().as_uri()
                for path in pdf_image_paths(q, variant)
            ],
        })
        progress(35 + int(35 * index / len(questions)), f"正在排版第 {index}/{len(questions)} 题")

    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=select_autoescape(["html"]))
    template = env.get_template("pdf.html")
    katex_css = settings.project_root / "node_modules" / "katex" / "dist" / "katex.min.css"
    if not katex_css.exists():
        raise RuntimeError("缺少 KaTeX。请先运行 ./scripts/setup.sh（它会执行 npm install）。")
    html_text = template.render(
        questions=prepared,
        variant=variant,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        katex_css_uri=katex_css.resolve().as_uri(),
    )
    progress(78, "页面组装完成，正在写入 PDF")
    HTML(string=html_text, base_url=settings.project_root.as_uri()).write_pdf(output)
    progress(98, "PDF 已生成，正在完成校验")
    return output
