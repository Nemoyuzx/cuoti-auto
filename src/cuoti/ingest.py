from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from .classification import classify_text
from .config import Settings, ensure_directories
from .db import SubjectStore
from .models import ExtractedQuestion, ExtractionBatch


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff", ".bmp"}


def parse_osd_rotation(output: str) -> int:
    """Return Tesseract's clockwise correction angle, or zero when uncertain."""
    match = re.search(r"^Rotate:\s*(0|90|180|270)\s*$", output, re.MULTILINE)
    if not match:
        return 0
    confidence = re.search(r"^Orientation confidence:\s*([0-9.]+)\s*$", output, re.MULTILINE)
    if confidence and float(confidence.group(1)) < 5:
        return 0
    return int(match.group(1))


def detect_image_rotation(path: Path) -> int:
    """Detect the clockwise rotation needed to make a text-heavy photo upright."""
    if shutil.which("tesseract") is None:
        return 0
    try:
        result = subprocess.run(
            ["tesseract", str(path), "stdout", "--psm", "0", "-l", "osd"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    return parse_osd_rotation(f"{result.stdout}\n{result.stderr}")


def normalize_display_image(source: Path, target: Path) -> int:
    """Create an upright display copy while preserving the user's original photo."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
        with tempfile.TemporaryDirectory(prefix="cuoti-orientation-") as temp:
            osd_input = Path(temp) / "page.png"
            image.convert("RGB").save(osd_input, format="PNG")
            rotation = detect_image_rotation(osd_input)
        if rotation:
            image = image.rotate(-rotation, expand=True)
        suffix = target.suffix.casefold()
        if suffix in {".jpg", ".jpeg"}:
            image.convert("RGB").save(target, format="JPEG", quality=94, optimize=True)
        elif suffix == ".png":
            image.save(target, format="PNG", optimize=True)
        elif suffix == ".webp":
            image.save(target, format="WEBP", quality=94)
        else:
            image.convert("RGB").save(target, format="JPEG", quality=94, optimize=True)
        return rotation
    except Exception:
        shutil.copy2(source, target)
        return 0


ANALYSIS_PROMPT = """你正在整理中国考研纸质错题。逐题读取图片，不能把多道题合成一道。
必须忠实保留题干、选项、学生错误答案、标准正确答案和手写批注；数学公式写成 LaTeX，行内用 $...$、独立公式用 $$...$$。
科目只能是 数学、英语、408、政治。章节与板块尽量使用考研常见命名。
若原图缺少解析，请给出可独立理解、步骤完整的解析；不要伪造看不清的内容，看不清处写 [无法辨认] 并将 needs_review 设为 true。
error_reason 要总结真正的知识或方法漏洞，knowledge_points 使用短标签。source_page 从 1 开始。
"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_images(path: Path) -> list[Path]:
    path = path.expanduser().resolve()
    if path.is_file():
        return [path] if path.suffix.casefold() in IMAGE_EXTENSIONS else []
    return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.casefold() in IMAGE_EXTENSIONS)


def extract_tesseract(path: Path) -> ExtractionBatch:
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", "chi_sim+eng", "--psm", "6"],
        capture_output=True, text=True, check=True,
    )
    text = result.stdout.strip() or "[Tesseract 未识别出文字，请人工复核原图]"
    cls = classify_text(text)
    question = ExtractedQuestion(
        subject=cls.subject, chapter=cls.chapter, section=cls.section,
        question_text=text, confidence=cls.confidence, needs_review=True,
        analysis="Tesseract 仅完成文字初识别；请在详情页补充答案和解析。",
    )
    return ExtractionBatch(questions=[question], page_notes="本地 Tesseract 保底识别")


def extract_openai(path: Path, settings: Settings) -> ExtractionBatch:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("未检测到 OPENAI_API_KEY；可改用 --provider tesseract，或直接把图片发给 Codex 后导入 JSON。")
    from openai import OpenAI

    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    client = OpenAI()
    response = client.responses.parse(
        model=settings.openai_model,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": ANALYSIS_PROMPT},
                {"type": "input_image", "image_url": f"data:{mime};base64,{encoded}", "detail": "high"},
            ],
        }],
        text_format=ExtractionBatch,
    )
    if response.output_parsed is None:
        raise RuntimeError("视觉模型未返回可解析的结构化结果")
    return response.output_parsed


def extract_mineru(path: Path) -> ExtractionBatch:
    if shutil.which("mineru") is None:
        raise RuntimeError("未安装 MinerU。请参考 docs/OPEN_SOURCE.md 安装，或改用 openai/tesseract。")
    with tempfile.TemporaryDirectory(prefix="cuoti-mineru-") as temp:
        subprocess.run(["mineru", "-p", str(path), "-o", temp, "-b", "pipeline"], check=True)
        markdown_files = sorted(Path(temp).rglob("*.md"))
        if not markdown_files:
            raise RuntimeError("MinerU 没有生成 Markdown")
        text = "\n\n".join(item.read_text(encoding="utf-8") for item in markdown_files)
    cls = classify_text(text)
    return ExtractionBatch(questions=[ExtractedQuestion(
        subject=cls.subject, chapter=cls.chapter, section=cls.section,
        question_text=text, confidence=cls.confidence, needs_review=True,
        analysis="MinerU 已保留版面与公式；请复核题目切分、答案并补全解析。",
    )])


def save_batch(batch: ExtractionBatch, source: Path, settings: Settings | None = None) -> list[tuple[str, int]]:
    settings = settings or Settings.load()
    ensure_directories(settings)
    digest = sha256_file(source)
    saved: list[tuple[str, int]] = []
    normalized_asset: Path | None = None
    for index, question in enumerate(batch.questions, start=1):
        store = SubjectStore(question.subject, settings)
        suffix = source.suffix.casefold() or ".jpg"
        asset_name = f"{digest[:16]}-{index}{suffix}"
        asset = store.root / "assets" / asset_name
        if not asset.exists():
            if normalized_asset is None:
                normalize_display_image(source, asset)
            else:
                shutil.copy2(normalized_asset, asset)
        if normalized_asset is None:
            normalized_asset = asset
        relative = str(asset.relative_to(store.root))
        question_id = store.insert(question, digest, str(source), relative)
        saved.append((question.subject, question_id))
    return saved


def ingest_path(path: Path, provider: str = "tesseract", settings: Settings | None = None) -> list[tuple[str, int]]:
    settings = settings or Settings.load()
    extractors = {
        "tesseract": lambda p: extract_tesseract(p),
        "openai": lambda p: extract_openai(p, settings),
        "mineru": lambda p: extract_mineru(p),
    }
    if provider not in extractors:
        raise ValueError(f"未知识别器 {provider}；可选：{', '.join(extractors)}")
    images = discover_images(path)
    if not images:
        raise FileNotFoundError(f"没有找到支持的图片：{path}")
    saved: list[tuple[str, int]] = []
    for image in images:
        saved.extend(save_batch(extractors[provider](image), image, settings))
    return saved


def import_json(json_path: Path, source: Path, settings: Settings | None = None) -> list[tuple[str, int]]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    batch = ExtractionBatch.model_validate(data)
    return save_batch(batch, source.expanduser().resolve(), settings)
