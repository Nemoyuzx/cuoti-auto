from pathlib import Path

from cuoti.config import Settings
from cuoti.db import SubjectStore
from cuoti.models import ExtractedQuestion
from cuoti.search import search_questions


def test_description_finds_integral_of_previous_solution_squared(tmp_path: Path) -> None:
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "model")
    store = SubjectStore("数学", settings)
    target = store.insert(
        ExtractedQuestion(
            subject="数学",
            chapter="第13章 多元函数微分学",
            question_text=(
                "设 f 由一个偏导关系确定。"
                "（1）求 f(x)；（2）求图形绕 x 轴旋转一周的体积。"
            ),
            analysis="体积 V=\\int_0^1 f(x)^2 dx。",
        ),
        "target", "source.jpg",
    )
    store.insert(
        ExtractedQuestion(
            subject="数学",
            question_text="（1）求微分方程的解；（2）计算一个普通积分。",
            analysis="令 y'=x^2，得到 y=x^3/3。",
        ),
        "distractor", "source.jpg",
    )

    hits = search_questions(
        "一道大题，第一问是微分方程的解，第二问积分的被积函数是第一问解的平方",
        subject="数学", settings=settings,
    )

    assert hits[0].question.id == target
    assert "函数平方作为被积函数" in hits[0].matched_clues


def test_search_is_subject_scoped_and_empty_query_has_no_results(tmp_path: Path) -> None:
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "model")
    SubjectStore("408", settings).insert(
        ExtractedQuestion(subject="408", question_text="微分方程的积分与平方"),
        "other-subject", "source.jpg",
    )
    assert search_questions("微分方程 积分 平方", subject="数学", settings=settings) == []
    assert search_questions("  ", settings=settings) == []
