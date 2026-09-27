"""tests/actus/test_dependency.py — 依赖解析器测试

对齐 vools.actus 2026-09 合并后的依赖 API：`Dependency.type` 是 `DepType` 枚举、
`strategy` 是 `DepStrategy` 枚举（定义见 actus/vools/actus/dependency.py）。
Python 包依赖串的现行写法是 `pip:<pkg>`（旧 `python:<pkg>` 前缀已不存在，
统一并入 `DepType.LANG` + `lang_manager='pip'`）。
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from vools.actus.dependency import (
    Dependency, DependencyResolver, DepCheckResult, DepStrategy, DepType,
    get_resolver,
)


class TestDependency:
    """Dependency 数据类测试"""

    def test_basic_creation(self):
        # 测试目的：不传 type 时默认落到 DepType.ACTION（枚举默认值，不再是字符串 'action'）
        dep = Dependency(name='test_dep')
        assert dep.name == 'test_dep'
        assert dep.type is DepType.ACTION
        assert dep.required is True

    def test_explicit_type_kept_as_enum(self):
        # 测试目的：显式传 DepType 成员时原样持有，且与字符串形态可区分（钉住 type 是枚举这一契约）
        dep = Dependency(name='test_dep', type=DepType.SYSTEM)
        assert dep.type is DepType.SYSTEM
        assert dep.type != 'system'

    def test_optional_fields(self):
        # 测试目的：cs_build 依赖的 build_command / build_check 透传不被丢
        dep = Dependency(
            name='cs_test',
            type=DepType.CS_BUILD,
            build_command='build.cmd',
            build_check='/path/to/output.dll',
        )
        assert dep.build_command == 'build.cmd'
        assert dep.build_check == '/path/to/output.dll'
        assert dep.type is DepType.CS_BUILD


class TestDepCheckResult:
    """DepCheckResult 数据类测试"""

    def test_satisfied(self):
        # 测试目的：只给三个必填参数时 auto_fixable 默认 False（未声明可自动修就不许报可修）
        result = DepCheckResult('test', True, 'ok')
        assert result.satisfied is True
        assert result.auto_fixable is False

    def test_unsatisfied_with_fix(self):
        # 测试目的：auto_fixable=True 必须把 fix_command 一起带出来（提示策略靠它输出安装命令）
        result = DepCheckResult('test', False, 'missing', auto_fixable=True, fix_command='pip install test')
        assert result.satisfied is False
        assert result.auto_fixable is True
        assert result.fix_command == 'pip install test'


class TestDependencyResolver:
    """DependencyResolver 核心功能测试"""

    @pytest.fixture
    def resolver(self):
        return DependencyResolver(actions_root='/tmp/nonexistent')

    def test_parse_dep_string_python(self, resolver):
        # 测试目的：pip:<pkg> 解析成 DepType.LANG + lang_manager='pip'，包名剥掉前缀
        dep = resolver._parse_dep_string('pip:requests')
        assert dep.name == 'requests'
        assert dep.type is DepType.LANG
        assert dep.lang_manager == 'pip'

    def test_parse_dep_string_npm(self, resolver):
        # 测试目的：npm:<pkg> 与 pip 共用 DepType.LANG，靠 lang_manager='npm' 区分
        dep = resolver._parse_dep_string('npm:shiki')
        assert dep.name == 'shiki'
        assert dep.type is DepType.LANG
        assert dep.lang_manager == 'npm'

    def test_parse_dep_string_system(self, resolver):
        # 测试目的：system:<cmd> 解析成 DepType.SYSTEM，懒加载策略默认 HINT（提示不硬失败）
        dep = resolver._parse_dep_string('system:git')
        assert dep.name == 'git'
        assert dep.type is DepType.SYSTEM
        assert dep.strategy is DepStrategy.HINT

    def test_parse_dep_string_action(self, resolver):
        # 测试目的：action:<id> 解析成 DepType.ACTION，动作 id 完整保留
        dep = resolver._parse_dep_string('action:actus.test.hello')
        assert dep.name == 'actus.test.hello'
        assert dep.type is DepType.ACTION

    def test_parse_dep_string_cs(self, resolver):
        # 测试目的：cs_forms 这类裸前缀走 C# 构建分支，带出 build_command/build_check
        dep = resolver._parse_dep_string('cs_forms')
        assert dep.type is DepType.CS_BUILD
        assert dep.name == 'cs_forms'
        assert dep.build_check.endswith('actus-dialogs.exe')
        assert 'cs_forms' in dep.build_command

    def test_parse_dep_string_default_action(self, resolver):
        # 测试目的：没有任何已知前缀的依赖串按动作依赖兜底，不静默丢名字
        dep = resolver._parse_dep_string('some.random.action')
        assert dep.type is DepType.ACTION
        assert dep.name == 'some.random.action'

    def test_parse_deps(self, resolver):
        # 测试目的：parse_deps 对字符串列表逐条走前缀解析，类型顺序与内容都落对
        deps = resolver.parse_deps(['pip:requests', 'system:git'])
        assert len(deps) == 2
        assert deps[0].type is DepType.LANG
        assert deps[0].name == 'requests'
        assert deps[1].type is DepType.SYSTEM
        assert deps[1].name == 'git'

    def test_parse_deps_dict_format(self, resolver):
        # 测试目的：dict 形态的 type 字符串被转成 DepType 枚举（不是留在 str 上比对）
        deps = resolver.parse_deps([
            {'name': 'requests', 'type': 'lang', 'required': True},
        ])
        assert len(deps) == 1
        assert deps[0].name == 'requests'
        assert deps[0].type is DepType.LANG

    def test_parse_deps_dict_unknown_type_falls_back_to_action(self, resolver):
        # 测试目的：dict 形态给了枚举里没有的 type 时降级为 ACTION，而不是抛异常中断解析
        deps = resolver.parse_deps([{'name': 'requests', 'type': 'python'}])
        assert len(deps) == 1
        assert deps[0].type is DepType.ACTION

    def test_check_python_pkg_installed(self, resolver):
        # 测试目的：DepType.LANG 的已装包判为满足（走 _check_lang_pkg 分支，不是报 unknown type）
        dep = Dependency(name='os', type=DepType.LANG)
        result = resolver.check_dep(dep)
        assert result.satisfied is True

    def test_check_python_pkg_missing(self, resolver):
        # 测试目的：DepType.LANG 的缺装包判为不满足且给出可自动修复的 pip 安装命令
        dep = Dependency(name='nonexistent_pkg_xyz_12345', type=DepType.LANG)
        result = resolver.check_dep(dep)
        assert result.satisfied is False
        assert result.auto_fixable is True
        assert result.fix_command == 'pip install nonexistent_pkg_xyz_12345'

    def test_topological_sort_no_cycle(self, resolver):
        # 测试目的：无环图拓扑排序返回 ok=True 且顺序满足 c→b→a 的依赖先后
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
        # 测试目的：a↔b 互相依赖必须被检出为有环（ok=False），不能给出假排序
        actions = {
            'a': ['b'],
            'b': ['a'],
        }
        ok, sorted_list = resolver.topological_sort(actions)
        assert ok is False

    def test_resolve_all_satisfied(self, resolver):
        # 测试目的：全部依赖满足时 resolve 返回 ok=True，且每个依赖都有对应消息
        deps = [Dependency(name='os', type=DepType.LANG)]
        ok, messages = resolver.resolve(deps)
        assert ok is True
        assert any('os' in m for m in messages)

    def test_resolve_with_missing(self, resolver):
        # 测试目的：任一必需依赖不满足时 resolve 必须返回 ok=False（不许被 HINT 策略洗成绿）
        deps = [Dependency(name='nonexistent_xyz_999', type=DepType.LANG)]
        ok, messages = resolver.resolve(deps)
        assert ok is False
        assert any('nonexistent_xyz_999' in m for m in messages)


class TestGetResolver:
    """get_resolver 单例测试"""

    def test_returns_resolver(self):
        # 测试目的：get_resolver 返回可用的 DependencyResolver 单例（两次调用同一实例）
        r = get_resolver()
        assert isinstance(r, DependencyResolver)
        assert get_resolver() is r
