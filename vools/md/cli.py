"""
vools.md CLI 命令行工具

用法：
    python -m vools.md.cli md2html input.md -o output.html
    python -m vools.md.cli md2json input.md -o output.json
    python -m vools.md.cli md2org input.md -o output.org
    python -m vools.md.cli md2text input.md -o output.txt
"""
import sys
import argparse


def cmd_md2html(args):
    from .html import to_html_file
    with open(args.input, 'r', encoding='utf-8') as f:
        md = f.read()
    to_html_file(md, args.output)
    print(f'HTML written to {args.output}')


def cmd_md2json(args):
    from .utils import to_json
    with open(args.input, 'r', encoding='utf-8') as f:
        md = f.read()
    json_str = to_json(md, indent=args.indent)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(json_str)
    print(f'JSON written to {args.output}')


def cmd_md2org(args):
    from .utils import to_org_mode
    with open(args.input, 'r', encoding='utf-8') as f:
        md = f.read()
    org = to_org_mode(md)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(org)
    print(f'Org-mode written to {args.output}')


def cmd_md2text(args):
    from .utils import to_plain_text
    with open(args.input, 'r', encoding='utf-8') as f:
        md = f.read()
    text = to_plain_text(md)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(text)
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
