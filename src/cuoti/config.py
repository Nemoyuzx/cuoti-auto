from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


SUBJECTS = ("数学", "英语", "408", "政治")
SUBJECT_SLUGS = {"数学": "math", "英语": "english", "408": "cs408", "政治": "politics"}


def project_root() -> Path:
    configured = os.environ.get("CUOTI_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    desktop: Path
    host: str
    port: int
    openai_model: str

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            project_root=project_root(),
            desktop=Path(os.environ.get("CUOTI_DESKTOP", "~/Desktop")).expanduser().resolve(),
            host=os.environ.get("CUOTI_HOST", "127.0.0.1"),
            port=int(os.environ.get("CUOTI_PORT", "8765")),
            openai_model=os.environ.get("CUOTI_OPENAI_MODEL", "gpt-4o-mini"),
        )

    def subject_root(self, subject: str) -> Path:
        if subject not in SUBJECTS:
            raise ValueError(f"未知科目：{subject}")
        return self.desktop / subject / "错题_auto"

    @property
    def inbox(self) -> Path:
        return self.project_root / "data" / "inbox"

    @property
    def pdf_output(self) -> Path:
        return self.project_root / "output" / "pdf"


def ensure_directories(settings: Settings | None = None) -> None:
    settings = settings or Settings.load()
    settings.inbox.mkdir(parents=True, exist_ok=True)
    settings.pdf_output.mkdir(parents=True, exist_ok=True)
    (settings.project_root / "tmp").mkdir(parents=True, exist_ok=True)
    for subject in SUBJECTS:
        root = settings.subject_root(subject)
        for child in ("assets", "markdown", "exports", "backups"):
            (root / child).mkdir(parents=True, exist_ok=True)
