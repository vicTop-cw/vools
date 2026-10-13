"""
测试字符编码文件编解码（filecodec）：GBK/UTF-8/UTF-16/BOM 探测、读写、转换。

覆盖目标（对应 agent 编码痛点）：
- 读取带 BOM 的 UTF-8/UTF-16/UTF-32 文件不再崩；
- 读取 GBK / GB18030 中文文件自动识别；
- 写入可显式控制编码与 BOM（跨平台产物一致性）；
- 任意字节都不抛解码异常（兜底 latin-1）。
"""

import codecs
import os
import sys

import pytest

from vools.encoding import filecodec
from vools.encoding.filecodec import (
    BOM_SIGNATURES,
    SUPPORTED,
    convert,
    detect,
    normalize_encoding,
    read_bytes,
    read_text,
    sniff_stdio,
    strip_bom,
    write_text,
)

ZH = "中文测试 hello world 123"
ZH_TW = "中文測試 你好世界"
ZH_JA = "日本語のテスト"


# ─── 编码名规范化 ─────────────────────────────────────────────────────────────


def test_normalize_encoding_aliases():
    assert normalize_encoding("UTF8") == "utf-8"
    assert normalize_encoding("utf_8") == "utf-8"
    assert normalize_encoding("GBK") == "gbk"
    assert normalize_encoding("gb2312") == "gb2312"
    assert normalize_encoding("Shift_JIS") == "shift-jis"
    assert normalize_encoding("latin1") == "latin-1"


def test_supported_nonempty():
    assert SUPPORTED
    for e in ("utf-8", "utf-16-le", "gb18030", "gbk", "big5", "shift-jis"):
        assert e in SUPPORTED


# ─── BOM 嗅探（最可靠路径）────────────────────────────────────────────────────


@pytest.mark.parametrize("bom,enc,content", [
    (codecs.BOM_UTF8, "utf-8", ZH),
    (codecs.BOM_UTF16_LE, "utf-16-le", ZH),
    (codecs.BOM_UTF16_BE, "utf-16-be", ZH),
    (codecs.BOM_UTF32_LE, "utf-32-le", ZH),
    (codecs.BOM_UTF32_BE, "utf-32-be", ZH),
])
def test_detect_bom_sniff(bom, enc, content):
    raw = bom + content.encode(enc.replace("-le", "-le").replace("-be", "-be"))
    # 部分编码（如 utf-32）BOM 表与编码名一致
    if enc.startswith("utf-16") or enc.startswith("utf-32"):
        raw = bom + content.encode(enc)
    info = detect(raw)
    assert info["confidence"] == "bom"
    assert info["encoding"] == enc
    assert info["bom"] is not None


def test_detect_utf8_bom():
    raw = codecs.BOM_UTF8 + ZH.encode("utf-8")
    info = detect(raw)
    assert info["bom"] == "utf-8-sig"
    assert info["encoding"] == "utf-8"


# ─── UTF-8 无 BOM ─────────────────────────────────────────────────────────────


def test_detect_utf8_plain_high_confidence():
    info = detect(ZH.encode("utf-8"))
    assert info["encoding"] == "utf-8"
    assert info["confidence"] == "high"
    assert info["bom"] is None


def test_detect_ascii_is_utf8():
    info = detect(b"plain ascii 123\n")
    assert info["encoding"] == "utf-8"
    assert info["confidence"] == "high"


# ─── UTF-16 无 BOM 启发式 ─────────────────────────────────────────────────────


def test_detect_utf16_le_no_bom():
    # 中英文混合 → 高位零字节多，启发式命中
    info = detect(ZH.encode("utf-16-le"))
    assert info["encoding"] == "utf-16-le"


def test_detect_utf16_be_no_bom():
    info = detect(ZH.encode("utf-16-be"))
    # BE 与 LE 都是候选，启发式按零字节分布挑 LE/BE；至少识别为 utf-16 族
    assert info["encoding"].startswith("utf-16")


# ─── 中文编码（GBK/GB18030）──────────────────────────────────────────────────


def test_detect_gbk_defaults_gb18030():
    info = detect(ZH.encode("gbk"))
    assert info["encoding"] == "gb18030"
    assert info["confidence"] in ("medium", "low")
    assert "gb18030" in info["candidates"]


def test_detect_gb18030():
    info = detect(ZH.encode("gb18030"))
    assert info["encoding"] == "gb18030"


def test_detect_big5_shiftjis_report_candidates():
    # GB18030 是 Big5/Shift-JIS 的超集，单凭字节无法完全区分 → 必须报 candidates
    for enc, text in (("big5", ZH_TW), ("shift-jis", ZH_JA)):
        raw = text.encode(enc)
        info = detect(raw)
        assert info["candidates"], "多字节编码歧义时必须给出候选列表"
        # 显式指定编码读取应准确
        body, _bom = strip_bom(raw)
        assert body.decode(enc) == text


# ─── 空 / 异常输入 ────────────────────────────────────────────────────────────


def test_detect_empty_bytes():
    info = detect(b"")
    assert info["encoding"] == "latin-1"
    assert info["confidence"] == "low"
    assert info["size"] == 0


def test_detect_never_raises_on_random_bytes():
    # 任意随机字节都不抛异常（兜底 latin-1）
    for n in (0, 1, 7, 64, 1024, 65536):
        info = detect(os.urandom(n))
        assert isinstance(info["encoding"], str)


