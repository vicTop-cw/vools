# -*- coding: utf-8 -*-
"""P2 后遗之一：Actus 调用面要求、但 vools 真源给不出的四处复位钩子（docs/39 §10.3）。

要拦的失效有两类：

1. **钩子被 alias 吞掉**。`d6c0292` 把 Actus 侧 `actuscore/*.py` 改成
   `sys.modules[__name__] = vools.actus.X` 之后，Actus 那份文件里自带的名字就**变不出来了**
   —— 状态在本模块，复位只能在本模块做。缺的后果不是"测试写法要改"这么简单：
   Actus 全量当场 110 errors（`vault2.reset_singleton` 51 / `vault.reset_vault_singleton` 40 /
   `calllog.reset_store` 5 个文件 / `runtimes.reset_registry` 4）。
2. **规则机制不是漏搬，是按裁决删的**（本轮差点搞错，记在这里）：`NotificationManager`
   的 class docstring 还写着"管理通知渠道、**规则**和发送"，看着像规则被合并落在了丢掉的那一侧；
   但 `stats()` 的 docstring 明写「规则特性（`add_rule`/`check_rules`/`NotifyRule`）已**整条删除**
   （全仓零调用，"规则永不评估却打印规则数"属统计名不副实），`cli.py` 的 `notify stats` 打印行也一并删」
   —— 出处 `686ce42f`。所以**本件不恢复规则**，只钉四处钩子；
   残留的 `_evaluate_condition()`（现无调用者）是 vools 侧的清理项，由 vools 自己裁决。
   教训：判断"这是漏搬还是裁决删除"，要读到**同一能力的所有自述**（class docstring 只是其中一处），
   并把删除那笔提交的正文翻出来。

出口条件：本文件全绿，且 Actus 侧 `tests/test_notify.py` / `test_vault2.py` /
`test_calllog.py` / `test_runtimes.py` / `test_vault.py` / `test_env_isolation.py` /
`test_secrets_inject.py` 的 ImportError 归零（读数在 Actus 仓
`Find_BUG/actus_2026q3/evidence/20261102_vools_track/`）。
"""

import importlib
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _ai_local_bootstrap  # noqa: E402
_ai_local_bootstrap.install()

from vools.actus import calllog, runtimes, vault, vault2  # noqa: E402


# ===========================================================================
# 四处复位钩子：清的是本模块的全局，且语义与合并前 Actus 那份一致
# ===========================================================================

def test_reset_hooks_exist_on_the_module_that_holds_the_state():
    """退步了会怎样：钩子又回到"调用方那侧"，而状态在这侧 —— alias 之后名字变不出来。

    断言：四个名字在场且可调用。
    """
    for mod, name in ((vault2, "reset_singleton"), (vault, "reset_vault_singleton"),
                      (runtimes, "reset_registry"), (calllog, "reset_store")):
        assert callable(getattr(mod, name, None)), f"{mod.__name__}.{name} 不在"


def test_reset_singleton_and_registry_clear_the_global():
    """退步了会怎样：钩子存在但不看全局（清错了对象），单例继续跨用例存活。

    断言：置成哨兵后复位 ⇒ 全局是 None，且下一次取值拿到的是**新对象**。
    """
    sentinel = object()
    vault2._vault2_singleton = sentinel
    vault2.reset_singleton()
    assert vault2._vault2_singleton is None

    runtimes._registry = sentinel
    runtimes.reset_registry()
    assert runtimes._registry is None
    assert runtimes._get_registry() is not sentinel

    vault._vault_singleton = sentinel
    vault.reset_vault_singleton()
    assert vault._vault_singleton is None


def test_reset_store_closes_the_handle_it_drops(tmp_path, monkeypatch):
    """退步了会怎样：只把 `_store` 置 None 而不 close —— 旧 meta_dir 的连接/句柄活在外面，
    下一个用例换了目录却仍读写上一份库（隔离失效，且实测这类"没关的句柄"会留临时文件锁）。

    断言：close 被调用过、`_store` 与 `_store_key` 一起归 None、二次调用不抛。
    """
    closed = []

    class _Recorder:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(calllog, "_store", _Recorder())
    monkeypatch.setattr(calllog, "_store_key", "somewhere")
    calllog.reset_store()
    assert closed == [True]
    assert calllog._store is None and calllog._store_key is None
    calllog.reset_store()                       # 空单例时再复位不得抛


def test_alias_shim_exposes_the_restored_names():
    """打到调用面：Actus 侧 `actuscore.X` 是本模块的 alias，补上的名字必须从那一侧也看得见。

    断言：这四个钩子在 vools 模块对象上都在位（Actus 侧 `actuscore.*` 是它的 alias，
    这里在位 ⇒ 那一侧也在位）。
    """
    for mod_name, name in (("vault2", "reset_singleton"), ("vault", "reset_vault_singleton"),
                           ("runtimes", "reset_registry"), ("calllog", "reset_store")):
        mod = importlib.import_module(f"vools.actus.{mod_name}")
        assert hasattr(mod, name), f"vools.actus.{mod_name}.{name} 缺失"
