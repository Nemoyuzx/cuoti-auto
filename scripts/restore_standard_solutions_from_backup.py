"""Restore solution fields that were replaced by the review placeholder.

This is a narrow recovery tool for the accidental provenance quarantine.  It
copies only ``correct_answer`` and ``analysis`` (plus their earlier confidence)
from a user-selected online SQLite backup, and only for rows whose current
analysis is the exact quarantine placeholder.  All later edits to the question,
options, student answer, classification, notes and image links are preserved.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from cuoti.config import Settings
from cuoti.db import SubjectStore


PENDING = "标准解析待人工核对（见已关联解析图）"


def online_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)


def restore(subject: str, source_backup: Path) -> tuple[int, int]:
    settings = Settings.load()
    store = SubjectStore(subject, settings)
    store.initialize()

    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    safety_backup = store.root / "backups" / f"{stamp}-before-standard-solution-restore.sqlite3"
    online_backup(store.db_path, safety_backup)

    with sqlite3.connect(source_backup) as connection:
        connection.row_factory = sqlite3.Row
        earlier = {
            int(row["id"]): row
            for row in connection.execute(
                "SELECT id, source_file, question_text, correct_answer, analysis, confidence "
                "FROM questions"
            )
        }

    restored = 0
    skipped = 0
    for record in store.list():
        if record.analysis.strip() != PENDING:
            continue
        old = earlier.get(record.id)
        if (
            old is None
            or old["source_file"] != record.source_file
            or old["question_text"] != record.question_text
            or not str(old["analysis"]).strip()
            or str(old["analysis"]).strip() == PENDING
        ):
            skipped += 1
            continue
        store.update(
            record.id,
            {
                "correct_answer": str(old["correct_answer"]).strip(),
                "analysis": str(old["analysis"]).strip(),
                "confidence": float(old["confidence"]),
                "status": "待复核",
            },
        )
        restored += 1

    print(
        f"subject={subject} restored={restored} skipped={skipped} "
        f"safety_backup={safety_backup}"
    )
    return restored, skipped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", required=True, choices=("数学", "英语", "408", "政治"))
    parser.add_argument("--backup", required=True, type=Path)
    args = parser.parse_args()
    if not args.backup.is_file():
        parser.error(f"backup not found: {args.backup}")
    restore(args.subject, args.backup.resolve())


if __name__ == "__main__":
    main()
