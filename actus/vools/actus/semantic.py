"""轻量语义相似度计算（提升计划 F1：语义检索）。

设计目标：
- 零硬依赖：TF-IDF + 余弦相似度全部用标准库实现，任何环境开箱可用；
- 优雅降级：可选 Sentence-Transformer 嵌入（通过 `try_load_embedder` 探测），
  模型缺失/导入失败时自动回退到 TF-IDF 路径，绝不抛异常；
- 与关键词打分正交：`SemanticScorer` 只负责给出「查询 ↔ 动作文档」的
  0~1 语义相似分，融合/权重/开关逻辑由 registry 层决策。
"""

import math
import re
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = ["SemanticScorer", "try_load_embedder"]

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    """轻量分词：英文/数字按单词，CJK 文本切 2-gram 并保留整词。

    - 英文 token：小写保留（如 'web', 'page'）；
    - 中文 token：长度 >1 时同时产出整词与 2-gram（如 '监控' 与
      '监控文件夹' -> '监控','文件夹','监控文','控文件','件夹'），
      使"监控文件夹"与"监控 文件夹"能互相命中；
    - 单字符 token 丢弃（噪声）。
    """
    tokens: List[str] = []
    for m in _TOKEN_RE.finditer((text or "").lower()):
        tok = m.group(0)
        if len(tok) < 2:
            continue
        tokens.append(tok)
        if len(tok) > 2 and _CJK_RE.search(tok):
            tokens.extend(tok[i:i + 2] for i in range(len(tok) - 1))
    return tokens


class SemanticScorer:
    """TF-IDF + 余弦相似度的轻量语义打分器。

    用法：
        1. `build(docs)`：docs 为 {action_id: 归一化文本}，构建 TF-IDF 词表；
        2. `scores(query)`：返回 {action_id: 0~1 归一化语义分}；
        3. 可选 `embedder`：预留 Sentence-Transformer 兼容接口，
           传入后优先用嵌入向量做余弦（见 `try_load_embedder`），
           为 None 时走内置 TF-IDF 路径。
    """

    def __init__(self, embedder: Optional[object] = None) -> None:
        self.embedder = embedder
        self._doc_ids: List[str] = []
        self._tf: List[Counter] = []          # 每篇文档的词频
        self._idf: Dict[str, float] = {}      # 词 → idf 权重
        self._built: bool = False
        self._emb_docs: Optional[List[object]] = None  # embedder 文档向量缓存

    def build(self, docs: Dict[str, str]) -> "SemanticScorer":
        """用 {action_id: 文本} 构建 TF-IDF 模型。可重复调用（重建）。

        若配置了 embedder（可选 Sentence-Transformer），同时尝试编码文档
        向量；编码失败（模型损坏/内存等）自动忽略，仅走 TF-IDF 路径——
        优雅降级不抛异常。
        """
        self._doc_ids = list(docs.keys())
        df: Counter = Counter()
        self._tf = []
        texts = [docs.get(aid, "") for aid in self._doc_ids]
        for text in texts:
            counts = Counter(_tokenize(text))
            self._tf.append(counts)
            for term in counts:
                df[term] += 1
        n = len(self._doc_ids)
        self._idf = {
            term: math.log((1.0 + n) / (1.0 + freq)) + 1.0
            for term, freq in df.items()
        }
        self._emb_docs = None
        if self.embedder is not None:
            try:
                self._emb_docs = list(self.embedder.encode(texts))
            except Exception:
                self._emb_docs = None  # 降级：忽略嵌入，走 TF-IDF
        self._built = True
        return self

    # ── 内部：文档向量 / 查询向量 ──
    def _doc_vec(self, idx: int) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for term, freq in self._tf[idx].items():
            out[term] = freq * self._idf.get(term, 0.0)
        return out

    def _query_vec(self, query: str) -> Dict[str, float]:
        counts = Counter(_tokenize(query))
        out: Dict[str, float] = {}
        for term, freq in counts.items():
            if term in self._idf:
                out[term] = freq * self._idf[term]
        return out

    @staticmethod
    def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        denom = math.sqrt(sum(v * v for v in a.values()) *
                          sum(v * v for v in b.values()))
        if denom == 0.0:
            return 0.0
        return sum(a.get(k, 0.0) * v for k, v in b.items()) / denom

    def _embedding_cosine(self, a: object, b: object) -> float:
        """嵌入向量余弦（兼容 numpy 数组 / list / tensor）。"""
        try:
            import numpy as np
            va = np.asarray(a, dtype=float).reshape(-1)
            vb = np.asarray(b, dtype=float).reshape(-1)
            denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
            if denom == 0.0:
                return 0.0
            return float(np.dot(va, vb) / denom)
        except Exception:
            return 0.0

    def _embedding_scores(self, query: str) -> Dict[str, float]:
        """embedder 路径：查询编码后与文档向量做余弦，min-max 归一化。"""
        if not self._emb_docs:
            return {}
        try:
            qvec = self.embedder.encode([query])[0]
        except Exception:
            return {}  # 查询编码失败 → 降级为空（调用方按关键词路径回退）
        raw = [self._embedding_cosine(qvec, dv) for dv in self._emb_docs]
        lo, hi = min(raw), max(raw)
        if hi - lo < 1e-9:
            return {aid: 0.0 for aid in self._doc_ids}
        span = hi - lo
        return {
            aid: round((v - lo) / span, 4)
            for aid, v in zip(self._doc_ids, raw)
        }

    def scores(self, query: str) -> Dict[str, float]:
        """返回 {action_id: 0~1 语义分}（min-max 归一化）。未 build 返回 {}。

        embedder 可用且文档向量构建成功时走嵌入余弦；否则走内置 TF-IDF
        余弦——两条路径均归一化到 0~1，融合层无感知。
        """
        if not self._built or not (query or "").strip():
            return {}
        if self.embedder is not None and self._emb_docs:
            return self._embedding_scores(query)
        qvec = self._query_vec(query)
        raw = [
            self._cosine(qvec, self._doc_vec(i))
            for i in range(len(self._doc_ids))
        ]
        if not raw:
            return {}
        lo, hi = min(raw), max(raw)
        if hi - lo < 1e-9:
            return {aid: 0.0 for aid in self._doc_ids}
        span = hi - lo
        return {
            aid: round((v - lo) / span, 4)
            for aid, v in zip(self._doc_ids, raw)
        }

    def as_dict(self) -> dict:
        """序列化模型摘要（调试/诊断用）。"""
        return {
            "docs": len(self._doc_ids),
            "terms": len(self._idf),
            "embedder": None if self.embedder is None else type(self.embedder).__name__,
            "built": self._built,
        }


def try_load_embedder(model_name: Optional[str] = None) -> Optional[object]:
    """尝试加载可选 Sentence-Transformer 嵌入器；失败优雅降级返回 None。

    调用方拿到 None 时应使用内置 TF-IDF 路径（`SemanticScorer(embedder=None)`）。
    模型缺失 / 依赖未安装 / 加载失败 均不抛异常。
    """
    try:
        from sentence_transformers import SentenceTransformer  # 可选依赖
    except Exception:
        return None
    try:
        return SentenceTransformer(model_name or "paraphrase-MiniLM-L6-v2")
    except Exception:
        return None
