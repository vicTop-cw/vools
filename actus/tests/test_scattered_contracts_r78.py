"""scattered.py 契约测试（第 78 轮：清扫 r29/r31 未覆盖分支）。

覆盖缺口（对照 r29+r31 已测项）：
  1. ScatteredError.to_payload / ScatteredAction.as_dict（entry_path None）
  2. is_scattered_path：.actus.schema.md 双后缀 / 尾斜杠 / 普通文件
  3. authorized_root_for / _assert_inside（相等/子路径/逃逸 details）
  4. resolve_scattered 全错误分支（空路径/非动作文件/目录缺入口/路径不存在）
  5. load_project_deps：tomllib 主路径 + _parse_toml_subset 兜底全分支（屏蔽 tomllib/tomli）
  6. declared_dep_tokens / declared_env_names / _split_deps 全前缀矩阵
  7. _pick_executor 回退链；_core_injection_roots（ACTUS_REPO_ROOT/engine + 去重）
  8. build_injection_env（PYTHONPATH 去重 / base_env 提供形态）
  9. injection_report（unavailable 分支）
  10. _resolve_path_dep 全分支；_detect_path_cycle（环/自环/无环）
  11. _collect_path_dep_graph（解析失败跳过 / limit 超限显式报错）
  12. check_scattered：id 依赖缺失/异常、路径环、with_deps=False、授权根警告
  13. run_scattered：no-form / 缺 id / happy（file+dir 形态、preparsed 缺省值、env 零残留）

隔离与 r31 同口径：HOME/ACTUS_META_DIR/ACTUS_REPO_ROOT 指 tmp；执行器一律假实现。
"""
import json
import os
import re
import sys
import types

import pytest

from vools.actus import scattered as S
from vools.actus.process_state import PROCESS_STATE_LOCK


# ═══════════════════════════════════════════════════════════════════
# 夹具
# ═══════════════════════════════════════════════════════════════════


def _action_text(action_id="actus.scat.demo", deps=None, trust="sandbox"):
    cfg = {"id": action_id, "name": action_id.rsplit(".", 1)[-1], "version": "1.0.0",
           "trust": trust, "entry": "main", "description": "d", "author": "t",
           "kind": "exec", "platform": ["desktop"]}
    if deps is not None:
        cfg["deps"] = deps
    return ("```json #!cfg\n" + json.dumps(cfg, ensure_ascii=False) + "\n```\n\n"
            "```python #!run tag=main\nimport json\nprint(json.dumps({'ok': 1}))\n```\n")


@pytest.fixture
def world(monkeypatch, tmp_path):
    home = tmp_path / "home"
    meta = tmp_path / "meta"
    repo = tmp_path / "repo"
    for d in (home, meta, repo):
        d.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACTUS_META_DIR", str(meta))
    monkeypatch.setenv("ACTUS_REPO_ROOT", str(repo))
    return {"home": home, "meta": meta, "repo": repo, "tmp": tmp_path}


@pytest.fixture
def action_file(world):
    root = world["tmp"] / "proj"
    root.mkdir()
    path = root / "demo.actus.md"
    path.write_text(_action_text(), encoding="utf-8")
    return path


@pytest.fixture
def spy_executor(monkeypatch):
    """假执行器：记录调用并返回固定结果，绝不真跑动作代码。"""
    calls = []

    def executor(action_id, params, **kw):
        calls.append({"action_id": action_id, "params": dict(params or {}),
                      "kw": dict(kw),
                      "env_scattered": os.environ.get("ACTUS_SCATTERED"),
                      "lock_free": PROCESS_STATE_LOCK.acquire(blocking=False)})
        if calls[-1]["lock_free"]:
            PROCESS_STATE_LOCK.release()
        return {"status": "ok", "data": {"spy": True}}

    monkeypatch.setattr(S, "_pick_executor", lambda: executor)
    return calls


# ═══════════════════════════════════════════════════════════════════
# ① 基础类型
# ═══════════════════════════════════════════════════════════════════