# ─── strip_bom ────────────────────────────────────────────────────────────────


def test_strip_bom_utf8():
    raw = codecs.BOM_UTF8 + "中文".encode("utf-8")
    body, bom = strip_bom(raw)
    assert bom == "utf-8-sig"
    assert body.decode("utf-8") == "中文"


def test_strip_bom_none():
    body, bom = strip_bom(b"hello")
    assert bom is None
    assert body == b"hello"


# ─── 读写（tmp_path）──────────────────────────────────────────────────────────


@pytest.mark.parametrize("enc,text", [
    ("utf-8", ZH),
    ("gbk", ZH),
    ("gb18030", ZH),
    ("big5", ZH_TW),
    ("shift-jis", ZH_JA),
])
def test_read_text_roundtrip_explicit_encoding(tmp_path, enc, text):
    """显式指定编码时读写应精确往返。"""
    p = tmp_path / f"t.{enc}.txt"
    write_text(str(p), text, encoding=enc)
    got = read_text(str(p), encoding=enc)
    assert got == text


def test_read_text_auto_detect_gbk(tmp_path):
    """自动探测应识别 GBK 中文文件。"""
    p = tmp_path / "zh_gbk.txt"
    write_text(str(p), ZH, encoding="gbk")
    got = read_text(str(p))
    assert got == ZH


def test_read_text_auto_detect_utf8_bom(tmp_path):
    p = tmp_path / "zh_bom.txt"
    write_text(str(p), ZH, encoding="utf-8", bom=True)
    raw = read_bytes(str(p))
    assert raw.startswith(codecs.BOM_UTF8)
    assert read_text(str(p)) == ZH


def test_read_text_auto_detect_utf16_bom(tmp_path):
    p = tmp_path / "zh_u16.txt"
    write_text(str(p), ZH, encoding="utf-16", bom=True)
    assert read_text(str(p)) == ZH


def test_read_text_never_raises_on_binary(tmp_path):
    """读取任意二进制文件不抛解码异常（兜底 latin-1）。"""
    p = tmp_path / "bin.dat"
    p.write_bytes(os.urandom(4096))
    got = read_text(str(p))
    assert isinstance(got, str)


def test_read_text_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_text(str(tmp_path / "nope.txt"))


def test_write_text_creates_parent_dir(tmp_path):
    p = tmp_path / "deep" / "nested" / "x.txt"
    write_text(str(p), "hi")
    assert p.exists()
    assert p.read_text(encoding="utf-8") == "hi"


def test_write_text_returns_encoding(tmp_path):
    p = tmp_path / "a.txt"
    assert write_text(str(p), "x", encoding="utf-16-le") == "utf-16-le"


@pytest.mark.parametrize("enc,bom_bytes", [
    ("utf-8", codecs.BOM_UTF8),
    ("utf-16-le", codecs.BOM_UTF16_LE),
    ("utf-16-be", codecs.BOM_UTF16_BE),
])
def test_write_text_bom_roundtrip(tmp_path, enc, bom_bytes):
    p = tmp_path / f"bom_{enc}.txt"
    write_text(str(p), ZH, encoding=enc, bom=True)
    raw = read_bytes(str(p))
    assert raw.startswith(bom_bytes)
    # 有 BOM → 自动探测应命中
    info = detect(raw)
    assert info["bom"] is not None


# ─── convert ──────────────────────────────────────────────────────────────────


def test_convert_gbk_to_utf8(tmp_path):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    write_text(str(src), "你好世界", encoding="gbk")
    res = convert(str(src), str(dst), encoding="utf-8")
    assert res["to"] == "utf-8"
    assert res["chars"] == 4
    assert read_text(str(dst)) == "你好世界"


def test_convert_with_bom(tmp_path):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    write_text(str(src), ZH, encoding="gbk")
    res = convert(str(src), str(dst), encoding="utf-8", bom=True)
    assert read_bytes(str(dst)).startswith(codecs.BOM_UTF8)


def test_convert_explicit_in_encoding(tmp_path):
    src = tmp_path / "big5.txt"
    dst = tmp_path / "out.txt"
    write_text(str(src), ZH_TW, encoding="big5")
    res = convert(str(src), str(dst), encoding="utf-8", in_encoding="big5")
    assert res["from"] == "big5"
    assert read_text(str(dst)) == ZH_TW


# ─── sniff_stdio ──────────────────────────────────────────────────────────────


def test_sniff_stdio_keys():
    info = sniff_stdio()
    for k in ("stdin", "stdout", "stderr", "filesystem", "preferred"):
        assert k in info
        assert isinstance(info[k], str)


# ─── doctest ──────────────────────────────────────────────────────────────────


def test_doctest():
    import doctest
    results = doctest.testmod(filecodec, verbose=False)
    assert results.failed == 0


# ─── 导出面 ───────────────────────────────────────────────────────────────────


def test_public_api_exports():
    """顶层 `vools` 应能直接拿到 filecodec 主函数。"""
    import vools
    for name in ("detect", "read_text", "write_text", "convert", "sniff_stdio"):
        assert hasattr(vools, name), f"vools.{name} 缺失"


def test_bom_signatures_ordering():
    """BOM 表顺序必须长在前短在后（UTF-32 先于 UTF-16，UTF-16 先于 UTF-8）。"""
    lens = [len(b) for b, _e, _n in BOM_SIGNATURES]
    assert lens == sorted(lens, reverse=True)