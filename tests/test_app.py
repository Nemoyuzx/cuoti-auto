from pathlib import Path
import time
from urllib.parse import unquote

from fastapi.testclient import TestClient
from starlette.requests import Request

from cuoti import app as app_module
from cuoti.config import Settings
from cuoti.db import SubjectStore
from cuoti.models import ExtractedQuestion
from cuoti import export_jobs


def test_review_page_shows_source_and_edit_form(monkeypatch, tmp_path: Path):
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("408", settings)
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image")
    question_id = store.insert(
        ExtractedQuestion(subject="408", chapter="树", section="数据结构", question_text="一道待复核题"),
        "review-hash", str(source), "assets/source.jpg",
    )
    (store.root / "assets" / "source.jpg").write_bytes(b"image")
    monkeypatch.setattr(app_module, "settings", settings)
    client = TestClient(app_module.app)

    start = client.get("/review?subject=408", follow_redirects=False)
    assert start.status_code == 303
    assert start.headers["location"] == f"/review/408/{question_id}"

    page = client.get(start.headers["location"])
    assert page.status_code == 200
    assert "原始照片" in page.text
    assert "识别结果" in page.text
    assert "data-review-image" in page.text
    assert 'name="question_text"' in page.text
    assert 'data-preview-source="question-preview"' in page.text
    assert 'data-preview-source="options-preview"' in page.text
    assert 'data-preview-source="analysis-preview"' in page.text
    assert page.text.count('class="live-preview-title">实际效果') == 3
    assert 'value="confirm_next"' in page.text
    assert 'id="taxonomy-chapters"' in page.text
    assert "4.2.2 KMP 算法" in page.text

    confirmed = client.post(
        f"/question/408/{question_id}",
        data={
            "chapter": "树", "section": "数据结构",
            "question_text": "一道已复核题", "status": "待复核",
            "review_mode": "1", "submit_action": "confirm_next",
        },
        follow_redirects=False,
    )
    assert confirmed.status_code == 303
    assert confirmed.headers["location"] == "/review?subject=408"
    assert store.get(question_id).status == "已复核"  # type: ignore[union-attr]


def test_review_template_has_safe_taxonomy_default(monkeypatch, tmp_path: Path):
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("数学", settings)
    question_id = store.insert(
        ExtractedQuestion(subject="数学", chapter="极限", section="高等数学", question_text="默认上下文测试"),
        "default-context", "source.jpg",
    )
    monkeypatch.setattr(app_module, "settings", settings)
    request = Request({
        "type": "http", "method": "GET", "path": f"/review/数学/{question_id}",
        "headers": [], "query_string": b"", "scheme": "http",
        "server": ("testserver", 80), "client": ("testclient", 50000),
    })
    response = app_module.render(
        "review.html", request, question=store.get(question_id),
        previous_question=None, next_question=None, remaining=1,
    )
    assert response.status_code == 200
    assert b"taxonomy_choices" not in response.body
    assert "删除本题" in response.body.decode("utf-8")


def test_politics_review_uses_generic_taxonomy(monkeypatch, tmp_path: Path):
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("政治", settings)
    question_id = store.insert(
        ExtractedQuestion(
            subject="政治", chapter="待确认", section="习近平新时代中国特色社会主义思想概论",
            question_text="中国式现代化测试题",
        ),
        "politics-taxonomy", "source.jpg",
    )
    monkeypatch.setattr(app_module, "settings", settings)

    page = TestClient(app_module.app).get(f"/review/政治/{question_id}")

    assert page.status_code == 200
    assert "习近平新时代中国特色社会主义思想概论" in page.text
    assert "第13章 全面从严治党" in page.text
    assert "中国近现代史纲要 / 新中国时期 / 第10章 中国特色社会主义新时代" in page.text


