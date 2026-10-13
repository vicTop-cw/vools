"""vools.bridge.core.wsl 命令解析测试（不依赖真实 WSL/编译器）。

回归点：resolve_command 在本地 PATH 和 WSL 都找不到命令时，会回退一个
【未经验证】的裸命令名（执行期兼容）；这个回退不能被当成「工具链可用」。
可用性必须用 command_resolves() 判断 —— 否则 available() 谎报 True、
真正执行才 FileNotFoundError（pentad p5c 实测事故）。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vools.bridge.core import wsl


def test_command_resolves_true_when_on_path(monkeypatch):
    monkeypatch.setattr(wsl.shutil, 'which', lambda name: '/usr/bin/' + name)
    # 即使 WSL 探测不可用，PATH 命中也算可用
    monkeypatch.setattr(wsl, 'check_wsl_command', lambda name: False)
    assert wsl.command_resolves('ruby') is True


def test_command_resolves_true_via_wsl(monkeypatch):
    monkeypatch.setattr(wsl.shutil, 'which', lambda name: None)
    monkeypatch.setattr(wsl, 'check_wsl_command', lambda name: True)
    assert wsl.command_resolves('p5c') is True


def test_command_resolves_false_when_nowhere(monkeypatch):
    monkeypatch.setattr(wsl.shutil, 'which', lambda name: None)
    monkeypatch.setattr(wsl, 'check_wsl_command', lambda name: False)
    assert wsl.command_resolves('p5c') is False


def test_resolve_command_fallback_is_bare_name_but_not_claim(monkeypatch):
    """两处都找不到：回退裸名（执行期兼容），但 command_resolves 仍为 False。"""
    monkeypatch.setattr(wsl.shutil, 'which', lambda name: None)
    monkeypatch.setattr(wsl, 'check_wsl_command', lambda name: False)
    prefix, _conv, use_wsl = wsl.resolve_command('p5c')
    assert prefix == ['p5c']          # 执行期仍给一个可交给 OS 的命令
    assert use_wsl is False
    assert wsl.command_resolves('p5c') is False   # 关键：不谎报可用


def test_pentad_resolves_to_empty_when_toolchain_missing(monkeypatch):
    """p5c 在 configs/PATH/WSL 都不存在时，解析结果必须是空前缀（不可用信号）。

    _resolve_pentad_command 在函数内 import configs/wsl，故 patch 这两个
    模块的相应符号即可；模块导入期缓存的 _P5C_OK == bool(空前缀) == False。
    """
    import shutil
    from vools.bridge.pentad import compiler as pc
    import vools.bridge.configs as cfg

    monkeypatch.setattr(cfg, 'resolve_compiler', lambda lang: None)
    monkeypatch.setattr(wsl, 'command_resolves', lambda name: False)
    monkeypatch.setattr(shutil, 'which', lambda name: None)  # _find_p5c 内部 import shutil

    prefix, _conv, use_wsl = pc._resolve_pentad_command()
    assert prefix == []
    assert use_wsl is False
    assert bool(prefix) is False   # 即 _P5C_OK 的取值：不可用
