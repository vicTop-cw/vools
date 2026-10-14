"""市场体检与造前查重。

这一模块回答一个很具体的问题：**我要不要造这个新动作？**

现状痛点（实测 `_meta/actions.index.json`，109 个动作）：
`actus.cli.curl` 与 `cli.curl`、`http.fetch` 与 `actus.http.fetch`
等 6 组同能力双份实现；27 个动作没按 `actus.` 前缀约定命名。
成因很具体 —— `actions/cli/curl.actus.md` 一个文件声明了两个 id，
而 `validate` 不拦。多 agent 并行加动作时没有全局去重机制，
重复就是这样长出来的。

相似度算法刻意**不用 embedding**：体检必须纯离线可跑、结果可复现、
不被 API key 卡住。

Example:
    >>> rep = analyze_market(ToolCatalog(()))
    >>> rep['counts']['total']
    0
"""

__all__ = ['GapReport', 'find_similar', 'analyze_market', 'health_report',
           'similarity', 'CAPABILITY_ANCHORS',
           'VERDICT_REUSE', 'VERDICT_COMPOSE', 'VERDICT_GAP']

import re

from vools.core.dataclass_compat import dataclass, field

from .catalog import ToolCatalog, detect_duplicates

VERDICT_REUSE = 'reuse'        # 有现成的，直接用
VERDICT_COMPOSE = 'compose'    # 有多个相近的，建议用 workflow 组合
VERDICT_GAP = 'gap'            # 确实缺能力，允许造

# 中文停用词：分词后这些词不携带区分度，计入相似度只会拉高基线
_STOPWORDS = frozenset([
    '的', '了', '和', '与', '或', '是', '在', '对', '把', '给', '从', '到',
    '一个', '这个', '那个', '可以', '需要', '进行', '使用', '通过', '支持',
    'a', 'an', 'the', 'to', 'of', 'and', 'or', 'in', 'on', 'for', 'with',
])

# 英文/数字词（含点分 id 段）
_WORD = re.compile(r'[a-z0-9_.]+')
# 中文按 2-gram 切（中文无空格，单字区分度太低）
_CJK = re.compile(r'[一-鿿]+')

# 能力锚点表：相似度的**强信号**，命中即视为同能力。
#
# 为什么必须有这张表：中文同义表达千变万化，纯字符算法无能为力。
# 实测「截个图看看屏幕」与 tool_screen（description 写的是「截取屏幕」）
# 最长公共子串只有「屏幕」二字，jaccard 仅 0.07 —— 纯字符相似度会把
# 明显的同能力判成 gap。用户查东西时用的是自己的话，不是动作作者的用词。
#
# 所以：查询与动作描述**任意一方**命中同一锚点词，即视为同能力。
# 这张表是人工维护的确定性资产：可解释、可离线、可增量补充，
# 且命中了哪一项可以打印给人看（find_similar 的 advice 里会带出来）。
CAPABILITY_ANCHORS = {
    'screenshot': ('截图', '截屏', '屏幕', 'screen', 'screenshot', 'snapshot',
                   'capture'),
    'clipboard': ('剪贴板', '粘贴', '复制', 'clipboard', 'paste', 'copy'),
    'convert': ('转换', '互转', '转成', '转档', 'convert', 'transform', 'pandoc',
                '格式'),
    'json': ('json', 'jq'),
    'http': ('http', '请求', '抓取', 'fetch', 'curl', '下载', '上传', 'api'),
    'dialog': ('弹窗', '对话框', 'dialog', 'popup'),
    'git': ('git', '提交', 'commit', '版本'),
    'sftp': ('sftp', '文件传输', '远程拷贝'),
    'checksum': ('哈希', '摘要', '校验和', 'checksum', 'md5', 'sha1', 'sha256',
                 'sha', 'blake2b'),
    'mcp': ('mcp',),
    'cron': ('cron', '定时', '周期任务'),
    'macro': ('宏', 'macro', '键鼠回放', '录制'),
    'watch': ('监控', '监听', 'watch', '变化'),
    'encode': ('编码', '转义', 'encode', 'decode', '解码'),
    'form': ('表单', 'form', '填写'),
    'secret': ('密钥', '口令', '密码', 'secret', 'vault', 'credential'),
}


