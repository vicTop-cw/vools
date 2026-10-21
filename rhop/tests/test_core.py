"""v2 核心协议测试：core.py（Side 枚举 + TaskStatus 状态机）。

Phase 0 里程碑：本地构造信封、写入 mirror DB、校验通过。
"""

import pytest

from vools.rhop.core import Side, TaskStatus


class TestSide:
    def test_side_values(self):
        assert Side.REQUESTER.value == "requester"
        assert Side.EXECUTOR.value == "executor"

    def test_side_other(self):
        assert Side.REQUESTER.other == Side.EXECUTOR
        assert Side.EXECUTOR.other == Side.REQUESTER


class TestTaskStatus:
    def test_pending_can_claim(self):
        assert TaskStatus.PENDING.can_transition(TaskStatus.CLAIMED)
        assert TaskStatus.PENDING.can_transition(TaskStatus.CANCELLED)

    def test_pending_cannot_jump_to_done(self):
        assert not TaskStatus.PENDING.can_transition(TaskStatus.DONE)
        assert not TaskStatus.PENDING.can_transition(TaskStatus.RUNNING)

    def test_claimed_can_run(self):
        assert TaskStatus.CLAIMED.can_transition(TaskStatus.RUNNING)

    def test_running_can_finish(self):
        assert TaskStatus.RUNNING.can_transition(TaskStatus.DONE)
        assert TaskStatus.RUNNING.can_transition(TaskStatus.FAILED)

    def test_done_is_terminal(self):
        assert TaskStatus.DONE.is_terminal
        assert TaskStatus.FAILED.is_terminal
        assert TaskStatus.CANCELLED.is_terminal

    def test_non_terminal_states(self):
        assert not TaskStatus.PENDING.is_terminal
        assert not TaskStatus.CLAIMED.is_terminal
        assert not TaskStatus.RUNNING.is_terminal
