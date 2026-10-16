# -*- coding: utf-8 -*-
"""tests/test_csharp_cache.py — C# 缓存命中不变式（dotnet-free 单元锁）。

钉 BUG-58：_call_csharp_func 实际跑的是【同目录同名的 apphost/.exe】，但旧
check_cache 只看 .dll 存在即判命中——半截缓存（.dll 有、.exe 无，dotnet publish
被中断时实测会出现）会返回坏路径，调用期抛 FileNotFoundError。

本锁不调 dotnet（快、确定性、不污染共享 Temp 缓存），只验缓存判定的不变式：
只有 .dll 与同名 .exe 同时存在，check_cache 才返回路径；缺一律视为未命中（返回
None），从而让上层 _compile_with_cache 触发重编自愈。
"""

import hashlib
import os

import pytest

from vools.bridge.csharp.compiler import CSharpBridge, _cache_entry_valid


CODE = 'namespace VoolsBridge { public class BridgeFunctions { public static int add(int a, int b) { return a + b; } } }'


def _expected_name(func_name):
    """复刻 CSharpBridge 的缓存键算法，得到 base 名（不含扩展名）。"""
    h = hashlib.md5(CODE.encode('utf-8')).hexdigest()
    return f'{func_name}_{h}'


def test_cache_hit_requires_dll_and_exe(tmp_path):
    bridge = CSharpBridge()
    base = _expected_name('add')
    dll = tmp_path / (base + '.dll')

    # 只有 .dll：半截产物，必须判为未命中（否则调用期会 FileNotFoundError）
    dll.write_text('stub')
    assert _cache_entry_valid(str(tmp_path), base) is False
    assert bridge.check_cache(CODE, 'add', cache_dir=str(tmp_path)) is None

    # 补上同名 .exe：齐全，判为命中
    exe = tmp_path / (base + '.exe')
    exe.write_text('stub')
    assert _cache_entry_valid(str(tmp_path), base) is True
    got = bridge.check_cache(CODE, 'add', cache_dir=str(tmp_path))
    assert got is not None and got.endswith(base + '.dll')


def test_cache_miss_when_no_dll(tmp_path):
    bridge = CSharpBridge()
    assert bridge.check_cache(CODE, 'add', cache_dir=str(tmp_path)) is None

    # 只放 .exe 不放 .dll，仍不算命中
    base = _expected_name('add')
    (tmp_path / (base + '.exe')).write_text('stub')
    assert bridge.check_cache(CODE, 'add', cache_dir=str(tmp_path)) is None
