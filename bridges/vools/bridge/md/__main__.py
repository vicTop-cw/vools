"""
vools.bridge.md CLI 入口

用法：
    python -m vools.bridge.md run script.md [--only tag] [--force] [--debug]
    python -m vools.bridge.md info script.md
    python -m vools.bridge.md code script.md
    python -m vools.bridge.md check script.md
    python -m vools.bridge.md clean script.md [--stale] [--keep tag]
    python -m vools.bridge.md rich script.md [--out FILE] [--no-open]
"""


__all__ = [
    "main",
]

import argparse
import os
import sys
from typing import Optional


def main():
    parser = argparse.ArgumentParser(
        prog="vools.bridge.md", description="Markdown 即代码：让 .md 文件成为可直接运行的多语言脚本"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # run
    run_parser = subparsers.add_parser("run", help="执行 md 脚本")
    run_parser.add_argument("md_path", help=".md 文件路径")
    run_parser.add_argument("--only", help="只执行这些 tag 的块")
    run_parser.add_argument("--force", action="store_true", help="强制全量重跑")
    run_parser.add_argument("--debug", action="store_true", help="调试模式")
    run_parser.add_argument("--build-dir", help="产物根目录")

    # info
    info_parser = subparsers.add_parser("info", help="干跑：打印块/指令/依赖")
    info_parser.add_argument("md_path", help=".md 文件路径")

    # code
    code_parser = subparsers.add_parser("code", help="只展开源码")
    code_parser.add_argument("md_path", help=".md 文件路径")

    # check
    check_parser = subparsers.add_parser("check", help="依赖/编译器可用性检查")
    check_parser.add_argument("md_path", help=".md 文件路径")

    # clean
    clean_parser = subparsers.add_parser("clean", help="清理产物")
    clean_parser.add_argument("md_path", help=".md 文件路径")
    clean_parser.add_argument("--stale", action="store_true", help="只清清单外的孤儿文件")
    clean_parser.add_argument("--keep", help="保留指定 tag 的产物")

    # rich: 富内容展示预览（计划 §4.2，P1）
    rich_parser = subparsers.add_parser("rich", help="渲染富内容展示块（html/svg/rich）为预览 HTML")
    rich_parser.add_argument("md_path", help=".md 文件路径")
    rich_parser.add_argument("--output", "--out", dest="out", help="预览 HTML 输出路径（默认 build_dir/artifacts/rich/rich-preview.html）")
    rich_parser.add_argument("--open", dest="open_", action="store_true", default=True, help="渲染后自动打开浏览器（默认）")
    rich_parser.add_argument("--no-open", dest="open_", action="store_false", help="渲染后不自动打开浏览器")
    rich_parser.add_argument("--serve", nargs="?", const="8765", metavar="PORT", help="启动本地 HTTP 预览服务（默认端口 8765）")
    rich_parser.add_argument("--hot-reload", dest="hot_reload", choices=("l1", "l2"), default="l1", help="热更新档位（默认 l1 全文替换）")
    rich_parser.add_argument("--viewer", action="store_true", help="使用内置 WebView2 查看器打开富内容预览（P6）")
    rich_parser.add_argument("--watch", action="store_true", help="监听 md 变化自动热更新（隐含 --serve，默认端口 8765）")

    args = parser.parse_args()

    if args.command == "run":
        _cmd_run(args)
    elif args.command == "info":
        _cmd_info(args)
    elif args.command == "code":
        _cmd_code(args)
    elif args.command == "check":
        _cmd_check(args)
    elif args.command == "clean":
        _cmd_clean(args)
    elif args.command == "rich":
        _cmd_rich(args)
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_run(args):
    from .runner import run_md

    only = args.only.split(",") if args.only else None
    result = run_md(
        args.md_path,
        only=only,
        force=args.force,
        debug=args.debug,
        build_dir=args.build_dir,
    )

    print(f"md_hash: {result['md_hash']}")
    print(f"total_duration_ms: {result['total_duration_ms']:.1f}")
    print()

    for block in result["blocks"]:
        status_icon = {
            "ok": "✅",
            "failed": "❌",
            "skipped": "⏭️",
            "timeout": "⏱️",
            "error": "⚠️",
        }.get(block["status"], "?")
        print(
            f"  {status_icon} [{block['index']}] {block['language']} "
            f"tag={block['tag']} status={block['status']} "
            f"({block['duration_ms']:.1f}ms)"
        )

    if result["deps_status"]["missing"]:
        print()
        print(f"Missing deps: {', '.join(result['deps_status']['missing'])}")


def _cmd_info(args):
    from .parser import parse_md

    parsed = parse_md(args.md_path)
    fd = parsed.file_directives

    print(f"File: {args.md_path}")
    print(f"  config: {fd.config or '(auto)'}")
    print(f"  deps: {fd.deps or '(auto)'}")
    print(f"  build-dir: {fd.build_dir}")
    print(f"  entry: {fd.entry or '(none)'}")
    print(f"  only: {fd.only or '(none)'}")
    print(f"  md_hash: {parsed.md_hash}")
    print()

    print(f"Blocks ({len(parsed.blocks)}):")
    for block in parsed.blocks:
        print(f"  [{block.index}] {block.language} " f"directives={block.directives} tag={block.tag}")


def _cmd_code(args):
    from .parser import parse_md

    parsed = parse_md(args.md_path)

    for block in parsed.blocks:
        print(f"# === Block {block.index}: {block.language} ===")
        print(block.content)
        print()


def _cmd_check(args):
    from .parser import parse_md
    from .deps import check_deps

    parsed = parse_md(args.md_path)
    fd = parsed.file_directives

    md_dir = os.path.dirname(os.path.abspath(args.md_path))
    deps_path = fd.deps
    if deps_path and not os.path.isabs(deps_path):
        deps_path = os.path.join(md_dir, deps_path)

    report = check_deps(deps_path, md_dir)

    print("Dependency Check:")
    if report.ok:
        print(f"  ✅ OK: {', '.join(report.ok)}")
    if report.missing:
        print(f"  ❌ Missing: {', '.join(report.missing)}")
    if report.warnings:
        print(f"  ⚠️ Warning: {', '.join(report.warnings)}")


def _cmd_clean(args):
    from .parser import parse_md
    from .artifacts import clean_build

    parsed = parse_md(args.md_path)
    build_dir = parsed.file_directives.build_dir

    if not os.path.isabs(build_dir):
        md_dir = os.path.dirname(os.path.abspath(args.md_path))
        build_dir = os.path.join(md_dir, build_dir)

    keep = args.keep.split(",") if args.keep else None
    clean_build(build_dir, stale=args.stale, keep=keep)
    print(f"Cleaned: {build_dir}")


def _cmd_rich(args):
    """渲染 md 富内容预览（scan_rich + render，支持 --output/--open/--serve，计划 P2~P6）。"""
    from .artifacts import ensure_build_dir
    from .parser import parse_md
    from .rich import RichConfig, scan_rich, render
    from .rich.hotreload import parse_hot_reload_mode

    parsed = parse_md(args.md_path)
    build_dir = parsed.file_directives.build_dir
    if not os.path.isabs(build_dir):
        md_dir = os.path.dirname(os.path.abspath(args.md_path))
        build_dir = os.path.join(md_dir, build_dir)
    ensure_build_dir(build_dir)

    # 文件级 #!rich 指令 + CLI 覆盖（命令行参数优先，计划 §5.3）
    config = RichConfig()
    config.hot_reload = parse_hot_reload_mode(args.hot_reload)
    if getattr(args, "serve", None):
        # serve 模式下默认允许远程链接 opt-in（预览服务仍受 CSP 约束）
        config.allow_remote = True

    doc = scan_rich(args.md_path, build_dir=build_dir, config=config)
    result = render(
        doc,
        interactive=True,
        hot_reload=config.hot_reload,
    )

    if not doc.body_html and not doc.inline_svgs and not doc.inline_htmls:
        print(f"[rich] 未找到 html/svg/rich 展示块与富内容正文: {args.md_path}")
        sys.exit(1)

    if args.out:
        out_path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    else:
        out_path = os.path.join(build_dir, "artifacts", "rich", "rich-preview.html")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result.html)

    print(f"[rich] 预览: {out_path}")
    print(f"[rich] 富内容: 内联 SVG {len(doc.inline_svgs)} / 内嵌 HTML {len(doc.inline_htmls)} / 文件链接 {len(doc.file_links)} / 产物 {len(doc.artifacts)}")

    if args.viewer:
        # P6 内置 WebView2 查看器（open_preview + hot_reload 挂钩）
        from .rich import RichPreviewHost

        md_dir = os.path.dirname(os.path.abspath(args.md_path))
        host = RichPreviewHost()
        session = host.open(
            args.md_path,
            build_dir=build_dir,
            config=config,
            hot_reload=config.hot_reload,
            rich_open_root=md_dir,
        )
        print(f"[rich] viewer: 已打开（block_id={session.block_id}，{config.hot_reload} 热更新就绪）")
        print("[rich] 按 Ctrl+C 退出")
        try:
            import time as _t

            while True:
                _t.sleep(1)
        except KeyboardInterrupt:
            session.close()
            return
        return

    # P6 --watch：隐含 --serve（热更新由 _serve_rich 在 md_path 提供时自动启用）
    if args.watch and not args.serve:
        args.serve = "8765"
        config.allow_remote = True

    if args.open_ and not args.serve:
        import webbrowser

        webbrowser.open(f"file:///{out_path.replace(os.sep, '/')}")

    if args.serve:
        _serve_rich(
            build_dir=build_dir,
            port_str=args.serve,
            preview_path=out_path,
            md_path=args.md_path,
            hot_reload=config.hot_reload,
            rich_config=config,
        )