@dataclass(frozen=True)
class GapReport(object):
    """一次查重的结论。

    Attributes:
        action_id: 被查的动作 id（新建时可能还不存在，故可为空）。
        verdict: VERDICT_REUSE / VERDICT_COMPOSE / VERDICT_GAP。
        similar: 相似的已有动作摘要，按相似度降序。
        advice: 给人看的一句话建议。
        top_score: 最高相似度。

    Example:
        >>> GapReport(action_id='x.y', verdict=VERDICT_GAP).top_score
        0.0
    """

    action_id: str = ''
    verdict: str = VERDICT_GAP
    similar: tuple = ()
    advice: str = ''
    top_score: float = 0.0


def _tokens(text):
    """把文本切成用于比较的词元。

    中文走 2-gram、英文数字走整词，都去小写并剔除停用词。

    Args:
        text: 待切分文本。

    Returns:
        set: 词元集合。

    Example:
        >>> 'json' in _tokens('处理 JSON 数据')
        True
    """
    low = str(text or '').lower()
    out = set()
    for run in _CJK.findall(low):
        if len(run) == 1:
            out.add(run)
            continue
        for i in range(len(run) - 1):
            out.add(run[i:i + 2])
    for word in _WORD.findall(low):
        if len(word) > 1 and word not in _STOPWORDS:
            out.add(word)
    return out - _STOPWORDS


def _jaccard(a, b):
    """Jaccard 相似度。

    Args:
        a: 词元集合。
        b: 词元集合。

    Returns:
        float: 0..1。两个都为空时返回 0（无信息不算相似）。
    """
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return float(inter) / float(len(a | b))


def _segment_score(query, entry):
    """「查询里直接出现了动作 id 的某一段」这一强信号的分数。

    为什么不能只靠 jaccard：查询通常很短（「用 jq 处理 JSON」几个词元），
    而 description 很长，jaccard 的分母被 description 撑大，短查询即使
    完全命中也拿不到及格分。实测 jaccard 下 cli.jq 只有 0.34，
    卡在阈值下沿误判成 gap。所以对 id 段命中单独给按长度分级的分。

    段长分级而非一刀切：段越长越不可能是巧合（'json_util' 基本是专名，
    'ok' 则可能是），避免 2 字符段造成大面积误判。

    Args:
        query: 待查描述。
        entry: CatalogEntry。

    Returns:
        float: 0..1。无命中返回 0.0。
    """
    low = str(query or '').lower()
    best = 0.0
    for seg in str(entry.action_id or '').split('.'):
        if len(seg) < 2 or seg not in low:
            continue
        if len(seg) >= 4:
            best = max(best, 0.8)
        elif len(seg) == 3:
            best = max(best, 0.7)
        else:
            best = max(best, 0.5)
    for tag in entry.tags:
        tag = str(tag or '').lower()
        if len(tag) >= 3 and tag in low:
            best = max(best, 0.6)
    return best


