"""vools.bridge.md.rich 测试：P0~P4 出口验收（BRIDGES_MD_RICH_CONTENT_PLAN）。

覆盖：
- P0 出口：resolver 单测（含 .. 越权样本）、status 文案映射、protocol 序列化往返
- P1 出口：恶意 HTML 样本（script/onerror/javascript:/iframe）被 L1 剥离、CLI rich 渲染最小样例
- P2 出口：scan_rich 顶层 SVG/HTML 提取、#!rich 指令解析、SVG 净化（script/on* 剥离）
- P3 出口：hotreload L1/L2 补丁生成、HotReloadManager 哈希 diff
- P4 出口：FileLinkRouter 路径越权拒绝、detect_link_kind 分类、RichOpener 错误分类、
  open_file 协议徽标数据（open_result）、webview2 导航兜底白名单
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
    RichOpener,
    RichPathResolver,
    build_l1_patch,
    build_l2_patch,
    build_pending_status,
    detect_link_kind,
    error_status,
    message_for,
    ok_status,
    parse_hot_reload_mode,
    render,
    sanitize_html_fragment,
    sanitize_svg,
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


# ═════════════════ P2：SVG 展示（runner 级） ═════════════════

def _make_svg_block(index=7, content="", directives=None, language="svg"):
    from vools.bridge.md.runner import CodeBlock

    return CodeBlock(
        index=index,
        language=language,
        content=content,
        directives=directives or {},
        tag=[],
    )


def test_svg_block_runner_writes_file():
    from vools.bridge.md.runner import _execute_rich_block

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50">'
        "<rect x='10' y='10' width='80' height='30' fill='#4a90d9'/>"
        "</svg>"
    )
    with tempfile.TemporaryDirectory() as root:
        ctx = {"build_dir": root}
        stdout, stderr, code = _execute_rich_block(_make_svg_block(content=svg), ctx, {})
        assert code == 0, stderr
        out_svg = os.path.join(root, "artifacts", "rich", "block_7.svg")
        assert os.path.isfile(out_svg), stdout
        # 卡片引用落盘文件
        card = open(os.path.join(root, "artifacts", "rich", "block_7.html"), encoding="utf-8").read()
        assert 'src="block_7.svg"' in card
        assert "<img" in card
        assert "svg 剥离" not in stdout  # 干净 SVG 无剥离审计


def test_svg_block_strips_script_via_runner():
    from vools.bridge.md.runner import _execute_rich_block

    evil = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<script>alert(1)</script>'
        "<rect width='10' height='10'/>"
        "</svg>"
    )
    with tempfile.TemporaryDirectory() as root:
        ctx = {"build_dir": root}
        stdout, stderr, code = _execute_rich_block(_make_svg_block(index=8, content=evil), ctx, {})
        assert code == 0, stderr
        out_svg = os.path.join(root, "artifacts", "rich", "block_8.svg")
        assert os.path.isfile(out_svg), stdout
        safe = open(out_svg, encoding="utf-8").read()
        assert "<script" not in safe.lower()
        assert "alert" not in safe
        assert "svg 剥离" in stdout


def test_svg_block_bad_xml_falls_back_to_source():
    from vools.bridge.md.runner import _execute_rich_block

    bad = "<svg><unclosed></svg>"
    with tempfile.TemporaryDirectory() as root:
        ctx = {"build_dir": root}
        stdout, stderr, code = _execute_rich_block(_make_svg_block(index=9, content=bad), ctx, {})
        assert code == 0, stderr
        assert "svg-rejected" in stdout
        assert not os.path.isfile(os.path.join(root, "artifacts", "rich", "block_9.svg"))


# ═════════════════ P3：图片链接展示 ═════════════════

def _write_scan_md(root, body):
    md_path = os.path.join(root, "doc.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(body)
    return md_path


def test_img_remote_disabled_by_default():
    with tempfile.TemporaryDirectory() as root:
        md_path = _write_scan_md(root, "看 ![示例](https://example.com/a.png)\n")
        doc = scan_rich(md_path)
        assert "md-rich-denied" in doc.body_html
        assert "图片:示例" in doc.body_html
        assert doc.file_links and doc.file_links[0].kind == "remote"
        assert doc.file_links[0].status.code == "E_REMOTE_DISABLED"


def test_img_remote_optin_allows():
    from vools.bridge.md.rich.scanner import RichConfig

    with tempfile.TemporaryDirectory() as root:
        md_path = _write_scan_md(root, "看 ![示例](https://example.com/a.png)\n")
        cfg = RichConfig(allow_remote_images=True)
        doc = scan_rich(md_path, config=cfg)
        assert "<img" in doc.body_html
        assert 'src="https://example.com/a.png"' in doc.body_html
        assert "md-rich-denied" not in doc.body_html


def test_img_missing_local_placeholder():
    with tempfile.TemporaryDirectory() as root:
        md_path = _write_scan_md(root, "![缺失图](not_exist.png)\n")
        doc = scan_rich(md_path)
        assert "md-rich-missing" in doc.body_html
        assert doc.file_links and doc.file_links[0].status.code == "E_FILE_MISSING"


def test_img_local_exists_renders():
    with tempfile.TemporaryDirectory() as root:
        open(os.path.join(root, "ok.png"), "wb").close()
        md_path = _write_scan_md(root, "![存在图](ok.png)\n")
        doc = scan_rich(md_path)
        assert "<img" in doc.body_html
        assert 'src="ok.png"' in doc.body_html
        assert "md-rich-missing" not in doc.body_html
        assert "md-rich-denied" not in doc.body_html


def test_bom_does_not_break_directive():
    with tempfile.TemporaryDirectory() as root:
        md_path = os.path.join(root, "bom.md")
        with open(md_path, "wb") as f:
            f.write(b"\xef\xbb\xbf" + "#!rich=allow-remote\n\n正文\n".encode("utf-8"))
        doc = scan_rich(md_path)
        assert "#!rich" not in doc.body_html  # 指令行不得进入正文
        assert "<p>正文</p>" in doc.body_html
        assert doc.config.allow_remote is True


# ═════════════════ P4：RichOpener 错误分类 ═════════════════


def _fake_opener_ok(path):
    return True


def _fake_opener_fail(path):
    raise OSError("simulated", getattr(OSError(""), "winerror", None))


def test_opener_open_existing_file_ok():
    with tempfile.TemporaryDirectory() as root:
        target = os.path.join(root, "ok.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("hi")
        opener = RichOpener(root=root, opener=_fake_opener_ok)
        status = opener.open("ok.txt")
        assert status.ok is True
        assert "已打开" in status.message
        assert status.code == "OK"


def test_opener_missing_file_not_found():
    with tempfile.TemporaryDirectory() as root:
        opener = RichOpener(root=root, opener=_fake_opener_ok)
        status = opener.open("no_such.txt")
        assert status.ok is False
        assert status.code == "E_PATH_NOT_FOUND"


def test_opener_dotdot_escape_rejected():
    with tempfile.TemporaryDirectory() as root:
        opener = RichOpener(root=root, opener=_fake_opener_ok)
        status = opener.open("../outside.txt")
        assert status.ok is False
        assert status.code == "E_ACCESS_DENIED"


def test_opener_absolute_path_rejected_by_default():
    with tempfile.TemporaryDirectory() as root:
        opener = RichOpener(root=root, opener=_fake_opener_ok)
        status = opener.open(os.path.join(root, "ok.txt"))
        assert status.ok is False
        assert status.code == "E_ACCESS_DENIED"


def test_opener_unsupported_extension_rejected():
    with tempfile.TemporaryDirectory() as root:
        target = os.path.join(root, "evil.exe")
        with open(target, "wb") as f:
            f.write(b"MZ")
        opener = RichOpener(root=root, opener=_fake_opener_ok)
        status = opener.open("evil.exe")
        assert status.ok is False
        assert status.code in ("E_UNSUPPORTED_EXT", "E_ACCESS_DENIED")


def test_opener_oserror_classified():
    with tempfile.TemporaryDirectory() as root:
        target = os.path.join(root, "ok.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("hi")

        class _RaisingOpener:
            def __call__(self, path):
                raise PermissionError("denied")

        opener = RichOpener(root=root, opener=_RaisingOpener())
        status = opener.open("ok.txt")
        assert status.ok is False
        assert status.code == "E_ACCESS_DENIED"


def test_build_pending_status_ok():
    status = build_pending_status()
    assert status.ok is True
    assert "已请求打开" in status.message


def test_opener_open_link_updates_status():
    from vools.bridge.md.rich.scanner import FileLink

    with tempfile.TemporaryDirectory() as root:
        target = os.path.join(root, "ok.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("hi")
        link = FileLink(index=0, text="ok", target="ok.txt", resolved_path=target)
        opener = RichOpener(root=root, opener=_fake_opener_ok)
        status = opener.open_link(link)
        assert status.ok is True
        assert link.status is status  # 状态同步回链接，供徽标刷新


def test_opener_open_link_missing():
    from vools.bridge.md.rich.scanner import FileLink

    with tempfile.TemporaryDirectory() as root:
        link = FileLink(index=0, text="x", target="no_such.txt", resolved_path=os.path.join(root, "no_such.txt"))
        opener = RichOpener(root=root, opener=_fake_opener_ok)
        status = opener.open_link(link)
        assert status.ok is False
        assert status.code == "E_PATH_NOT_FOUND"


# ═════════════════ P4：webview2 导航兜底 + open_file 协议 ═════════════════


def test_navigation_whitelist_allows_local():
    from vools.bridge.md.webview2 import _is_allowed_navigation

    assert _is_allowed_navigation("file:///C:/x/ok.html") is True
    assert _is_allowed_navigation("about:blank") is True
    assert _is_allowed_navigation("http://127.0.0.1:8000/p") is True
    assert _is_allowed_navigation("http://localhost:8000/p") is True


def test_navigation_whitelist_blocks_remote():
    from vools.bridge.md.webview2 import _is_allowed_navigation

    assert _is_allowed_navigation("https://evil.com/x") is False
    assert _is_allowed_navigation("http://evil.com/x") is False
    assert _is_allowed_navigation("javascript:alert(1)") is False


def test_handle_open_file_disabled_when_no_root():
    from vools.bridge.md.webview2 import WebView2Config, _handle_open_file

    cfg = WebView2Config()
    status = _handle_open_file({"data": {"target": "ok.txt"}}, cfg)
    assert status.ok is False
    assert status.code == "E_ACCESS_DENIED"


def test_handle_open_file_rejects_escape():
    from vools.bridge.md.webview2 import WebView2Config, _handle_open_file

    with tempfile.TemporaryDirectory() as root:
        cfg = WebView2Config(rich_open_root=root)
        status = _handle_open_file({"data": {"target": "../secret.txt"}}, cfg)
        assert status.ok is False
        assert status.code == "E_ACCESS_DENIED"


def test_handle_open_file_missing_target():
    from vools.bridge.md.webview2 import WebView2Config, _handle_open_file

    with tempfile.TemporaryDirectory() as root:
        cfg = WebView2Config(rich_open_root=root)
        status = _handle_open_file({"data": {"target": "no_such.txt"}}, cfg)
        assert status.ok is False
        assert status.code == "E_PATH_NOT_FOUND"

# ═════════════════ 恶意样本矩阵扩充（P5 前置安全收口） ═════════════════

def test_sanitize_html_event_attr_matrix():
    """on* 事件属性全家族 + 大小写混淆 → 全部剥离。"""
    cases = [
        '<img src="x.png" onerror="alert(1)">',
        '<div onload="evil()">t</div>',
        '<a href="#" onmouseover="evil()">x</a>',
        '<a href="#" onfocus="evil()">x</a>',
        '<img src="x.png" ONERROR="alert(1)">',
        '<a href="#" OnClick="evil()">x</a>',
        '<div onpointerdown="evil()">x</div>',
        '<img src="x.png" onload=alert(1)>',
    ]
    for html in cases:
        safe, removed = sanitize_html_fragment(html)
        assert removed, f"事件属性应被剥离记录: {html!r}"
        assert any(r.endswith("[on") or "[on" in r for r in removed), f"缺失剥离记录: {removed}"
        assert "alert" not in safe and "evil" not in safe
        assert not any(attr in safe.lower() for attr in
                       ("onerror", "onload", "onmouseover", "onfocus", "onclick", "onpointerdown"))


def test_sanitize_html_scheme_matrix():
    """危险协议链接（含大小写/字符实体混淆）→ href 剥离。"""
    cases = [
        '<a href="javascript:alert(1)">x</a>',
        '<a href="JaVaScRiPt:alert(1)">x</a>',
        '<a href="vbscript:msgbox(1)">x</a>',
        '<a href="data:text/html,<b>phish</b>">x</a>',
        '<a href="file:///C:/Windows/win.ini">x</a>',
        '<a href="blob:https://evil/1">x</a>',
        '<a href="&#106;avascript:alert(1)">x</a>',  # 字符实体混淆
    ]
    for html in cases:
        safe, removed = sanitize_html_fragment(html)
        assert "href=" not in safe, f"href 应被剥离: {safe!r}"
        assert "a[href]" in removed, f"缺失剥离记录: {removed}"


def test_sanitize_html_dangerous_container_matrix():
    """危险容器 14 类整棵子树剥离（子内容一并丢弃）。"""
    containers = ["script", "style", "iframe", "object", "embed", "form", "input",
                  "button", "select", "textarea", "meta", "link", "base", "template"]
    for tag in containers:
        html = f'<div>keep<{tag}>bad</{tag}>end</div>'
        safe, removed = sanitize_html_fragment(html)
        assert f"<{tag}" not in safe, f"{tag} 应被剥离: {safe!r}"
        assert "bad" not in safe and "alert" not in safe
        assert "keep" in safe and "end" in safe
        assert f"<{tag}>" in removed, f"缺失剥离记录: {removed}"


def test_sanitize_html_style_and_hidden_content():
    """style / 注释 / 声明 / PI / 非法 id / 非数值尺寸 → 剥离。"""
    safe, removed = sanitize_html_fragment(
        '<div style="background:url(https://evil)">a</div>'
        '<!-- comment --><div id="bad id!">b</div>'
        '<img src="x.png" width="10px" height="abc">'
        '<?php evil ?><div id="ok_id">c</div>'
    )
    assert "style=" not in safe and "<!--" not in safe
    assert "bad id" not in safe and "<?php" not in safe
    assert 'width="10px"' not in safe and 'height="abc"' not in safe
    assert 'id="ok_id"' in safe
    assert "div[style]" in removed and "div[id]" in removed
    assert "img[width]" in removed and "img[height]" in removed


def test_sanitize_html_remote_image_policy():
    """远程图片默认禁；opt-in 放行；protocol-relative 图片剥离。"""
    default, removed = sanitize_html_fragment('<img src="https://evil/x.png" alt="a">')
    assert "src=" not in default and "img[src]" in removed

    optin, _ = sanitize_html_fragment(
        '<img src="https://evil/x.png" alt="a">', allow_remote_images=True
    )
    assert 'src="https://evil/x.png"' in optin

    proto_rel, r2 = sanitize_html_fragment('<img src="//evil/x.png">')
    assert "src=" not in proto_rel and "img[src]" in r2


def test_sanitize_html_safe_content_kept():
    """合法内容保留：锚点 / 相对路径 / data:image 图片。"""
    safe, removed = sanitize_html_fragment(
        '<a href="#sec">锚</a><a href="doc.md">文档</a>'
        '<img src="data:image/png;base64,AAA=" alt="d">'
    )
    assert 'href="#sec"' in safe and 'href="doc.md"' in safe
    assert 'src="data:image/png;base64,AAA="' in safe


def test_sanitize_svg_event_style_matrix():
    """SVG on*/style 属性剥离（含命名空间属性键）。"""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg">'
           '<rect onload="evil()" style="fill:url(#x)" width="10"/>'
           '<circle onbegin="evil()" onclick="evil()" r="5"/></svg>')
    safe, removed = sanitize_svg(svg)
    assert "onload" not in safe and "onbegin" not in safe and "onclick" not in safe
    assert "style" not in safe and "evil" not in safe
    assert '<rect width="10"' in safe
    assert "rect[onload]" in removed and "rect[style]" in removed
    assert "circle[onbegin]" in removed and "circle[onclick]" in removed


def test_sanitize_svg_dangerous_elements():
    """SVG 危险元素整树剥离：script/foreignObject/a/iframe。"""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg">'
           '<script>alert(1)</script>'
           '<foreignObject><div onclick="x()">hi</div></foreignObject>'
           '<a href="https://evil"><rect width="1"/></a>'
           '<iframe src="https://evil"/></svg>')
    safe, removed = sanitize_svg(svg)
    assert "<script" not in safe and "foreignObject" not in safe
    assert "<a" not in safe and "<iframe" not in safe and "evil" not in safe
    assert "<script>" in removed and "<foreignobject>" in removed
    assert "<a>" in removed and "<iframe>" in removed


def test_sanitize_svg_href_policy():
    """SVG href 只放行 # 与 data:image；http/javascript/file 剥离。"""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" '
           'xmlns:xlink="http://www.w3.org/1999/xlink">'
           '<use href="#s1"/><image href="data:image/png;base64,AAA="/>'
           '<use href="https://evil/s.svg"/><use xlink:href="javascript:alert(1)"/>'
           '<image href="file:///etc/passwd"/></svg>')
    safe, removed = sanitize_svg(svg)
    assert 'href="#s1"' in safe
    assert "data:image/png" in safe
    assert "https://evil" not in safe and "javascript:" not in safe and "file:" not in safe
    assert "use[href]" in removed and "image[href]" in removed


