"""selfdrive 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- SelfDrive 状态机行为改变 → 自驱执行失败/状态错乱
- goal/max_rounds 校验失效 → 无效配置导致运行时崩溃
- _echo_worker 行为改变 → 确定性自检失效
"""
import pytest


class TestRequireGoal:
    def test_none_goal_raises_typeerror(self):
        """退步了会怎样：None 目标应报 TypeError，而不是生成名为「None」的任务。"""
        from vools.actus.selfdrive import Decomposer
        with pytest.raises(TypeError, match="必须是字符串"):
            Decomposer._require_goal(None)

    def test_empty_string_goal_raises_valueerror(self):
        """退步了会怎样：空字符串目标应报 ValueError。"""
        from vools.actus.selfdrive import Decomposer
        with pytest.raises(ValueError, match="不能为空"):
            Decomposer._require_goal("   ")

    def test_valid_goal_passes(self):
        """退步了会怎样：合法 goal 应原样通过。"""
        from vools.actus.selfdrive import Decomposer
        assert Decomposer._require_goal("实现功能X") == "实现功能X"


class TestSelfDriveInit:
    def test_valid_init(self):
        """退步了会怎样：合法参数应正常初始化。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="测试目标", meta_dir="/tmp/test_meta")
        assert sd.goal == "测试目标"
        assert sd.max_rounds == 3
        assert sd.run_id is not None
        assert sd.nodes == []

    def test_none_goal_raises(self):
        """退步了会怎样：None goal 应在 __init__ 时报错。"""
        from vools.actus.selfdrive import SelfDrive
        with pytest.raises(TypeError):
            SelfDrive(goal=None, meta_dir="/tmp/test_meta")

    @pytest.mark.parametrize("bad_rounds", [0, -1, True, False, "3", 1.5, None])
    def test_invalid_max_rounds_raises(self, bad_rounds):
        """退步了会怎样：非法 max_rounds 应报 ValueError。"""
        from vools.actus.selfdrive import SelfDrive
        with pytest.raises(ValueError):
            SelfDrive(goal="测试", max_rounds=bad_rounds, meta_dir="/tmp/test_meta")


class TestEchoWorker:
    def test_echo_worker_returns_ok(self):
        """退步了会怎样：_echo_worker 应返回确定性 ok 结果。"""
        from vools.actus.selfdrive import SelfDrive
        node = {'id': 'n1', 'goal': '测试', 'children': [], 'status': 'pending'}
        result = SelfDrive._echo_worker(node)
        assert result['status'] == 'ok'
        assert result['echo'] is True


class TestRun:
    def test_run_all_done_with_echo_worker(self):
        """退步了会怎样：用 echo worker 跑完所有节点，应全部 done。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="实现功能X", max_depth=1, meta_dir="/tmp/test_meta")
        result = sd.run()
        assert result['summary']['all_done'] is True
        assert result['summary']['done'] == result['summary']['total']

    def test_run_failed_worker(self):
        """退步了会怎样：worker 抛异常时节点应判 failed。"""
        from vools.actus.selfdrive import SelfDrive

        def failing_worker(node):
            raise RuntimeError("模拟执行失败")

        sd = SelfDrive(goal="实现功能X", max_depth=1, meta_dir="/tmp/test_meta",
                       worker=failing_worker)
        result = sd.run()
        assert result['summary']['failed'] > 0


class TestSnapshot:
    def test_snapshot_structure(self):
        """退步了会怎样：snapshot 应包含 run_id/goal/summary 等字段。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="测试目标", meta_dir="/tmp/test_meta")
        snap = sd.snapshot()
        assert snap['run_id'] is not None
        assert snap['goal'] == "测试目标"
        assert 'summary' in snap
        assert snap['summary']['total'] == 0
        assert snap['summary']['done'] == 0
        assert snap['summary']['failed'] == 0


class TestSummary:
    def test_summary_empty(self):
        """退步了会怎样：空 nodes 应 summary 为 0。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="测试", meta_dir="/tmp/test_meta")
        s = sd.summary()
        assert s['total'] == 0
        assert s['done'] == 0
        assert s['failed'] == 0
        assert s['all_done'] is False  # 空不算 done

    def test_summary_after_run(self):
        """退步了会怎样：run 后 summary 应反映执行结果。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="实现功能X", max_depth=1, meta_dir="/tmp/test_meta")
        sd.run()
        s = sd.summary()
        assert s['total'] > 0
        assert s['done'] == s['total']
        assert s['all_done'] is True
