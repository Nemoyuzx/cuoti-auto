from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from cuoti.config import Settings
from cuoti.db import SubjectStore
from cuoti.models import ExtractedQuestion
from cuoti.pdf_export import export_pdf, is_solution_question, pdf_image_paths, render_rich_many


def test_both_pdf_variants_render(tmp_path: Path):
    project = Path(__file__).resolve().parents[1]
    settings = Settings(project, tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("数学", settings)
    (store.root / "assets").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 50), "white").save(store.root / "assets" / "source.png")
    question_id = store.insert(ExtractedQuestion(
        subject="数学", chapter="一元积分", section="高等数学", question_type="计算题",
        question_text="计算 $\\int_0^1 x e^{x^2}\\,dx$。",
        options=["A. $0$", "B. $1$"],
        wrong_answer="$e-1$", correct_answer="$\\frac{e-1}{2}$",
        analysis="令 $u=x^2$，则 $du=2x\\,dx$。",
        error_reason="换元后遗漏系数。", knowledge_points=["换元积分法"], needs_review=False,
    ), "sample", "sample.png", "assets/source.png")
    store.set_practice_images(question_id, ["assets/source.png"])
    records = [store.get(question_id)]
    assert records[0] is not None
    assert pdf_image_paths(records[0], "practice") == ["assets/source.png"]  # type: ignore[arg-type]
    assert pdf_image_paths(records[0], "notebook") == []  # type: ignore[arg-type]
    for variant in ("practice", "notebook"):
        output = tmp_path / f"{variant}.pdf"
        progress = []
        export_pdf(records, variant, output, settings, lambda value, message: progress.append((value, message)))  # type: ignore[arg-type]
        assert output.read_bytes().startswith(b"%PDF")
        assert output.stat().st_size > 5_000
        assert progress[0][0] == 8
        assert progress[-1][0] == 98


def test_pdf_rich_text_renders_fenced_code_without_rendering_formula_inside_code(tmp_path: Path):
    project = Path(__file__).resolve().parents[1]
    settings = Settings(project, tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    rendered = render_rich_many([
        "公式 $x^2$\n```c\nif (x < 2 && value == '$x$') return;\n```",
    ], settings)[0]

    assert '<pre><code class="language-c">' in rendered
    assert "if (x &lt; 2 &amp;&amp; value == &#x27;$x$&#x27;)" in rendered
    assert rendered.count('class="katex"') == 1


def test_pdf_rich_text_removes_breaks_around_display_math(tmp_path: Path):
    project = Path(__file__).resolve().parents[1]
    settings = Settings(project, tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")

    rendered = render_rich_many([
        "先说明。\n\n$$x^2=1$$\n\n再说明 $x=1$。\n\n$$y=2$$\n\n结束。",
    ], settings)[0]

    assert "<br><span class=\"katex-display\">" not in rendered
    assert "</span><br>" not in rendered
    assert "先说明。<span class=\"katex-display\">" in rendered
    assert "</span>再说明" in rendered
    assert "</span>结束。" in rendered


def test_algorithm_application_is_a_solution_question(tmp_path: Path):
    project = Path(__file__).resolve().parents[1]
    settings = Settings(project, tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("408", settings)
    solution_id = store.insert(
        ExtractedQuestion(subject="408", question_type="算法应用题", question_text="写出算法"),
        "solution", "source.jpg",
    )
    choice_id = store.insert(
        ExtractedQuestion(subject="408", question_type="单项选择题", question_text="选择正确答案"),
        "choice", "source.jpg",
    )

    assert is_solution_question(store.get(solution_id))  # type: ignore[arg-type]
    assert not is_solution_question(store.get(choice_id))  # type: ignore[arg-type]


def test_short_solution_questions_fill_the_same_pdf_page(tmp_path: Path):
    """短解答题只要不被拆栏，不应强制每题独占整个栏高。"""
    project = Path(__file__).resolve().parents[1]
    settings = Settings(project, tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("数学", settings)
    records = []
    for index in range(4):
        question_id = store.insert(
            ExtractedQuestion(
                subject="数学",
                chapter="第1章",
                section="高等数学",
                question_type="解答题",
                question_text=f"计算第 {index + 1} 题。",
                correct_answer=str(index + 1),
                analysis="按定义直接计算。",
                needs_review=False,
            ),
            f"solution-{index}",
            f"source-{index}.jpg",
        )
        records.append(store.get(question_id))

    output = tmp_path / "dense-solutions.pdf"
    export_pdf(records, "notebook", output, settings)  # type: ignore[arg-type]

    assert len(PdfReader(output).pages) == 1
