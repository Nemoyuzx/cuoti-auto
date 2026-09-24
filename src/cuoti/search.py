"""本地错题线索检索：中文切词、数学记号同义词与模糊排序。

题库目前只有数百条记录，直接读取四个 SQLite 小库比维护另一份索引更简单。
只返回候选题和匹配线索；原图与标准解析仍需人工核对。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import jieba
from rapidfuzz import fuzz

from .config import Settings
from .db import list_all
from .models import QuestionRecord


jieba.setLogLevel(logging.WARNING)

# 只扩展常见数学写法，不把推断出的概念写回题目或数据库。
_CONCEPTS: dict[str, tuple[str, ...]] = {
    "微分方程": ("微分方程", "偏微分", "偏导", "\\partial", "\\frac{dy}", "dy", "y'", "f'"),
    "积分": ("积分", "\\int", "面积", "体积"),
    "平方": ("平方", "^2", "²"),
    "导数": ("导数", "求导", "\\partial", "f'", "y'"),
    "极限": ("极限", "\\lim"),
    "旋转体": ("旋转体", "旋转一周", "绕x轴", "绕y轴"),
}
_STOP_WORDS = {
    "一道", "大题", "题目", "这个", "那个", "一个", "结果", "第一", "第二",
    "被积", "被积函数", "函数", "计算", "求解", "求出", "里面", "其中", "可以",
    "的", "是", "和", "有", "求", "解", "题", "问", "部分", "第一问", "第二问",
}
_POWER_TWO = re.compile(r"\^\s*\{\s*2\s*\}")
_SPACES = re.compile(r"\s+")
_FIRST_PART = re.compile(r"第一问|第\s*[（(]?1[)）]?\s*问")
_SECOND_PART = re.compile(r"第二问|第二题|第\s*[（(]?2[)）]?\s*问")
_SQUARED_FUNCTION_INTEGRAL = re.compile(r"\\i?int.{0,160}(?:f|y)\([a-z]\)\^2")


@dataclass(frozen=True)
class SearchHit:
    question: QuestionRecord
    score: float
    matched_clues: tuple[str, ...]


def _normalize(value: str) -> str:
    return _SPACES.sub("", _POWER_TWO.sub("^2", value)).casefold()


def _query_clues(query: str) -> tuple[list[tuple[str, tuple[str, ...]]], list[str]]:
    concepts: list[tuple[str, tuple[str, ...]]] = []
    remaining = query
    for name, aliases in _CONCEPTS.items():
        if name in query:
            concepts.append((name, aliases))
            remaining = remaining.replace(name, " ")
    if _FIRST_PART.search(query):
        concepts.append(("第一问", ("（1）", "(1)", "第(1)问", "第一问")))
        remaining = _FIRST_PART.sub(" ", remaining)
    if _SECOND_PART.search(query):
        concepts.append(("第二问", ("（2）", "(2)", "第(2)问", "第二问")))
        remaining = _SECOND_PART.sub(" ", remaining)

    words = {
        word.casefold()
        for word in jieba.cut_for_search(remaining)
        if len(word.strip()) >= 2 and word.strip() not in _STOP_WORDS
    }
    # 长词通常比其中的二字片段更有区分度；限制数量可避免长口述拖慢排序。
    return concepts, sorted(words, key=lambda word: (-len(word), word))[:10]


def _field_values(question: QuestionRecord) -> tuple[tuple[str, float], ...]:
    return (
        (_normalize(question.question_text), 1.0),
        (_normalize(" ".join(question.knowledge_points)), 0.9),
        (_normalize(question.correct_answer), 0.8),
        (_normalize(question.analysis), 0.65),
        (_normalize(question.chapter + " " + question.section), 0.5),
    )


def _best_match(variants: tuple[str, ...], fields: tuple[tuple[str, float], ...]) -> float:
    return max(
        (weight for text, weight in fields if any(_normalize(variant) in text for variant in variants)),
        default=0.0,
    )


def search_questions(
    query: str,
    *,
    subject: str = "",
    limit: int = 10,
    settings: Settings | None = None,
) -> list[SearchHit]:
    """按描述检索候选题。检索时不生成模型向量，也不上传任何题目。"""
    query = query.strip()
    if not query or limit < 1:
        return []
    concepts, words = _query_clues(query)
    if not concepts and not words:
        words = [query.casefold()]

    filters = {"subject": subject} if subject else {}
    hits: list[SearchHit] = []
    for question in list_all(filters, settings):
        fields = _field_values(question)
        matched: list[str] = []
        score = 0.0
        for name, aliases in concepts:
            strength = _best_match(aliases, fields)
            if strength:
                score += 28 * strength
                matched.append(name)
        for word in words:
            normalized = _normalize(word)
            strength = _best_match((normalized,), fields)
            if strength:
                score += 8 * strength
                matched.append(word)
            elif len(normalized) >= 3:
                # RapidFuzz 只用于剩余线索的轻量容错；长解析截断后仍保留题干。
                best = max(
                    (fuzz.partial_ratio(normalized, text[:1200]) / 100 * weight
                     for text, weight in fields[:2] if text),
                    default=0.0,
                )
                if best >= 0.85:
                    score += 4 * best
                    matched.append(f"{word}≈")
        if "平方" in query and ("积分" in query or "被积函数" in query):
            if any(_SQUARED_FUNCTION_INTEGRAL.search(text) for text, _ in fields[:4]):
                score += 42
                matched.append("函数平方作为被积函数")
        if score:
            hits.append(SearchHit(question, round(score, 2), tuple(matched)))
    return sorted(hits, key=lambda hit: (-hit.score, hit.question.subject, hit.question.id))[:limit]
