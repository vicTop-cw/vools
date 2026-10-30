"""concurrency 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- ConcurrencyManager 并发控制失效 → 动作重复执行/超限执行
- acquire_slot 超时逻辑错误 → 永久阻塞或提前放弃
"""
import pytest


@pytest.fixture(autouse=True)
def reset_manager():
    """每个测试前重置单例。"""
    from vools.actus.concurrency import ConcurrencyManager
    ConcurrencyManager.reset()
    yield
    ConcurrencyManager.reset()


class TestRegister:
    def test_register_action(self):
        """退步了会怎样：register_action 应注册 action。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a", max_instances=2)
        assert cm.is_registered("act.a") is True

    def test_register_action_default_max(self):
        """退步了会怎样：默认 max_instances=0（无上限）。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a")
        can, _ = cm.can_run("act.a")
        assert can is True

    def test_unregister_action(self):
        """退步了会怎样：unregister_action 应移除 action。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a")
        cm.unregister_action("act.a")
        assert cm.is_registered("act.a") is False

    def test_unregister_nonexistent(self):
        """退步了会怎样：unregister 不存在的 action 不应崩溃。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.unregister_action("not.exists")  # 不应抛异常


class TestCanRun:
    def test_unregistered_can_run(self):
        """退步了会怎样：未注册的 action 应允许运行。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        can, msg = cm.can_run("act.a")
        assert can is True

    def test_at_limit_cannot_run(self):
        """退步了会怎样：达到上限时不应允许运行。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a", max_instances=1)
        cm.acquire_slot("act.a", "exec-1", {})
        can, msg = cm.can_run("act.a")
        assert can is False
        assert "上限" in msg

    def test_under_limit_can_run(self):
        """退步了会怎样：未达上限时应允许运行。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a", max_instances=2)
        cm.acquire_slot("act.a", "exec-1", {})
        can, msg = cm.can_run("act.a")
        assert can is True


class TestAcquireRelease:
    def test_acquire_unregistered(self):
        """退步了会怎样：未注册的 action 应能 acquire（无上限）。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        ok, msg = cm.acquire_slot("act.a", "exec-1", {})
        assert ok is True

    def test_acquire_limit(self):
        """退步了会怎样：超过上限应等待超时。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a", max_instances=1)
        cm.acquire_slot("act.a", "exec-1", {})
        # 第二次应超时
        ok, msg = cm.acquire_slot("act.a", "exec-2", {}, timeout=0.2)
        assert ok is False
        assert "超时" in msg

    def test_release_slot(self):
        """退步了会怎样：release_slot 应释放对应 exec_id 的槽位。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a", max_instances=1)
        cm.acquire_slot("act.a", "exec-1", {})
        cm.release_slot("act.a", "exec-1")
        assert cm.get_running_count("act.a") == 0

    def test_release_slot_then_acquire(self):
        """退步了会怎样：释放后应能重新 acquire。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a", max_instances=1)
        cm.acquire_slot("act.a", "exec-1", {})
        cm.release_slot("act.a", "exec-1")
        ok, msg = cm.acquire_slot("act.a", "exec-2", {})
        assert ok is True


class TestGetStatus:
    def test_status_unregistered(self):
        """退步了会怎样：未注册的 action 状态应显示 registered=False。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        st = cm.get_status("act.a")
        assert st["registered"] is False

    def test_status_registered(self):
        """退步了会怎样：已注册的 action 状态应显示正确信息。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a", max_instances=2)
        cm.acquire_slot("act.a", "exec-1", {})
        st = cm.get_status("act.a")
        assert st["registered"] is True
        assert st["max_instances"] == 2
        assert st["running"] == 1

    def test_status_all_actions(self):
        """退步了会怎样：无 action_id 时应返回所有 actions。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a", max_instances=1)
        cm.register_action("act.b", max_instances=2)
        st = cm.get_status()
        assert st["total_registered"] == 2
        assert "act.a" in st["actions"]
        assert "act.b" in st["actions"]


class TestGetRunningInstances:
    def test_instances_empty(self):
        """退步了会怎样：无运行时实例应返回空列表。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a")
        assert cm.get_running_instances("act.a") == []

    def test_instances_with_running(self):
        """退步了会怎样：有运行时实例应返回正确信息。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a")
        cm.acquire_slot("act.a", "exec-1", {"x": 1})
        instances = cm.get_running_instances("act.a")
        assert len(instances) == 1
        assert instances[0]["exec_id"] == "exec-1"


class TestSetMaxInstances:
    def test_set_max_instances(self):
        """退步了会怎样：set_max_instances 应更新上限。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.register_action("act.a", max_instances=1)
        cm.set_max_instances("act.a", 3)
        _, msg = cm.can_run("act.a")
        assert "3" in msg

    def test_set_max_instances_unregistered(self):
        """退步了会怎样：对未注册的 action 设置 max 应不崩溃。"""
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        cm.set_max_instances("not.exists", 3)  # 不应抛异常


class TestGetManager:
    def test_get_manager_returns_singleton(self):
        """退步了会怎样：get_manager 应返回单例。"""
        from vools.actus.concurrency import get_manager
        mgr = get_manager()
        from vools.actus.concurrency import ConcurrencyManager
        cm = ConcurrencyManager()
        assert mgr is cm
