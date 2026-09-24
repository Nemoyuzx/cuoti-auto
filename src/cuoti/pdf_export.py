from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from jinja2 import Environment, FileSystemLoader, select_autoescape
from .config import Settings
from .models import QuestionRecord, option_label
from .rich_text import code_block_html, normalize_rich_text_spacing, split_rich_text


FORMULA_RE = re.compile(r"\$\$(.+?)\$\$|(?<!\$)\$([^$\n]+?)\$(?!\$)", re.DOTALL)
SOLUTION_TYPE_MARKERS = ("解答", "应用", "计算", "证明", "简答", "论述", "写作", "翻译")
PDF_CHUNK_SIZE = 24


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
    values = [normalize_rich_text_spacing(value) for value in texts]
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
            previous_was_display = False
            for match in FORMULA_RE.finditer(segment.text):
                before = segment.text[cursor:match.start()]
                if previous_was_display:
                    before = before.lstrip("\n")
                is_display = match.group(1) is not None
                if is_display:
                    before = before.rstrip("\n")
                parts.append(html.escape(before).replace("\n", "<br>"))
                parts.append(rendered_formulas[formula_index])
                formula_index += 1
                cursor = match.end()
                previous_was_display = is_display
            tail = segment.text[cursor:]
            if previous_was_display:
                tail = tail.lstrip("\n")
            parts.append(html.escape(tail).replace("\n", "<br>"))
        outputs.append("".join(parts))
    return outputs


def _required_executable(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f"PDF 导出需要 {name}；请运行 ./.venv/bin/cuoti doctor 检查环境。")
    return executable


def _render_chunks(
    prepared: list[dict[str, object]],
    variant: str,
    output: Path,
    settings: Settings,
    template: object,
    katex_css_uri: str,
    generated_at: str,
    progress: Callable[[int, str], None],
) -> None:
    """Render bounded batches in child processes, then merge them in order.

    WeasyPrint otherwise retains the layout graph for every one of hundreds of
    formula-heavy cards at once.  A fresh process per chunk gives the OS a hard
    reclamation boundary and keeps the long-running web server lightweight.
    """
    temp_root = settings.project_root / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    chunk_groups = [
        prepared[index:index + PDF_CHUNK_SIZE]
        for index in range(0, len(prepared), PDF_CHUNK_SIZE)
    ]
    with tempfile.TemporaryDirectory(prefix="cuoti-pdf-chunks-", dir=temp_root) as temp_name:
        temp = Path(temp_name)
        chunk_pdfs: list[Path] = []
        for chunk_index, chunk in enumerate(chunk_groups):
            html_path = temp / f"chunk-{chunk_index:03d}.html"
            pdf_path = temp / f"chunk-{chunk_index:03d}.pdf"
            html_path.write_text(
                template.render(
                    questions=chunk,
                    variant=variant,
                    generated_at=generated_at,
                    katex_css_uri=katex_css_uri,
                    show_header=chunk_index == 0,
                    total_count=len(prepared),
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "cuoti.pdf_worker",
                    str(html_path),
                    str(pdf_path),
                    settings.project_root.as_uri(),
                ],
                text=True,
                capture_output=True,
            )
            if result.returncode:
                detail = result.stderr.strip() or result.stdout.strip() or "未知错误"
                raise RuntimeError(f"PDF 分块 {chunk_index + 1}/{len(chunk_groups)} 渲染失败：{detail}")
            chunk_pdfs.append(pdf_path)
            progress(
                78 + int(18 * (chunk_index + 1) / len(chunk_groups)),
                f"已渲染 {min((chunk_index + 1) * PDF_CHUNK_SIZE, len(prepared))}/{len(prepared)} 题",
            )

        output.unlink(missing_ok=True)
        if len(chunk_pdfs) == 1:
            shutil.copy2(chunk_pdfs[0], output)
        else:
            result = subprocess.run(
                [_required_executable("pdfunite"), *map(str, chunk_pdfs), str(output)],
                text=True,
                capture_output=True,
            )
            if result.returncode:
                detail = result.stderr.strip() or result.stdout.strip() or "未知错误"
                raise RuntimeError(f"PDF 分块合并失败：{detail}")


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
    env.filters["option_label"] = option_label
    template = env.get_template("pdf.html")
    katex_css = settings.project_root / "node_modules" / "katex" / "dist" / "katex.min.css"
    if not katex_css.exists():
        raise RuntimeError("缺少 KaTeX。请先运行 ./scripts/setup.sh（它会执行 npm install）。")
    progress(78, "页面组装完成，正在分块写入 PDF")
    _render_chunks(
        prepared,
        variant,
        output,
        settings,
        template,
        katex_css.resolve().as_uri(),
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        progress,
    )
    progress(98, "PDF 已生成，正在完成校验")
    return output
