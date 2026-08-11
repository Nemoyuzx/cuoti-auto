from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from .config import SUBJECTS, SUBJECT_SLUGS, Settings, ensure_directories
from .db import SubjectStore, initialize_all, list_all, natural_text_sort_key
from .export_jobs import export_job_output, get_export_job, start_export_job
from .ingest import ingest_path
from .pdf_export import export_pdf
from .rich_text import render_web_rich_text
from .taxonomy import data_structure_choices, politics_choices


settings = Settings.load()
ensure_directories(settings)
initialize_all(settings)

PACKAGE_ROOT = Path(__file__).parent
templates = Environment(
    loader=FileSystemLoader(PACKAGE_ROOT / "templates"),
    autoescape=select_autoescape(["html"]),
)
templates.filters["richtext"] = lambda value: Markup(render_web_rich_text(value or ""))

app = FastAPI(title="错题_auto", version="0.1.0")
app.mount("/static", StaticFiles(directory=PACKAGE_ROOT / "static"), name="static")
katex_dist = settings.project_root / "node_modules" / "katex" / "dist"
if katex_dist.exists():
    app.mount("/vendor/katex", StaticFiles(directory=katex_dist), name="katex")


def render(name: str, request: Request, **context: object) -> HTMLResponse:
    # 模板与 Python 模块在开发热重载时可能短暂处于不同版本；可选上下文必须有安全默认值。
    context.setdefault("taxonomy_choices", {"chapters": [], "sections": [], "points": []})
    context.setdefault("review_confidence", "")
    context.setdefault("review_query", "")
    template = templates.get_template(name)
    return HTMLResponse(template.render(
        request=request, subjects=SUBJECTS, subject_slugs=SUBJECT_SLUGS, **context,
    ))