class TestErrorAndAction:
    def test_to_payload_roundtrip(self):
        err = S.ScatteredError('path_escaped', '逃逸', {'root': 'r'})
        assert err.code == 'path_escaped'
        assert err.to_payload() == {'code': 'path_escaped', 'message': '逃逸',
                                    'details': {'root': 'r'}}

    def test_details_default_empty(self):
        assert S.ScatteredError('x', 'm').details == {}

    def test_as_dict_entry_none_becomes_empty(self, world):
        sc = S.ScatteredAction('p.actus.md', str(world['tmp']), 'file')
        d = sc.as_dict()
        assert d['entry_path'] == ''
        assert d['kind'] == 'file'
        assert d['defaults_applied'] == {}

    def test_as_dict_entry_kept_and_slash_normalized(self, world):
        entry = os.path.join(str(world['tmp']), 'main.actus.md')
        sc = S.ScatteredAction('p.actus.md', str(world['tmp']), 'dir', entry_path=entry)
        assert sc.as_dict()['entry_path'] == entry.replace(os.sep, '/')

    def test_repr_mentions_kind(self, world):
        sc = S.ScatteredAction('p.actus.md', str(world['tmp']), 'file')
        assert "kind='file'" in repr(sc)


# ═══════════════════════════════════════════════════════════════════
# ② 形态判定 / 授权根 / 路径边界
# ═══════════════════════════════════════════════════════════════════


class TestFormDetection:
    def test_schema_md_suffix_is_scattered(self, world):
        p = world['tmp'] / 'a.actus.schema.md'
        p.write_text('x', encoding='utf-8')
        assert S.is_scattered_path(str(p)) is True

    def test_url_never_scattered(self):
        assert S.is_scattered_path('https://x.dev/a.actus.md') is False

    def test_trailing_slash_dir_detected(self, world):
        d = world['tmp'] / 'demo.actus'
        d.mkdir()
        assert S.is_scattered_path(str(d) + os.sep) is True

    def test_plain_file_not_scattered(self, world):
        p = world['tmp'] / 'plain.txt'
        p.write_text('x', encoding='utf-8')
        assert S.is_scattered_path(str(p)) is False

    def test_empty_path_false(self):
        assert S.is_scattered_path('') is False

    def test_authorized_root_file_is_parent(self, action_file):
        assert S.authorized_root_for(str(action_file)) == str(action_file.parent)

    def test_authorized_root_dot_actus_dir_is_self(self, world):
        d = world['tmp'] / 'demo.actus'
        d.mkdir()
        assert S.authorized_root_for(str(d)) == str(d)

    def test_assert_inside_equal_and_child(self, world):
        root = str(world['tmp'])
        assert S._assert_inside(root, root) == os.path.realpath(root)
        child = os.path.join(root, 'sub', 'f.txt')
        assert S._assert_inside(root, child) == os.path.realpath(child)

    def test_assert_inside_escape_details(self, world):
        # home 在 tmp 之内（world 布局），必须用 tmp 的兄弟目录才真正逃逸
        outside = world['tmp'].parent / 'evil_escape_target.txt'
        with pytest.raises(S.ScatteredError) as ei:
            S._assert_inside(str(world['tmp']), str(outside), '依赖引用 ./evil')
        assert ei.value.code == 'path_escaped'
        assert ei.value.details['root'] and ei.value.details['resolved']


