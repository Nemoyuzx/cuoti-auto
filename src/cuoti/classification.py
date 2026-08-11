from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Classification:
    subject: str
    chapter: str
    section: str
    confidence: float


RULES: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "408": [
        ("数据结构", ("二叉树", "链表", "栈", "队列", "图", "排序", "查找", "时间复杂度", "数据结构")),
        ("计算机组成原理", ("cache", "缓存命中", "指令周期", "流水线", "补码", "存储器", "cpu", "总线", "组成原理")),
        ("操作系统", ("进程", "线程", "死锁", "页面置换", "虚拟内存", "信号量", "调度", "文件系统", "操作系统")),
        ("计算机网络", ("tcp", "udp", "ip地址", "子网", "路由", "拥塞", "http", "以太网", "网络层", "计算机网络")),
    ],
    "数学": [
        ("高等数学", ("极限", "导数", "微分", "积分", "级数", "微分方程", "多元函数", "曲线积分", "曲面积分")),
        ("线性代数", ("矩阵", "行列式", "向量组", "线性相关", "特征值", "特征向量", "二次型", "秩")),
        ("概率论与数理统计", ("概率", "随机变量", "分布函数", "期望", "方差", "协方差", "大数定律", "中心极限定理", "参数估计")),
    ],
    "英语": [
        ("阅读理解", ("according to", "the passage", "author", "paragraph", "阅读")),
        ("完形填空", ("cloze", "完形", "choose the best word")),
        ("翻译", ("translate", "translation", "翻译", "译文")),
        ("写作", ("essay", "letter", "write an", "写作", "作文")),
        ("词汇与语法", ("vocabulary", "grammar", "语法", "词汇", "单词")),
    ],
    "政治": [
        ("马克思主义基本原理", ("马克思", "唯物", "辩证法", "认识论", "剩余价值", "政治经济学", "马原")),
        ("习近平新时代中国特色社会主义思想概论", ("习近平", "新时代中国特色社会主义", "中国式现代化", "全过程人民民主", "人类命运共同体", "全面从严治党", "习思想")),
        ("毛泽东思想和中国特色社会主义理论体系概论", ("毛泽东思想", "中国特色社会主义", "新民主主义", "改革开放", "毛中特")),
        ("中国近现代史纲要", ("近代史", "新文化运动", "五四", "抗日战争", "史纲")),
        ("思想道德与法治", ("道德", "法治", "人生价值", "理想信念", "思修")),
        ("形势与政策", ("时政", "形势与政策", "国际局势", "年度会议")),
    ],
}


def classify_text(text: str) -> Classification:
    haystack = text.casefold()
    best: tuple[int, str, str] = (0, "数学", "待确认")
    for subject, sections in RULES.items():
        for section, keywords in sections:
            score = sum(2 if len(keyword) >= 4 else 1 for keyword in keywords if keyword.casefold() in haystack)
            if score > best[0]:
                best = (score, subject, section)
    if best[0] == 0:
        if sum(ch.isascii() and ch.isalpha() for ch in text) > max(20, len(text) * 0.45):
            return Classification("英语", "待确认", "待确认", 0.35)
        return Classification("数学", "待确认", "待确认", 0.2)
    confidence = min(0.9, 0.45 + best[0] * 0.08)
    return Classification(best[1], best[2], best[2], confidence)