def test_sanitize_svg_size_and_root_guard():
    """SVG 大小上限 / 根元素校验 / 坏 XML → 拒绝并记录。"""
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1"/></svg>'
    safe, removed = sanitize_svg(svg, max_size=10)
    assert safe == "" and "size-over-limit" in removed

    safe2, removed2 = sanitize_svg('<html><body>x</body></html>')
    assert safe2 == "" and any("root-not-svg" in r for r in removed2)

    safe3, removed3 = sanitize_svg('not xml <<<')
    assert safe3 == "" and any("parse-error" in r for r in removed3)


def test_sanitize_svg_namespace_prefix_kept():
    """带命名空间前缀的合法元素保留（本地名剥离前缀）。"""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" '
           'xmlns:svg2="http://www.w3.org/2000/svg">'
           '<svg2:rect width="10" fill="red"/></svg>')
    safe, removed = sanitize_svg(svg)
    assert "rect" in safe and "fill" in safe
    assert not removed or all("script" not in r for r in removed)


def test_render_remote_image_optin_end_to_end():
    """渲染层：内联 HTML 远程图片默认剥离，#!rich=allow-remote-images=true 放行。"""
    html_block = '<div><img src="https://example.com/x.png" alt="r"></div>\n'
    with tempfile.TemporaryDirectory() as root:
        p = os.path.join(root, "rimg.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(html_block)
        doc = scan_rich(p)
        res = render(doc, interactive=True)
        assert "https://example.com/x.png" not in res.html

        with open(p, "w", encoding="utf-8") as f:
            f.write("#!rich=allow-remote-images=true\n\n" + html_block)
        doc2 = scan_rich(p)
        res2 = render(doc2, interactive=True)
        assert "https://example.com/x.png" in res2.html


# ═════════════════ P5：产物集成 ═════════════════

def _make_rich_build(root, files=("out.txt",)):
    build = os.path.join(root, ".mdbuild")
    rich = os.path.join(build, "artifacts", "rich")
    os.makedirs(rich)
    for name in files:
        p = os.path.join(rich, name)
        if name.endswith(".png"):
            with open(p, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        elif name.endswith(".svg"):
            with open(p, "w", encoding="utf-8") as fh:
                fh.write('<svg xmlns="http://www.w3.org/2000/svg"><rect width="4"/></svg>')
        else:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("hello artifact")
    return build, rich


def test_render_artifacts_section():
    """P5：产物区渲染 + @artifacts open_file 链接 + RenderResult.artifacts。"""
    with tempfile.TemporaryDirectory() as root:
        md = os.path.join(root, "doc.md")
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("# t\n\nbody\n")
        build, _rich = _make_rich_build(root, ("out.txt", "fig.png"))
        doc = scan_rich(md, build_dir=build)
        assert len(doc.artifacts) == 2
        res = render(doc)
        assert 'class="md-rich-artifacts"' in res.html
        assert "@artifacts/out.txt" in res.html
        assert 'data-rich-open="art-0"' in res.html
        assert 'data-rich-target="@artifacts/out.txt"' in res.html
        assert res.artifacts and len(res.artifacts) == 2


def test_render_artifact_image_thumb_inline():
    """P5：小图片产物内联 base64 缩略图（img data URI）。"""
    with tempfile.TemporaryDirectory() as root:
        md = os.path.join(root, "doc.md")
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("# t\n")
        build, _rich = _make_rich_build(root, ("fig.png",))
        doc = scan_rich(md, build_dir=build)
        res = render(doc)
        assert "data:image/png;base64," in res.html
        assert 'class="md-rich-art-thumb"' in res.html


def test_render_artifact_svg_uses_img_not_inline_markup():
    """P5：SVG 产物经 img 渲染（data:image/svg+xml），不直接注入可执行标记。"""
    with tempfile.TemporaryDirectory() as root:
        md = os.path.join(root, "doc.md")
        with open(md, "w", encoding="utf-8") as fh:
            fh.write("# t\n")
        build, _rich = _make_rich_build(root, ("plot.svg",))
        doc = scan_rich(md, build_dir=build)
        res = render(doc)
        assert "data:image/svg+xml;base64," in res.html
        # SVG 原文不得以可执行标记形式直出（img src 内渲染不执行脚本）
        assert "<svg" not in res.html


def test_register_artifact_type_guess():
    """P5：register_artifact 类型感知（type_hint 覆盖扩展名推断）。"""
    from vools.bridge.md.artifacts import register_artifact

    with tempfile.TemporaryDirectory() as root:
        txt = os.path.join(root, "a.txt")
        png = os.path.join(root, "b.png")
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write("x")
        with open(png, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n")
        table = {}
        register_artifact(table, "a", txt, 0)
        register_artifact(table, "b", png, 1)
        register_artifact(table, "c", txt, 2, type_hint="html")
        assert table["a"]["type"] == "text"
        assert table["b"]["type"] == "image"
        assert table["c"]["type"] == "html"


def test_clean_build_stale_recursive_rich():
    """P5：stale 清理递归 artifacts/rich/，孤儿删除、manifest 有效产物保留、空目录腾退。"""
    from vools.bridge.md.artifacts import clean_build
    from vools.bridge.md.manifest import write_manifest

    with tempfile.TemporaryDirectory() as root:
        build, rich = _make_rich_build(root, ("orphan.txt",))
        # 有效产物放 artifacts/ 顶层；rich/ 下文件均为孤儿 → 删除后目录腾退
        keep_path = os.path.join(build, "artifacts", "keep.txt")
        with open(keep_path, "w", encoding="utf-8") as fh:
            fh.write("keep")
        write_manifest(build, {"blocks": [{"artifact": keep_path}]})
        clean_build(build, stale=True)
        assert os.path.exists(keep_path)
        assert not os.path.exists(os.path.join(rich, "orphan.txt"))
        # 空子目录腾退：rich 目录下无孤儿后应被移除（顶层 artifacts/ 保留）
        assert os.path.isdir(os.path.join(build, "artifacts"))
        assert not os.path.exists(rich)