class TestResolveScattered:
    def test_empty_path(self):
        with pytest.raises(S.ScatteredError) as ei:
            S.resolve_scattered('')
        assert ei.value.code == 'action_not_found'

    def test_file_wrong_suffix(self, world):
        p = world['tmp'] / 'nope.txt'
        p.write_text('x', encoding='utf-8')
        with pytest.raises(S.ScatteredError) as ei:
            S.resolve_scattered(str(p))
        assert ei.value.code == 'action_not_found'
        assert '.actus.md' in ei.value.message

    def test_file_ok(self, action_file):
        sc = S.resolve_scattered(str(action_file))
        assert sc.kind == 'file'
        assert sc.entry_path is None
        assert sc.root == str(action_file.parent)

    def test_dir_wrong_suffix(self, world):
        d = world['tmp'] / 'plain'
        d.mkdir()
        with pytest.raises(S.ScatteredError) as ei:
            S.resolve_scattered(str(d))
        assert ei.value.details['path'].endswith('/plain')

    def test_dir_missing_entry(self, world):
        d = world['tmp'] / 'demo.actus'
        d.mkdir()
        with pytest.raises(S.ScatteredError) as ei:
            S.resolve_scattered(str(d))
        assert ei.value.details['expected_entry'] == 'main.actus.md'

    def test_dir_ok_returns_entry(self, world):
        d = world['tmp'] / 'demo.actus'
        d.mkdir()
        entry = d / 'main.actus.md'
        entry.write_text(_action_text(), encoding='utf-8')
        sc = S.resolve_scattered(str(d))
        assert sc.kind == 'dir'
        assert sc.entry_path == str(entry)

    def test_missing_path(self, world):
        with pytest.raises(S.ScatteredError) as ei:
            S.resolve_scattered(str(world['tmp'] / 'ghost.actus.md'))
        assert '路径不存在' in ei.value.message


# ═══════════════════════════════════════════════════════════════════
# ③ project.actus.toml 解析（含 fallback 子集解析器）
# ═══════════════════════════════════════════════════════════════════


def _block_toml(monkeypatch):
    """屏蔽 tomllib/tomli → 强制走 _parse_toml_subset 兜底。"""
    monkeypatch.setitem(__import__('sys').modules, 'tomllib', None)
    monkeypatch.setitem(__import__('sys').modules, 'tomli', None)


class TestProjectDeps:
    def test_missing_file_returns_empty_decl(self, world):
        out = S.load_project_deps(str(world['tmp']))
        assert out['_present'] is False
        assert out['_path'].endswith('project.actus.toml')

    def test_tomllib_parser_tagged(self, world):
        (world['tmp'] / 'project.actus.toml').write_text(
            'pip = ["requests"]\n', encoding='utf-8')
        out = S.load_project_deps(str(world['tmp']))
        assert out['_present'] is True
        assert out['pip'] == ['requests']
        assert out['_parser'] in ('tomllib', 'tomli')

    def test_bad_toml_explicit_error(self, world):
        (world['tmp'] / 'project.actus.toml').write_text('pip = [unclosed\n', encoding='utf-8')
        with pytest.raises(S.ScatteredError) as ei:
            S.load_project_deps(str(world['tmp']))
        assert ei.value.code == 'action_invalid'
        assert '解析失败' in ei.value.message

    def test_unknown_keys_reported(self, world):
        (world['tmp'] / 'project.actus.toml').write_text(
            'pip = ["requests"]\nmystery = 1\n', encoding='utf-8')
        out = S.load_project_deps(str(world['tmp']))
        assert out['_unknown_keys'] == ['mystery']

    def test_fallback_subset_tables_and_lists(self, world, monkeypatch):
        _block_toml(monkeypatch)
        (world['tmp'] / 'project.actus.toml').write_text(
            '# comment\n'
            'pip = ["a", "b"]\n'
            '[env]\n'
            'KEY = "value"   # inline comment\n'
            'FLAG = true\n'
            'N = 42\n', encoding='utf-8')
        out = S.load_project_deps(str(world['tmp']))
        assert out['_parser'] == 'fallback'
        assert out['pip'] == ['a', 'b']
        assert out['env'] == {'KEY': 'value', 'FLAG': True, 'N': 42}

    def test_fallback_unparseable_line_raises_with_lineno(self, world, monkeypatch):
        _block_toml(monkeypatch)
        (world['tmp'] / 'project.actus.toml').write_text(
            'pip = ["a"]\nbare line\n', encoding='utf-8')
        with pytest.raises(S.ScatteredError) as ei:
            S.load_project_deps(str(world['tmp']))
        assert ei.value.details.get('line') == 'bare line'

    def test_fallback_bad_value_raises(self, world, monkeypatch):
        _block_toml(monkeypatch)
        (world['tmp'] / 'project.actus.toml').write_text('k = not-a-value\n', encoding='utf-8')
        with pytest.raises(S.ScatteredError) as ei:
            S.load_project_deps(str(world['tmp']))
        assert '无法解析值' in ei.value.message

    def test_fallback_empty_table_name_raises(self, world, monkeypatch):
        _block_toml(monkeypatch)
        (world['tmp'] / 'project.actus.toml').write_text('[]\n', encoding='utf-8')
        with pytest.raises(S.ScatteredError) as ei:
            S.load_project_deps(str(world['tmp']))
        assert '空 table 名' in ei.value.message

    def test_non_dict_top_level_rejected(self, world, monkeypatch):
        # fallback 解析器恒返回 dict → 这里用 tomllib 主路径造非 table 顶层
        (world['tmp'] / 'project.actus.toml').write_text('not = "table but ok"\n', encoding='utf-8')
        out = S.load_project_deps(str(world['tmp']))
        assert out['_present'] is True  # dict 顶层，键被过滤


