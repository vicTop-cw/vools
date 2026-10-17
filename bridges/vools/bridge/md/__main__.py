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

    if args.open_ and not args.serve:
        import webbrowser

        webbrowser.open(f"file:///{out_path.replace(os.sep, '/')}")

    if args.serve:
        _serve_rich(build_dir, args.serve, out_path)


def _serve_rich(build_dir: str, port_str: str, preview_path: str) -> None:
    """启动本地 HTTP 预览服务（线程化，Ctrl+C 退出）。"""
    import http.server
    import threading

    try:
        port = int(port_str)
    except ValueError:
        port = 8765

    preview_name = os.path.basename(preview_path)
    build_dir_abs = os.path.abspath(build_dir)

    class RichHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *hargs, **hkwargs):
            super().__init__(*hargs, directory=build_dir_abs, **hkwargs)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.path = "/" + preview_name
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

