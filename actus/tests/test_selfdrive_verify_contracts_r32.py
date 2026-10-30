"""selfdrive _verify + _resolve_spec 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- _verify 无 spec 时行为错误 → strong 模式下节点被误判或漏判
- _resolve_spec 未调用 spec_resolver → 语料无法关联
"""
import pytest


@pytest.fixture
def tmp_meta(tmp_path, monkeypatch):
    d = tmp_path / "meta"
    d.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ACTUS_META_DIR", str(d))
    return str(d)


class TestResolveSpec:
    def test_resolve_spec_no_resolver(self, tmp_meta):
        """退步了会怎样：无 spec_resolver 应返回 None。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="测试", meta_dir=tmp_meta)
        node = {'id': 't001', 'goal': 'a', 'children': [], 'status': 'pending', 'depth': 1}
        assert sd._resolve_spec(node) is None

    def test_resolve_spec_with_resolver(self, tmp_meta):
        """退步了会怎样：有 spec_resolver 应调用并返回结果。"""
        from vools.actus.selfdrive import SelfDrive

        def resolver(node):
            return "/path/to/spec.json"

        sd = SelfDrive(goal="测试", meta_dir=tmp_meta, spec_resolver=resolver)
        node = {'id': 't001', 'goal': 'a', 'children': [], 'status': 'pending', 'depth': 1}
        assert sd._resolve_spec(node) == "/path/to/spec.json"


class TestVerify:
    def test_verify_no_spec_strong(self, tmp_meta):
        """退步了会怎样：strong 模式下无 spec 应判失败。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="测试", strong=True, meta_dir=tmp_meta)
        node = {'id': 't001', 'goal': 'a', 'children': [], 'status': 'pending', 'depth': 1}
        gate = sd._verify(node, {'status': 'ok'})
        assert gate['passed'] is False
        assert gate['reason'] == 'omega_spec_missing'

    def test_verify_no_spec_soft(self, tmp_meta):
        """退步了会怎样：非 strong 模式无 spec 应判通过。"""
        from vools.actus.selfdrive import SelfDrive
        sd = SelfDrive(goal="测试", strong=False, meta_dir=tmp_meta)
        node = {'id': 't001', 'goal': 'a', 'children': [], 'status': 'pending', 'depth': 1}
        gate = sd._verify(node, {'status': 'ok'})
        assert gate['passed'] is True
        assert gate['reason'] == 'no_spec_soft'

    def test_verify_with_spec_mock(self, tmp_meta, monkeypatch):
        """退步了会怎样：有 spec 时应调用 _omega.verify_output。"""
        from vools.actus import selfdrive as selfdrive_mod
        from vools.actus.selfdrive import SelfDrive

        # mock _omega.verify_output
        mock_report = {'gate': {'passed': True, 'accuracy': 100.0}}
        monkeypatch.setattr(selfdrive_mod._omega, 'verify_output',
                            lambda spec_path, result: mock_report)

        def resolver(node):
            return "/path/to/spec.json"

        sd = SelfDrive(goal="测试", strong=True, meta_dir=tmp_meta, spec_resolver=resolver)
        node = {'id': 't001', 'goal': 'a', 'children': [], 'status': 'pending', 'depth': 1}
        gate = sd._verify(node, {'status': 'ok'})
        assert gate['passed'] is True

    def test_verify_with_spec_error(self, tmp_meta, monkeypatch):
        """退步了会怎样：verify_output 抛异常应判失败。"""
        from vools.actus import selfdrive as selfdrive_mod
        from vools.actus.selfdrive import SelfDrive

        # mock _omega.verify_output 抛异常
        def raise_err(spec_path, result):
            raise RuntimeError("mock error")

        monkeypatch.setattr(selfdrive_mod._omega, 'verify_output', raise_err)

        def resolver(node):
            return "/path/to/spec.json"

        sd = SelfDrive(goal="测试", strong=True, meta_dir=tmp_meta, spec_resolver=resolver)
        node = {'id': 't001', 'goal': 'a', 'children': [], 'status': 'pending', 'depth': 1}
        gate = sd._verify(node, {'status': 'ok'})
        assert gate['passed'] is False
        assert 'omega_error' in gate['reason']
