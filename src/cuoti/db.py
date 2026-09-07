from __future__ import annotations

import json
import re
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .config import SUBJECTS, Settings, ensure_directories
from .models import (
    ExtractedQuestion,
    QuestionRecord,
    normalize_correct_answer,
    normalize_error_reason,
    normalize_options,
    normalize_wrong_answer,
    option_label,
    utc_now,
)
from .rich_text import normalize_rich_text_spacing


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_hash TEXT NOT NULL,
    source_file TEXT NOT NULL,
    subject TEXT NOT NULL,
    chapter TEXT NOT NULL DEFAULT '待确认',
    section TEXT NOT NULL DEFAULT '待确认',
    question_type TEXT NOT NULL DEFAULT '未知题型',
    question_text TEXT NOT NULL,
    options_json TEXT NOT NULL DEFAULT '[]',
    wrong_answer TEXT NOT NULL DEFAULT '',
    correct_answer TEXT NOT NULL DEFAULT '',
    analysis TEXT NOT NULL DEFAULT '',
    error_reason TEXT NOT NULL DEFAULT '',
    knowledge_points_json TEXT NOT NULL DEFAULT '[]',
    difficulty INTEGER NOT NULL DEFAULT 3 CHECK(difficulty BETWEEN 1 AND 5),
    confidence REAL NOT NULL DEFAULT 0.5 CHECK(confidence BETWEEN 0 AND 1),
    status TEXT NOT NULL DEFAULT '待复核',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_hash, question_text)
);
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    original_name TEXT NOT NULL,
    page_index INTEGER NOT NULL DEFAULT 1,
    image_role TEXT NOT NULL DEFAULT 'question' CHECK(image_role IN ('question', 'work', 'solution', 'supplement')),
    include_in_practice INTEGER NOT NULL DEFAULT 0,
    UNIQUE(question_id, relative_path)
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    attempted_at TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    is_correct INTEGER,
    note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_questions_filter ON questions(subject, chapter, section, status);
