from cuoti.taxonomy import (
    canonicalize_data_structure,
    data_structure_choices,
    data_structure_taxonomy,
    politics_choices,
    politics_taxonomy,
)


def test_data_structure_taxonomy_is_generic_and_complete():
    taxonomy = data_structure_taxonomy()
    choices = data_structure_choices()
    assert taxonomy["module"] == "数据结构"
    assert len(taxonomy["chapters"]) == 8
    assert "source_images" not in taxonomy
    assert "第4章 字符串" in choices["chapters"]
    assert "4.2.2 KMP 算法" in choices["points"]
    assert "8.4.2 败者树与最佳归并树" in choices["points"]


def test_legacy_data_structure_labels_are_canonicalized():
    assert canonicalize_data_structure("串", "KMP算法") == (
        "第4章 字符串", "4.2.2 KMP 算法",
    )
    assert canonicalize_data_structure("线性表", "顺序表与链表") == (
        "第2章 线性表", "2.3.4 顺序存储与链式存储的比较",
    )


def test_politics_taxonomy_is_generic_and_covers_standard_modules():
    taxonomy = politics_taxonomy()
    choices = politics_choices()
    modules = taxonomy["modules"]

    assert taxonomy["subject"] == "政治"
    assert "source_images" not in taxonomy
    assert len(modules) == 6
    assert "习近平新时代中国特色社会主义思想概论" in choices["sections"]
    assert "形势与政策" in choices["sections"]
    assert "第13章 全面从严治党" in choices["chapters"]
    assert "第2章 新民主主义革命理论" in choices["chapters"]
    assert (
        "中国近现代史纲要 / 新民主主义革命时期 / 第4章 中国共产党的成立与革命新局面"
        in choices["points"]
    )
    assert (
        "中国近现代史纲要 / 新中国时期 / 第10章 中国特色社会主义新时代"
        in choices["points"]
    )
    assert all("参考答案" not in point for point in choices["points"])
