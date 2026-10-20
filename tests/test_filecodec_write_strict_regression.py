# -*- coding: utf-8 -*-
"""回归测试：write_text/convert 落盘默认 strict，不静默损坏（BUG-219）。

原 `write_text` 硬编码 `encode(enc, errors="replace")`——目标编码装不下的
字符（emoji→GBK）被替换成 `?` 静默落盘、函数返回编码名伪装成功，调用方
失去 stdlib strict 默认给的纠错决定权；docstring 从未声明有损行为。

修复：新增 `errors` 参数默认 `strict`（UnicodeEncodeError 在写盘前抛，
坏数据不落盘）；有损场景显式 `errors="replace"`；`convert()` 透传。
"""

import os

import pytest

from vools.encoding.filecodec import convert, read_text, write_text


class TestWriteTextStrictDefault:
    """不可编码字符默认报错，不伪装成功（BUG-219 核心）。"""

    def test_unencodable_raises(self, tmp_path):
        p = str(tmp_path / "t.txt")
        with pytest.raises(UnicodeEncodeError):
            write_text(p, "庆祝🎉发布", encoding="gbk")

    def test_failure_does_not_write_corrupt_file(self, tmp_path):
        p = str(tmp_path / "t.txt")
        with pytest.raises(UnicodeEncodeError):
            write_text(p, "🎉", encoding="gbk")
        assert not os.path.exists(p)          # encode 在 open 之前

    def test_encodable_content_unchanged(self, tmp_path):
        p = str(tmp_path / "ok.txt")
        assert write_text(p, "中文测试", encoding="gbk") == "gbk"
        assert read_text(p) == "中文测试"


class TestExplicitReplacePreserved:
    """旧有损能力显式保留（兼容通道）。"""

    def test_errors_replace_works(self, tmp_path):
        p = str(tmp_path / "t.txt")
        ret = write_text(p, "庆祝🎉", encoding="gbk", errors="replace")
        assert ret == "gbk"
        assert read_text(p, encoding="gbk") == "庆祝?"   # 显式有损，知情


class TestConvertPropagation:
    """convert 透传 errors（BUG-219 同链）。"""

    def test_convert_strict_raises(self, tmp_path):
        src = str(tmp_path / "src.txt")
        dst = str(tmp_path / "dst.txt")
        write_text(src, "🎉x", encoding="utf-8")
        with pytest.raises(UnicodeEncodeError):
            convert(src, dst, encoding="gbk")

    def test_convert_explicit_replace(self, tmp_path):
        src = str(tmp_path / "src.txt")
        dst = str(tmp_path / "dst.txt")
        write_text(src, "🎉x", encoding="utf-8")
        r = convert(src, dst, encoding="gbk", errors="replace")
        assert r["to"] == "gbk"


class TestOtherPathsUnaffected:
    """BOM/utf-16/父目录创建等原语义保持。"""

    def test_bom_roundtrip(self, tmp_path):
        p = str(tmp_path / "b.txt")
        write_text(p, "文本", encoding="utf-8", bom=True)
        assert open(p, "rb").read().startswith(b"\xef\xbb\xbf")

    def test_parent_dir_created(self, tmp_path):
        p = str(tmp_path / "sub" / "deep" / "x.txt")
        write_text(p, "hi")
        assert read_text(p) == "hi"

    def test_utf16_le_returns_name(self, tmp_path):
        p = str(tmp_path / "u.txt")
        assert write_text(p, "x", encoding="utf-16-le") == "utf-16-le"