"""
vools.bridge.md CLI 入口

用法：
    python -m vools.bridge.md run script.md [--only tag] [--force] [--debug]
    python -m vools.bridge.md info script.md
    python -m vools.bridge.md code script.md
    python -m vools.bridge.md check script.md
    python -m vools.bridge.md clean script.md [--stale] [--keep tag]
"""
import sys, os, json, argparse


def main():
    parser = argparse.ArgumentParser(
        prog='vools.bridge.md',
        description='Markdown 即代码：让 .md 文件成为可直接运行的多语言脚本'
    )
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # run
    run_parser = subparsers.add_parser('run', help='执行 md 脚本')
    run_parser.add_argument('md_path', help='.md 文件路径')
    run_parser.add_argument('--only', help='只执行这些 tag 的块')
    run_parser.add_argument('--force', action='store_true', help='强制全量重跑')
    run_parser.add_argument('--debug', action='store_true', help='调试模式')
    run_parser.add_argument('--build-dir', help='产物根目录')

    # info
    info_parser = subparsers.add_parser('info', help='干跑：打印块/指令/依赖')
    info_parser.add_argument('md_path', help='.md 文件路径')

    # code
    code_parser = subparsers.add_parser('code', help='只展开源码')
    code_parser.add_argument('md_path', help='.md 文件路径')

    # check
    check_parser = subparsers.add_parser('check', help='依赖/编译器可用性检查')
    check_parser.add_argument('md_path', help='.md 文件路径')

    # clean
    clean_parser = subparsers.add_parser('clean', help='清理产物')
    clean_parser.add_argument('md_path', help='.md 文件路径')
    clean_parser.add_argument('--stale', action='store_true', help='只清清单外的孤儿文件')
    clean_parser.add_argument('--keep', help='保留指定 tag 的产物')

    args = parser.parse_args()

    if args.command == 'run':
        _cmd_run(args)
    elif args.command == 'info':
        _cmd_info(args)
    elif args.command == 'code':
        _cmd_code(args)
    elif args.command == 'check':
        _cmd_check(args)
    elif args.command == 'clean':
        _cmd_clean(args)
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_run(args):
    from .runner import run_md

    only = args.only.split(',') if args.only else None
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

    for block in result['blocks']:
        status_icon = {
            'ok': '✅',
            'failed': '❌',
            'skipped': '⏭️',
            'timeout': '⏱️',
            'error': '⚠️',
        }.get(block['status'], '?')
        print(f"  {status_icon} [{block['index']}] {block['language']} "
              f"tag={block['tag']} status={block['status']} "
              f"({block['duration_ms']:.1f}ms)")

    if result['deps_status']['missing']:
        print()
        print(f"Missing deps: {', '.join(result['deps_status']['missing'])}")


def _cmd_info(args):
    from .parser import parse_md
    from .deps import check_deps

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
        print(f"  [{block.index}] {block.language} "
              f"directives={block.directives} "
              f"tag={block.tag}")


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
        build_dir = os.path.join(os.path.dirname(os.path.abspath(args.md_path)), build_dir)

    keep = args.keep.split(',') if args.keep else None
    clean_build(build_dir, stale=args.stale, keep=keep)
    print(f"Cleaned: {build_dir}")


if __name__ == '__main__':
    main()
