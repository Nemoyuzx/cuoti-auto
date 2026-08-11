from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from .config import SUBJECTS, Settings
from .db import initialize_all, list_all
from .ingest import import_json, ingest_path
from .pdf_export import export_pdf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cuoti", description="纸质错题自动化工作流")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="创建四科目录和 SQLite 数据库")
    ingest = sub.add_parser("ingest", help="识别一个图片或文件夹")
    ingest.add_argument("path", type=Path)
    ingest.add_argument("--provider", choices=("tesseract", "openai", "mineru"), default="tesseract")
    imported = sub.add_parser("import-json", help="导入 Codex/人工复核后的结构化 JSON")
    imported.add_argument("json_path", type=Path)
    imported.add_argument("--source", type=Path, required=True)
    serve = sub.add_parser("serve", help="启动本地错题本网页")
    serve.add_argument("--no-open", action="store_true")
    export = sub.add_parser("export", help="导出 PDF")
    export.add_argument("--variant", choices=("practice", "notebook"), required=True)
    export.add_argument("--subject", choices=SUBJECTS)
    export.add_argument("--chapter", default="")
    export.add_argument("--section", default="")
    export.add_argument("--output", type=Path)
    sub.add_parser("doctor", help="检查运行环境和数据库")
    return parser


def command_doctor(settings: Settings) -> int:
    checks = {
        "Python 3.11-3.13": (3, 11) <= sys.version_info[:2] < (3, 14),
        "Tesseract（保底 OCR）": shutil.which("tesseract") is not None,
        "Node.js（KaTeX/PDF）": shutil.which("node") is not None,
        "KaTeX": (settings.project_root / "node_modules/katex/dist/katex.min.css").exists(),
        "OpenAI Key（可选）": bool(os.environ.get("OPENAI_API_KEY")),
        "MinerU（可选）": shutil.which("mineru") is not None,
    }
    initialize_all(settings)
    print("错题_auto 环境检查")
    for name, ok in checks.items():
        optional = "（不影响基础功能）" if "可选" in name else ""
        print(f"  {'✓' if ok else '✗'} {name}{optional}")
    for subject in SUBJECTS:
        print(f"  ✓ {subject}: {settings.subject_root(subject) / 'wrong_questions.sqlite3'}")
    return 0 if all(ok for name, ok in checks.items() if "可选" not in name) else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.load()
    if args.command == "init":
        initialize_all(settings)
        for subject in SUBJECTS:
            print(settings.subject_root(subject))
        return 0
    if args.command == "ingest":
        for subject, question_id in ingest_path(args.path, args.provider, settings):
            print(f"已入库：{subject} #{question_id}")
        return 0
    if args.command == "import-json":
        for subject, question_id in import_json(args.json_path, args.source, settings):
            print(f"已入库：{subject} #{question_id}")
        return 0
    if args.command == "serve":
        if not args.no_open:
            timer = threading.Timer(0.8, webbrowser.open, args=(f"http://{settings.host}:{settings.port}",))
            timer.daemon = True
            timer.start()
        try:
            return subprocess.call([
                sys.executable, "-m", "uvicorn", "cuoti.app:app", "--host", settings.host,
                "--port", str(settings.port),
            ], cwd=settings.project_root)
        except KeyboardInterrupt:
            return 0
    if args.command == "export":
        questions = list_all({"subject": args.subject or "", "chapter": args.chapter, "section": args.section}, settings)
        print(export_pdf(questions, args.variant, args.output, settings))
        return 0
    if args.command == "doctor":
        return command_doctor(settings)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
