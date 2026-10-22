"""
vools.md.rich.linker 文件链接路由测试（BRIDGES_MD_RICH_CONTENT_PLAN P4）

测试范围：
- 链接提取（本地/远程/data URI）
- 路径安全（穿越/设备名/UNC/类型白名单/长度）
- 文件存在性检查
- FileLinkRouter 路由
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.md.rich.linker import (
    FileLink, FileLinkRouter, extract_file_links, can_open_file,
)


class TestExtractFileLinks:
    """链接提取"""

    def test_local_link(self):
        links = extract_file_links("[PDF](file.pdf)", ".")
        assert len(links) == 1
        assert links[0].kind == 'local'
        assert links[0].text == 'PDF'

    def test_remote_link(self):
        links = extract_file_links("[Web](https://example.com)", ".")
        assert len(links) == 1
        assert links[0].kind == 'remote'

    def test_data_uri(self):
        links = extract_file_links("[Data](data:text/plain,hello)", ".")
        assert len(links) == 1
        assert links[0].kind == 'data'

    def test_mixed_links(self):
        text = "[PDF](file.pdf)\n\n[Doc](./docs/readme.md)\n\n[Web](https://x.com)\n"
        links = extract_file_links(text, ".")
        assert len(links) == 3
        assert links[0].kind == 'local'
        assert links[1].kind == 'local'
        assert links[2].kind == 'remote'

    def test_file_url_scheme(self):
        links = extract_file_links("[F](file:///tmp/test.pdf)", ".")
        assert len(links) == 1
        assert links[0].kind == 'local'


class TestPathSecurity:
    """路径安全"""

    def test_path_traversal_blocked(self):
        links = extract_file_links("[x](../../../etc/passwd)", "/tmp/test")
        assert links[0].exists == False
        assert links[0].resolved_path is None

    def test_device_name_blocked(self):
        links = extract_file_links("[x](CON)", "/tmp/test")
        assert links[0].exists == False

    def test_unc_path_blocked(self):
        links = extract_file_links(r"[x](\\server\share\file)", "/tmp/test")
        assert links[0].exists == False

    def test_file_type_whitelist(self):
        # .exe 不在白名单
        links = extract_file_links("[x](script.exe)", "/tmp/test")
        assert links[0].exists == False

    def test_allowed_file_type(self):
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "test.pdf")
            with open(f, "w") as fh:
                fh.write("x")
            links = extract_file_links("[PDF](test.pdf)", td)
            assert links[0].exists == True
            assert links[0].resolved_path == f

    def test_can_open_file_safe(self):
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "test.md")
            with open(f, "w") as fh:
                fh.write("# Title\n")
            assert can_open_file("test.md", td) == True

    def test_can_open_file_traversal(self):
        with tempfile.TemporaryDirectory() as td:
            assert can_open_file("../evil.exe", td) == False

    def test_can_open_file_missing(self):
        with tempfile.TemporaryDirectory() as td:
            assert can_open_file("missing.pdf", td) == False


class TestFileLinkRouter:
    """FileLinkRouter"""

    def test_can_open_nonexistent(self):
        router = FileLinkRouter(".")
        link = FileLink("test", "file.pdf")
        assert router.can_open(link) == False

    def test_can_open_exists(self):
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "test.pdf")
            with open(f, "w") as fh:
                fh.write("x")
            router = FileLinkRouter(td)
            link = FileLink("PDF", "test.pdf", f, True, 'local')
            assert router.can_open(link) == True

    def test_can_open_remote(self):
        router = FileLinkRouter(".")
        link = FileLink("Web", "https://x.com", kind='remote')
        assert router.can_open(link) == False

    def test_can_open_data(self):
        router = FileLinkRouter(".")
        link = FileLink("Data", "data:text/plain,x", kind='data')
        assert router.can_open(link) == False

    def test_open_nonexistent(self):
        router = FileLinkRouter(".")
        link = FileLink("test", "file.pdf")
        assert router.open(link) == False


class TestFileLinkStructure:
    """FileLink 数据结构"""

    def test_to_dict(self):
        link = FileLink("text", "url.pdf", "/path/url.pdf", True, 'local')
        d = link.to_dict()
        assert d['text'] == 'text'
        assert d['url'] == 'url.pdf'
        assert d['resolved_path'] == '/path/url.pdf'
        assert d['exists'] == True
        assert d['kind'] == 'local'

    def test_repr(self):
        link = FileLink("text", "url.pdf")
        r = repr(link)
        assert "FileLink" in r
        assert "url.pdf" in r