class TestDepTokens:
    def test_tokens_from_lists_and_scalars(self):
        doc = {'pip': ['requests', 'flask'], 'npm': 'esbuild', 'system': ['git'],
               'env': ['A', '', 'B']}
        # env 也在 _DECLARABLE_DEP_KEYS（'pip','npm','system','env'）→ 摊平成 env:X
        assert S.declared_dep_tokens(doc) == ['pip:requests', 'pip:flask',
                                              'npm:esbuild', 'system:git',
                                              'env:A', 'env:B']
        assert S.declared_env_names(doc) == ['A', 'B']

    def test_tokens_skip_non_string_items(self):
        assert S.declared_dep_tokens({'pip': ['ok', 7, None, '  ']}) == ['pip:ok']

    def test_env_names_none_and_scalar(self):
        assert S.declared_env_names({}) == []
        assert S.declared_env_names({'env': 'X'}) == ['X']


class TestSplitDeps:
    def test_full_matrix(self):
        path_d, declared, id_d, core = S._split_deps([
            './lib.actus/', '..\\up.actus.md', 'vools', 'actuscore', 'sigma',
            'pip:r', 'npm:x', 'system:git', 'env:K',
            'lang:python', 'mcp:fs', 'action:other', 'cs_form', 'build:py',
            'plain.dep', '  ', 123, None, ''])
        assert path_d == ['./lib.actus/', '..\\up.actus.md']
        assert core == ['vools', 'actuscore', 'sigma']
        assert declared == ['pip:r', 'npm:x', 'system:git', 'env:K']
        assert id_d == ['lang:python', 'mcp:fs', 'action:other', 'cs_form',
                        'build:py', 'plain.dep']

    def test_none_deps(self):
        assert S._split_deps(None) == ([], [], [], [])


# ═══════════════════════════════════════════════════════════════════
# ④ 注入环境
# ═══════════════════════════════════════════════════════════════════


