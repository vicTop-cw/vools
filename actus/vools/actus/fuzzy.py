"""fuzzy.py —— F2 模糊匹配与拼写纠错（提升计划 F2）。

提供：
- **Levenshtein 编辑距离容错**（≤2，对查询词与索引 term 匹配）；
- **拼音前缀容错**（可选 pypinyin，导入失败优雅降级，绝不崩溃）；
- **did-you-mean 纠错建议**（无命中时返回距离最近且得分达阈值的候选词）。

设计原则：
- **零硬依赖**：pypinyin 是可选依赖。缺失时 `has_pinyin_support()` 返回
  False、`pinyin_prefix()` 返回 None，上层按"无拼音候选"回退，不抛异常。
- **纯函数**：本模块不触碰文件系统、不感知动作注册表；`registry.py` 负责
  把动作条目映射为候选 term 并调用本模块的纯函数做容错判定。
- **阈值参数化**：编辑距离上限与相似度阈值全部由调用方传入，模块只做
  确定性计算（同一输入恒有同一输出，便于测试锁定）。

改动范围限 `E:\\IDEProjects\\AI\\vools\\actus`（红线：不删除文件、
不破坏 schema、可 git 回溯）。
"""

# 可选依赖：pypinyin（导入失败优雅降级，绝不向上抛）。
try:
    from pypinyin import lazy_pinyin as _lazy_pinyin
    _HAS_PYPINYIN = True
except Exception:  # pragma: no cover - 环境缺包时走到
    _lazy_pinyin = None
    _HAS_PYPINYIN = False


def has_pinyin_support() -> bool:
    """pypinyin 是否可用（供上层决定是否启用拼音前缀路径）。"""
    return _HAS_PYPINYIN


def levenshtein_distance(a: str, b: str, max_dist: int = 2) -> int:
    """计算 a、b 的 Levenshtein 编辑距离；超过 max_dist 返回 max_dist + 1。

    快速失败边界：
    - 相等 → 0；
    - 长度差 > max_dist → 必然超过（增删操作无法弥补长度差）；
    - 滚动数组 DP：行最小值单调非降（编辑距离对第二个串单调），
      当前行最小值 > max_dist 即可提前终止。
    """
    if a == b:
        return 0
    if max_dist < 0:
        return max_dist + 1
    la, lb = len(a), len(b)
    if abs(la - lb) > max_dist:
        return max_dist + 1
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] * (lb + 1)
        row_min = cur[0]
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if cur[j] < row_min:
                row_min = cur[j]
        if row_min > max_dist:
            return max_dist + 1
        prev = cur
    return prev[lb]


def fuzzy_match(word: str, term: str, max_dist: int = 2) -> bool:
    """查询词 word 与索引 term 是否编辑距离容错匹配（≤max_dist）。

    小写归一后比较；任一侧为空返回 False。
    """
    if not word or not term:
        return False
    return levenshtein_distance(word.lower(), term.lower(), max_dist) <= max_dist


def edit_similarity(word: str, term: str, max_dist: int = 2) -> float:
    """归一化编辑相似度：1 - dist / max(len)；超出 max_dist 返回 0.0。"""
    if not word or not term:
        return 0.0
    d = levenshtein_distance(word.lower(), term.lower(), max_dist)
    if d > max_dist:
        return 0.0
    return 1.0 - d / max(len(word), len(term))


def pinyin_prefix(text: str):
    """文本的小写拼音串（无分隔）。pypinyin 不可用返回 None（降级）。

    对非汉字字符（英文/数字/标点），pypinyin 默认原样保留；
    因此英文 term 的"拼音串"就是原文，天然与拼音查询互斥。
    """
    if not text:
        return ""
    if _lazy_pinyin is None:
        return None
    try:
        return "".join(_lazy_pinyin(text)).lower()
    except Exception:  # pragma: no cover - 防御性兜底
        return None


def pinyin_prefix_match(query: str, term: str, max_dist: int = 2) -> bool:
    """拼音前缀容错：term 拼音串包含/前缀匹配查询拼音（编辑距离 ≤max_dist）。

    匹配规则（任一成立即命中）：
    - term 拼音串以查询拼音开头（`startswith`）；
    - term 拼音串包含查询拼音（`in`，覆盖中文词在字段中段场景）；
    - term 拼音串前缀与查询拼音编辑距离 ≤max_dist（容忍拼音输入错误）。

    pypinyin 不可用或任一侧无有效拼音串 → False（降级为无命中）。
    """
    q_py = pinyin_prefix(query)
    t_py = pinyin_prefix(term)
    if not q_py or not t_py:
        return False
    if t_py.startswith(q_py) or q_py in t_py:
        return True
    return levenshtein_distance(q_py, t_py[:len(q_py)], max_dist) <= max_dist


def edit_suggestions(query: str, terms, max_dist: int = 2,
                     cutoff: float = 0.5, top_n: int = 3) -> list:
    """did-you-mean 候选：在 terms 中找编辑距离最近且相似度达阈值的候选词。

    参数:
        query: 查询词。
        terms: 候选词列表（小写归一在函数内完成）。
        max_dist: 最大编辑距离。
        cutoff: 相似度阈值（similarity = 1 - dist/max(len)，低于则丢弃）。
        top_n: 最多返回条数。

    返回:
        [{term, distance, similarity}]，按 (distance, -similarity) 排序；
        无候选返回 []（不抛异常）。
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    out = []
    for t in terms:
        t = (t or "").strip().lower()
        if not t or t == q:
            continue
        d = levenshtein_distance(q, t, max_dist)
        if d > max_dist:
            continue
        sim = 1.0 - d / max(len(q), len(t))
        if sim >= cutoff:
            out.append({"term": t, "distance": d, "similarity": sim})
    out.sort(key=lambda x: (x["distance"], -x["similarity"], x["term"]))
    return out[:top_n]


def pinyin_suggestions(query: str, terms, max_dist: int = 2,
                       cutoff: float = 0.5, top_n: int = 3) -> list:
    """did-you-mean 候选：拼音前缀命中（可选 pypinyin）。

    返回:
        [{term, distance, similarity, kind='pinyin'}]；pypinyin 不可用或无
        命中返回 []。
    """
    if not has_pinyin_support():
        return []
    q = (query or "").strip().lower()
    q_py = pinyin_prefix(q)
    if not q_py:
        return []
    out = []
    for t in terms:
        t = (t or "").strip().lower()
        if not t or t == q:
            continue
        t_py = pinyin_prefix(t)
        if not t_py:
            continue
        if not (t_py.startswith(q_py) or q_py in t_py):
            continue
        d = levenshtein_distance(q_py, t_py[:len(q_py)], max_dist)
        if d > max_dist:
            continue
        sim = 1.0 - d / max(len(q_py), len(t_py))
        if sim >= cutoff:
            out.append({"term": t, "distance": d, "similarity": sim,
                        "kind": "pinyin"})
    out.sort(key=lambda x: (x["distance"], -x["similarity"], x["term"]))
    return out[:top_n]
