from pathlib import Path

import pytest

from cuoti.config import Settings
from cuoti.db import SubjectStore, list_all, natural_text_sort_key
from cuoti.models import (
    ExtractedQuestion,
    normalize_correct_answer,
    normalize_error_reason,
    normalize_options,
    normalize_wrong_answer,
    option_label,
    parse_options_text,
)


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


def test_insert_and_update_remove_blank_lines_around_display_math(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = SubjectStore("数学", settings)
    question_id = store.insert(
        ExtractedQuestion(
            subject="数学",
            question_text="题干\n\n$$x=1$$\n\n结束",
            analysis="第一步\n\n$$y=2$$\n\n第二步",
        ),
        "math-spacing",
        "source.jpg",
    )

    record = store.get(question_id)
    assert record and record.question_text == "题干\n$$x=1$$\n结束"
    assert record.analysis == "第一步\n$$y=2$$\n第二步"

    store.update(question_id, {"correct_answer": "因此\n\n$$z=3$$\n\n成立"})
    updated = store.get(question_id)
    assert updated and updated.correct_answer == "因此\n$$z=3$$\n成立"


def test_options_store_bodies_and_markdown_generates_labels(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = SubjectStore("408", settings)
    question_id = store.insert(
        ExtractedQuestion(
            subject="408", question_text="选项规范化",
            options=["A. 第一项", "B．第二项", "(C) 第三项", "D）第四项"],
        ),
        "option-labels", "source.jpg",
    )

    record = store.get(question_id)
    assert record and record.options == ["第一项", "第二项", "第三项", "第四项"]
    markdown = (store.root / "markdown" / f"{question_id:06d}.md").read_text(encoding="utf-8")
    assert "- A. 第一项" in markdown and "- D. 第四项" in markdown
    assert "A. A. 第一项" not in markdown


def test_option_helpers_preserve_nonmatching_content() -> None:
    assert normalize_options(["B. 不是第一项前缀", "B. 第二项"]) == ["B. 不是第一项前缀", "第二项"]
    assert normalize_options(["f(x) 连续", "B 树"] ) == ["f(x) 连续", "B 树"]
    assert normalize_options(["", "", "C. 第三项", "D. 第四项"]) == ["", "", "第三项", "第四项"]
    assert parse_options_text("A. 第一项\n\nB. 第二项") == ["第一项", "第二项"]
    assert option_label(0) == "A" and option_label(25) == "Z" and option_label(26) == "AA"


def test_correct_answer_option_label_has_no_parentheses() -> None:
    assert normalize_correct_answer("(C)") == "C"
    assert normalize_correct_answer("（d） $x=1$") == "D $x=1$"
    assert normalize_correct_answer("$f(x)=(C+x)$") == "$f(x)=(C+x)$"


@pytest.mark.parametrize("placeholder", ["见解析", "见标准解析", "待确认"])
def test_extracted_question_rejects_correct_answer_placeholder(placeholder: str) -> None:
    with pytest.raises(ValueError, match="正确答案必须填写明确结果"):
        ExtractedQuestion(subject="数学", question_text="题目", correct_answer=placeholder)


def test_insert_and_update_normalize_correct_answer_option_label(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store = SubjectStore("408", settings)
    question_id = store.insert(
        ExtractedQuestion(subject="408", question_text="正确答案格式", correct_answer="(B) $O(n)$"),
        "correct-answer-label", "source.jpg",
    )
    assert store.get(question_id).correct_answer == "B $O(n)$"  # type: ignore[union-attr]

    store.update(question_id, {"correct_answer": "（C） 结论"})
    record = store.get(question_id)
    assert record and record.correct_answer == "C 结论"
    markdown = (store.root / "markdown" / f"{question_id:06d}.md").read_text(encoding="utf-8")
    assert "（C）" not in markdown and "C 结论" in markdown


def test_error_reason_requires_specific_solution_evidence() -> None:
    placeholder = "题号被圈或答案被红笔订正，需要对照标准解析复盘原解中的具体错误。"
    assert normalize_error_reason(placeholder) == ""
    assert normalize_error_reason("未独立完成，需要按标准解析补全方法和运算过程。") == ""
    assert normalize_error_reason("计算时漏乘 $2$；未独立完成，需要按标准解析补全方法和运算过程。") == "计算时漏乘 $2$"
    assert normalize_error_reason("再做一次。") == "再做一次。"
    assert normalize_error_reason("题号被圈，但解答中漏乘 $2$。") == "题号被圈，但解答中漏乘 $2$。"


def test_insert_normalizes_generic_error_reason_to_empty(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store = SubjectStore("数学", settings)
    question_id = store.insert(
        ExtractedQuestion(
            subject="数学", question_text="没有作答过程",
            error_reason="题号被圈或答案被红笔订正，需要对照标准解析复盘原解中的具体错误。",
            knowledge_points=["极限"],
        ),
        "empty-error-reason", "source.jpg",
    )
    record = store.get(question_id)
    assert record and record.error_reason == ""


def test_wrong_answer_empty_or_red_only_uses_cannot_solve_marker() -> None:
    assert normalize_wrong_answer("") == "不会"
    assert normalize_wrong_answer("未作答") == "不会"
    assert normalize_wrong_answer("待确认（见原图红笔答案或订正）") == "不会"
    assert normalize_wrong_answer("待确认（见原图中的原答案与红笔订正）") == "不会"
    assert normalize_wrong_answer("有思路但计算错误（具体过程见原图红笔批注）") == "不会"
    assert normalize_wrong_answer("思路错误") == "不会"
    assert normalize_wrong_answer("C（原答；红笔订正为 D）") == "C（原答；红笔订正为 D）"


def test_insert_and_update_normalize_wrong_answer(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store = SubjectStore("数学", settings)
    question_id = store.insert(
        ExtractedQuestion(subject="数学", question_text="空白作答", wrong_answer=""),
        "wrong-answer-normalize", "source.jpg",
    )
    assert store.get(question_id).wrong_answer == "不会"  # type: ignore[union-attr]

    store.update(question_id, {"wrong_answer": "待确认（见原图红笔答案或订正）"})
    assert store.get(question_id).wrong_answer == "不会"  # type: ignore[union-attr]


def test_source_images_are_excluded_from_practice_until_selected(tmp_path: Path):
    settings = make_settings(tmp_path)
    store = SubjectStore("数学", settings)
    question_id = store.insert(
        ExtractedQuestion(subject="数学", question_text="含图题"),
        "image-hash", "source.jpg", "assets/source.jpg",
    )
    record = store.get(question_id)
    assert record and record.image_paths == ["assets/source.jpg"]
    assert record.question_image_paths == ["assets/source.jpg"]
    assert record.solution_image_paths == []
    assert record.practice_image_paths == []
    store.add_image(question_id, "assets/solution.jpg", "answer.jpg", 2, "solution")
    store.set_practice_images(question_id, ["assets/source.jpg", "assets/solution.jpg"])
    record = store.get(question_id)
    assert record and record.question_image_paths == ["assets/source.jpg"]
    assert record.solution_image_paths == ["assets/solution.jpg"]
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
