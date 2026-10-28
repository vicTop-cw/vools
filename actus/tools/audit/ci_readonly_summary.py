# -*- coding: utf-8 -*-
"""把 `readonly_name_writes.py --json` 的结果渲染成 Job Summary 用的 Markdown。

用法:
    python tools/audit/readonly_name_writes.py --depth 3 --json ro.json
    python tools/audit/ci_readonly_summary.py ro.json >> "$GITHUB_STEP_SUMMARY"

⚠️ **这是告警级输出，不是门禁**：AST 扫描看得到"名字像只读但链路里有写"，
但有已知误报（kwarg 常量关闭写、三方库按名字归类、动态分派），详见
`readonly_name_writes.py` 的 docstring。CI 里配合 `continue-on-error: true` 使用。
"""
import argparse
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('json_path')
    ap.add_argument('--max', type=int, default=15)
    args = ap.parse_args()

    if not os.path.isfile(args.json_path):
        print('### 只读命名 vs 写副作用（告警级）')
        print()
        print('⚠️ 扫描器没有产出结果文件（扫描本身失败），请查看日志。')
        return 0

    with open(args.json_path, encoding='utf-8') as f:
        rows = json.load(f)
    if isinstance(rows, dict):
        rows = rows.get('candidates') or rows.get('results') or []

    direct = [r for r in rows if r.get('has_direct')]
    indirect = [r for r in rows if not r.get('has_direct')]

    print('### 只读命名 vs 写副作用（**告警级，不阻塞合并**）')
    print()
    print('扫描器：`actus/tools/audit/readonly_name_writes.py --depth 3` · '
          '共 **%d** 条候选（其中直接写 %d / 仅传递写 %d）'
          % (len(rows), len(direct), len(indirect)))
    print()
    print('> 已知误报：kwarg 常量关闭写（如 `_persist=False`）、三方库按名字归类'
          '（`subprocess.run`/`Path.unlink`）、动态分派。**人工确认后再改**，'
          '不要为了清零而放宽检测。')
    print()

    if direct:
        print('| 函数 | 位置 | 直接写 |')
        print('|---|---|---|')
        for r in direct[:args.max]:
            print('| `%s` | `%s:%s` | %s |' % (
                r.get('qual'), r.get('file'), r.get('line'),
                ', '.join('`%s`' % d for d in (r.get('direct') or [])[:4])))
        print()
    if indirect:
        print('<details><summary>仅传递写（%d 条，展开看调用链）</summary>' % len(indirect))
        print()
        for r in indirect[:args.max]:
            chains = []
            for symbol, info in (r.get('transitive') or {}).items():
                chain = info.get('chain') if isinstance(info, dict) else None
                chains.append('`%s`%s' % (symbol, (' ← ' + chain) if chain else ''))
            print('- `%s` (%s:%s): %s' % (r.get('qual'), r.get('file'), r.get('line'),
                                          '; '.join(chains[:3]) or '—'))
        print()
        print('</details>')
    return 0


if __name__ == '__main__':
    sys.exit(main())
