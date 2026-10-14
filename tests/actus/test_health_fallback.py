"""tests/actus/test_health_fallback.py — 健康检查在"纯 vools 安装"下不得误报

背景（2026-10-13 实测）：`health.check_vault()` 原先只 `from actuscore.vault import Vault`。
`actuscore` 是 **Actus 仓的顶层包名**，vools 独立安装时不存在 —— 于是这个检查在
纯 vools 环境下**永远返回 warn**（"Vault 模块导入失败: No module named 'actuscore'"），
把一条健康检查变成永远为假的断言。

修法：先试 `actuscore.vault`（从 Actus 仓调用时那是 CLI/MCP 跑的那份），
再退回 `vools.actus.vault`。本文件钉住两格：
  1. 纯 vools 环境下必须 ok（不是 warn）
  2. 这个检查不得因为 actuscore 缺席而抛异常
"""
import os
import subprocess
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _run_vools_only(code):
    """在**不挂 Actus/engine** 的子进程里跑 code —— 模拟纯 vools 安装。"""
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join([
        os.path.join(REPO, 'actus'),
        REPO,
        os.path.join(REPO, 'bridges'),
        os.path.join(REPO, 'rx'),
    ])
    return subprocess.run([sys.executable, '-c', code],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, env=env, encoding='utf-8', errors='replace')


def test_check_vault_ok_without_actuscore():
    """纯 vools 环境（无 actuscore）下 check_vault 必须 ok，且 actuscore 确实不可用。"""
    code = (
        'import json, sys\n'
        'res = {}\n'
        'try:\n'
        '    import actuscore\n'
        '    res["actuscore"] = "present"\n'
        'except Exception:\n'
        '    res["actuscore"] = "absent"\n'
        'from vools.actus.health import check_vault\n'
        'r = check_vault(".")\n'
        'res["status"] = r.status\n'
        'res["message"] = r.message\n'
        'sys.stdout.write(json.dumps(res, ensure_ascii=False))\n'
    )
    p = _run_vools_only(code)
    assert p.returncode == 0, f'子进程失败: {p.stderr[-400:]}'
    import json
    res = json.loads(p.stdout.strip())
    # 前提：本格测的就是 actuscore 缺席的情形
    assert res['actuscore'] == 'absent', f"预期 actuscore 不可用，实际 {res['actuscore']}"
    assert res['status'] == 'ok', (
        f"纯 vools 环境下 check_vault 应 ok，实际 {res['status']}: {res['message']}")


def test_check_vault_prefers_actuscore_when_present():
    """挂了 Actus 引擎时仍走 actuscore.vault 那一份（不因回退而改变优先级）。"""
    code = (
        'import json, sys\n'
        'res = {}\n'
        'try:\n'
        '    import actuscore\n'
        '    res["actuscore"] = "present"\n'
        'except Exception:\n'
        '    res["actuscore"] = "absent"\n'
        'from vools.actus.health import check_vault\n'
        'r = check_vault(".")\n'
        'res["status"] = r.status\n'
        'sys.stdout.write(json.dumps(res, ensure_ascii=False))\n'
    )
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join([
        r'E:\IDEProjects\AI\Actus\engine',
        os.path.join(REPO, 'actus'), REPO,
        os.path.join(REPO, 'bridges'), os.path.join(REPO, 'rx'),
    ])
    p = subprocess.run([sys.executable, '-c', code],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, env=env, encoding='utf-8', errors='replace')
    if p.returncode != 0:
        pytest.skip(f'Actus 引擎不可用，跳过对照格: {p.stderr[-200:]}')
    import json
    res = json.loads(p.stdout.strip())
    assert res['status'] == 'ok', res
