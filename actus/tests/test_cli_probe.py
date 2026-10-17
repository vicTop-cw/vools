# -*- coding: utf-8 -*-
"""actus/tests/test_cli_probe.py — probe CLI 集成验收测试。

覆盖 analysis/PROBE_PLAN.md §9 Phase 3：
- `python -m actus probe`（人类可读输出）
- `python -m actus probe --json`（机器消费）
- `--force-refresh` 强制刷新、`--max-age` 缓存有效期、`--verbose`
- `_build_parser()` 已注册 probe 子命令

与同目录其它 actus 测试一致：先跑本地源码引导，让 vools.actus 命中源码树。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402  — 必须先于 vools.actus 导入
_ai_local_bootstrap.install()

from vools.actus import cli


def _run(argv, capsys):
    """运行 CLI main()，返回 (退出码, stdout 文本)。"""
    rc = cli.main(argv)
    captured = capsys.readouterr()
    return rc, captured.out


def test_parser_registers_probe_subcommand():
    """_build_parser 必须注册 probe 子命令及其参数。"""
    parser = cli._build_parser()
    for argv in (['probe'],
                 ['probe', '--json'],
                 ['probe', '--force-refresh'],
                 ['probe', '--force'],
                 ['probe', '--max-age', '120'],
                 ['probe', '--verbose', '--json']):
        # 解析不抛错即注册成功
        args = parser.parse_args(argv)
        assert args.command == 'probe'


def test_probe_json_output(capsys):
    """--json 输出必须是完整 ProbeReport（含四个维度 + items + summary）。"""
    rc, out = _run(['probe', '--json', '--force-refresh'], capsys)
    assert rc == 0
    data = json.loads(out)
    assert 'timestamp' in data
    assert 'platform' in data
    assert 'permissions' in data
    assert 'environment' in data
    assert 'resources' in data
    assert isinstance(data['items'], list)
    assert 'summary' in data
    assert data['summary']['total_items'] > 0


def test_probe_human_readable_output(capsys):
    """默认人类可读模式输出 format_summary 摘要。"""
    rc, out = _run(['probe'], capsys)
    assert rc == 0
    assert 'vools probe report' in out
    assert '[Platform]' in out
    assert '[Summary]' in out


def test_probe_force_refresh_flag_maps_to_kwarg(capsys):
    """--force-refresh 与 --force 别名解析到同一 dest。"""
    parser = cli._build_parser()
    args = parser.parse_args(['probe', '--force-refresh'])
    assert args.force_refresh is True
    args2 = parser.parse_args(['probe', '--force'])
    assert args2.force_refresh is True
    args3 = parser.parse_args(['probe'])
    assert args3.force_refresh is False
    assert args3.as_json is False
    assert args3.max_age == 3600


def test_probe_verbose_json(capsys):
    """verbose + json 组合：verbose 打点不影响 JSON 合法性。"""
    rc, out = _run(['probe', '--verbose', '--json'], capsys)
    assert rc == 0
    # verbose 的打点（[probe] ...）先打印，_out 的 JSON 是 indent=2 多行；
    # 从第一个 '{' 起解析即可（打点行不含 '{'）。
    assert '{' in out, 'stdout 中没有 JSON 输出'
    data = json.loads(out[out.index('{'):])
    assert 'platform' in data