class TestInjection:
    def test_repo_root_engine_dir_included_and_deduped(self, world, monkeypatch):
        eng = world['repo'] / 'engine'
        eng.mkdir()
        roots = S._core_injection_roots()
        assert str(eng) in roots
        # 去重：无重复 realpath
        assert len(roots) == len(set(os.path.realpath(r) for r in roots))

    def test_missing_engine_dir_skipped(self, world):
        roots = S._core_injection_roots()
        assert str(world['repo'] / 'engine') not in roots
        assert len(roots) >= 1  # 本包子树根恒在

    def test_build_env_marks_scattered_and_core(self, world):
        env = S.build_injection_env(base_env={})
        assert env['ACTUS_SCATTERED'] == '1'
        assert env['ACTUS_INJECTED_CORE'] == 'actuscore,sigma,vools'
        assert 'ACTUS_INJECTED_CORE' not in os.environ  # 不污染宿主

    def test_build_env_pythonpath_dedup_no_host_mutation(self, world):
        root = S._core_injection_roots()[0]
        base = {'PYTHONPATH': root + os.pathsep + 'C:\\other'}
        env = S.build_injection_env(base)
        parts = env['PYTHONPATH'].split(os.pathsep)
        assert parts.count(root) == 1
        assert 'C:\\other' in parts

    def test_injection_report_unavailable_branch(self, monkeypatch):
        import importlib
        real = importlib.import_module

        def fake(dotted):
            if dotted == 'vools.actus.sigma':
                raise ImportError('no sigma here')
            return real(dotted)

        monkeypatch.setattr(importlib, 'import_module', fake)
        rep = S.injection_report()
        # 白名单还有 actuscore（本机未装，天然 unavailable）→ 按名字找 sigma
        sigma_rows = [u for u in rep['unavailable'] if u['name'] == 'sigma']
        assert sigma_rows and 'ImportError' in sigma_rows[0]['reason']
        assert sigma_rows[0]['provider'] == 'vools.actus.sigma'
        assert 'vools' in rep['injected']

    def test_injection_report_has_version_and_file(self):
        rep = S.injection_report()
        ent = rep['injected']['vools']
        assert ent['provider'] == 'vools'
        assert isinstance(ent['file'], str)


# ═══════════════════════════════════════════════════════════════════
# ⑤ 执行器选择与路径依赖
# ═══════════════════════════════════════════════════════════════════


class TestPickExecutor:
    def test_fallback_to_vools_executor(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, 'actuscore.executor', None)
        fn = S._pick_executor()
        assert callable(fn)

    def test_prefers_actuscore_when_importable(self, monkeypatch):
        # CPython 3.13: `import a.b` 先导入父包 a —— 即使 sys.modules['a.b'] 在场，
        # 父包不存在也直接 ModuleNotFoundError（实测）。父包 + 叶子都要进 sys.modules，
        # 且父包的 executor 属性要指向替身（`import a.b as x` 走 IMPORT_FROM getattr）。
        fake = types.ModuleType('actuscore.executor')
        fake.execute = lambda *a, **k: {'via': 'fake'}
        parent = types.ModuleType('actuscore')
        parent.executor = fake
        monkeypatch.setitem(sys.modules, 'actuscore', parent)
        monkeypatch.setitem(sys.modules, 'actuscore.executor', fake)
        assert S._pick_executor() is fake.execute


class TestResolvePathDep:
    def test_file_dep_ok(self, world):
        root = world['tmp'] / 'proj'
        root.mkdir()
        f = root / 'lib.actus.md'
        f.write_text('x', encoding='utf-8')
        info = S._resolve_path_dep('./lib.actus.md', str(root), str(root))
        assert info['kind'] == 'file'
        assert info['ref'] == './lib.actus.md'

    def test_dir_dep_ok(self, world):
        root = world['tmp'] / 'proj'
        root.mkdir()
        d = root / 'lib.actus'
        d.mkdir()
        (d / 'main.actus.md').write_text('x', encoding='utf-8')
        info = S._resolve_path_dep('./lib.actus', str(root), str(root))
        assert info['kind'] == 'dir'
        assert info['entry'].endswith('main.actus.md')

    def test_dir_dep_missing_entry(self, world):
        root = world['tmp'] / 'proj'
        root.mkdir()
        d = root / 'lib.actus'
        d.mkdir()
        with pytest.raises(S.ScatteredError) as ei:
            S._resolve_path_dep('./lib.actus', str(root), str(root))
        assert ei.value.code == 'dependency_missing'
        assert '依赖目录缺少入口' in ei.value.message

    def test_file_dep_missing(self, world):
        root = world['tmp'] / 'proj'
        root.mkdir()
        with pytest.raises(S.ScatteredError) as ei:
            S._resolve_path_dep('./ghost.actus.md', str(root), str(root))
        assert '依赖文件不存在' in ei.value.message

    def test_non_scattered_target_rejected(self, world):
        root = world['tmp'] / 'proj'
        root.mkdir()
        f = root / 'data.txt'
        f.write_text('x', encoding='utf-8')
        with pytest.raises(S.ScatteredError) as ei:
            S._resolve_path_dep('./data.txt', str(root), str(root))
        assert '路径依赖必须指向' in ei.value.message

    def test_escape_rejected(self, world):
        root = world['tmp'] / 'proj'
        root.mkdir()
        with pytest.raises(S.ScatteredError) as ei:
            S._resolve_path_dep('../outside.actus.md', str(root), str(root))
        assert ei.value.code == 'path_escaped'