def _anchor_hit(query, entry):
    """查「查询」与「动作」是否命中同一个能力锚点，并给出分级强度。

    两边任意一方命中即算 —— 用户可能用「截个图」，动作作者写「截取屏幕」，
    没人会写和对方一样的词。

    **强度按命中位置分级**（这一级区分解决了实测中的排序错乱）：
      - 0.85：动作 id 或 tags 命中该锚点 —— 这通常就是该能力的主动作
        （如 tool_clipboard 的 tag 是 clipboard，而 quicker.capture 只是
        description 里顺带提到剪贴板）
      - 0.70：仅 description 命中 —— 相关但很可能不是用户要找的那个

    不分级的话所有命中者并列 0.75，「读取剪贴板」会返回 quicker.capture
    而不是 tool_clipboard。

    Args:
        query: 待查描述。
        entry: CatalogEntry。

    Returns:
        tuple: (能力名, 强度)。没命中返回 ('', 0.0)。
    """
    q = str(query or '').lower()
    meta = ('%s %s' % (entry.action_id or '', ' '.join(entry.tags or ()))).lower()
    desc = str(entry.description or '').lower()
    if not q:
        return '', 0.0

    for cap, words in sorted(CAPABILITY_ANCHORS.items()):
        if not any(w in q for w in words):
            continue
        if any(w in meta for w in words):
            return cap, 0.85
        if any(w in desc for w in words):
            return cap, 0.70
    return '', 0.0


def _long_terms(text):
    """抽出文本里信息量高的长词（英文/数字，长度 >= 4）。

    中文靠锚点表处理同义，英文/专名只能靠词面 —— 「Markdown」「docx」
    这类词是区分 pandoc 与 jq 的唯一依据，不能被中文 2-gram 稀释掉。

    Args:
        text: 待抽词文本。

    Returns:
        set: 长词集合（小写，已去停用词）。

    Example:
        >>> sorted(_long_terms('把 Markdown 转成 docx'))
        ['docx', 'markdown']
    """
    return set(w for w in _WORD.findall(str(text or '').lower())
               if len(w) >= 4 and w not in _STOPWORDS)


def _term_score(query, entry):
    """按「查询长词被动作覆盖」的程度打分 —— 主路径。

    与锚点表互补：锚点解决中文同义（「截个图」≈「截取屏幕」），
    本函数解决专名精确匹配（Markdown / docx / sha256 只可能属于一个动作）。
    两者都命中时锚点负责同类能力、本函数负责同类中的正确个体。

    Args:
        query: 待查描述。
        entry: CatalogEntry。

    Returns:
        float: 0..1。查询里没有长词时返回 0.0。
    """
    terms = _long_terms(query)
    if not terms:
        return 0.0
    desc = str(entry.description or '').lower()
    meta = ('%s %s' % (entry.action_id or '',
                       ' '.join(entry.tags or ()))).lower()

    covered = 0
    meta_hit = 0
    for t in terms:
        in_desc = t in desc
        in_meta = t in meta
        if in_desc or in_meta:
            covered += 1
        if in_meta:
            meta_hit += 1

    if not covered:
        return 0.0
    base = 0.9 * (float(covered) / len(terms))
    # 专名直接出现在 id/tag 里，比只出现在描述里更像「就是这个动作」
    if meta_hit:
        base += 0.05
    return min(1.0, base)


def similarity(query, entry):
    """算「一段描述」与「一个动作」的相似度。

    取三条路径里最高者：

    1. **专名覆盖**（主）：0.9 × 查询长词被 id/description 覆盖的比例，
       id/tag 直接命中再 +0.05。区分同类动作中的正确个体。
    2. **能力锚点**：0.85（id/tags 命中）/ 0.70（仅 description 命中）。
       处理中文同义表达。见 _anchor_hit。
    3. **字符相似度**：0.4 × id/标签信号 + 0.4 × description jaccard
       + 0.2 × 尾段命中（尾段命中时该项即 0.2）。兜底，处理锚点表未覆盖的
       新能力。

    Args:
        query: 待查描述。
        entry: CatalogEntry。

    Returns:
        float: 0..1 的相似度。

    Example:
        >>> from vools.actus.ai.catalog import CatalogEntry
        >>> e = CatalogEntry(tool_name='cli_jq', action_id='cli.jq',
        ...                  description='jq JSON 处理')
        >>> similarity('用 jq 处理 JSON', e) > 0.35
        True
    """
    if not str(query or '').strip():
        return 0.0

    term = _term_score(query, entry)
    if term:
        return term

    _, anchor_score = _anchor_hit(query, entry)
    if anchor_score:
        return anchor_score

    q = _tokens(query)
    if not q:
        return 0.0

    id_tokens = _tokens(entry.action_id.replace('.', ' '))
    tag_tokens = _tokens(' '.join(entry.tags))

    seg = _segment_score(query, entry)
    s_id = seg if seg > 0 else _jaccard(q, id_tokens | tag_tokens)
    s_desc = _jaccard(q, _tokens(entry.description))

    tail = str(entry.action_id or '').split('.')[-1].lower()
    s_tail = 0.2 if tail and len(tail) > 1 and tail in str(query or '').lower() else 0.0

    return 0.4 * s_id + 0.4 * s_desc + s_tail


