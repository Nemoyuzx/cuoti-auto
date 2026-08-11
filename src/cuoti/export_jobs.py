from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from .config import Settings
from .models import QuestionRecord
from .pdf_export import export_pdf


@dataclass
class ExportJob:
    id: str
    variant: str
    subject: str
    state: str = "queued"
    progress: int = 0
    message: str = "等待导出"
    filename: str = ""
    output_path: str = ""
    error: str = ""
    created_at: str = ""
    updated_at: str = ""

    def public(self) -> dict[str, object]:
        data = asdict(self)
        data.pop("output_path")
        data["download_url"] = f"/api/exports/{self.id}/download" if self.state == "ready" else ""
        data["variant_label"] = "纯题重做版" if self.variant == "practice" else "完整错题本"
        return data


_jobs: dict[str, ExportJob] = {}
_lock = Lock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cuoti-pdf")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _update(job_id: str, **fields: object) -> None:
    with _lock:
        job = _jobs[job_id]
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = _now()


def _run_job(job_id: str, questions: list[QuestionRecord], settings: Settings) -> None:
    def report(progress: int, message: str) -> None:
        _update(job_id, state="running", progress=max(1, min(99, progress)), message=message)

    try:
        _update(job_id, state="running", progress=2, message="正在准备题目")
        job = get_export_job(job_id)
        if job is None:
            return
        output = export_pdf(
            questions, job.variant, settings=settings, progress_callback=report,
        )
        _update(
            job_id, state="ready", progress=100, message="导出完成",
            filename=output.name, output_path=str(output),
        )
    except Exception as error:
        _update(job_id, state="error", message="导出失败", error=str(error))


def start_export_job(
    questions: list[QuestionRecord],
    variant: str,
    subject: str,
    settings: Settings,
) -> ExportJob:
    if variant not in {"practice", "notebook"}:
        raise ValueError("PDF 类型必须是 practice 或 notebook")
    if not questions:
        raise ValueError("当前筛选条件下没有可导出的错题")
    now = _now()
    job = ExportJob(
        id=uuid4().hex, variant=variant, subject=subject,
        created_at=now, updated_at=now,
    )
    with _lock:
        _jobs[job.id] = job
        if len(_jobs) > 100:
            oldest = sorted(_jobs.values(), key=lambda item: item.created_at)[:20]
            for item in oldest:
                if item.state in {"ready", "error"}:
                    _jobs.pop(item.id, None)
    _executor.submit(_run_job, job.id, list(questions), settings)
    return job


def get_export_job(job_id: str) -> ExportJob | None:
    with _lock:
        job = _jobs.get(job_id)
        return ExportJob(**asdict(job)) if job else None


def export_job_output(job_id: str) -> Path | None:
    job = get_export_job(job_id)
    if job is None or job.state != "ready" or not job.output_path:
        return None
    path = Path(job.output_path)
    return path if path.is_file() else None