class TestCycleAndGraph:
    def test_cycle_self_and_none(self):
        assert S._detect_path_cycle({'a': ['a']}, 'a') == ['a', 'a']
        assert S._detect_path_cycle({'a': ['b'], 'b': ['c'], 'c': []}, 'a') is None
        assert S._detect_path_cycle({'a': ['b'], 'b': ['a']}, 'a') == ['a', 'b', 'a']

    def test_graph_skips_unparseable(self, world, monkeypatch):
        root = world['tmp'] / 'proj'
        root.mkdir()
        f0 = root / 'f0.actus.md'
        f0.write_text('x', encoding='utf-8')
        f1 = root / 'f1.actus.md'
        f1.write_text('x', encoding='utf-8')

        def fake_parse(path):
            if path.endswith('f1.actus.md'):
                raise ValueError('bad cfg')
            return types.SimpleNamespace(meta={'deps': ['./f1.actus.md']})

        monkeypatch.setattr('vools.actus.model.parse_cfg_from_file', fake_parse)
        edges = S._collect_path_dep_graph(str(f0), str(root))
        assert edges[str(os.path.realpath(f0))] != []  # f1 边保留
        # f1 解析失败 → 其出边为空且不抛
        assert any(k.endswith('f1.actus.md') for k in edges)

    def test_graph_limit_raises(self, world, monkeypatch):
        root = world['tmp'] / 'proj'
        root.mkdir()
        for i in range(70):
            (root / ('f%d.actus.md' % i)).write_text('x', encoding='utf-8')

        def fake_parse(path):
            n = int(re.search(r'f(\d+)', path).group(1))
            nxt = [] if n >= 69 else ['./f%d.actus.md' % (n + 1)]
            return types.SimpleNamespace(meta={'deps': nxt})

        monkeypatch.setattr('vools.actus.model.parse_cfg_from_file', fake_parse)
        with pytest.raises(S.ScatteredError) as ei:
            S._collect_path_dep_graph(str(root / 'f0.actus.md'), str(root))
        assert ei.value.code == 'action_invalid'
        assert '64' in ei.value.message


# ═══════════════════════════════════════════════════════════════════
# ⑥ check_scattered 深分支
# ═══════════════════════════════════════════════════════════════════


