from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


PRIVATE_SUFFIXES = {
    ".db", ".heic", ".jpeg", ".jpg", ".pdf", ".png", ".sqlite", ".sqlite3",
}
RUNTIME_PREFIXES = ("data/inbox/", "output/", "tmp/")
CONTENT_PATTERNS = {
    "macOS 用户目录": re.compile(r"/Users/[^/\s]+/"),
    "相机原始文件名": re.compile(r"\bIMG_[0-9]{3,}\b", re.IGNORECASE),
    "点分隔批次日期": re.compile(r"\b20[0-9]{2}\.[01][0-9]\.[0-3][0-9]\b"),
}


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        pytest.skip("Git metadata is unavailable in this test environment")
    return [
        root / item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item
    ]


def test_tracked_tree_excludes_private_study_data() -> None:
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for path in tracked_files(root):
        relative = path.relative_to(root).as_posix()
        if not path.exists():
            continue
        if path.suffix.casefold() in PRIVATE_SUFFIXES:
            violations.append(f"{relative}: private binary/media file")
        if relative.endswith("/.gitkeep"):
            continue
        if relative.startswith(RUNTIME_PREFIXES):
            violations.append(f"{relative}: runtime/local-data path")
        if relative == "tests/test_privacy.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in CONTENT_PATTERNS.items():
            if pattern.search(text):
                violations.append(f"{relative}: {label}")
    assert not violations, "\n".join(violations)
