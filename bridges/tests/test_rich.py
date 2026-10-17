"""vools.bridge.md.rich 测试：P0~P4 出口验收（BRIDGES_MD_RICH_CONTENT_PLAN）。

覆盖：
- P0 出口：resolver 单测（含 .. 越权样本）、status 文案映射、protocol 序列化往返
- P1 出口：恶意 HTML 样本（script/onerror/javascript:/iframe）被 L1 剥离、CLI rich 渲染最小样例
- P2 出口：scan_rich 顶层 SVG/HTML 提取、#!rich 指令解析、SVG 净化（script/on* 剥离）
- P3 出口：hotreload L1/L2 补丁生成、HotReloadManager 哈希 diff
- P4 出口：FileLinkRouter 路径越权拒绝、detect_link_kind 分类
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vools.bridge.md.rich import (
    ARTIFACTS_REF_PREFIX,
    FileLinkRouter,
    HotReloadManager,
    RichPathResolver,
    build_l1_patch,
    build_l2_patch,
    detect_link_kind,
    error_status,
    message_for,
    ok_status,
    parse_hot_reload_mode,
    render,
    scan_rich,
    serialize,
    deserialize,
    validate_message,
)
from vools.bridge.md.errors import MDRichPathError, MDRichAccessDeniedError
from vools.bridge.md.rich.scanner import FileLink
from vools.bridge.md.rich.protocol import build_open_file


# ═════════════════ P0：resolver ═════════════════

def test_resolver_local_file():
    with tempfile.TemporaryDirectory() as root:
        open(os.path.join(root, "a.md"), "w").close()
        # 相对路径：无需 opt-in
        r = RichPathResolver(root)
        resolved = r.resolve("a.md")
        assert resolved == os.path.join(root, "a.md")
        # 绝对路径：默认拒绝，opt-in 后放行
        r2 = RichPathResolver(root, allow_absolute=True)
        resolved2 = r2.resolve(os.path.join(root, "a.md"))
        assert resolved2 == os.path.join(root, "a.md")


def test_resolver_rejects_traversal():
    with tempfile.TemporaryDirectory() as root:
        r = RichPathResolver(root)
        try:
            r.resolve(os.path.join(root, "..", "..", "Windows", "win.ini"))
            assert False, "should raise"
        except (MDRichPathError, MDRichAccessDeniedError):
            pass


def test_resolver_artifacts_ref():
    with tempfile.TemporaryDirectory() as root:
        sub = os.path.join(root, ".mdbuild", "artifacts", "rich")
        os.makedirs(sub)
        open(os.path.join(sub, "out.txt"), "w").close()
        r = RichPathResolver(root)
        resolved = r.resolve(ARTIFACTS_REF_PREFIX + "/out.txt")
        assert resolved == os.path.join(sub, "out.txt")


# ═════════════════ P0：status 文案映射 ═════════════════

def test_status_messages():
    assert message_for("OK") == "成功"
    assert ok_status().code == "OK" and ok_status().ok is True
    e = error_status("E_ACCESS_DENIED")
    assert e.code == "E_ACCESS_DENIED" and e.ok is False
    assert "越权" in e.message or "拒绝" in e.message


# ═════════════════ P0：protocol 序列化往返 ═════════════════

def test_protocol_roundtrip():
    msg = build_open_file(block_id="b0", request_id="req-1", target="a.md")
    raw = serialize(msg)
    data = deserialize(raw)
    assert data["type"] == "open_file" and data["request_id"] == "req-1"
    assert data["payload"]["target"] == "a.md"
    validate_message(data)


# ═════════════════ P1：HTML L1 净化（恶意样本） ═════════════════

def test_render_strips_malicious_html():
    md = (
        "# 恶意样本\n\n"
        "<div onclick=\"alert(1)\"><script>alert(2)</script>"
        "<img src=x onerror=alert(3)><a href=\"javascript:alert(4)\">x</a>"
        "<iframe src=\"https://evil\"></iframe></div>\n"
    )
    with tempfile.TemporaryDirectory() as root:
        p = os.path.join(root, "evil.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)
        doc = scan_rich(p)
        assert len(doc.inline_htmls) == 1
        res = render(doc, interactive=True)
        html = res.html
        assert "<script" not in html and "onerror" not in html and "onclick" not in html
        assert "javascript:" not in html


# ═════════════════ P2：scan_rich / #!rich 指令 / SVG 净化 ═════════════════

def test_scan_rich_directive():
    with tempfile.TemporaryDirectory() as root:
        p = os.path.join(root, "d.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("#!rich=allow-remote=true,hot-reload=l2\n\n正文\n")
        doc = scan_rich(p)
        assert doc.config.allow_remote is True
        assert doc.config.hot_reload == "l2"


def test_scan_rich_extracts_top_level_only():
    with tempfile.TemporaryDirectory() as root:
        p = os.path.join(root, "t.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(
                "# 标题\n\n"
                "<svg xmlns=\"http://www.w3.org/2000/svg\"><rect width=\"1\"/></svg>\n"
                "<div>c</div>\n"
                "```svg\n<svg><circle/></svg>\n```\n"
                "```html\n<div>fenced</div>\n```\n"
            )
        doc = scan_rich(p)
        assert len(doc.inline_svgs) == 1 and len(doc.inline_htmls) == 1


def test_svg_sanitize_strips_script():
    with tempfile.TemporaryDirectory() as root:
        p = os.path.join(root, "s.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<rect width="10"/><script>alert(1)</script>'
                '<g onclick="evil()">x</g></svg>\n'
            )
        doc = scan_rich(p)
        assert len(doc.inline_svgs) == 1
        safe = doc.inline_svgs[0].safe
        assert "<script" not in safe and "onclick" not in safe
        assert "<rect" in safe and "<g" in safe


# ═════════════════ P3：hotreload L1/L2 ═════════════════

def test_hot_reload_l1_patch():
    p = build_l1_patch("<html><body>NEW</body></html>")
    assert "setAttribute('srcdoc'" in p and "NEW" in p


def test_hot_reload_l2_patch():
    p = build_l2_patch({"#zone": "<b>new</b>"})
    assert "querySelector" in p and "#zone" in p


def test_hot_reload_manager_diff():
    m = HotReloadManager(mode="l2")
    m.register_region("#a", "same")
    updates = m.diff_updates({"#a": "same", "#b": "changed"})
    assert "#a" not in updates and "#b" in updates


def test_parse_hot_reload_mode():
    assert parse_hot_reload_mode("l2") == "l2"
    assert parse_hot_reload_mode("L1") == "l1"
    assert parse_hot_reload_mode("x") == "l1"


# ═════════════════ P4：文件链接路由 ═════════════════

def test_detect_link_kind():
    assert detect_link_kind("a.png") == "image"
    assert detect_link_kind("a.svg") == "svg"
    assert detect_link_kind("a.html") == "html"
    assert detect_link_kind("a.json") == "json"
    assert detect_link_kind("a.md") == "text"


def test_router_rejects_escape():
    with tempfile.TemporaryDirectory() as root:
        r = FileLinkRouter(root=root, allow_absolute=False)
        lk = FileLink(index=0, text="..", target=os.path.join(root, "..", "x.md"))
        assert not r.can_open(lk)


def test_router_accepts_local():
    with tempfile.TemporaryDirectory() as root:
        sub = os.path.join(root, "img")
        os.makedirs(sub)
        open(os.path.join(sub, "logo.png"), "wb").close()
        r = FileLinkRouter(root=root, allow_absolute=False)
        # 相对路径 target
        lk = FileLink(index=0, text="logo", target=os.path.join("img", "logo.png"))
        assert r.can_open(lk)
