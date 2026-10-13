"""filecodec 编码探测/读写边界测试（OCR 寻虫轮新增）。

detect() 的 BOM 嗅探 / UTF-8 严格校验 / UTF-16 无 BOM 零字节判据 /
GBK·GB18030·Big5 多字节歧义打分此前只有 4 个 doctest，没有 pytest 覆盖。
本文件用确定性样本锁定关键不变量。
"""

import codecs
import os
import tempfile

import pytest

from vools.encoding import filecodec as fc


# ---------- BOM ----------

@pytest.mark.parametrize("payload,expected", [
    (codecs.BOM_UTF8 + "中文".encode("utf-8"), "utf-8"),
    (codecs.BOM_UTF16_LE + "中文".encode("utf-16-le"), "utf-16-le"),
    (codecs.BOM_UTF16_BE + "中文".encode("utf-16-be"), "utf-16-be"),
])
def test_detect_bom(payload, expected):
    info = fc.detect(payload)
    assert info["bom"] is not None
    assert info["encoding"] == expected
    assert info["confidence"] == "bom"


def test_detect_empty_bytes():
    info = fc.detect(b"")
    assert info["encoding"] == "latin-1"
    assert info["size"] == 0


# ---------- UTF-8 ----------

def test_detect_plain_utf8():
    info = fc.detect("hello world 你好".encode("utf-8"))
    assert info["encoding"] == "utf-8"
    assert info["confidence"] == "high"


def test_detect_pure_ascii_is_utf8():
    info = fc.detect(b"plain ascii text, no bom here")
    assert info["encoding"] == "utf-8"
    assert info["confidence"] == "high"


# ---------- GBK 中文 ----------

def test_read_gbk_roundtrip(tmp_path):
    p = str(tmp_path / "g.txt")
    text = "这是一段 GBK 中文测试文本，包含标点：你好，世界！"
    fc.write_text(p, text, encoding="gbk")
    assert fc.read_text(p) == text


def test_detect_gbk_chinese_is_chinese_family(tmp_path):
    raw = "中文编码自动探测测试内容".encode("gbk")
    info = fc.detect(raw)
    # 必须落在中文编码族，绝不能误判成 latin-1
    assert info["encoding"] in ("gb18030", "gbk", "big5", "utf-16-le", "utf-16-be")


# ---------- BOM strip + read 一致性 ----------

@pytest.mark.parametrize("encname", ["utf-8", "utf-16-le", "utf-16-be"])
def test_read_text_strips_bom(tmp_path, encname):
    p = str(tmp_path / ("b_" + encname + ".txt"))
    text = "带BOM的文本 ABC 123"
    fc.write_text(p, text, encoding=encname, bom=True)
    out = fc.read_text(p)
    assert not out.startswith("\ufeff")
    assert out == text


# ---------- write/convert ----------

def test_write_returns_normalized_encoding(tmp_path):
    p = str(tmp_path / "x.txt")
    used = fc.write_text(p, "abc", encoding="UTF8")
    assert used == "utf-8"


def test_convert_gbk_to_utf8(tmp_path):
    src = str(tmp_path / "s.txt")
    dst = str(tmp_path / "d.txt")
    text = "转换测试 convert"
    fc.write_text(src, text, encoding="gbk")
    rep = fc.convert(src, dst, encoding="utf-8")
    assert rep["from"] in ("gb18030", "gbk")
    assert rep["to"] == "utf-8"
    assert open(dst, "rb").read().decode("utf-8") == text


def test_never_raises_on_garbage_bytes():
    """任意非法字节都不应让 read_text 崩（latin-1/errors=replace 兜底）。"""
    p = os.path.join(tempfile.gettempdir(), "_fc_garbage.bin")
    with open(p, "wb") as f:
        f.write(bytes(range(256)) * 4)
    try:
        out = fc.read_text(p)
        assert isinstance(out, str)
    finally:
        os.remove(p)
