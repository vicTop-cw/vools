"""selfdrive _run_node 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- _run_node 门禁阻塞路径不生效 → 节点未被 blocked
- _run_node worker 异常处理错误 → 节点状态错乱
"""
import pytest


@pytest.fixture
def tmp_meta(tmp_path, monkeypatch):
    d = tmp_path / "meta"
    d.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ACTUS_META_DIR", str(d))
    return str(d)


def _make_node(nid="t001", goal="a"):
    return {'id': nid, 'goal': goal, 'children': [], 'status': 'pending',
            'depth': 1, 'result': None, 'omega': None}


class TestRunNode:
    def test_run_node_pre_gate_blocks(self, tmp_meta, monkeypatch):
        """退步了会怎样：pre_gate 返回结论时应阻塞节点。"""
        from vools.actus.selfdrive import SelfDrive

        sd = SelfDrive(goal="测试", meta_dir=tmp_meta)

        # mock _pre_execute_gate 返回 blocked
        monkeypatch.setattr(sd, '_pre_execute_gate',
                            lambda node: {'passed': False, 'reason': 'omega_execute_gate',
                                          'detail': 'missing spec'})
        node = _make_node()
        sd._run_node(node)
        assert node['status'] == 'failed'
        assert node['reason'] == 'omega_execute_gate'
        assert node['result']['status'] == 'blocked'

    def test_run_node_worker_success(self, tmp_meta):
        """退步了会怎样：worker 成功时节点应 done。"""
        from vools.actus.selfdrive import SelfDrive

        def ok_worker(node):
            return {'status': 'ok'}

        sd = SelfDrive(goal="测试", meta_dir=tmp_meta, worker=ok_worker)
        node = _make_node()
        sd._run_node(node)
        assert node['status'] == 'done'
        assert node['result']['status'] == 'ok'

    def test_run_node_worker_failure(self, tmp_meta):
        """退步了会怎样：worker 失败时节点应 failed。"""
        from vools.actus.selfdrive import SelfDrive

        def fail_worker(node):
            return {'status': 'failed'}

        sd = SelfDrive(goal="测试", meta_dir=tmp_meta, worker=fail_worker)
        node = _make_node()
        sd._run_node(node)
        assert node['status'] == 'failed'

    def test_run_node_worker_exception(self, tmp_meta):
        """退步了会怎样：worker 抛异常时应判 failed。"""
        from vools.actus.selfdrive import SelfDrive

        def boom_worker(node):
            raise RuntimeError("boom")

        sd = SelfDrive(goal="测试", meta_dir=tmp_meta, worker=boom_worker)
        node = _make_node()
        sd._run_node(node)
        assert node['status'] == 'failed'
        assert node['result']['error']['code'] == 'worker_error'

    def test_run_node_non_dict_result(self, tmp_meta):
        """退步了会怎样：worker 返回非 dict 应包装为 dict。"""
        from vools.actus.selfdrive import SelfDrive

        def str_worker(node):
            return "not a dict"

        sd = SelfDrive(goal="测试", meta_dir=tmp_meta, worker=str_worker)
        node = _make_node()
        sd._run_node(node)
        assert node['status'] == 'done'
        assert node['result']['status'] == 'ok'
        assert node['result']['value'] == "not a dict"
