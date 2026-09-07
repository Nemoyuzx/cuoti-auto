from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .config import SUBJECTS
from .rich_text import normalize_rich_text_spacing


OPTION_PREFIX_RE = re.compile(
    r"^\s*(?:[（(]\s*(?P<wrapped>[A-Z])\s*[)）]|(?P<plain>[A-Z])\s*[.．、:：)）])\s*",
    re.IGNORECASE,
)
CORRECT_ANSWER_OPTION_RE = re.compile(
    r"^\s*[（(]\s*(?P<label>[A-Z])\s*[)）](?=\s|$)",
    re.IGNORECASE,
)
ERROR_REASON_CLAUSE_SEPARATOR_RE = re.compile(r"[；;]\s*")
GENERIC_ERROR_REASON_CLAUSES = {
    "题号被圈或答案被红笔订正，需要对照标准解析复盘原解中的具体错误",
    "题号被红笔圈出或答案被红笔订正，需要对照标准解析复盘具体错误",
    "题号被圈或页面有明显订正痕迹",
    "需回看原图核对原答",
    "未独立完成，需要按标准解析补全方法和运算过程",
    "典型题，方法具有代表性，建议整理后再次独立完成",
}
WRONG_ANSWER_UNKNOWN_VALUES = {
    "",
    "待确认（见原图红笔答案或订正）",
    "待确认（见原图中的原答案与红笔订正）",
    "原作答见图（红笔订正）",
    "未作答",
    "无（不会）",
    "无（不会做）",
    "不会做",
    "有思路但计算错误（具体过程见原图红笔批注）",
    "未完成；有思路但计算未得到结果",
    "思路错误",
}


def option_label(index: int) -> str:
    """生成 A、B、…、Z、AA 形式的稳定选项标签。"""
    if index < 0:
        raise ValueError("选项序号不能为负数")
    label = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def normalize_options(values: list[str]) -> list[str]:
    """数据库只保存选项正文，并保留空项所代表的原始选项位置。"""
    normalized: list[str] = []
    for index, raw_value in enumerate(values):
        value = normalize_rich_text_spacing(str(raw_value)).strip()
        match = OPTION_PREFIX_RE.match(value)
        prefix = (match.group("wrapped") or match.group("plain")) if match else ""
        if match and prefix.upper() == option_label(index):
            value = value[match.end():].strip()
        normalized.append(value)
    return normalized


def normalize_correct_answer(value: object) -> str:
    """正确答案开头的选择题字母不保留括号，公式内部括号不受影响。"""
    normalized = normalize_rich_text_spacing("" if value is None else str(value)).strip()
    match = CORRECT_ANSWER_OPTION_RE.match(normalized)
    if not match:
        return normalized
    return f"{match.group('label').upper()}{normalized[match.end():]}"


CORRECT_ANSWER_PLACEHOLDERS = {
    "见解析", "见标准解析", "待确认", "标准解析待人工核对（见已关联解析图）",
}


def normalize_error_reason(value: object) -> str:
    """只保留有具体作答证据的错因，清除由圈题或订正状态推断的占位话术。"""
    normalized = normalize_rich_text_spacing("" if value is None else str(value)).strip()
    clauses = ERROR_REASON_CLAUSE_SEPARATOR_RE.split(normalized)
    kept = [
        clause.strip()
        for clause in clauses
        if clause.strip() and clause.strip().rstrip("。.!！") not in GENERIC_ERROR_REASON_CLAUSES
    ]
    return "；".join(kept)


def normalize_wrong_answer(value: object) -> str:
    """空白、只有红笔答案或旧版待确认占位统一记录为“不会”。"""
    normalized = normalize_rich_text_spacing("" if value is None else str(value)).strip()
    return "不会" if normalized in WRONG_ANSWER_UNKNOWN_VALUES else normalized


def parse_options_text(value: str) -> list[str]:
    """解析人工编辑文本；忽略装饰性空行，显式 ``A.`` 空项仍保留位置。"""
    lines = [line for line in value.splitlines() if line.strip()]
    return normalize_options(lines)


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

    @field_validator(
        "question_text", "analysis",
        mode="before",
    )
    @classmethod
    def normalize_text_spacing(cls, value: object) -> str:
        return normalize_rich_text_spacing("" if value is None else str(value)).strip()

    @field_validator("correct_answer", mode="before")
    @classmethod
    def correct_answer_stores_plain_option_label(cls, value: object) -> str:
        normalized = normalize_correct_answer(value)
        if normalized in CORRECT_ANSWER_PLACEHOLDERS:
            raise ValueError("正确答案必须填写明确结果，不能使用指向解析或图片的占位文本")
        return normalized

    @field_validator("error_reason", mode="before")
    @classmethod
    def error_reason_requires_specific_evidence(cls, value: object) -> str:
        return normalize_error_reason(value)

    @field_validator("wrong_answer", mode="before")
    @classmethod
    def wrong_answer_uses_cannot_solve_marker(cls, value: object) -> str:
        return normalize_wrong_answer(value)

    @field_validator("question_text")
    @classmethod
    def question_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("题目文本不能为空")
        return value

    @field_validator("options")
    @classmethod
    def options_store_bodies_only(cls, value: list[str]) -> list[str]:
        return normalize_options(value)


class ExtractionBatch(BaseModel):
    questions: list[ExtractedQuestion]
    page_notes: str = ""


class QuestionRecord(ExtractedQuestion):
    id: int
    source_hash: str
    source_file: str
    image_paths: list[str] = Field(default_factory=list)
    question_image_paths: list[str] = Field(default_factory=list)
    solution_image_paths: list[str] = Field(default_factory=list)
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
