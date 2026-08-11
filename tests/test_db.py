from pathlib import Path

from cuoti.config import Settings
from cuoti.db import SubjectStore, list_all, natural_text_sort_key
from cuoti.models import ExtractedQuestion


def make_settings(tmp_path: Path) -> Settings:
    return Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")


def test_insert_deduplicates_and_writes_markdown(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = SubjectStore("数学", settings)
    item = ExtractedQuestion(
        subject="数学", chapter="极限", section="高等数学",
        question_text="求 $\\lim_{x\\to0} \\frac{\\sin x}{x}$",
        correct_answer="$1$", knowledge_points=["重要极限"],
    )
    first = store.insert(item, "abc", "/tmp/source.jpg")
    second = store.insert(item, "abc", "/tmp/source.jpg")
    assert first == second
    assert len(store.list()) == 1
    markdown = store.root / "markdown" / f"{first:06d}.md"
    assert "重要极限" in markdown.read_text(encoding="utf-8")


def test_update_syncs_markdown(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = SubjectStore("408", settings)
    question_id = store.insert(ExtractedQuestion(subject="408", question_text="何为死锁？"), "hash", "source")
    store.update(question_id, {
        "section": "操作系统", "analysis": "四个必要条件。",
        "confidence": 0.82, "status": "已复核",
    })
    record = store.get(question_id)
    assert record and record.status == "已复核"
    markdown = (store.root / "markdown" / f"{question_id:06d}.md").read_text(encoding="utf-8")
    assert "四个必要条件" in markdown
    assert "confidence: 0.82" in markdown


def test_source_images_are_excluded_from_practice_until_selected(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = SubjectStore("数学", settings)
    question_id = store.insert(
        ExtractedQuestion(subject="数学", question_text="含图题"),
        "image-hash", "source.jpg", "assets/source.jpg",
    )
    record = store.get(question_id)
    assert record and record.image_paths == ["assets/source.jpg"]
    assert record.practice_image_paths == []
    store.set_practice_images(question_id, ["assets/source.jpg"])
    assert store.get(question_id).practice_image_paths == ["assets/source.jpg"]  # type: ignore[union-attr]


def test_questions_are_sorted_by_natural_chapter_section_and_number(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = SubjectStore("408", settings)
    inserted = [
        ("chapter-10", "第10章 高级主题", "10.1 基础", "02 第十章题"),
        ("question-11", "第2章 线性表", "2.2 顺序表", "11 第十一题"),
        ("section-10", "第2章 线性表", "2.10 其他", "01 后续小节"),
        ("question-3", "第2章 线性表", "2.2 顺序表", "03 第三题"),
        ("unknown", "待确认", "待确认", "01 待分类题"),
    ]
    for source_hash, chapter, section, question_text in inserted:
        store.insert(
            ExtractedQuestion(
                subject="408", chapter=chapter, section=section, question_text=question_text,
            ),
            source_hash, "source.jpg",
        )

    ordered = store.list()
    assert [item.question_text for item in ordered] == [
        "03 第三题", "11 第十一题", "01 后续小节", "02 第十章题", "01 待分类题",
    ]
    assert [item.id for item in list_all({"subject": "408"}, settings)] == [item.id for item in ordered]


def test_natural_sort_treats_unicode_digit_symbols_as_text() -> None:
    values = ["10. 普通题", "2. 普通题", "① 圈号题"]
    assert sorted(values, key=natural_text_sort_key) == ["2. 普通题", "10. 普通题", "① 圈号题"]


def test_confidence_band_filters(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = SubjectStore("数学", settings)
    for source_hash, confidence in (("low", 0.62), ("medium", 0.81), ("high", 0.95)):
        store.insert(
            ExtractedQuestion(
                subject="数学", question_text=f"{source_hash} confidence",
                confidence=confidence,
            ),
            source_hash, "source.jpg",
        )

    assert [item.confidence for item in store.list({"confidence": "low"})] == [0.62]
    assert [item.confidence for item in store.list({"confidence": "medium"})] == [0.81]
    assert [item.confidence for item in store.list({"confidence": "high"})] == [0.95]