def find_similar(description, catalog=None, threshold=0.35, limit=8):
    """造新动作之前先查重。

    判定：
      - `reuse`   最高相似度 >= threshold 且只有一个候选 → 直接复用
      - `compose` 最高相似度 >= threshold 但有多个候选 → 建议 workflow 组合
      - `gap`     无候选超过 threshold → 确实缺能力，可以造

    Args:
        description: 想造的动作的描述（自然语言）。
        catalog: 工具目录；None 时用 load_catalog() 现取。
        threshold: 判定阈值。
        limit: 最多返回几个相似项。

    Returns:
        GapReport: 查重结论。**纯离线可跑，不调 LLM。**

    Example:
        >>> find_similar('x', catalog=ToolCatalog(())).verdict
        'gap'
    """
    from .catalog import load_catalog
    cat = catalog if catalog is not None else load_catalog()

    scored = []
    for entry in cat:
        score = similarity(description, entry)
        if score > 0:
            scored.append((score, entry))
    # 分数降序，同分按 id 排序保证结果可复现
    scored.sort(key=lambda t: (-t[0], t[1].action_id))

    top = scored[0][0] if scored else 0.0
    passed = [t for t in scored if t[0] >= threshold][:limit]
    similar = tuple({
        'action_id': e.action_id, 'tool_name': e.tool_name,
        'description': e.description[:200], 'score': round(s, 4),
    } for s, e in passed)

    if not passed:
        verdict = VERDICT_GAP
        advice = '市场里没有相似动作（最高相似度 %.2f < %.2f），确实缺能力，可以造。' % (top, threshold)
    elif len(passed) == 1:
        verdict = VERDICT_REUSE
        advice = '已有动作 %s 能干这件事（相似度 %.2f），优先复用。' % (
            passed[0][1].action_id, passed[0][0])
    else:
        verdict = VERDICT_COMPOSE
        advice = ('有 %d 个相似动作（最高 %s，相似度 %.2f），'
                  '建议用 workflow 组合而不是新造。') % (
            len(passed), passed[0][1].action_id, passed[0][0])

    return GapReport(action_id='', verdict=verdict, similar=similar,
                     advice=advice, top_score=round(top, 4))