@app.post("/api/render-preview")
async def render_preview(request: Request) -> JSONResponse:
    """用正式网页渲染器生成编辑区预览，避免预览与最终展示规则分叉。"""
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(400, "预览数据必须是 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(400, "预览数据格式错误")

    kind = payload.get("kind", "richtext")
    value = payload.get("value", "")
    if kind not in {"richtext", "options"} or not isinstance(value, str):
        raise HTTPException(400, "预览字段格式错误")

    if kind == "options":
        options = [line.strip() for line in value.splitlines() if line.strip()]
        rendered = "".join(
            f"<span>{render_web_rich_text(option)}</span>" for option in options
        )
    else:
        rendered = render_web_rich_text(value)
    return JSONResponse({"html": rendered})


@app.get("/")
def home(request: Request, subject: str = "") -> RedirectResponse:
    selected = subject if subject in SUBJECTS else "408"
    params = {key: value for key, value in request.query_params.items() if key != "subject"}
    suffix = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(f"/subject/{SUBJECT_SLUGS[selected]}{suffix}", status_code=303)


@app.get("/subject/{subject_slug}", response_class=HTMLResponse)
def subject_dashboard(
    request: Request,
    subject_slug: str,
    chapter: str = "",
    section: str = "",
    status: str = "",
    confidence: str = "",
    q: str = "",
) -> HTMLResponse:
    subject_by_slug = {slug: name for name, slug in SUBJECT_SLUGS.items()}
    subject = subject_by_slug.get(subject_slug)
    if subject is None:
        raise HTTPException(404)
    filters = {
        "subject": subject, "chapter": chapter, "section": section,
        "status": status, "confidence": confidence, "q": q,
    }
    questions = list_all(filters, settings)
    all_items = list_all({"subject": subject}, settings)
    facets = {
        "chapters": sorted({item.chapter for item in all_items}, key=natural_text_sort_key),
        "sections": sorted({item.section for item in all_items}, key=natural_text_sort_key),
        "statuses": sorted({item.status for item in all_items}),
    }
    stats = {
        "total": len(all_items),
        "visible": len(questions),
        "review": sum(item.status == "待复核" for item in all_items),
        "low_confidence": sum(
            item.status == "待复核" and item.confidence < 0.75 for item in all_items
        ),
    }
    subject_counts = {name: len(SubjectStore(name, settings).list()) for name in SUBJECTS}
    review_params = {
        key: value for key, value in filters.items()
        if key in {"subject", "chapter", "section", "confidence", "q"} and value
    }
    review_url = "/review" + (f"?{urlencode(review_params)}" if review_params else "")
    low_review_url = f"/review?{urlencode({'subject': subject, 'confidence': 'low'})}"
    return render(
        "dashboard.html", request, questions=questions, filters=filters,
        facets=facets, stats=stats, review_url=review_url, low_review_url=low_review_url,
        active_subject=subject, subject_slug=subject_slug, subject_counts=subject_counts,
    )


@app.get("/review")
def review_start(
    subject: str = "",
    chapter: str = "",
    section: str = "",
    confidence: str = "",
    q: str = "",
) -> RedirectResponse:
    filters = {
        "subject": subject, "chapter": chapter, "section": section,
        "status": "待复核", "confidence": confidence, "q": q,
    }
    questions = list_all(filters, settings)
    if not questions:
        selected = subject if subject in SUBJECTS else "408"
        params = {"status": "待复核", "reviewed": "all"}
        if confidence:
            params["confidence"] = confidence
        return RedirectResponse(
            f"/subject/{SUBJECT_SLUGS[selected]}?{urlencode(params)}", status_code=303,
        )
    first = questions[0]
    suffix = f"?{urlencode({'confidence': confidence})}" if confidence else ""
    return RedirectResponse(f"/review/{first.subject}/{first.id}{suffix}", status_code=303)


@app.get("/review/{subject}/{question_id}", response_class=HTMLResponse)
def question_review(
    request: Request, subject: str, question_id: int, confidence: str = "",
) -> HTMLResponse:
    if subject not in SUBJECTS:
        raise HTTPException(404)
    store = SubjectStore(subject, settings)
    question = store.get(question_id)
    if question is None:
        raise HTTPException(404)
    pending = store.list({"status": "待复核", "confidence": confidence})
    pending_ids = [item.id for item in pending]
    if question_id not in pending_ids:
        pending.insert(0, question)
        pending_ids.insert(0, question_id)
    index = pending_ids.index(question_id)
    previous_question = pending[index - 1] if index > 0 else None
    next_question = pending[index + 1] if index + 1 < len(pending) else None
    if subject == "408":
        taxonomy_choices = data_structure_choices()
    elif subject == "政治":
        taxonomy_choices = politics_choices()
    else:
        taxonomy_choices = {"chapters": [], "sections": [], "points": []}
    return render(
        "review.html", request, question=question,
        previous_question=previous_question, next_question=next_question,
        remaining=sum(item.status == "待复核" for item in pending),
        review_confidence=confidence,
        review_query=f"?{urlencode({'confidence': confidence})}" if confidence else "",
        taxonomy_choices=taxonomy_choices,
    )


@app.get("/question/{subject}/{question_id}", response_class=HTMLResponse)
def question_detail(request: Request, subject: str, question_id: int) -> HTMLResponse:
    if subject not in SUBJECTS:
        raise HTTPException(404)
    question = SubjectStore(subject, settings).get(question_id)
    if question is None:
        raise HTTPException(404)
    return render("detail.html", request, question=question)


@app.post("/question/{subject}/{question_id}")
def question_update(
    subject: str,
    question_id: int,
    chapter: str = Form(...),
    section: str = Form(...),
    question_type: str = Form("未知题型"),
    question_text: str = Form(...),
    options: str = Form(""),
    wrong_answer: str = Form(""),
    correct_answer: str = Form(""),
    analysis: str = Form(""),
    error_reason: str = Form(""),
    knowledge_points: str = Form(""),
    difficulty: int = Form(3),
    confidence: float | None = Form(default=None),
    status: str = Form("待复核"),
    practice_images: list[str] = Form(default=[]),
    submit_action: str = Form("save"),
    review_mode: str = Form(""),
    review_confidence: str = Form(""),
    next_id: int | None = Form(default=None),
) -> RedirectResponse:
    if subject not in SUBJECTS:
        raise HTTPException(404)
    store = SubjectStore(subject, settings)
    resolved_status = "已复核" if submit_action == "confirm_next" else status
    updates = {
        "chapter": chapter.strip() or "待确认",
        "section": section.strip() or "待确认",
        "question_type": question_type.strip() or "未知题型",
        "question_text": question_text.strip(),
        "options": [line.strip() for line in options.splitlines() if line.strip()],
        "wrong_answer": wrong_answer.strip(),
        "correct_answer": correct_answer.strip(),
        "analysis": analysis.strip(),
        "error_reason": error_reason.strip(),
        "knowledge_points": [item.strip() for item in knowledge_points.replace("，", ",").split(",") if item.strip()],
        "difficulty": max(1, min(5, difficulty)),
        "status": resolved_status,
    }
    if confidence is not None:
        updates["confidence"] = max(0.0, min(1.0, confidence))
    store.update(question_id, updates)
    store.set_practice_images(question_id, practice_images)
    if review_mode:
        review_suffix = f"&confidence={review_confidence}" if review_confidence else ""
        next_suffix = f"?confidence={review_confidence}" if review_confidence else ""
        if submit_action == "confirm_next" and next_id is not None:
            separator = "&" if next_suffix else "?"
            return RedirectResponse(
                f"/review/{subject}/{next_id}{next_suffix}{separator}confirmed={question_id}",
                status_code=303,
            )
        if submit_action == "confirm_next":
            return RedirectResponse(
                f"/review?subject={subject}{review_suffix}", status_code=303,
            )
        return RedirectResponse(
            f"/review/{subject}/{question_id}?saved=1{review_suffix}", status_code=303,
        )
    return RedirectResponse(f"/question/{subject}/{question_id}?saved=1", status_code=303)


@app.post("/question/{subject}/{question_id}/delete")
def question_delete(
    subject: str,
    question_id: int,
    next_id: int | None = Form(default=None),
    previous_id: int | None = Form(default=None),
    review_confidence: str = Form(""),
) -> RedirectResponse:
    if subject not in SUBJECTS:
        raise HTTPException(404)
    store = SubjectStore(subject, settings)
    if store.delete(question_id) is None:
        raise HTTPException(404, "错题不存在")

    for candidate_id in (next_id, previous_id):
        if candidate_id is not None and store.get(candidate_id) is not None:
            suffix = f"&confidence={review_confidence}" if review_confidence else ""
            return RedirectResponse(
                f"/review/{subject}/{candidate_id}?deleted={question_id}{suffix}", status_code=303,
            )
    return RedirectResponse(
        f"/subject/{SUBJECT_SLUGS[subject]}?deleted={question_id}", status_code=303,
    )


@app.post("/import")
def upload_import(
    files: list[UploadFile] = File(...),
    provider: str = Form("tesseract"),
) -> RedirectResponse:
    saved: list[tuple[str, int]] = []
    with tempfile.TemporaryDirectory(prefix="cuoti-upload-") as temp:
        for upload in files:
            target = Path(temp) / Path(upload.filename or "upload.jpg").name
            with target.open("wb") as stream:
                shutil.copyfileobj(upload.file, stream)
            saved.extend(ingest_path(target, provider, settings))
    subject = saved[0][0] if saved else "408"
    return RedirectResponse(f"/subject/{SUBJECT_SLUGS[subject]}?imported=1", status_code=303)


@app.get("/media/{subject}/{relative_path:path}")
def media(subject: str, relative_path: str) -> FileResponse:
    if subject not in SUBJECTS:
        raise HTTPException(404)
    root = settings.subject_root(subject).resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


@app.get("/export")
def pdf_download(
    variant: str = Query("practice", pattern="^(practice|notebook)$"),
    subject: str = "",
    chapter: str = "",
    section: str = "",
    status: str = "",
    confidence: str = "",
    q: str = "",
) -> FileResponse:
    questions = list_all({
        "subject": subject, "chapter": chapter, "section": section,
        "status": status, "confidence": confidence, "q": q,
    }, settings)
    try:
        path = export_pdf(questions, variant, settings=settings)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return FileResponse(path, filename=path.name, media_type="application/pdf")


@app.post("/api/exports")
def pdf_export_start(
    variant: str = Form(...),
    subject: str = Form(...),
    chapter: str = Form(""),
    section: str = Form(""),
    status: str = Form(""),
    confidence: str = Form(""),
    q: str = Form(""),
) -> JSONResponse:
    if subject not in SUBJECTS:
        raise HTTPException(400, "科目无效")
    questions = list_all(
        {
            "subject": subject, "chapter": chapter, "section": section,
            "status": status, "confidence": confidence, "q": q,
        },
        settings,
    )
    try:
        job = start_export_job(questions, variant, subject, settings)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return JSONResponse(job.public(), status_code=202)


@app.get("/api/exports/{job_id}")
def pdf_export_status(job_id: str) -> JSONResponse:
    job = get_export_job(job_id)
    if job is None:
        raise HTTPException(404, "导出任务不存在或已过期")
    return JSONResponse(job.public())


@app.get("/api/exports/{job_id}/download")
def pdf_export_download(job_id: str) -> FileResponse:
    job = get_export_job(job_id)
    path = export_job_output(job_id)
    if job is None:
        raise HTTPException(404, "导出任务不存在")
    if path is None:
        raise HTTPException(409, "PDF 尚未完成")
    return FileResponse(path, filename=job.filename, media_type="application/pdf")
