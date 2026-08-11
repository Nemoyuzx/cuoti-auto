from pathlib import Path

from PIL import Image

from cuoti import ingest


def test_parse_osd_rotation_uses_confidence_threshold():
    assert ingest.parse_osd_rotation("Rotate: 90\nOrientation confidence: 18.5") == 90
    assert ingest.parse_osd_rotation("Rotate: 270\nOrientation confidence: 2.0") == 0
    assert ingest.parse_osd_rotation("no orientation") == 0


def test_normalize_display_image_rotates_copy(monkeypatch, tmp_path: Path):
    source = tmp_path / "sideways.jpg"
    target = tmp_path / "upright.jpg"
    Image.new("RGB", (80, 40), "white").save(source)
    monkeypatch.setattr(ingest, "detect_image_rotation", lambda _path: 90)

    assert ingest.normalize_display_image(source, target) == 90
    with Image.open(target) as result:
        assert result.size == (40, 80)
