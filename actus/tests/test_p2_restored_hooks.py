# -*- coding: utf-8 -*-
"""合并回灌的四处测试支撑钩子 + notify 规则机制（docs/39 §10.3 的 P2 后遗）。

要拦的失效有两类：

1. **钩子被 alias 吞掉**。`d6c0292` 把 Actus 侧 `actuscore/*.py` 改成
   `sys.modules[__name__] = vools.actus.X` 之后，Actus 那份文件里自带的名字就**变不出来了**
   —— 状态在本模块，复位只能在本模块做。缺的后果不是"测试写法要改"这么简单：
   Actus 全量当场 110 errors（`vault2.reset_singleton` 51 / `vault.reset_vault_singleton` 40 /
   `calllog.reset_store` 5 个文件 / `runtimes.reset_registry` 4）。
2. **规则机制整块留在被合并掉的那一侧**。`NotificationManager` 的 docstring 一直写着
   "管理通知渠道、**规则**和发送"，而 `_evaluate_condition()` 在产品里**没有任何调用者** ——
   读代码的人会以为规则已生效，实际上 `add_rule` / `check_rules` 根本不存在。
   这比缺一个功能更糟（虚假安全感），所以除了补实现，本件还专门钉
   "`_evaluate_condition` 确实被 `check_rules` 调用"那一格。

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

from vools.actus import calllog, notify, runtimes, vault, vault2  # noqa: E402


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


# ===========================================================================
# notify 规则机制：docstring 承诺的能力要真的在产品里跑
# ===========================================================================

def _rule(mgr, name="r1", condition="status == 'failed'", **kw):
    mgr.add_rule(notify.NotifyRule(name=name, condition=condition,
                                   channel=notify.NotifyChannel.CONSOLE,
                                   template="失败: {action_id}", **kw))
    return mgr


def test_rule_surface_exists():
    """退步了会怎样：规则面再次只存在于某一份副本里（合并后单源，就必须在这一源上有）。

    断言：`NotifyRule` 与三个方法在场。
    """
    mgr = notify.NotificationManager()
    assert hasattr(notify, "NotifyRule")
    for m in ("add_rule", "remove_rule", "check_rules"):
        assert callable(getattr(mgr, m, None)), m
    assert mgr._rules == []


def test_check_rules_fires_and_maps_level_from_status():
    """退步了会怎样：命中不发、或级别不按 status 映射 —— "失败要报警"这件事只是文档。

    断言：failed ⇒ 发 1 条且 level=ERROR；ok ⇒ SUCCESS；不匹配 ⇒ 0 条且历史不动。
    """
    mgr = _rule(notify.NotificationManager())
    fired = mgr.check_rules({"status": "failed", "action_id": "demo.x"})
    assert fired == 1 and len(mgr._history) == 1
    assert mgr._history[-1]["message"].level is notify.NotifyLevel.ERROR
    assert mgr._history[-1]["delivered"] is True
    assert mgr._history[-1]["message"].body == "失败: demo.x"

    mgr2 = _rule(notify.NotificationManager(), condition="status == 'ok'")
    mgr2.check_rules({"status": "ok", "action_id": "demo.y"})
    assert mgr2._history[-1]["message"].level is notify.NotifyLevel.SUCCESS

    mgr3 = _rule(notify.NotificationManager())
    assert mgr3.check_rules({"status": "ok", "action_id": "demo.z"}) == 0
    assert mgr3._history == []


def test_check_rules_consults_the_evaluator():
    """**反孤儿断言**：`_evaluate_condition` 曾经是谁都没调用的死代码，而 docstring 说规则生效。

    断言：`check_rules` 每条启用的规则都过一次求值器（用计数替身证明调用关系，不是证明结果）。
    """
    calls = []
    mgr = _rule(notify.NotificationManager(), condition="status == 'failed'")
    mgr._evaluate_condition = lambda cond, ctx: (calls.append(cond) or False)
    assert mgr.check_rules({"status": "failed", "action_id": "a"}) == 0
    assert calls == ["status == 'failed'"], calls


def test_enabled_and_cooldown_are_honored():
    """退步了会怎样：`enabled=False` 仍发、或 cooldown 形同虚设 —— 一次故障刷一条告警风暴。

    断言：停用 ⇒ 0 条；cooldown 内第二次 ⇒ 0 条，cooldown 外 ⇒ 1 条。
    """
    mgr = _rule(notify.NotificationManager(), enabled=False)
    assert mgr.check_rules({"status": "failed", "action_id": "a"}) == 0

    mgr = _rule(notify.NotificationManager(), cooldown=999)
    assert mgr.check_rules({"status": "failed", "action_id": "a"}) == 1
    assert mgr.check_rules({"status": "failed", "action_id": "a"}) == 0
    mgr._rules[0].cooldown = 0                  # 冷却窗口过后仍可再发
    assert mgr.check_rules({"status": "failed", "action_id": "a"}) == 1


def test_remove_rule_drops_only_that_name():
    """退步了会怎样：remove 按前缀/按对象误删 —— 删一条规则把别的规则带走。

    断言：两条规则删其一，剩的那条仍在且仍能触发。
    """
    mgr = _rule(notify.NotificationManager(), name="keep", condition="status == 'ok'")
    _rule(mgr, name="drop")
    mgr.remove_rule("drop")
    assert [r.name for r in mgr._rules] == ["keep"]
    assert mgr.check_rules({"status": "ok", "action_id": "a"}) == 1


def test_alias_shim_exposes_the_restored_names():
    """打到调用面：Actus 侧 `actuscore.X` 是本模块的 alias，补上的名字必须从那一侧也看得见。

    断言：从 `actuscore.*` 导入这四个钩子 + `NotifyRule` 全部可用（Actus 树不在位时 skip 无意义 ⇒
    直接按 vools 的模块对象判）。
    """
    for mod_name, name in (("vault2", "reset_singleton"), ("vault", "reset_vault_singleton"),
                           ("runtimes", "reset_registry"), ("calllog", "reset_store"),
                           ("notify", "NotifyRule")):
        mod = importlib.import_module(f"vools.actus.{mod_name}")
        assert hasattr(mod, name), f"vools.actus.{mod_name}.{name} 缺失"