def test_review_can_delete_mistaken_question_with_backup(monkeypatch, tmp_path: Path):
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("408", settings)
    original = tmp_path / "original.jpg"
    original.write_bytes(b"original-user-photo")
    mistaken_id = store.insert(
        ExtractedQuestion(subject="408", chapter="待确认", section="数据结构", question_text="误收题"),
        "mistaken", str(original), "assets/mistaken.jpg",
    )
    next_id = store.insert(
        ExtractedQuestion(subject="408", chapter="绪论", section="数据结构", question_text="保留题"),
        "keep", str(original), "assets/keep.jpg",
    )
    (store.root / "assets" / "mistaken.jpg").write_bytes(b"derived-mistaken")
    (store.root / "assets" / "keep.jpg").write_bytes(b"derived-keep")
    markdown = store.root / "markdown" / f"{mistaken_id:06d}.md"
    monkeypatch.setattr(app_module, "settings", settings)
    client = TestClient(app_module.app)

    response = client.post(
        f"/question/408/{mistaken_id}/delete",
        data={"next_id": next_id}, follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/review/408/{next_id}?deleted={mistaken_id}"
    assert store.get(mistaken_id) is None
    assert store.get(next_id) is not None
    assert not markdown.exists()
    assert original.read_bytes() == b"original-user-photo"
    backups = list((store.root / "backups" / "deleted_questions").glob("*.json"))
    assert len(backups) == 1 and '"question_text": "误收题"' in backups[0].read_text(encoding="utf-8")
    moved_assets = list((store.root / "backups" / "deleted_assets").rglob("mistaken.jpg"))
    assert len(moved_assets) == 1 and moved_assets[0].read_bytes() == b"derived-mistaken"

    next_page = client.get(response.headers["location"])
    assert next_page.status_code == 200
    assert f"误收题目 #{mistaken_id} 已删除" in next_page.text


def test_subjects_have_separate_pages_without_subject_select(monkeypatch, tmp_path: Path):
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    SubjectStore("408", settings).insert(
        ExtractedQuestion(subject="408", chapter="树", section="数据结构", question_text="408题"),
        "subject-hash", "source.jpg",
    )
    monkeypatch.setattr(app_module, "settings", settings)
    client = TestClient(app_module.app)

    home = client.get("/", follow_redirects=False)
    assert home.headers["location"] == "/subject/cs408"
    page = client.get("/subject/cs408")
    assert page.status_code == 200
    assert 'href="/subject/math"' in page.text
    assert 'href="/subject/english"' in page.text
    assert 'href="/subject/politics"' in page.text
    assert 'select name="subject"' not in page.text
    assert 'data-export-panel data-subject="408"' in page.text
    assert 'class="export-popover"' in page.text
    assert "完整版不包含原始拍照页" in page.text


def test_dashboard_uses_two_column_cards_horizontal_options_and_dates(monkeypatch, tmp_path: Path):
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("408", settings)
    question_id = store.insert(
        ExtractedQuestion(
            subject="408", chapter="第2章 线性表", section="2.2 顺序表",
            question_text="横向选项测试", options=["A. 甲", "B. 乙"],
        ),
        "horizontal-options", "source.jpg",
    )
    monkeypatch.setattr(app_module, "settings", settings)
    page = TestClient(app_module.app).get("/subject/cs408")

    assert page.status_code == 200
    assert '<div class="options math-content">' in page.text
    assert '<ol class="options' not in page.text
    assert page.text.count("A. 甲") == 1 and page.text.count("B. 乙") == 1
    assert f"#{question_id} · 20" in page.text


def test_dashboard_prioritizes_low_confidence_review(monkeypatch, tmp_path: Path):
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("数学", settings)
    low_id = store.insert(
        ExtractedQuestion(subject="数学", question_text="低置信度题", confidence=0.62),
        "low-confidence", "source.jpg",
    )
    store.insert(
        ExtractedQuestion(subject="数学", question_text="高置信度题", confidence=0.95),
        "high-confidence", "source.jpg",
    )
    monkeypatch.setattr(app_module, "settings", settings)
    client = TestClient(app_module.app)

    dashboard = client.get("/subject/math")
    assert dashboard.status_code == 200
    assert "优先复核低置信度（1）" in dashboard.text
    assert "置信度 62%" in dashboard.text
    assert 'select name="confidence"' in dashboard.text

    start = client.get("/review?subject=数学&confidence=low", follow_redirects=False)
    assert start.status_code == 303
    assert unquote(start.headers["location"]) == f"/review/数学/{low_id}?confidence=low"
    review = client.get(start.headers["location"])
    assert review.status_code == 200
    assert "当前科目还有 1 题待复核" in review.text
    assert 'name="review_confidence" value="low"' in review.text


def test_live_preview_endpoint_uses_formal_rich_text_renderer():
    client = TestClient(app_module.app)

    rich = client.post(
        "/api/render-preview",
        json={"kind": "richtext", "value": "解：$x^2$\n```c\nif (a < b) return;\n```"},
    )
    assert rich.status_code == 200
    assert '<pre><code class="language-c">' in rich.json()["html"]
    assert "if (a &lt; b) return;" in rich.json()["html"]

    options = client.post(
        "/api/render-preview",
        json={"kind": "options", "value": "A. $1$\n\nB. <script>"},
    )
    assert options.status_code == 200
    assert options.json()["html"].count("<span>") == 2
    assert "&lt;script&gt;" in options.json()["html"]
    assert "<script>" not in options.json()["html"]
    stylesheet = (Path(__file__).resolve().parents[1] / "src/cuoti/static/app.css").read_text(encoding="utf-8")
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in stylesheet
    assert ".question-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; align-items: start; }" in stylesheet
    assert ".question-card { width: 100%; min-height: 0;" in stylesheet
    assert ".question-card { min-height: 280px; }" not in stylesheet


def test_dashboard_renders_crlf_fenced_code_as_code_block(monkeypatch, tmp_path: Path):
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("408", settings)
    store.insert(
        ExtractedQuestion(
            subject="408", chapter="第1章 绪论", section="算法效率",
            question_text="17 求时间复杂度：\r\n```c\r\nint sum=0;\r\nsum++;\r\n```",
        ),
        "crlf-code", "source.jpg",
    )
    monkeypatch.setattr(app_module, "settings", settings)

    page = TestClient(app_module.app).get("/subject/cs408")

    assert page.status_code == 200
    assert '<pre><code class="language-c">' in page.text
    assert "int sum=0;\nsum++;" in page.text
    assert "```c" not in page.text


def test_question_detail_prioritizes_content_and_collapses_source_editor(monkeypatch, tmp_path: Path):
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("408", settings)
    question_id = store.insert(
        ExtractedQuestion(
            subject="408", question_type="算法应用题", question_text="编写代码",
            analysis="解法：\n```c\nvoid solve(SqList &L) {}\n```",
        ),
        "detail-rich", "source.jpg", "assets/source.jpg",
    )
    (store.root / "assets" / "source.jpg").write_bytes(b"image")
    monkeypatch.setattr(app_module, "settings", settings)
    page = TestClient(app_module.app).get(f"/question/408/{question_id}")

    assert page.status_code == 200
    assert 'class="detail-primary"' in page.text
    assert '<details class="detail-maintenance">' in page.text
    assert "展开原题图片与编辑区域" in page.text
    assert '<pre><code class="language-c">' in page.text
    assert "SqList &amp;L" in page.text
    assert "detail-layout" not in page.text
    assert f"#{question_id} · 20" in page.text


def test_dashboard_and_chapter_filter_use_natural_chapter_order(monkeypatch, tmp_path: Path):
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    store = SubjectStore("408", settings)
    for source_hash, chapter, text in (
        ("chapter-10", "第10章 排序", "10章题"),
        ("chapter-2", "第2章 线性表", "2章题"),
        ("chapter-1", "第1章 绪论", "1章题"),
    ):
        store.insert(
            ExtractedQuestion(subject="408", chapter=chapter, section="数据结构", question_text=text),
            source_hash, "source.jpg",
        )
    monkeypatch.setattr(app_module, "settings", settings)
    page = TestClient(app_module.app).get("/subject/cs408")

    assert page.status_code == 200
    assert page.text.index("1章题") < page.text.index("2章题") < page.text.index("10章题")
    assert page.text.index("第1章 绪论") < page.text.index("第2章 线性表") < page.text.index("第10章 排序")


def test_pdf_export_api_runs_in_background(monkeypatch, tmp_path: Path):
    settings = Settings(tmp_path / "project", tmp_path / "Desktop", "127.0.0.1", 8765, "gpt-4o-mini")
    SubjectStore("408", settings).insert(
        ExtractedQuestion(subject="408", chapter="树", section="数据结构", question_text="导出题"),
        "export-hash", "source.jpg",
    )
    monkeypatch.setattr(app_module, "settings", settings)

    def fake_export(questions, variant, output=None, settings=None, progress_callback=None):
        assert questions and variant == "practice"
        if progress_callback:
            progress_callback(45, "正在测试后台导出")
        path = tmp_path / "background.pdf"
        path.write_bytes(b"%PDF-1.7\nbackground")
        return path

    monkeypatch.setattr(export_jobs, "export_pdf", fake_export)
    client = TestClient(app_module.app)
    started = client.post("/api/exports", data={"variant": "practice", "subject": "408"})
    assert started.status_code == 202
    job_id = started.json()["id"]
    final = None
    for _ in range(50):
        final = client.get(f"/api/exports/{job_id}").json()
        if final["state"] == "ready":
            break
        time.sleep(0.01)
    assert final and final["state"] == "ready" and final["progress"] == 100
    download = client.get(f"/api/exports/{job_id}/download")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
