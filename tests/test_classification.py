from cuoti.classification import classify_text


def test_classifies_core_subject_sections():
    assert classify_text("二叉树的层序遍历时间复杂度").section == "数据结构"
    assert classify_text("矩阵的特征值与特征向量").section == "线性代数"
    assert classify_text("TCP 拥塞控制与网络层路由").section == "计算机网络"
    assert classify_text("唯物辩证法的矛盾分析方法").section == "马克思主义基本原理"


def test_english_fallback():
    result = classify_text("Which of the following statements best describes the author attitude?")
    assert result.subject == "英语"


def test_classifies_xi_jinping_thought_as_its_own_politics_module():
    result = classify_text("中国式现代化和人类命运共同体")
    assert result.subject == "政治"
    assert result.section == "习近平新时代中国特色社会主义思想概论"