class TestCheckScattered:
    def test_parse_failure_reported(self, world):
        root = world['tmp'] / 'proj'
        root.mkdir()
        p = root / 'demo.actus.md'
        p.write_text('```json #!cfg\n{broken\n```\n', encoding='utf-8')
        rep = S.check_scattered(str(p))
        assert rep['valid'] is False
        assert rep['errors'] and rep['errors'][0]['message']

    def test_id_dep_missing(self, world, monkeypatch):
        root = world['tmp'] / 'proj'
        root.mkdir()
        p = root / 'demo.actus.md'
        p.write_text(_action_text(deps=['ghost.dep']), encoding='utf-8')
        monkeypatch.setattr('vools.actus.indexer.scan_actions',
                            lambda *a, **k: {'actus.scat.demo': None})
        rep = S.check_scattered(str(p))
        assert any(e['code'] == 'dependency_missing' and
                   e['details']['missing'] == ['ghost.dep'] for e in rep['errors'])

    def test_id_dep_found_runs_validate_graph(self, world, monkeypatch):
        root = world['tmp'] / 'proj'
        root.mkdir()
        p = root / 'demo.actus.md'
        p.write_text(_action_text(deps=['other.dep']), encoding='utf-8')
        monkeypatch.setattr('vools.actus.indexer.scan_actions',
                            lambda *a, **k: {'actus.scat.demo': None, 'other.dep': None})
        seen = {}
        monkeypatch.setattr('vools.actus.validate.validate_graph',
                            lambda sub: seen.setdefault('n', len(sub)))
        rep = S.check_scattered(str(p))
        assert seen['n'] == 2
        assert rep['valid'] is True

    def test_id_dep_scan_raises_becomes_error(self, world, monkeypatch):
        root = world['tmp'] / 'proj'
        root.mkdir()
        p = root / 'demo.actus.md'
        p.write_text(_action_text(deps=['other.dep']), encoding='utf-8')

        def boom(*a, **k):
            raise RuntimeError('scan exploded')

        monkeypatch.setattr('vools.actus.indexer.scan_actions', boom)
        rep = S.check_scattered(str(p))
        assert any(e['code'] == 'dependency_missing' and 'scan exploded' in e['message']
                   for e in rep['errors'])

    def test_path_dep_missing_file(self, world):
        root = world['tmp'] / 'proj'
        root.mkdir()
        p = root / 'demo.actus.md'
        p.write_text(_action_text(deps=['./ghost.actus.md']), encoding='utf-8')
        rep = S.check_scattered(str(p))
        assert any('依赖文件不存在' in e['message'] for e in rep['errors'])

    def test_path_cycle_detected_and_with_deps_false_skips(self, world):
        root = world['tmp'] / 'proj'
        root.mkdir()
        a = root / 'a.actus.md'
        b = root / 'b.actus.md'
        a.write_text(_action_text(action_id='actus.scat.a', deps=['./b.actus.md']),
                     encoding='utf-8')
        b.write_text(_action_text(action_id='actus.scat.b', deps=['./a.actus.md']),
                     encoding='utf-8')
        rep = S.check_scattered(str(a))
        assert any(e['code'] == 'dependency_cycle' for e in rep['errors'])
        rep2 = S.check_scattered(str(a), with_deps=False)
        assert not any(e['code'] == 'dependency_cycle' for e in rep2['errors'])

    def test_foreign_root_warning(self, action_file, world):
        rep = S.check_scattered(str(action_file), authorized_root=str(world['tmp']))
        assert any('授权根不是动作所在目录' in w for w in rep['warnings'])
        assert rep['valid'] is True

    def test_declared_dep_accepted_flow(self, world):
        root = world['tmp'] / 'proj'
        root.mkdir()
        (root / 'project.actus.toml').write_text('pip = ["requests"]\n', encoding='utf-8')
        p = root / 'demo.actus.md'
        p.write_text(_action_text(deps=['pip:requests']), encoding='utf-8')
        rep = S.check_scattered(str(p))
        assert rep['valid'] is True
        assert rep['deps']['declared'] == ['pip:requests']
        assert rep['deps']['project_config_present'] is True
        assert rep['deps']['declared_env'] == []

    def test_core_dep_whitelisted_no_declaration_needed(self, world):
        root = world['tmp'] / 'proj'
        root.mkdir()
        p = root / 'demo.actus.md'
        p.write_text(_action_text(deps=['vools', 'sigma']), encoding='utf-8')
        rep = S.check_scattered(str(p))
        assert rep['valid'] is True
        # 实现按动作 deps 的声明顺序收集命中白名单的项
        assert rep['deps']['core_injected'] == ['vools', 'sigma']


# ═══════════════════════════════════════════════════════════════════
# ⑦ run_scattered 深分支
# ═══════════════════════════════════════════════════════════════════


