# -*- coding: utf-8 -*-
"""假绿灯探针：在内存里把被测逻辑改坏，看目标测试是否仍然绿。

只读产品文件（不落盘改产品），用 pytest plugin 在 `pytest_configure` 里 monkeypatch。
运行：
    cd actus && python tools/audit/false_green_probes.py
"""
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
TESTS = os.path.join(ROOT, 'tests')
PKG = os.path.join(ROOT, 'vools', 'actus')


def _run(label, target_args, setup):
    """跑一组目标测试；setup 在 bootstrap 之后、收集之前执行 monkeypatch。"""
    class ProbePlugin(object):
        def pytest_configure(self, config):
            sys.path.insert(0, TESTS)
            import _ai_local_bootstrap as bootstrap
            bootstrap.install()
            setup()

    rc = pytest.main(['-q', '-p', 'no:cacheprovider', '--no-header',
                      '-o', 'addopts='] + target_args,
                     plugins=[ProbePlugin()])
    print('%-72s rc=%s %s' % (
        label, rc, '(仍然全绿 => 假绿灯)' if rc == 0 else '(测试变红 => 真护栏)'))
    return rc


def probe_source_string_guard():
    """探针 A：把防环守卫改成恒假（行为失效），源码子串断言仍全过。"""
    path = os.path.join(PKG, 'executor.py')
    src = open(path, encoding='utf-8').read()
    mutated = src.replace('if depth >= 5:', 'if depth >= 5 and False:')
    assert mutated != src, '未命中防环守卫源码（探针需更新）'
    checks = [
        'depth >= 5' in mutated,
        '疑似环' in mutated,
        '_forward_ctx.depth = depth + 1' in mutated,
    ]
    print('[A] kind_dispatch 源码守卫: 改动=%r 断言子串仍全部存在=%r 次数=%d' % (
        'if depth >= 5: -> if depth >= 5 and False:', checks, sum(checks)))
    print('    => test_forwarding_depth_guard_is_present_in_source 无法发现守卫被禁用')
    # 真正跑一遍该用例（源码没动，只演示它测的是什么都不测）
    _run('[A-run] test_kind_dispatch.py（守卫测试本身）',
         ['tests/test_kind_dispatch.py::test_forwarding_depth_guard_is_present_in_source'],
         lambda: None)


def probe_mcp_runtime_broken():
    """探针 B：把 MCP 派发/工具清单/服务入口全部改坏，看 MCP 相关测试。"""
    def setup():
        import vools.actus.mcp_server as mcp

        def boom(*args, **kwargs):
            raise RuntimeError('MCP runtime is completely broken by probe')

        mcp.MCPServer._call_tool = boom
        mcp.MCPServer._list_tools = boom
        mcp.MCPServer.handle = boom
        mcp.serve = boom

    _run('[B] MCP _call_tool/_list_tools/handle/serve 全部抛异常',
         ['tests/test_mcp_target_forms.py', 'tests/test_ai_catalog.py',
          'tests/test_error_codes.py', 'tests/test_new_capabilities.py'],
         setup)


def probe_visibility_symmetric_loss():
    """探针 C：to_dict 对称丢掉 require_signature 字段 → 往返测试仍绿。"""
    def setup():
        import vools.actus.visibility as vis

        original = vis.TeamConfig.to_dict

        def dropping(self):
            data = original(self)
            data.pop('require_signature', None)
            return data

        vis.TeamConfig.to_dict = dropping

    _run('[C] TeamConfig.to_dict 丢掉 require_signature（对称丢失）',
         ['tests/test_visibility_config.py'], setup)


def probe_weak_not_none():
    """探针 D：依赖查找返回一个错误值（垃圾字符串），弱断言用例仍绿。"""
    def setup():
        import vools.actus.dependency as dep

        dep.DependencyResolver._find_action_file = (
            lambda self, action_id: 'WRONG-ACTION-FILE-RETURNED')

    _run('[D] DependencyResolver._find_action_file 恒返回垃圾值',
         ['tests/test_action_lookup.py::test_dependency_lookup_delegates_and_finds_new_format'],
         setup)


def probe_trivial_assert_true():
    """探针 E：5 个 scaffold 骨架测试在任何环境下都绿（不碰产品）。"""
    env_note = 'ACTUS_REPO_ROOT=%s' % os.environ.get('ACTUS_REPO_ROOT')
    print('[E] scaffold 骨架测试环境: %s' % env_note)
    _run('[E] tests/test_foo.py + test_zh.py（内容只有 assert True）',
         ['tests/test_foo.py', 'tests/test_zh.py'], lambda: None)


def main():
    probe_source_string_guard()
    probe_mcp_runtime_broken()
    probe_visibility_symmetric_loss()
    probe_weak_not_none()
    probe_trivial_assert_true()


if __name__ == '__main__':
    main()