def _serve_rich(
    build_dir: str,
    port_str: str,
    preview_path: str,
    *,
    md_path: Optional[str] = None,
    hot_reload: str = "l1",
    rich_config=None,
) -> None:
    """启动本地 HTTP 预览服务（线程化，Ctrl+C 退出；P6 支持热更新推送）。

    热更新机制（仅 md_path 提供时启用）：
    - 后台 watcher 每 0.5s 检查 md 文件 mtime，变化后重新 scan_rich + render；
    - L1：生成全文补丁（build_l1_patch 替换预览 iframe 的 srcdoc）；
    - L2：提取 data-rich-l2 受控区域，HotReloadManager 按哈希 diff 只推送
      有变化的区域（build_l2_patch + replaceChildren）；
    - 预览页响应时注入 build_hot_reload_client 轮询脚本，轮询
      /__hot_reload__/poll 端点取补丁并执行。
    """
    import http.server
    import json as _json
    import threading
    import time as _time

    from .rich import HotReloadManager, scan_rich, render
    from .rich.hotreload import build_hot_reload_client, extract_l2_regions

    try:
        port = int(port_str)
    except ValueError:
        port = 8765

    preview_name = os.path.basename(preview_path)
    build_dir_abs = os.path.abspath(build_dir)

    # ── P6 热更新状态：版本号 + 当前补丁（watcher 写，handler 读）──
    state = {
        "version": 0,
        "patch": "",
        "lock": threading.Lock(),
    }
    hr_manager = HotReloadManager(mode=hot_reload)

    if md_path:
        md_abs = os.path.abspath(md_path)

        def _reload_doc() -> None:
            """重新扫描渲染 md，按档位生成补丁并推进版本。"""
            try:
                doc = scan_rich(md_abs, build_dir=build_dir_abs, config=rich_config)
                if hot_reload == "l2":
                    # L2：纯内层文档（frag 带 data-rich-l2），按区域 diff 推送
                    inner = render(doc, interactive=False, hot_reload="l2").html
                    updates = extract_l2_regions(inner)
                    patch = hr_manager.patch(new_contents=updates)
                else:
                    # L1：纯内层文档全文替换（预览页 iframe srcdoc）
                    inner = render(doc, interactive=False, hot_reload="l1").html
                    patch = hr_manager.patch(full_html=inner)
                with state["lock"]:
                    if patch:
                        state["version"] += 1
                        state["patch"] = patch
            except Exception as e:  # noqa: BLE001 渲染失败不中断服务
                print(f"[rich] hot-reload 失败: {e}")

        def _watch_loop() -> None:
            try:
                last_mtime = os.path.getmtime(md_abs)
            except OSError:
                last_mtime = 0.0
            _reload_doc()  # 启动即推一版基线补丁（避免首轮差异）
            while True:
                _time.sleep(0.5)
                try:
                    mt = os.path.getmtime(md_abs)
                except OSError:
                    continue
                if mt == last_mtime:
                    continue
                last_mtime = mt
                _reload_doc()

        watcher = threading.Thread(target=_watch_loop, daemon=True, name="rich-hot-reload")
        watcher.start()
        print(f"[rich] hot-reload: {hot_reload} 已启用（监听 {md_abs}）")

    class RichHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *hargs, **hkwargs):
            super().__init__(*hargs, directory=build_dir_abs, **hkwargs)

        def _handle_poll(self) -> bool:
            """/__hot_reload__/poll?v=N → {"version","mode","patch"}"""
            try:
                client_v = int(self.path.split("v=")[-1].split("&")[0])
            except Exception:
                client_v = 0
            with state["lock"]:
                ver = state["version"]
                patch = state["patch"] if ver != client_v else ""
            body = _json.dumps(
                {"version": ver, "mode": hot_reload, "patch": patch},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return True

        def do_GET(self):
            if self.path.startswith("/__hot_reload__/poll"):
                self._handle_poll()
                return
            if self.path in ("/", "/index.html"):
                self.path = "/" + preview_name
            if self.path == "/" + preview_name:
                # 注入热更新客户端脚本（运行时增强，不落盘）
                try:
                    with open(os.path.join(build_dir_abs, preview_name), "r", encoding="utf-8") as f:
                        html = f.read()
                    client = build_hot_reload_client(hot_reload)
                    if "</body>" in html:
                        html = html.replace("</body>", "<script>" + client + "</script></body>")
                    else:
                        html += "<script>" + client + "</script>"
                    data = html.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except OSError:
                    pass
            return super().do_GET()

        def log_message(self, fmt, *hargs):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), RichHandler)
    print(f"[rich] serve: http://127.0.0.1:{port}/{preview_name}")
    print("[rich] 按 Ctrl+C 退出服务")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def _extract_body(doc: str) -> str:
    """提取完整 HTML 文档的 <body> 内容，用于预览页拼接。"""
    start = doc.lower().find("<body>")
    end = doc.lower().rfind("</body>")
    if start >= 0 and end > start:
        return doc[start + len("<body>") : end]
    return doc


if __name__ == "__main__":
    main()