def analyze_market(catalog=None):
    """整体市场体检。全程离线，不调 LLM。

    五个部分：
      - `counts`       动作总数 / 无参动作数
      - `duplicates`   同能力多实现（见 detect_duplicates）
      - `orphans`      被 deps 引用但不存在或已下架的动作 id
      - `no_args`      没有可填参数的动作（LLM 只能调不能给参数）
      - `nonstandard_prefix`  未按 `actus.` 前缀命名的动作

    Args:
        catalog: 工具目录；None 时用 load_catalog() 现取。

    Returns:
        dict: 体检结果。目录为空时各字段为空列表/零计数，不抛异常。

    Example:
        >>> analyze_market(ToolCatalog(()))['duplicates']
        {'exact': [], 'suspect': [], 'nonstandard_prefix': []}
    """
    from .catalog import load_catalog
    cat = catalog if catalog is not None else load_catalog()

    dup = detect_duplicates(list(cat))
    known = set(cat.action_ids())

    # 孤儿依赖：需要原始 deps，从索引再取一次（目录本身不保留 deps）。
    # 关键：只统计【目录内工具】的 deps。若遍历整个全局索引，空目录也会
    # 被塞进一堆外部工具的依赖，产生"伪孤儿"（测试 test_analyze_market_on_
    # empty_catalog 要求空目录 orphan 为空）。
    referenced = set()
    try:
        from ..indexer import load_index
        index = load_index(cat.meta_dir or None)
        for action_id, brief in (index.get('actions') or {}).items():
            if action_id not in known:
                continue
            if not isinstance(brief, dict):
                continue
            for dep in brief.get('deps') or []:
                dep = str(dep)
                if dep.startswith('action:'):
                    referenced.add(dep[7:])
                elif ':' not in dep and dep and not dep.startswith('cs_'):
                    referenced.add(dep)
    except Exception:
        referenced = set()

    orphans = sorted(d for d in referenced
                     if d not in known and not d.startswith('_'))

    no_args = sorted(e.action_id for e in cat if e.no_args)

    return {
        'counts': {'total': len(cat),
                   'no_args': len(no_args),
                   'by_trust': _count_by(cat, lambda e: e.trust)},
        'duplicates': dup,
        'orphans': orphans,
        'no_args': no_args,
        'nonstandard_prefix': dup['nonstandard_prefix'],
    }


def _count_by(cat, key_fn):
    """按 key_fn 分组计数。

    Args:
        cat: ToolCatalog。
        key_fn: 取键函数。

    Returns:
        dict: 键 → 计数。
    """
    out = {}
    for e in cat:
        k = str(key_fn(e) or '')
        out[k] = out.get(k, 0) + 1
    return out


def health_report(catalog=None):
    """生成给人看的中文体检摘要。

    Args:
        catalog: 工具目录；None 时用 load_catalog() 现取。

    Returns:
        str: 多行文本。目录为空时返回一行「无动作可检」。

    Example:
        >>> '无动作' in health_report(ToolCatalog(()))
        True
    """
    from .catalog import load_catalog
    cat = catalog if catalog is not None else load_catalog()
    rep = analyze_market(cat)
    dup = rep['duplicates']

    if not len(cat):
        return '动作市场体检：无动作可检（目录为空或索引不可用）。'

    lines = []
    lines.append('动作市场体检（%d 个动作）' % rep['counts']['total'])
    lines.append('')
    lines.append('一、同能力多实现：%d 组' % len(dup['exact']))
    for item in dup['exact']:
        lines.append('  [%s] %s' % (item['key'], ' / '.join(item['action_ids'])))
    if not dup['exact']:
        lines.append('  （无）')

    lines.append('')
    lines.append('二、疑似同能力（仅提示）：%d 组' % len(dup['suspect']))
    for item in dup['suspect']:
        lines.append('  [%s] %s' % (item['capability'], ' / '.join(item['action_ids'])))
    if not dup['suspect']:
        lines.append('  （无）')

    lines.append('')
    lines.append('三、命名不规范（首段非 actus）：%d 个' % len(dup['nonstandard_prefix']))
    for aid in dup['nonstandard_prefix'][:30]:
        lines.append('  %s' % aid)
    if len(dup['nonstandard_prefix']) > 30:
        lines.append('  …（其余 %d 个略）' % (len(dup['nonstandard_prefix']) - 30))

    lines.append('')
    lines.append('四、孤儿依赖：%d 个' % len(rep['orphans']))
    for aid in rep['orphans'][:20]:
        lines.append('  %s' % aid)
    if len(rep['orphans']) > 20:
        lines.append('  …（其余 %d 个略）' % (len(rep['orphans']) - 20))

    lines.append('')
    lines.append('五、无可填参数（LLM 只能调不能传参）：%d 个' % rep['counts']['no_args'])
    return '\n'.join(lines)