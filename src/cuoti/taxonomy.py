from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


TAXONOMY_PATH = Path(__file__).parent / "data" / "408_data_structure_taxonomy.json"
POLITICS_TAXONOMY_PATH = Path(__file__).parent / "data" / "politics_taxonomy.json"


@lru_cache(maxsize=1)
def data_structure_taxonomy() -> dict[str, Any]:
    """Load the built-in generic data-structure taxonomy."""
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def data_structure_choices() -> dict[str, list[str]]:
    taxonomy = data_structure_taxonomy()
    chapters: list[str] = []
    sections: list[str] = []
    points: list[str] = []
    for chapter in taxonomy["chapters"]:
        chapters.append(f"第{chapter['code']}章 {chapter['title']}")
        for section in chapter["sections"]:
            sections.append(f"{section['code']} {section['title']}")
            sections.extend(section["points"])
            points.extend(section["points"])
    return {"chapters": chapters, "sections": sections, "points": points}


@lru_cache(maxsize=1)
def politics_taxonomy() -> dict[str, Any]:
    """Load the built-in generic politics taxonomy."""
    return json.loads(POLITICS_TAXONOMY_PATH.read_text(encoding="utf-8"))


def politics_choices() -> dict[str, list[str]]:
    """Map module -> chapter -> full knowledge path to the existing review fields."""
    taxonomy = politics_taxonomy()
    chapters: list[str] = []
    sections: list[str] = []
    points: list[str] = []
    for module in taxonomy["modules"]:
        sections.append(module["title"])
        for part in module["parts"]:
            for chapter in part["chapters"]:
                label = _politics_chapter_label(chapter)
                if label not in chapters:
                    chapters.append(label)
                points.append(f"{module['title']} / {part['title']} / {label}")
    return {"chapters": chapters, "sections": sections, "points": points}


def _politics_chapter_label(chapter: dict[str, Any]) -> str:
    code = chapter["code"]
    return f"{code} {chapter['title']}" if code == "导论" else f"第{code}章 {chapter['title']}"


CHAPTER_ALIASES = {
    "绪论": "第1章 基础概念与算法分析",
    "第1章 绪论": "第1章 基础概念与算法分析",
    "线性表": "第2章 线性表",
    "栈和队列": "第3章 栈、队列与数组",
    "数组和矩阵": "第3章 栈、队列与数组",
    "第3章 栈、队列和数组": "第3章 栈、队列与数组",
    "串": "第4章 字符串",
    "第4章 串": "第4章 字符串",
    "树与二叉树": "第5章 树与二叉树",
    "图": "第6章 图",
    "查找": "第7章 查找",
    "排序": "第8章 排序",
}

SECTION_ALIASES = {
    "数据结构的基本概念": "1.1 数据结构基础",
    "算法的基本概念": "1.2 算法分析",
    "时间复杂度": "1.2.2 时间复杂度",
    "空间复杂度": "1.2.3 空间复杂度",
    "顺序表": "2.2 顺序表",
    "顺序表算法": "2.2.2 顺序表的插入与删除",
    "单链表": "2.3.1 单链表",
    "链式存储": "2.3 链表",
    "链表": "2.3 链表",
    "循环单链表": "2.3.3 循环链表与静态链表",
    "有序链表": "2.3 链表",
    "顺序表与链表": "2.3.4 顺序存储与链式存储的比较",
    "栈与队列的基本概念": "3.1 栈",
    "栈的基本操作": "3.1 栈",
    "栈的出栈序列": "3.1 栈",
    "链式队列": "3.2.3 链式队列与双端队列",
    "循环队列": "3.2.2 循环队列",
    "队列": "3.2 队列",
    "栈的应用": "3.1.3 栈在递归和表达式中的应用",
    "对称矩阵压缩存储": "3.3.2 特殊矩阵的压缩存储",
    "特殊矩阵与稀疏矩阵": "3.3 数组与矩阵",
    "KMP算法": "4.2.2 KMP 算法",
    "树的基本概念": "5.1 树的基础",
    "树的度与叶结点": "5.1.1 树的术语与性质",
    "树的度与结点数": "5.1.1 树的术语与性质",
    "树的度与高度": "5.1.1 树的术语与性质",
}


def canonicalize_data_structure(chapter: str, section: str) -> tuple[str, str]:
    """Map legacy chapter/section labels to the generic built-in taxonomy."""
    return CHAPTER_ALIASES.get(chapter, chapter), SECTION_ALIASES.get(section, section)
