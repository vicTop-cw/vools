# -*- coding: utf-8 -*-
"""回归测试：encoding.filecodec 输入校验缺口（BUG-515）。

修复前（全部裸错）：

    strip_bom("hello")        # TypeError: startswith first arg must be str or a
                              #   tuple of str, not bytes（实现细节外泄）
    detect("hello")           # 同上（detect 文档明确要求字节）
    write_text(path, None)    # AttributeError: 'NoneType' object has no attribute 'encode'

修复后：strip_bom/detect 要求 bytes/bytearray/memoryview（并统一转 bytes），
write_text 要求 str；错误都带参数名。
"""

import os
import tempfile

import pytest

import vools.encoding.filecodec as fc


@pytest.fixture()
def tmpdir():
    path = tempfile.mkdtemp(prefix="v515_")
    yield path
    import shutil
    shutil.rmtree(path, ignore_errors=True)


class TestStripBomValidation:
    @pytest.mark.parametrize("bad", ["hello", None, 123, [1]])
    def test_rejects_non_bytes(self, bad):
        with pytest.raises(TypeError) as ei:
            fc.strip_bom(bad)
        assert "raw" in str(ei.value)

    @pytest.mark.parametrize("raw", [
        b"\xef\xbb\xbfhi",
        bytearray(b"\xef\xbb\xbfhi"),
        memoryview(b"\xef\xbb\xbfhi"),
    ])
    def test_accepts_bytes_like(self, raw):
        body, bom = fc.strip_bom(raw)
        assert body == b"hi"
        assert bom == "utf-8-sig"

    def test_without_bom(self):
        assert fc.strip_bom(b"hello") == (b"hello", None)


class TestDetectValidation:
    @pytest.mark.parametrize("bad", ["hello", None, 123])
    def test_rejects_non_bytes(self, bad):
        with pytest.raises(TypeError) as ei:
            fc.detect(bad)
        assert "raw" in str(ei.value)

    def test_detects_utf8(self):
        info = fc.detect("中文".encode("utf-8"))
        assert info["encoding"] == "utf-8"
        assert info["confidence"] == "high"

    def test_detects_bom(self):
        info = fc.detect("\ufeffhi".encode("utf-8"))
        assert info["bom"] == "utf-8-sig"
        assert info["confidence"] == "bom"

    def test_empty_bytes_low_confidence(self):
        assert fc.detect(b"")["confidence"] == "low"


class TestWriteTextValidation:
    @pytest.mark.parametrize("bad", [None, 123, b"bytes"])
    def test_rejects_non_str(self, tmpdir, bad):
        with pytest.raises(TypeError) as ei:
            fc.write_text(os.path.join(tmpdir, "a.txt"), bad)
        assert "text" in str(ei.value)

    def test_roundtrip(self, tmpdir):
        path = os.path.join(tmpdir, "a.txt")
        assert fc.write_text(path, "中文") == "utf-8"
        assert fc.read_text(path) == "中文"

    def test_gbk_roundtrip_and_convert(self, tmpdir):
        src = os.path.join(tmpdir, "s.txt")
        dst = os.path.join(tmpdir, "d.txt")
        fc.write_text(src, "中文", encoding="gbk")
        info = fc.convert(src, dst)
        assert info["to"] == "utf-8"
        assert fc.read_text(dst) == "中文"


class TestNormalizeEncodingUnchanged:
    @pytest.mark.parametrize("name,expected", [
        ("UTF8", "utf-8"),
        ("utf_8", "utf-8"),
        ("GBK", "gbk"),
        ("GB2312", "gb2312"),
    ])
    def test_aliases(self, name, expected):
        assert fc.normalize_encoding(name) == expected

    def test_unknown_passthrough_documented(self):
        # 文档：未知则原样小写返回
        assert fc.normalize_encoding("bogus") == "bogus"