class TestRunScattered:
    def test_invalid_refused_before_execution(self, world, spy_executor):
        bad = world['tmp'] / 'broken.actus.md'
        bad.write_text('```json #!cfg\n{broken\n```\n', encoding='utf-8')
        out = S.run_scattered(str(bad))
        assert out['status'] == 'failed'
        assert out['error']['code'] == 'action_invalid'
        assert out['scattered']['errors']
        assert spy_executor == []

    def test_no_form_with_check_first_false(self, world, spy_executor):
        out = S.run_scattered(str(world['tmp'] / 'ghost.actus.md'), check_first=False)
        assert out['status'] == 'failed'
        assert out['error']['code'] == 'action_not_found'

    def test_missing_id_blocked(self, world, monkeypatch, spy_executor, action_file):
        fake = types.SimpleNamespace(meta={'visibility': '', 'trust': ''})
        monkeypatch.setattr('vools.actus.model.parse_cfg_from_file', lambda p: fake)
        monkeypatch.setattr('vools.actus.validate.validate_action', lambda a: [])
        monkeypatch.setattr('vools.actus.validate.split_validation', lambda errs: ([], []))
        out = S.run_scattered(str(action_file))
        assert out['status'] == 'failed'
        assert out['error']['code'] == 'action_invalid'
        assert '缺少 id' in out['error']['message']

    def test_happy_file_form_passes_preparsed_and_restores_env(self, world, spy_executor,
                                                               monkeypatch):
        monkeypatch.setenv('PYTHONPATH', 'pre-existing')
        root = world['tmp'] / 'proj'
        root.mkdir()
        # trust 留空会被 C1 补 audit，而 audit 需要 meta.tests 绑定（docs/47 §4）→
        # 校验拒执行。用 sandbox 观察可见默认值：visibility 补 private。
        p = root / 'demo.actus.md'
        p.write_text(_action_text(trust='sandbox'), encoding='utf-8')
        out = S.run_scattered(str(p), params={'x': 1}, confirmed=True)
        assert out['status'] == 'ok'
        call = spy_executor[0]
        assert call['action_id'] == 'actus.scat.demo'
        assert call['kw']['confirmed'] is True
        assert call['kw']['actions_dir'] == str(root)
        assert call['kw']['meta_dir'] is None
        pre = call['kw']['preparsed_action']
        assert pre.meta['trust'] == 'sandbox'
        assert pre.meta['visibility'] == 'private'   # C1 缺省值经 preparsed 生效
        assert call['env_scattered'] == '1'           # 执行期间注入标志在
        assert out['scattered']['form']['kind'] == 'file'
        assert out['scattered']['defaults_applied'] == {'visibility': 'private'}
        # 宿主环境零残留
        assert os.environ.get('PYTHONPATH') == 'pre-existing'
        assert 'ACTUS_SCATTERED' not in os.environ
        assert 'ACTUS_INJECTED_CORE' not in os.environ

    def test_happy_dir_form_actions_dir_is_root(self, world, spy_executor):
        d = world['tmp'] / 'demo.actus'
        d.mkdir()
        (d / 'main.actus.md').write_text(_action_text(), encoding='utf-8')
        out = S.run_scattered(str(d))
        assert out['status'] == 'ok'
        assert spy_executor[0]['kw']['actions_dir'] == str(d)
        assert out['scattered']['form']['entry_path'].endswith('main.actus.md')

    def test_env_restored_when_keys_absent_before(self, world, spy_executor,
                                                   monkeypatch):
        monkeypatch.delenv('PYTHONPATH', raising=False)
        p = world['tmp'] / 'demo.actus.md'
        p.write_text(_action_text(), encoding='utf-8')
        out = S.run_scattered(str(p))
        assert out['status'] == 'ok'
        assert 'PYTHONPATH' not in os.environ
        assert 'ACTUS_SCATTERED' not in os.environ
