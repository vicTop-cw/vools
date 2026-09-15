"""tests/actus/test_dependency.py — 依赖解析器测试"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus.dependency import (
    Dependency, DependencyResolver, DepCheckResult, get_resolver,
)


class TestDependency:
    """Dependency 数据类测试"""

    def test_basic_creation(self):
        dep = Dependency(name='test_dep', type='action')
        assert dep.name == 'test_dep'
        assert dep.type == 'action'
        assert dep.required is True

    def test_optional_fields(self):
        dep = Dependency(
            name='cs_test',
            type='cs_build',
            build_command='build.cmd',
            build_check='/path/to/output.dll',
        )
        assert dep.build_command == 'build.cmd'


class TestDepCheckResult:
    """DepCheckResult 数据类测试"""

    def test_satisfied(self):
        result = DepCheckResult('test', True, 'ok')
        assert result.satisfied is True
        assert result.auto_fixable is False

    def test_unsatisfied_with_fix(self):
        result = DepCheckResult('test', False, 'missing', auto_fixable=True, fix_command='pip install test')
        assert result.satisfied is False
        assert result.auto_fixable is True


class TestDependencyResolver:
    """DependencyResolver 核心功能测试"""

    @pytest.fixture
    def resolver(self):
        return DependencyResolver(actions_root='/tmp/nonexistent')

    def test_parse_dep_string_python(self, resolver):
        dep = resolver._parse_dep_string('python:requests')
        assert dep.name == 'requests'
        assert dep.type == 'python'

    def test_parse_dep_string_npm(self, resolver):
        dep = resolver._parse_dep_string('npm:shiki')
        assert dep.name == 'shiki'
        assert dep.type == 'npm'

    def test_parse_dep_string_system(self, resolver):
        dep = resolver._parse_dep_string('system:git')
        assert dep.name == 'git'
        assert dep.type == 'system'

    def test_parse_dep_string_action(self, resolver):
        dep = resolver._parse_dep_string('action:actus.test.hello')
        assert dep.name == 'actus.test.hello'
        assert dep.type == 'action'

    def test_parse_dep_string_cs(self, resolver):
        dep = resolver._parse_dep_string('cs_forms')
        assert dep.type == 'cs_build'

    def test_parse_dep_string_default_action(self, resolver):
        dep = resolver._parse_dep_string('some.random.action')
        assert dep.type == 'action'

    def test_parse_deps(self, resolver):
        deps = resolver.parse_deps(['python:requests', 'system:git'])
        assert len(deps) == 2
        assert deps[0].type == 'python'
        assert deps[1].type == 'system'

    def test_parse_deps_dict_format(self, resolver):
        deps = resolver.parse_deps([
            {'name': 'requests', 'type': 'python', 'required': True},
        ])
        assert len(deps) == 1
        assert deps[0].name == 'requests'

    def test_check_python_pkg_installed(self, resolver):
        dep = Dependency(name='os', type='python')
        result = resolver.check_dep(dep)
        assert result.satisfied is True

    def test_check_python_pkg_missing(self, resolver):
        dep = Dependency(name='nonexistent_pkg_xyz_12345', type='python')
        result = resolver.check_dep(dep)
        assert result.satisfied is False
        assert result.auto_fixable is True

    def test_topological_sort_no_cycle(self, resolver):
        actions = {
            'a': ['b', 'c'],
            'b': ['c'],
            'c': [],
        }
        ok, sorted_list = resolver.topological_sort(actions)
        assert ok is True
        assert sorted_list.index('c') < sorted_list.index('b')
        assert sorted_list.index('b') < sorted_list.index('a')

    def test_topological_sort_with_cycle(self, resolver):
        actions = {
            'a': ['b'],
            'b': ['a'],
        }
        ok, sorted_list = resolver.topological_sort(actions)
        assert ok is False

    def test_resolve_all_satisfied(self, resolver):
        deps = [Dependency(name='os', type='python')]
        ok, messages = resolver.resolve(deps)
        assert ok is True
        assert any('os' in m for m in messages)

    def test_resolve_with_missing(self, resolver):
        deps = [Dependency(name='nonexistent_xyz_999', type='python')]
        ok, messages = resolver.resolve(deps)
        assert ok is False


class TestGetResolver:
    """get_resolver 单例测试"""

    def test_returns_resolver(self):
        r = get_resolver()
        assert isinstance(r, DependencyResolver)
