#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试耗时守卫（第 22 轮）：全量（或快跑）记录每条耗时，与基线对比，渐进退化告警。

背景：性能退化是渐进的 —— 每次 +0.5s 没人注意，20 次就慢 10s。
这与"假的保护"同类：**没有测量就没有守卫**。本脚本只**告警**不 fail，
避免文档/环境抖动把 CI 弄红。

用法：
    # 1) 直接跑全量并对比基线（默认路径 actus/tools/audit/test_duration_baseline.json）
    python actus/tools/audit/check_test_duration.py

    # 2) 只跑快子集
    python actus/tools/audit/check_test_duration.py --fast

    # 3) 用已保存的 pytest --durations=0 输出（不重复跑）
    python actus/tools/audit/check_test_duration.py --from-file /tmp/dur.txt

    # 4) 刷新基线（通常在"确认当前变慢是合理的"之后执行）
    python actus/tools/audit/check_test_duration.py --from-file /tmp/dur.txt --update-baseline

    # 5) 有告警时返回非零（默认永远返回 0）
    python actus/tools/audit/check_test_duration.py --strict

判定（默认阈值，均可命令行调整）：
  * 与基线相比单条涨 > 50% **且** 绝对值多 > 0.5s → 告警；
  * 基线里没有的新测试、单条 > 5s → 告警（新增慢测试）；
  * 基线里单条 < 0.2s 的条目不做比值告警（噪音）。
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ACTUS_ROOT = os.path.dirname(os.path.dirname(HERE))
DEFAULT_BASELINE = os.path.join(HERE, 'test_duration_baseline.json')

_DUR = re.compile(r'\s*([0-9.]+)s\s+(call|setup|teardown)\s+(tests[\\/]\S+)')


def parse_durations(text):
    """pytest --durations=0 文本 → {test_name: call_seconds}（只取 call 阶段）。"""
    out = {}
    for line in text.splitlines():
        m = _DUR.match(line)
        if not m:
            continue
        seconds, phase, name = float(m.group(1)), m.group(2), m.group(3)
        if phase != 'call':
            continue
        name = name.replace('\\', '/')
        out[name] = round(max(out.get(name, 0.0), seconds), 3)
    return out


def run_pytest(fast=False):
    args = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
            '--no-header', '--durations=0']
    if fast:
        args += ['-m', 'not slow']
    args.append('tests')
    proc = subprocess.run(args, cwd=ACTUS_ROOT, capture_output=True, text=True,
                          encoding='utf-8', errors='replace')
    return proc.stdout + '\n' + proc.stderr, proc.returncode


def compare(current, baseline, ratio=1.5, min_delta=0.5, new_slow=5.0,
            min_baseline=0.2):
    warnings = []
    for name, sec in sorted(current.items(), key=lambda kv: -kv[1]):
        if name not in baseline:
            if sec > new_slow:
                warnings.append(('NEW-SLOW', name, None, sec,
                                 '新增测试单条 >%.1fs' % new_slow))
            continue
        old = baseline[name]
        if old < min_baseline:
            continue
        if sec > old * ratio and (sec - old) > min_delta:
            warnings.append(('REGRESS', name, old, sec,
                             '较基线涨 %.0f%% (+%.2fs)'
                             % ((sec / old - 1) * 100, sec - old)))
    return warnings


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description='测试耗时基线与渐进退化告警')
    ap.add_argument('--baseline', default=DEFAULT_BASELINE)
    ap.add_argument('--from-file', default=None,
                    help='读取已有 pytest --durations=0 输出（不重新跑）')
    ap.add_argument('--fast', action='store_true', help='只跑 -m "not slow"')
    ap.add_argument('--update-baseline', action='store_true')
    ap.add_argument('--strict', action='store_true', help='有告警时返回 1')
    ap.add_argument('--ratio', type=float, default=1.5)
    ap.add_argument('--min-delta', type=float, default=0.5)
    ap.add_argument('--new-slow', type=float, default=5.0)
    ap.add_argument('--top', type=int, default=10)
    args = ap.parse_args()

    if args.from_file:
        text = open(args.from_file, encoding='utf-8', errors='replace').read()
        rc = 0
    else:
        text, rc = run_pytest(fast=args.fast)
        if rc != 0:
            print('[!] pytest 返回非零（%d）——仍继续解析耗时' % rc)

    current = parse_durations(text)
    if not current:
        print('[X] 没有解析到任何 duration 行（pytest 输出格式变了？）')
        return 2

    print('=== 本次最慢 %d 条 ===' % args.top)
    for name, sec in sorted(current.items(), key=lambda kv: -kv[1])[:args.top]:
        print('  %6.2fs  %s' % (sec, name))

    if args.update_baseline:
        json.dump(current, open(args.baseline, 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print('\n✅ 基线已更新: %s（%d 条）' % (args.baseline, len(current)))
        return 0

    if not os.path.isfile(args.baseline):
        print('\nℹ️ 基线不存在（%s）；先跑 --update-baseline 建立基线' % args.baseline)
        return 0

    baseline = json.load(open(args.baseline, encoding='utf-8'))
    warnings = compare(current, baseline, args.ratio, args.min_delta,
                       args.new_slow)
    if not warnings:
        print('\n✅ 无耗时告警（%d 条与基线对比）' % len(current))
        return 0

    print('\n⚠️ 耗时告警 %d 条：' % len(warnings))
    for kind, name, old, sec, why in warnings:
        if old is None:
            print('  [%s] %s：%.2fs（%s）' % (kind, name, sec, why))
        else:
            print('  [%s] %s：%.2fs → %.2fs（%s）' % (kind, name, old, sec, why))
    print('\n（只告警不失败；确认合理后 --update-baseline 刷新基线）')
    return 1 if args.strict else 0


if __name__ == '__main__':
    sys.exit(main())
