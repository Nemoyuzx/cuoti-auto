#!/usr/bin/env python3
"""将历史数据结构题的分类名归一到项目内置的通用分类。

默认只预览；确认后使用：
    .venv/bin/python scripts/normalize_408_taxonomy.py --apply

脚本通过 SubjectStore 更新 SQLite，并同步刷新每题的 Markdown 镜像。
"""

from __future__ import annotations

import argparse

from cuoti.config import Settings
from cuoti.db import SubjectStore
from cuoti.taxonomy import canonicalize_data_structure


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="实际写入 SQLite 和 Markdown")
    args = parser.parse_args()

    store = SubjectStore("408", Settings.load())
    changes = []
    for record in store.list():
        chapter, section = canonicalize_data_structure(record.chapter, record.section)
        if (chapter, section) != (record.chapter, record.section):
            changes.append((record.id, record.chapter, chapter, record.section, section))
            if args.apply:
                store.update(record.id, {"chapter": chapter, "section": section})

    action = "已写入" if args.apply else "预览"
    print(f"{action}：{len(changes)} 道数据结构题需要归一化")
    for question_id, old_chapter, chapter, old_section, section in changes:
        print(f"#{question_id}: {old_chapter} / {old_section} -> {chapter} / {section}")


if __name__ == "__main__":
    main()
