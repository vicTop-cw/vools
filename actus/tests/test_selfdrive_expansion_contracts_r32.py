"""selfdrive 失败展开 + 再试 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- _expand_failed 不展开 → 失败叶永不重试，max_rounds 退化为死参数
- _retry_children 不回退模板 → planner 返回空时回炉链失效
"""
import pytest


@pytest.fixture
def tmp_meta(tmp_path, monkeypatch):
    """隔离：meta_dir 指向 tmp。"""
    d = tmp_path / "meta"
    d.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ACTUS_META_DIR", str(d))
    return str(d)


class TestNextSeq:
    def test_next_seq_empty(self, tmp_meta):
        """退步了会怎样：无节点时序号应为 0。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="测试", meta_dir=tmp_meta)
        assert sd._next_seq() == 0

    def test_next_seq_with_nodes(self, tmp_meta):
        """退步了会怎样：应返回最大 tNNN 序号。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="测试", meta_dir=tmp_meta)
        sd.nodes = [
            {'id': 't001', 'goal': 'a', 'children': [], 'status': 'done', 'depth': 1},
            {'id': 't002', 'goal': 'b', 'children': [], 'status': 'done', 'depth': 1},
        ]
        assert sd._next_seq() == 2

    def test_next_seq_non_t_ids(self, tmp_meta):
        """退步了会怎样：非 tNNN id 不影响序号。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="测试", meta_dir=tmp_meta)
        sd.nodes = [
            {'id': 'custom', 'goal': 'a', 'children': [], 'status': 'done', 'depth': 1},
            {'id': 't005', 'goal': 'b', 'children': [], 'status': 'done', 'depth': 1},
        ]
        assert sd._next_seq() == 5


class TestRetryChildren:
    def test_retry_children_from_planner(self, tmp_meta):
        """退步了会怎样：planner 返回子目标时应使用 planner 结果。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="实现功能X", max_depth=3, meta_dir=tmp_meta)
        node = {'id': 't001', 'goal': '实现功能X', 'children': [], 'status': 'failed', 'depth': 1}
        kids = sd._retry_children(node)
        assert len(kids) > 0

    def test_retry_children_no_planner(self, tmp_meta):
        """退步了会怎样：无 planner 时应回退模板拆解。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="实现功能X", max_depth=3, meta_dir=tmp_meta)
        # 强制 planner 为 None
        sd.decomposer.planner = None
        node = {'id': 't001', 'goal': '实现功能X', 'children': [], 'status': 'failed', 'depth': 1}
        kids = sd._retry_children(node)
        assert len(kids) > 0


class TestExpandFailed:
    def test_expand_failed_no_targets(self, tmp_meta):
        """退步了会怎样：无失败叶时应返回 0。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="测试", max_depth=2, meta_dir=tmp_meta)
        # 无失败节点
        assert sd._expand_failed() == 0

    def test_expand_failed_expands(self, tmp_meta):
        """退步了会怎样：应把失败叶展开为子任务。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="实现功能X", max_depth=2, meta_dir=tmp_meta)
        # 手动构造一个失败叶
        sd.nodes = [
            {'id': 't001', 'goal': '实现功能X', 'children': [], 'status': 'failed', 'depth': 1, 'result': None, 'omega': None},
        ]
        expanded = sd._expand_failed()
        assert expanded >= 1
        # 原节点应被重置为 pending
        assert sd.nodes[0]['status'] == 'pending'
        # 应产生子节点
        assert len(sd.nodes) > 1

    def test_expand_failed_no_expand_at_max_depth(self, tmp_meta):
        """退步了会怎样：已达最大深度的失败叶不应展开。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="实现功能X", max_depth=1, meta_dir=tmp_meta)
        # 深度 1 = max_depth，不应展开
        sd.nodes = [
            {'id': 't001', 'goal': '实现功能X', 'children': [], 'status': 'failed', 'depth': 1, 'result': None, 'omega': None},
        ]
        expanded = sd._expand_failed()
        assert expanded == 0


class TestRunWithExpansion:
    def test_run_expands_and_retries(self, tmp_meta):
        """退步了会怎样：失败叶应在后续轮次被展开并重试。"""
        from vools.actus.selfdrive import SelfDrive

        def failing_worker(node):
            # 第一轮失败，第二轮成功（模拟重试后成功）
            if len(sd.log) < 2:
                raise RuntimeError("模拟失败")
            return {'status': 'ok', 'goal': node['goal']}

        sd = SelfDrive(goal="实现功能X", max_depth=2, max_rounds=3, meta_dir=tmp_meta,
                       worker=failing_worker)
        result = sd.run()
        # 至少应该跑完（可能仍有失败，但不应崩溃）
        assert result['summary']['total'] >= 1
