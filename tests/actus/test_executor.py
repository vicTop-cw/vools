"""tests/actus/test_executor.py — 执行器测试（结构/API 验证）"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus.executor import new_exec_id


class TestNewExecId:
    """new_exec_id 执行 ID 生成测试"""

    def test_returns_string(self):
        eid = new_exec_id()
        assert isinstance(eid, str)

    def test_unique(self):
        ids = {new_exec_id() for _ in range(100)}
        assert len(ids) == 100

    def test_contains_date_prefix(self):
        eid = new_exec_id()
        # 格式: YYYYMMDD-<6位随机hex>
        assert '-' in eid
        parts = eid.split('-')
        assert len(parts) == 2
        assert len(parts[0]) == 8  # YYYYMMDD
        assert len(parts[1]) == 6  # 6位hex
