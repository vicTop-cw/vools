"""
vools.md CLI 命令行工具

用法：
    python -m vools.md.cli md2html input.md -o output.html
    python -m vools.md.cli md2json input.md -o output.json
    python -m vools.md.cli md2org input.md -o output.org
    python -m vools.md.cli md2text input.md -o output.txt

编码：读入统一走 ``vools.encoding.filecodec.read_text``（自动探测 GBK/UTF-8/BOM，
不再因源文件带 BOM 或为 GBK 而崩）；写出统一走 ``write_text``（默认 UTF-8 无 BOM，
跨平台最安全）。
"""
import sys
import argparse

from ..encoding import read_text, write_text


def cmd_md2html(args):
    from .html import to_html_file
    md = read_text(args.input)
    to_html_file(md, args.output)
    print(f'HTML written to {args.output}')


def cmd_md2json(args):
    from .utils import to_json
    md = read_text(args.input)
    json_str = to_json(md, indent=args.indent)
    write_text(args.output, json_str)
    print(f'JSON written to {args.output}')


def cmd_md2org(args):
    from .utils import to_org_mode
    md = read_text(args.input)
    org = to_org_mode(md)
    write_text(args.output, org)
    print(f'Org-mode written to {args.output}')


def cmd_md2text(args):
    from .utils import to_plain_text
    md = read_text(args.input)
    text = to_plain_text(md)
    write_text(args.output, text)
    print(f'Text written to {args.output}')


def main():
    parser = argparse.ArgumentParser(prog='vools.md', description='Markdown 处理工具')
    subparsers = parser.add_subparsers(dest='command')

    # md2html
    p2h = subparsers.add_parser('md2html', help='Convert Markdown to HTML')
    p2h.add_argument('input', help='Input .md file')
    p2h.add_argument('-o', '--output', required=True, help='Output .html file')
    p2h.set_defaults(func=cmd_md2html)

    # md2json
    p2j = subparsers.add_parser('md2json', help='Convert Markdown to JSON AST')
    p2j.add_argument('input', help='Input .md file')
    p2j.add_argument('-o', '--output', required=True, help='Output .json file')
    p2j.add_argument('--indent', type=int, default=2, help='JSON indent')
    p2j.set_defaults(func=cmd_md2json)

    # md2org
    p2o = subparsers.add_parser('md2org', help='Convert Markdown to Org-mode')
    p2o.add_argument('input', help='Input .md file')
    p2o.add_argument('-o', '--output', required=True, help='Output .org file')
    p2o.set_defaults(func=cmd_md2org)

    # md2text
    p2t = subparsers.add_parser('md2text', help='Convert Markdown to plain text')
    p2t.add_argument('input', help='Input .md file')
    p2t.add_argument('-o', '--output', required=True, help='Output .txt file')
    p2t.set_defaults(func=cmd_md2text)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == '__main__':
    main()


__all__ = [
    'cmd_md2html',
    'cmd_md2json',
    'cmd_md2org',
    'cmd_md2text',
    'main'
]