CREATE INDEX IF NOT EXISTS idx_questions_updated ON questions(updated_at DESC);
"""


# 只把 ASCII 数字当作可转换的自然排序数字。Python 的 ``\d`` 和
# ``str.isdigit`` 也会匹配“①”等 Unicode 数字符号，但 ``int('①')``
# 会抛出 ValueError，导致含圈号的旧题让整个题库页面 500。
_NUMBER_PART = re.compile(r"([0-9]+)")
_UNSORTED_LABELS = {"", "待确认", "未知", "未分类"}
_SUBJECT_ORDER = {subject: index for index, subject in enumerate(SUBJECTS)}


def natural_text_sort_key(value: str) -> tuple[object, ...]:
    """按文本中的阿拉伯数字自然排序，未确认标签始终放在末尾。"""
    normalized = value.strip()
    unknown_rank = 1 if normalized in _UNSORTED_LABELS else 0
    parts = tuple(
        (0, int(part)) if part.isascii() and part.isdigit() else (1, part.casefold())
        for part in _NUMBER_PART.split(normalized)
        if part
    )
    return unknown_rank, parts


def question_sort_key(item: QuestionRecord) -> tuple[object, ...]:
    """全局内容顺序：科目→章→节/板块→题号→入库 ID。"""
    return (
        _SUBJECT_ORDER.get(item.subject, len(SUBJECTS)),
        natural_text_sort_key(item.chapter),
        natural_text_sort_key(item.section),
        natural_text_sort_key(item.question_text),
        item.id,
    )


class SubjectStore:
    def __init__(self, subject: str, settings: Settings | None = None):
        if subject not in SUBJECTS:
            raise ValueError(f"未知科目：{subject}")
        self.subject = subject
        self.settings = settings or Settings.load()
        self.root = self.settings.subject_root(subject)
        self.db_path = self.root / "wrong_questions.sqlite3"

    def initialize(self) -> None:
        ensure_directories(self.settings)
        with self.connection() as conn:
            conn.executescript(SCHEMA)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(images)")}
            if "include_in_practice" not in columns:
                conn.execute("ALTER TABLE images ADD COLUMN include_in_practice INTEGER NOT NULL DEFAULT 0")
            if "image_role" not in columns:
                conn.execute("ALTER TABLE images ADD COLUMN image_role TEXT NOT NULL DEFAULT 'question'")
                # Historical attached pages used a stable filename suffix. Mark
                # them conservatively until the batch-specific migration can
                # distinguish handwritten work from standard solutions.
                conn.execute(
                    "UPDATE images SET image_role='supplement' WHERE relative_path LIKE '%-supplement.%'"
                )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        self.root.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def insert(self, question: ExtractedQuestion, source_hash: str, source_file: str, image_path: str = "") -> int:
        self.initialize()
        now = utc_now()
        status = "待复核" if question.needs_review else "已复核"
        with self.connection() as conn:
            existing = conn.execute(
                "SELECT id FROM questions WHERE source_hash=? AND question_text=?",
                (source_hash, question.question_text),
            ).fetchone()
            if existing:
                return int(existing["id"])
            cursor = conn.execute(
                """INSERT INTO questions (
                    source_hash, source_file, subject, chapter, section, question_type,
                    question_text, options_json, wrong_answer, correct_answer, analysis,
                    error_reason, knowledge_points_json, difficulty, confidence, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source_hash, source_file, self.subject, question.chapter, question.section,
                    question.question_type, question.question_text,
                    json.dumps(question.options, ensure_ascii=False), question.wrong_answer,
                    question.correct_answer, question.analysis, question.error_reason,
                    json.dumps(question.knowledge_points, ensure_ascii=False), question.difficulty,
                    question.confidence, status, now, now,
                ),
            )
            question_id = int(cursor.lastrowid)
            if image_path:
                conn.execute(
                    """INSERT OR IGNORE INTO images(
                           question_id, relative_path, original_name, page_index, image_role
                       ) VALUES (?, ?, ?, ?, 'question')""",
                    (question_id, image_path, Path(source_file).name, question.source_page),
                )
        self.write_markdown(question_id)
        return question_id

    def get(self, question_id: int) -> QuestionRecord | None:
        self.initialize()
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()
            if not row:
                return None
            images, practice_images, question_images, solution_images = self._image_paths(conn, question_id)
        return _row_to_record(row, images, practice_images, question_images, solution_images)

    def list(self, filters: dict[str, str] | None = None) -> list[QuestionRecord]:
        self.initialize()
        filters = filters or {}
        clauses: list[str] = []
        params: list[Any] = []
        for key in ("chapter", "section", "status"):
            if filters.get(key):
                clauses.append(f"q.{key}=?")
                params.append(filters[key])
        confidence_band = filters.get("confidence", "")
        if confidence_band == "low":
            clauses.append("q.confidence < 0.75")
        elif confidence_band == "medium":
            clauses.append("q.confidence >= 0.75 AND q.confidence < 0.9")
        elif confidence_band == "high":
            clauses.append("q.confidence >= 0.9")
        if filters.get("q"):
            clauses.append("(q.question_text LIKE ? OR q.analysis LIKE ? OR q.knowledge_points_json LIKE ?)")
            needle = f"%{filters['q']}%"
            params.extend((needle, needle, needle))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT q.* FROM questions q {where}"
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            result = []
            for row in rows:
                images, practice_images, question_images, solution_images = self._image_paths(conn, row["id"])
                result.append(_row_to_record(row, images, practice_images, question_images, solution_images))
        return sorted(result, key=question_sort_key)

    def update(self, question_id: int, fields: dict[str, Any]) -> None:
        allowed = {
            "chapter", "section", "question_type", "question_text", "wrong_answer",
            "correct_answer", "analysis", "error_reason", "difficulty", "confidence", "status",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        for field in ("question_text", "wrong_answer", "correct_answer", "analysis", "error_reason"):
            if field in updates:
                updates[field] = (
                    normalize_correct_answer(updates[field])
                    if field == "correct_answer"
                    else normalize_wrong_answer(updates[field])
                    if field == "wrong_answer"
                    else normalize_error_reason(updates[field])
                    if field == "error_reason"
                    else normalize_rich_text_spacing(str(updates[field])).strip()
                )
        if "options" in fields:
            updates["options_json"] = json.dumps(normalize_options(fields["options"]), ensure_ascii=False)
        if "knowledge_points" in fields:
            updates["knowledge_points_json"] = json.dumps(fields["knowledge_points"], ensure_ascii=False)
        if not updates:
            return
        updates["updated_at"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in updates)
        with self.connection() as conn:
            conn.execute(f"UPDATE questions SET {assignments} WHERE id=?", [*updates.values(), question_id])
        self.write_markdown(question_id)

    def set_practice_images(self, question_id: int, relative_paths: list[str]) -> None:
        selected = set(relative_paths)
        with self.connection() as conn:
            rows = conn.execute(
                """SELECT relative_path FROM images
                   WHERE question_id=? AND image_role!='solution'""",
                (question_id,),
            ).fetchall()
            allowed = {row["relative_path"] for row in rows}
            conn.execute("UPDATE images SET include_in_practice=0 WHERE question_id=?", (question_id,))
            for relative_path in selected & allowed:
                conn.execute(
                    "UPDATE images SET include_in_practice=1 WHERE question_id=? AND relative_path=?",
                    (question_id, relative_path),
                )

    def add_image(
        self,
        question_id: int,
        relative_path: str,
        original_name: str,
        page_index: int,
        image_role: str = "question",
    ) -> None:
        """Attach a derived review image with an explicit semantic role."""
        if image_role not in {"question", "work", "solution", "supplement"}:
            raise ValueError(f"未知图片类型：{image_role}")
        self.initialize()
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO images(
                       question_id, relative_path, original_name, page_index, image_role, include_in_practice
                   ) VALUES (?, ?, ?, ?, ?, 0)
                   ON CONFLICT(question_id, relative_path) DO UPDATE SET
                       original_name=excluded.original_name,
                       page_index=excluded.page_index,
                       image_role=excluded.image_role""",
                (question_id, relative_path, original_name, page_index, image_role),
            )

    def delete(self, question_id: int) -> Path | None:
        """Remove one mistaken record while keeping a recoverable local backup."""
        self.initialize()
        record = self.get_without_init(question_id)
        if record is None:
            return None

        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
        backup_dir = self.root / "backups" / "deleted_questions"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{stamp}-question-{question_id}.json"
        backup_path.write_text(json.dumps({
            "deleted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "record": record.model_dump(mode="json"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        with self.connection() as conn:
            image_rows = conn.execute(
                "SELECT relative_path FROM images WHERE question_id=?", (question_id,),
            ).fetchall()
            conn.execute("DELETE FROM questions WHERE id=?", (question_id,))
            orphaned = [
                row["relative_path"] for row in image_rows
                if conn.execute(
                    "SELECT 1 FROM images WHERE relative_path=? LIMIT 1", (row["relative_path"],),
                ).fetchone() is None
            ]

        (self.root / "markdown" / f"{question_id:06d}.md").unlink(missing_ok=True)
        asset_backup_dir = self.root / "backups" / "deleted_assets" / stamp
        root = self.root.resolve()
        for relative_path in orphaned:
            asset = (self.root / relative_path).resolve()
            if root not in asset.parents or not asset.is_file():
                continue
            target = asset_backup_dir / Path(relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(asset), target)
        return backup_path

    @staticmethod
    def _image_paths(
        conn: sqlite3.Connection, question_id: int,
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        rows = conn.execute(
            """SELECT relative_path, include_in_practice, image_role
               FROM images WHERE question_id=? ORDER BY page_index, id""",
            (question_id,),
        ).fetchall()
        return (
            [row["relative_path"] for row in rows],
            [row["relative_path"] for row in rows if row["include_in_practice"]],
            [row["relative_path"] for row in rows if row["image_role"] != "solution"],
            [row["relative_path"] for row in rows if row["image_role"] == "solution"],
        )

    def write_markdown(self, question_id: int) -> Path:
        record = self.get_without_init(question_id)
        if record is None:
            raise KeyError(question_id)
        path = self.root / "markdown" / f"{question_id:06d}.md"
        options = "\n".join(
            f"- {option_label(index)}. {item}"
            for index, item in enumerate(record.options) if item
        ) or "（无选项）"
        question_images = "\n".join(
            f"![题目或作答照片](../{item})" for item in record.question_image_paths
        )
        solution_images = "\n".join(
            f"![答案或解析照片](../{item})" for item in record.solution_image_paths
        )
        knowledge = "、".join(record.knowledge_points) or "待补充"
        content = f"""---
id: {record.id}
subject: {record.subject}
chapter: {record.chapter}
section: {record.section}
status: {record.status}
difficulty: {record.difficulty}
confidence: {record.confidence:.2f}
source_hash: {record.source_hash}
updated_at: {record.updated_at}
---

# {record.subject}错题 #{record.id} · {record.created_at[:10]}

## 题目

{record.question_text}

{options}

{question_images}

## 我的错误答案

{record.wrong_answer or '待补充'}

## 正确答案

{record.correct_answer or '待补充'}

## 解析

{record.analysis or '待补充'}

{solution_images}

## 错因与知识点

- 错因：{record.error_reason or '待补充'}
- 知识点：{knowledge}
"""
        path.write_text(content, encoding="utf-8")
        return path

    def get_without_init(self, question_id: int) -> QuestionRecord | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()
            if not row:
                return None
            images, practice_images, question_images, solution_images = self._image_paths(conn, question_id)
        return _row_to_record(row, images, practice_images, question_images, solution_images)


def _row_to_record(
    row: sqlite3.Row,
    images: list[str],
    practice_images: list[str],
    question_images: list[str],
    solution_images: list[str],
) -> QuestionRecord:
    data = dict(row)
    data["options"] = json.loads(data.pop("options_json") or "[]")
    data["knowledge_points"] = json.loads(data.pop("knowledge_points_json") or "[]")
    data["image_paths"] = images
    data["practice_image_paths"] = practice_images
    data["question_image_paths"] = question_images
    data["solution_image_paths"] = solution_images
    data["needs_review"] = data["status"] == "待复核"
    return QuestionRecord.model_validate(data)


def initialize_all(settings: Settings | None = None) -> None:
    settings = settings or Settings.load()
    ensure_directories(settings)
    for subject in SUBJECTS:
        SubjectStore(subject, settings).initialize()


def list_all(filters: dict[str, str] | None = None, settings: Settings | None = None) -> list[QuestionRecord]:
    settings = settings or Settings.load()
    filters = filters or {}
    selected = [filters["subject"]] if filters.get("subject") in SUBJECTS else list(SUBJECTS)
    questions: list[QuestionRecord] = []
    for subject in selected:
        questions.extend(SubjectStore(subject, settings).list(filters))
    return sorted(questions, key=question_sort_key)
