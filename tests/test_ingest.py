from pathlib import Path

from PIL import Image

from cuoti import ingest


def test_parse_osd_rotation_uses_confidence_threshold():
    assert ingest.parse_osd_rotation("Rotate: 90\nOrientation confidence: 18.5") == 90
    assert ingest.parse_osd_rotation("Rotate: 270\nOrientation confidence: 2.0") == 0
    assert ingest.parse_osd_rotation("no orientation") == 0


def test_analysis_prompt_never_replaces_a_standard_solution_with_a_summary():
    assert "必须按原解的顺序、方法和计算步骤忠实转写" in ingest.ANALYSIS_PROMPT
    assert "不得概括、改写、缩写或用自己的解法替代" in ingest.ANALYSIS_PROMPT
    assert "【补充解析】" in ingest.ANALYSIS_PROMPT
    assert "correct_answer 和 analysis 留空" in ingest.ANALYSIS_PROMPT
    assert "禁止写“见解析”“见标准解析”“待确认”" in ingest.ANALYSIS_PROMPT


def test_analysis_prompt_excludes_blank_answers_with_mastery_checkmarks():
    assert "答案位置空白但旁边有明确对钩" in ingest.ANALYSIS_PROMPT
    assert "表示已经掌握，必须排除" in ingest.ANALYSIS_PROMPT
    assert "禁止仅因没有手写答案就把它当作错题" in ingest.ANALYSIS_PROMPT


def test_normalize_display_image_rotates_copy(monkeypatch, tmp_path: Path):
    source = tmp_path / "sideways.jpg"
    target = tmp_path / "upright.jpg"
    Image.new("RGB", (80, 40), "white").save(source)
    monkeypatch.setattr(ingest, "detect_image_rotation", lambda _path: 90)

    assert ingest.normalize_display_image(source, target) == 90
    with Image.open(target) as result:
        assert result.size == (40, 80)
