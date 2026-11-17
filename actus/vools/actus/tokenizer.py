"""tokenizer.py —— 统一轻量分词（T0r11：F3 中文/多语言支持）。

统一 tokenize 入口：英文/数字按空白切分（与 str.split() 等价，保证既有
英文关键词/倒排/语义/fuzzy 行为零回归）；CJK 连续段展开为「整词 + 分词
词」——优先 jieba（可选依赖，导入失败优雅降级），无 jieba 时回退 2-gram。

设计约束（红线）：
- 不得硬依赖 jieba：导入失败/运行期异常一律降级 2-gram，绝不抛异常；
- 纯英文/数字输入输出与 `(text.strip()).split()` 完全一致；
- 输出保序去重；长度不做裁剪（len 过滤由调用方按语义决定）。
"""
import re
from typing import List

__all__ = ["tokenize", "cjk_tokens", "has_jieba"]

#: CJK 统一表意文字区间（含扩展 A）。
_CJK_RANGES = "\u4e00-\u9fff\u3400-\u4dbf"
#: 捕获组模式：`split` 后捕获组位置即 CJK 连续段。
_CJK_SEG_RE = re.compile(r"([{0}]+)".format(_CJK_RANGES))

#: jieba 可选依赖。导入失败/环境缺失 → None，tokenize 走 2-gram 降级。
try:  # pragma: no cover - 分支覆盖由环境决定
    import jieba  # type: ignore
    _JIEBA = jieba
except Exception:
    _JIEBA = None


def has_jieba() -> bool:
    """当前进程是否加载了 jieba（测试/降级探测用）。"""
    return _JIEBA is not None


def cjk_tokens(seg: str, expand_ngram: bool = True) -> List[str]:
    """CJK 连续段展开：整词 + (jieba 词 | 2-gram)。

    参数:
        expand_ngram: True（默认）时对段做切词展开（jieba 词或 2-gram
            fallback）；False 时仅保留整段（供检索打分路径使用——
            查询侧展开短词会破坏既有"跨义词零命中"契约，整段+英文词
            粒度与 str.split() 等价且稳定）。
    """
    out = [seg]
    if not expand_ngram:
        return out
    if _JIEBA is not None:
        try:
            words = [w for w in _JIEBA.lcut(seg) if w and w.strip()]
            if words:
                out.extend(w for w in words if w not in out)
                return out
        except Exception:
            pass  # jieba 运行期异常 → 2-gram 降级
    if len(seg) > 2:
        out.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return list(dict.fromkeys(out))


def tokenize(text: str, lower: bool = True,
              expand_ngram: bool = True) -> List[str]:
    """统一轻量分词入口。

    参数:
        text: 原始查询/字段文本。
        lower: 是否先小写（默认 True；调用方已小写时传 True 幂等）。
        expand_ngram: 是否对 CJK 连续段展开切词（jieba 词 / 2-gram）。
            True（默认）供分词能力完整使用（含降级路径验证）；False
            仅保留整段（英文词 + CJK 整段），供检索打分/意图路由使用，
            保证既有"跨义词零命中"等契约不回归。

    返回:
        保序去重的 token 列表。纯英文/数字输入与
        `(text.strip()).split()` 完全一致；含 CJK 且 expand_ngram=True
        时每个连续中文段额外展开整词 + jieba 词（无 jieba 时为 2-gram）。
    """
    s = ((text or "").strip().lower() if lower else (text or "").strip())
    if not s:
        return []
    tokens: List[str] = []
    for piece in _CJK_SEG_RE.split(s):
        if not piece:
            continue
        if _CJK_SEG_RE.fullmatch(piece):
            tokens.extend(cjk_tokens(piece, expand_ngram))
        else:
            tokens.extend(piece.split())
    return list(dict.fromkeys(tokens))
