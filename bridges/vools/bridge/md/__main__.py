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
    rich_parser.add_argument("--out", help="预览 HTML 输出路径（默认 build_dir/artifacts/rich/rich-preview.html）")
    rich_parser.add_argument("--no-open", action="store_true", help="渲染后不自动打开浏览器")

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
    """渲染 md 中的富内容展示块（html/svg/rich）为预览 HTML（计划 §4.2，P1）。"""
    from .parser import parse_md
    from .runner import _execute_rich_block
    from .artifacts import ensure_build_dir
    from .rich.sanitize import build_csp_meta

    parsed = parse_md(args.md_path)
    build_dir = parsed.file_directives.build_dir
    if not os.path.isabs(build_dir):
        md_dir = os.path.dirname(os.path.abspath(args.md_path))
        build_dir = os.path.join(md_dir, build_dir)
    ensure_build_dir(build_dir)

    rich_blocks = [b for b in parsed.blocks if b.language in ("html", "svg", "rich")]
    if not rich_blocks:
        print(f"[rich] 未找到 html/svg/rich 展示块: {args.md_path}")
        sys.exit(1)

    context = {"build_dir": build_dir}
    card_parts = []
    for block in rich_blocks:
        stdout, stderr, exit_code = _execute_rich_block(block, context, {})
        if exit_code != 0:
            print(f"[rich] block {block.index} 渲染失败: {stderr}")
            sys.exit(1)
        print(stdout)
        card_path = os.path.join(build_dir, "artifacts", "rich", f"block_{block.index}.html")
        if os.path.exists(card_path):
            with open(card_path, "r", encoding="utf-8") as f:
                card_parts.append(_extract_body(f.read()))

    # 预览页：L1 基线 CSP + 各卡片 body 拼接（决策 3）
    preview_html = (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        + build_csp_meta(level=1, allow_remote_images=False)
        + "\n</head>\n<body>\n"
        + "\n".join(card_parts)
        + "\n</body>\n</html>"
    )

    if args.out:
        out_path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    else:
        out_path = os.path.join(build_dir, "artifacts", "rich", "rich-preview.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(preview_html)

    print(f"[rich] 预览: {out_path}")
    if not args.no_open:
        import webbrowser

        webbrowser.open(f"file:///{out_path.replace(os.sep, '/')}")
    print(f"[rich] 完成: {len(card_parts)} 个卡片")


def _extract_body(doc: str) -> str:
    """提取完整 HTML 文档的 <body> 内容，用于预览页拼接。"""
    start = doc.lower().find("<body>")
    end = doc.lower().rfind("</body>")
    if start >= 0 and end > start:
        return doc[start + len("<body>") : end]
    return doc


if __name__ == "__main__":
    main()
