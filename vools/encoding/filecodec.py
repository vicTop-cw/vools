"""
字符编码文件编解码（filecodec）

统一解决 agent 常见的 GBK / UTF-8 / UTF-16 / BOM 编码乱象，**纯标准库、跨平台**。

动机：agent 在不同平台读写文件时经常撞上编码问题——
- Windows PowerShell 5.1 默认按系统代码页（本机 `gb2312`）解码无 BOM 文本；
- Windows 记事本保存中文默认 UTF-16 LE / UTF-8 BOM；
- Python 侧 `open(..., encoding='utf-8')` 硬编码，遇 GBK / BOM / UTF-16 直接
  ``UnicodeDecodeError``；
- 产物写入时编码/BOM 与读取方预期不一致，导致乱码或解析失败。

本模块提供统一入口：探测 → 读取 → 写入 → 转换，**绝不抛解码异常**（失败时兜底
``latin-1``，任何字节都能解），并把编码名 / BOM / 置信度显式交给调用方。

核心 API：
- :func:`detect`          探测字节编码（BOM 嗅探 + UTF-8 严格校验 + 中文编码试探）
- :func:`read_text`       自动探测编码读取文件（剥离 BOM）
- :func:`write_text`      统一编码写入文件（可选 BOM）
- :func:`convert`         文件编码转换（源 → 目标，可选 BOM）
- :func:`sniff_stdio`     跨平台标准流编码探测
"""

# 刻意不使用延迟注解的 __future__ 开关（annotations）：核心 vools 支持
# Python 3.6，而该 future 语句是 3.7 才引入的（曾因这里误用导致包在 3.6
# import 即 SyntaxError）。本模块注解全部用 typing.Dict/List/Optional/Tuple，
# 3.6 原生即可求值，无需延迟注解。
import codecs
import os
import sys
from typing import Dict, List, Optional, Tuple

__all__ = [
    "BOM_SIGNATURES",
    "ENCODING_ALIASES",
    "detect",
    "read_text",
    "read_bytes",
    "write_text",
    "convert",
    "strip_bom",
    "guess_candidates",
    "normalize_encoding",
    "sniff_stdio",
    "SUPPORTED",
]

# ─── BOM 签名表 ───────────────────────────────────────────────────────────────
# (BOM 字节, 实际编码名, BOM 名称)。顺序重要：先长后短，UTF-32 在 UTF-16 之前。
BOM_SIGNATURES: List[Tuple[bytes, str, str]] = [
    (codecs.BOM_UTF32_LE, "utf-32-le", "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be", "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8", "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16-le", "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be", "utf-16-be"),
]

# 编码名 → BOM 字节（写入时用）
_BOM_BY_ENCODING: Dict[str, bytes] = {
    "utf-8": codecs.BOM_UTF8,
    "utf-8-sig": codecs.BOM_UTF8,
    "utf-16": codecs.BOM_UTF16_LE,   # 按平台字节序，Windows 为 LE
    "utf-16-le": codecs.BOM_UTF16_LE,
    "utf-16-be": codecs.BOM_UTF16_BE,
    "utf-32": codecs.BOM_UTF32_LE,
    "utf-32-le": codecs.BOM_UTF32_LE,
    "utf-32-be": codecs.BOM_UTF32_BE,
}

# 编码名统一映射（小写、去下划线/点）
ENCODING_ALIASES: Dict[str, str] = {
    "utf8": "utf-8",
    "utf_8": "utf-8",
    "utf-8-sig": "utf-8-sig",
    "utf_8_sig": "utf-8-sig",
    "utf-16": "utf-16",
    "utf-16-le": "utf-16-le",
    "utf_16_le": "utf-16-le",
    "utf-16-be": "utf-16-be",
    "utf_16_be": "utf-16-be",
    "gb2312": "gb2312",
    "gbk": "gbk",
    "gb18030": "gb18030",
    "gb_18030": "gb18030",
    "big5": "big5",
    "big5-hkscs": "big5-hkscs",
    "shift_jis": "shift-jis",
    "shift-jis": "shift-jis",
    "cp932": "cp932",
    "euc-jp": "euc-jp",
    "euc_kr": "euc-kr",
    "euc-kr": "euc-kr",
    "cp1252": "cp1252",
    "windows-1252": "cp1252",
    "latin1": "latin-1",
    "latin-1": "latin-1",
    "iso-8859-1": "latin-1",
}

