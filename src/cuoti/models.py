from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .config import SUBJECTS


class ExtractedQuestion(BaseModel):
    subject: Literal["数学", "英语", "408", "政治"]
    chapter: str = "待确认"
    section: str = "待确认"
    question_type: str = "未知题型"
    question_text: str
    options: list[str] = Field(default_factory=list)
    wrong_answer: str = ""
    correct_answer: str = ""
    analysis: str = ""
    error_reason: str = ""
    knowledge_points: list[str] = Field(default_factory=list)
    difficulty: int = Field(default=3, ge=1, le=5)
    confidence: float = Field(default=0.5, ge=0, le=1)
    needs_review: bool = True
    source_page: int = Field(default=1, ge=1)

    @field_validator("question_text")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("题目文本不能为空")
        return value


class ExtractionBatch(BaseModel):
    questions: list[ExtractedQuestion]
    page_notes: str = ""


class QuestionRecord(ExtractedQuestion):
    id: int
    source_hash: str
    source_file: str
    image_paths: list[str] = Field(default_factory=list)
    practice_image_paths: list[str] = Field(default_factory=list)
    status: str = "待复核"
    created_at: str
    updated_at: str


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalized_subject(value: str) -> str:
    if value not in SUBJECTS:
        raise ValueError(f"科目必须是 {', '.join(SUBJECTS)} 之一")
    return value
