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
    """--json 输出必须是完整 ProbeReport（含四个维度 + items + summary）。

    审计加固：原来只断言 `isinstance(items, list)` 与 `total_items > 0`，
    probe 只返回 1 条、或 items 全是空壳/维度被换成 `{"stub": 1}` 也能过。
    现在断言具体契约：四个维度非空 dict、每条 item 有 name/category、
    summary 的总数与 items/分类计数自洽、report_source 明确。
    """
    rc, out = _run(['probe', '--json', '--force-refresh'], capsys)
    assert rc == 0
    data = json.loads(out)
    assert 'timestamp' in data
    for dim in ('platform', 'permissions', 'environment', 'resources'):
        assert isinstance(data[dim], dict) and data[dim], '%s 维度为空' % dim
    items = data['items']
    assert items, 'probe 报告 items 不能为空'
    assert all(item.get('name') for item in items), '存在没有 name 的 item'
    assert all(item.get('category') for item in items), '存在没有 category 的 item'
    assert isinstance(data.get('report_source'), str) and data['report_source']
    summary = data['summary']
    assert summary['total_items'] == len(items), \
        'summary.total_items 与实际 items 数不一致: %r vs %d' % (
            summary.get('total_items'), len(items))
    by_category = summary.get('by_category') or {}
    assert by_category, 'summary.by_category 为空'
    assert sum(entry['total'] for entry in by_category.values()) == len(items)


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


def test_probe_max_age_default_and_override(capsys, monkeypatch):
    """第 20 轮（#15）：`max_age` 不抄 3600 字面量，断言**语义**：

    1. parser 默认值 == 核心 `probe()` 的默认值（单一真源；任一侧被改都会红）；
    2. 显式 `--max-age` 覆盖生效，并**真的传进 probe()**（打桩捕获 kwargs）；
    3. 不传时传入的是核心默认值（不是硬编码在 CLI 里的另一份）。
    """
    import inspect
    from vools.actus import probe as probe_mod

    core_default = inspect.signature(probe_mod.probe).parameters['max_age'].default
    parser = cli._build_parser()
    assert parser.parse_args(['probe']).max_age == core_default, \
        'CLI 默认 max_age 与 probe() 默认值不一致（出现两份真源）'
    assert parser.parse_args(['probe', '--max-age', '7']).max_age == 7

    captured = {}

    class _Report:
        def to_dict(self):
            return {'report_source': 'probe', 'items': [], 'summary': {}}

    def fake_probe(**kwargs):
        captured.update(kwargs)
        return _Report()

    monkeypatch.setattr(probe_mod, 'probe', fake_probe)
    rc = cli._cmd_probe(parser.parse_args(['probe', '--max-age', '7', '--json']))
    assert rc == 0
    assert captured.get('max_age') == 7, captured
    assert captured.get('force_refresh') is False

    captured.clear()
    rc = cli._cmd_probe(parser.parse_args(['probe', '--json']))
    assert rc == 0 and captured.get('max_age') == core_default, captured


def test_probe_verbose_json(capsys):
    """verbose + json 组合：verbose 打点不影响 JSON 合法性。"""
    rc, out = _run(['probe', '--verbose', '--json'], capsys)
    assert rc == 0
    # verbose 的打点（[probe] ...）先打印，_out 的 JSON 是 indent=2 多行；
    # 从第一个 '{' 起解析即可（打点行不含 '{'）。
    assert '{' in out, 'stdout 中没有 JSON 输出'
    data = json.loads(out[out.index('{'):])
    assert 'platform' in data