# 本模块探测时按此顺序试探（越靠前越优先）
_DETECT_ORDER: List[str] = [
    "utf-8", "gb18030", "gbk", "big5", "shift-jis", "cp932",
    "euc-kr", "cp1252", "latin-1",
]

# 编码检测取样上限（字节）：探测只看前缀，避免大文件全量解码
_SAMPLE_LIMIT = 64 * 1024

# 支持的编码（文档用）
SUPPORTED: List[str] = sorted(set(_DETECT_ORDER) | set(_BOM_BY_ENCODING))


# ─── 基础工具 ─────────────────────────────────────────────────────────────────


def normalize_encoding(name: str) -> str:
    """规范化编码名，返回本模块统一写法。未知则原样小写返回。

    >>> normalize_encoding("UTF8")
    'utf-8'
    >>> normalize_encoding("GBK")
    'gbk'
    """
    key = str(name).strip().lower()
    if key in ENCODING_ALIASES:
        return ENCODING_ALIASES[key]
    return key


def strip_bom(raw: bytes) -> Tuple[bytes, Optional[str]]:
    """剥离 BOM，返回 ``(剥离后的字节, BOM 编码名或 None)``。

    >>> raw = codecs.BOM_UTF8 + "中文".encode("utf-8")
    >>> body, bom = strip_bom(raw)
    >>> bom
    'utf-8-sig'
    >>> body.decode("utf-8")
    '中文'
    """
    for bom, _enc, bom_name in BOM_SIGNATURES:
        if raw.startswith(bom):
            return raw[len(bom):], bom_name
    return raw, None


def guess_candidates(raw: bytes) -> List[str]:
    """按置信度从高到低返回候选编码列表（不含 BOM 情形）。"""
    out: List[str] = []
    for enc in _DETECT_ORDER:
        try:
            raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        out.append(enc)
    return out


# 打分用的「合理字符」区间：控制字符、替换字符、C1 控制区、私用区都会拉低分。
_CONTROL_BLOCK = set(range(0x00, 0x20)) - {0x09, 0x0A, 0x0D}  # 除 \t \n \r
_C1_BLOCK = set(range(0x7F, 0xA0))
_PRIVATE_BLOCK = set(range(0xE000, 0xF900)) | set(range(0xF0000, 0x110000))
_SURROGATE_BLOCK = set(range(0xD800, 0xE000))


def score_text(text: str) -> float:
    """对解码后的文本打分（0~1）：越高越像自然文本。

    判据：控制字符 / 替换字符 / 私用区 / 孤立代理项 会拉低分；汉字、常用字母、
    数字、空格、标点拉高分。用于区分「恰好能解」的多字节编码歧义（如 GB18030
    与 UTF-16 无 BOM、Big5 与 GBK 互相误判）。
    """
    if not text:
        return 0.0
    good = 0
    for ch in text:
        o = ord(ch)
        if o in _CONTROL_BLOCK or o in _C1_BLOCK or o in _PRIVATE_BLOCK:
            continue
        if o in _SURROGATE_BLOCK or ch == "\ufffd":
            continue
        good += 1
    return good / len(text)


def _probe_text(raw: bytes) -> List[Tuple[float, str]]:
    """对所有候选编码解码并打分，返回 ``(得分, 编码)`` 降序列表。"""
    scored: List[Tuple[float, str]] = []
    for enc in _DETECT_ORDER:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        scored.append((score_text(text), enc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


# ─── 探测 ─────────────────────────────────────────────────────────────────────


def detect(raw: bytes) -> Dict[str, object]:
    """探测字节编码。

    返回::

        {
            "encoding": "utf-8",        # 推荐编码名
            "bom": "utf-8-sig" | None,  # BOM 名称（无 BOM 为 None）
            "confidence": "high"|"medium"|"low"|"bom",
            "candidates": [...],        # 其余可解编码（降序）
            "score": 1.0,               # 文本可读性得分（多字节歧义时才出现）
            "size": 123,                # 原始字节数
        }

    判据：
    - BOM 嗅探命中 → ``confidence="bom"``（最可靠，直接采用）。
    - UTF-8 严格解码成功 → ``confidence="high"``。
    - UTF-16 无 BOM：试 utf-16-le/be 且可读性得分不低于多字节候选最高分，并
      要求**零字节比例高**（真实 UTF-16 含 ASCII 时高位多为 0x00；GBK 中文几乎
      不含 0x00）→ ``confidence="medium"``。纯中文的 UTF-16 无 BOM 与 GBK 本质上
      不可区分，可显式指定。
    - 其余多字节编码（GB18030/GBK/Big5/Shift-JIS…）按可读性打分选优 →
      ``confidence="medium"`` 或 ``"low"``。**注意**：GB18030 是 GBK/Big5 的
      超集，三者对同一份字节都可能解出「看似合理」的文本，故无法仅凭字节
      完全区分；中文场景默认报 GB18030，``candidates`` 列出其余可能，调用方
      若已知编码请显式传给 :func:`read_text`。
    - 全失败 → ``latin-1`` 兜底（任何字节都可解），``confidence="low"``。
    """
    result: Dict[str, object] = {
        "encoding": "latin-1",
        "bom": None,
        "confidence": "low",
        "candidates": [],
        "size": len(raw),
    }

    if not raw:
        return result

    # 1) BOM 嗅探
    _body, bom_name = strip_bom(raw)
    if bom_name:
        enc = next((e for _b, e, _n in BOM_SIGNATURES if _n == bom_name), "utf-8")
        result.update({"encoding": enc, "bom": bom_name, "confidence": "bom"})
        return result

    # 取样：编码检测只看前 64KB，避免大文件全量解码
    sample = raw[: _SAMPLE_LIMIT]

    # 2) UTF-8 严格校验（UTF-8 结构严格，成功即高置信）
    try:
        sample.decode("utf-8")
        result.update({"encoding": "utf-8", "confidence": "high"})
        return result
    except UnicodeDecodeError:
        pass

    # 3) 多字节候选打分：GB18030 是 GBK/Big5 超集，单靠「能否解码」无法区分，
    #    用可读性得分挑最像自然文本的那个；中文场景下 GB18030 仍是默认偏好。
    scored = _probe_text(sample)
    best_score, best_enc = (scored[0] if scored else (0.0, None))

    # 4) UTF-16 无 BOM：试 utf-16-le/be，若可读性得分不低于多字节候选最高分，
    #    且**零字节比例高**（真实 UTF-16 含 ASCII 时高位字节多为 0x00；GBK/GB18030
    #    中文字节几乎不含 0x00），则判为 UTF-16。纯中文的 UTF-16 无 BOM 文本
    #    （罕见，Windows 记事本默认写 UTF-16 都会带 BOM）与 GBK 本质上不可区分，
    #    调用方可显式指定。
    if len(raw) >= 4 and len(raw) % 2 == 0:
        half = len(sample) // 2
        for probe, cand, off in (("utf-16-le", "utf-16-le", 1),
                                 ("utf-16-be", "utf-16-be", 0)):
            try:
                s16_text = raw.decode(probe)
            except (UnicodeDecodeError, LookupError):
                continue
            s16 = score_text(s16_text)
            if s16 <= 0.85 or s16 < best_score - 0.02:
                continue
            zeros = sum(1 for i in range(0, len(sample), 2) if sample[i + off] == 0)
            zero_ratio = (zeros / half) if half else 0.0
            if zero_ratio < 0.25:
                continue
            result.update({
                "encoding": cand,
                "confidence": "medium",
                "candidates": [e for _s, e in scored],
                "score": s16,
            })
            return result

    # 5) 多字节候选落定
    if scored:
        candidates = [e for _s, e in scored]
        if best_score > 0.95:
            result.update({
                "encoding": best_enc,
                "confidence": "medium",
                "candidates": candidates,
                "score": best_score,
            })
        else:
            # 得分低：可能是二进制或高损文本，优先报中文编码（最常需求）
            pref = next((c for c in candidates if c in ("gb18030", "gbk")),
                        candidates[0])
            result.update({
                "encoding": pref,
                "confidence": "low",
                "candidates": candidates,
                "score": best_score,
            })
        return result

    # 6) latin-1 兜底
    result["candidates"] = ["latin-1"]
    return result


# ─── 读写 ─────────────────────────────────────────────────────────────────────


def read_bytes(path: str) -> bytes:
    """读取原始字节（不存在则抛 FileNotFoundError）。"""
    with open(path, "rb") as f:
        return f.read()


def read_text(path: str, encoding: Optional[str] = None) -> str:
    """读取文件并自动探测编码，**绝不抛解码异常**。

    - ``encoding`` 为 None 时自动探测；指定时按该编码解码。
    - 自动探测时剥离 BOM，且失败时兜底 ``latin-1``（任何字节都能解）。
    - 返回解码后的文本，同时可通过 :func:`detect` 单独获取编码信息。

    >>> import tempfile, os
    >>> p = tempfile.mktemp(suffix=".txt")
    >>> _ = write_text(p, "中文测试", encoding="gbk")  # GBK 写入
    >>> read_text(p)                                  # 自动探测读出
    '中文测试'
    >>> os.remove(p)
    """
    raw = read_bytes(path)

    if encoding:
        enc = normalize_encoding(encoding)
        return raw.decode(enc, errors="replace")

    info = detect(raw)
    enc = str(info["encoding"])
    body, _bom = strip_bom(raw)
    return body.decode(enc, errors="replace")


def write_text(path: str, text: str, encoding: str = "utf-8", bom: bool = False) -> str:
    """统一编码写入文件，返回实际使用的编码名。

    - 默认 ``utf-8`` 无 BOM（跨平台最安全）。
    - ``bom=True`` 时按编码写入对应 BOM（utf-8 → UTF-8 BOM；utf-16 → LE BOM）。
    - ``utf-16``/``utf-32`` 平台字节序编码在 ``str.encode`` 时 Python 会自动加
      平台 BOM，与 ``bom=True`` 叠加会重复，故需 BOM 时改用显式 ``-le`` 字节序。
    - 自动创建父目录。

    >>> import tempfile, os
    >>> p = tempfile.mktemp(suffix=".txt")
    >>> write_text(p, "中文", encoding="gbk")          # 返回实际编码名
    'gbk'
    >>> os.remove(p)
    """
    enc = normalize_encoding(encoding)
    if bom and enc in ("utf-16", "utf-32"):
        # Python 的 utf-16/utf-32 codec 自带平台 BOM，需 BOM 时改显式 LE
        enc = enc + "-le"
    data = text.encode(enc, errors="replace")
    if bom:
        bom_bytes = _BOM_BY_ENCODING.get(enc)
        if bom_bytes:
            data = bom_bytes + data
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return enc


def convert(src: str, dst: str, encoding: str = "utf-8", bom: bool = False,
            in_encoding: Optional[str] = None) -> Dict[str, object]:
    """文件编码转换：把 ``src`` 按探测/指定编码读入，按 ``dst`` 编码写出。

    返回::

        {
            "src": "a.txt",
            "dst": "b.txt",
            "from": "gbk",
            "to": "utf-8",
            "bytes": 42,
            "chars": 20,
        }
    """
    info = detect(read_bytes(src)) if not in_encoding else {
        "encoding": normalize_encoding(in_encoding), "bom": None}
    text = read_text(src, encoding=in_encoding)
    to_enc = write_text(dst, text, encoding=encoding, bom=bom)
    return {
        "src": src,
        "dst": dst,
        "from": str(info["encoding"]),
        "to": to_enc,
        "bytes": os.path.getsize(dst),
        "chars": len(text),
    }


# ─── 跨平台标准流编码探测 ─────────────────────────────────────────────────────


def sniff_stdio() -> Dict[str, str]:
    """探测当前进程标准流编码（跨平台）。

    Windows 下 Python 默认 ``locale.getpreferredencoding()`` 常为 ``cp936``
    （GBK），而终端可能期待 UTF-8；这里显式给出各方编码，便于调用方决定
    何时显式 ``sys.stdout.reconfigure(encoding='utf-8')``。

    返回::

        {
            "stdin": "utf-8",
            "stdout": "utf-8",
            "stderr": "utf-8",
            "filesystem": "utf-8",
            "preferred": "cp936",
        }
    """
    def _enc(stream) -> str:
        try:
            return normalize_encoding(stream.encoding or "utf-8")
        except Exception:
            return "utf-8"

    try:
        preferred = normalize_encoding(locale_preferred())
    except Exception:
        preferred = "utf-8"
    return {
        "stdin": _enc(sys.stdin),
        "stdout": _enc(sys.stdout),
        "stderr": _enc(sys.stderr),
        "filesystem": normalize_encoding(sys.getfilesystemencoding() or "utf-8"),
        "preferred": preferred,
    }


def locale_preferred() -> str:
    """取 locale 偏好编码（等价 ``locale.getpreferredencoding(False)`` 但更稳健）。"""
    try:
        import locale
        return locale.getpreferredencoding(False)
    except Exception:
        return "utf-8"


if __name__ == "__main__":  # pragma: no cover - 手动自检
    import doctest
    print(doctest.testmod())