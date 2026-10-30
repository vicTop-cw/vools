# -*- coding: utf-8 -*-
"""author.py 契约测试（第 84 轮）——AI 修改动作 + 7 步校验流水线 + publish_action。

本模块此前零测试触及。覆盖：
- _collapse_ai_modified_marks（留痕折叠）
- Pipeline.run 全 7 步（happy/parse 失败/entry/args/deps/dry_run 失败/沙箱三态/dry_run_only）
- run_pipeline 便捷入口
- author_action：ai_not_connected / 留痕折叠幂等 / ai_edit 注入三态（str/非 str/异常）
- publish_action：not_found / rejected / needs_human_confirm / 入索引 / 索引异常
- _find_action_file 委托 resolver、异常吞掉

隔离：tmp repo（<root>/actions/*.actus.md），HOME/META 指 tmp。
"""
import _ai_local_bootstrap  # noqa: F401  必须在 import vools.* 之前

import pytest

import vools.actus.author as am
from vools.actus.author import (Pipeline, _collapse_ai_modified_marks,
                                author_action, publish_action, run_pipeline)
from vools.actus.errors import ActionError

_CFG_ENTRY = ('{"id": "myapp.demo", "name": "Demo", "version": "1.0.0", '
              '"description": "d", "trust": "sandbox", "entry": "main", '
              '"platform": "desktop", "kind": "exec"}')
_ACT = ("# t\n\n```json #!cfg\n" + _CFG_ENTRY + "\n```\n\n"
        "```python #!run tag=main\nprint(1)\n```\n")
_BAD_ACT = ("```json #!cfg\n{broken json\n```\n\n"
            "```python #!run tag=main\nprint(1)\n```\n")


@pytest.fixture
def world(tmp_path, monkeypatch):
    (tmp_path / 'actions').mkdir()
    (tmp_path / '_meta').mkdir()
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.setenv('ACTUS_META_DIR', str(tmp_path / '_meta'))
    monkeypatch.setenv('ACTUS_REPO_ROOT', str(tmp_path))
    return tmp_path


def _write_action(root, text=_ACT, name='demo.actus.md'):
    p = root / 'actions' / name
    p.write_text(text, encoding='utf-8')
    return p


# ═══════════════════════════════════════════════════════════════════
# _collapse_ai_modified_marks
# ═══════════════════════════════════════════════════════════════════

class TestCollapse:
    def test_no_mark_passthrough(self):
        assert _collapse_ai_modified_marks('a\nb\n') == 'a\nb\n'

    def test_empty(self):
        assert _collapse_ai_modified_marks('') == ''

    def test_removes_marks_keeps_rest(self):
        text = ('x\n# AI-MODIFIED [2026] instruction: one\n'
                '  # AI-MODIFIED [2025] instruction: old\ny\n')
        out = _collapse_ai_modified_marks(text)
        assert 'AI-MODIFIED' not in out
        assert out == 'x\ny\n'


# ═══════════════════════════════════════════════════════════════════
# Pipeline.run —— 7 步
# ═══════════════════════════════════════════════════════════════════

class TestPipeline:
    def test_steps_table(self):
        assert len(Pipeline.STEPS) == 7
        assert Pipeline.STEPS[0][0] == 'parse_cfg'
        assert Pipeline.STEPS[-1][0] == 'sandbox_trial'
        assert dict(Pipeline.STEPS)['dry_run'] == '干跑预览'

    def test_happy_all_pass(self, world):
        p = _write_action(world)
        act = am.__dict__  # noqa
        from vools.actus.model import parse_cfg_from_file
        action = parse_cfg_from_file(str(p))
        pipe = Pipeline(action, repo_root=str(world))
        r = pipe.run(dry_run_only=True)
        assert r['action_id'] == 'myapp.demo'
        assert r['valid'] is True
        assert [s['step'] for s in r['steps']] == [
            'parse_cfg', 'schema_validate', 'entry_block', 'args_schema',
            'graph_validate', 'dry_run', 'sandbox_trial']
        assert all(s['ok'] for s in r['steps'])
        assert '跳过' in r['steps'][-1]['message']
        assert r['total_ms'] >= 0

    def test_parse_failure_marks_first_step(self, world):
        from vools.actus.model import parse_cfg_from_file, Action
        p = _write_action(world, _BAD_ACT)
        try:
            parse_cfg_from_file(str(p))
            pytest.skip('坏 JSON 未被拒')
        except ActionError:
            pass
        action = Action(meta={}, path=str(p), sha256='0' * 64)
        pipe = Pipeline(action, repo_root=str(world))
        r = pipe.run(dry_run_only=True)
        assert r['steps'][0]['ok'] is False
        assert r['valid'] is False

    def test_missing_dep_reported(self, world):
        from vools.actus.model import parse_cfg_from_file
        p = _write_action(world)
        text = p.read_text(encoding='utf-8').replace(
            '"entry": "main", "platform"',
            '"entry": "main", "deps": ["ghost.dep"], "platform"')
        p.write_text(text, encoding='utf-8')
        action = parse_cfg_from_file(str(p))
        pipe = Pipeline(action, repo_root=str(world))
        r = pipe.run(dry_run_only=True)
        graph = [s for s in r['steps'] if s['step'] == 'graph_validate'][0]
        assert graph['ok'] is False
        assert 'ghost.dep' in graph['message']

    def test_runtime_notes_surface(self, world, monkeypatch):
        # schema_validate 产生 runtime 提示（非真实错误）→ 透传不判红
        from vools.actus.model import parse_cfg_from_file
        p = _write_action(world)
        action = parse_cfg_from_file(str(p))
        monkeypatch.setattr(
            "vools.actus.author.validate_action",
            lambda a: ['runtime: 缺 contracts（环境提示）'])
        pipe = Pipeline(action, repo_root=str(world))
        r = pipe.run(dry_run_only=True)
        assert r['runtime_notes'] == ['runtime: 缺 contracts（环境提示）']
        schema = [s for s in r['steps'] if s['step'] == 'schema_validate'][0]
        assert schema['ok'] is True
        assert '1 条环境提示' in schema['message']

    def test_schema_real_error_fails(self, world, monkeypatch):
        from vools.actus.model import parse_cfg_from_file
        p = _write_action(world)
        action = parse_cfg_from_file(str(p))
        monkeypatch.setattr(
            "vools.actus.author.validate_action",
            lambda a: ['semantic: bad thing'])
        pipe = Pipeline(action, repo_root=str(world))
        r = pipe.run(dry_run_only=True)
        schema = [s for s in r['steps'] if s['step'] == 'schema_validate'][0]
        assert schema['ok'] is False and 'bad thing' in schema['message']
        assert r['valid'] is False

    def test_dry_run_failure_recorded(self, world, monkeypatch):
        from vools.actus.model import parse_cfg_from_file
        from vools.actus import executor as ex
        p = _write_action(world)
        action = parse_cfg_from_file(str(p))
        def boom(aid, actions_dir=None, **kw):
            raise RuntimeError('no preview')
        # 字符串寻址防 bootstrap 重建（本套件通用契约）
        monkeypatch.setattr("vools.actus.executor.preview", boom)
        pipe = Pipeline(action, repo_root=str(world))
        r = pipe.run(dry_run_only=True)
        dry = [s for s in r['steps'] if s['step'] == 'dry_run'][0]
        assert dry['ok'] is False and 'no preview' in dry['message']

    def test_sandbox_trial_ok_and_awaiting(self, world, monkeypatch):
        from vools.actus.model import parse_cfg_from_file
        p = _write_action(world)
        action = parse_cfg_from_file(str(p))
        monkeypatch.setattr(
            "vools.actus.executor.execute",
            lambda aid, params, **kw: {'status': 'awaiting_confirmation'})
        pipe = Pipeline(action, repo_root=str(world))
        r = pipe.run()
        sb = r['steps'][-1]
        assert sb['step'] == 'sandbox_trial' and sb['ok'] is True
        assert 'awaiting_confirmation' in sb['message']

    def test_sandbox_trial_exception(self, world, monkeypatch):
        from vools.actus.model import parse_cfg_from_file
        p = _write_action(world)
        action = parse_cfg_from_file(str(p))
        def boom(aid, params, **kw):
            raise RuntimeError('sandbox boom')
        monkeypatch.setattr("vools.actus.executor.execute", boom)
        pipe = Pipeline(action, repo_root=str(world))
        r = pipe.run()
        sb = r['steps'][-1]
        assert sb['ok'] is False and 'sandbox boom' in sb['message']

    def test_schema_md_format_branch(self, world, monkeypatch):
        # .actus.schema.md 双后缀 → validate_schema_md 分支（134-135）
        from vools.actus.model import Action
        p = _write_action(world, 'x', name='md.actus.schema.md')
        monkeypatch.setattr("vools.actus.validate.validate_schema_md",
                            lambda a: [])
        monkeypatch.setattr("vools.actus.executor.preview",
                            lambda aid, actions_dir=None, **kw: {'blocks': []})
        action = Action(meta={'id': 'myapp.md'}, path=str(p), sha256='0' * 64)
        pipe = Pipeline(action, repo_root=str(world))
        r = pipe.run(dry_run_only=True)
        schema = [s for s in r['steps'] if s['step'] == 'schema_validate'][0]
        assert schema['ok'] is True

    def test_default_root_publish_uses_meta_dir(self, world):
        # 不传 repo_root（走 ACTUS_REPO_ROOT）→ meta_base 跟随 paths.meta_dir()
        _write_action(world)
        r = publish_action('myapp.demo')
        assert r['status'] in ('published', 'rejected')
        assert 'index_status' in r


# ═══════════════════════════════════════════════════════════════════
# run_pipeline 便捷入口
# ═══════════════════════════════════════════════════════════════════

class TestRunPipeline:
    def test_convenience(self, world):
        p = _write_action(world)
        r = run_pipeline(str(p), repo_root=str(world), dry_run_only=True)
        assert r['action_id'] == 'myapp.demo' and r['valid'] is True


# ═══════════════════════════════════════════════════════════════════
# author_action
# ═══════════════════════════════════════════════════════════════════

class TestAuthorAction:
    def test_not_found(self, world):
        with pytest.raises(ActionError) as ei:
            author_action('ghost.act', '改成蓝色', repo_root=str(world))
        assert ei.value.code == 'action_not_found'

    def test_no_ai_edit_records_and_fails_honestly(self, world):
        p = _write_action(world)
        r = author_action('myapp.demo', '把按钮改成蓝色', repo_root=str(world))
        assert r['status'] == 'failed'
        assert r['reason'] == 'ai_not_connected'
        assert r['ai_applied'] is False
        text = p.read_text(encoding='utf-8')
        assert '# AI-MODIFIED [' in text
        assert '把按钮改成蓝色' in text
        # 留痕插在 entry tag 行后
        lines = text.splitlines()
        tag_idx = [i for i, l in enumerate(lines) if '#!run tag=main' in l][0]
        assert lines[tag_idx + 1].startswith('# AI-MODIFIED [')

    def test_mark_collapsed_across_runs(self, world):
        p = _write_action(world)
        author_action('myapp.demo', '第一次', repo_root=str(world))
        author_action('myapp.demo', '第二次', repo_root=str(world))
        text = p.read_text(encoding='utf-8')
        assert text.count('# AI-MODIFIED [') == 1
        assert '第二次' in text and '第一次' not in text

    def test_ai_edit_non_str_rejected(self, world):
        p = _write_action(world)
        with pytest.raises(ActionError) as ei:
            author_action('myapp.demo', 'x', repo_root=str(world),
                          ai_edit=lambda t, i, f: 12345)
        assert ei.value.code == 'invalid_ai_edit_result'
        # 失败留痕：文件已带指令记录
        assert '# AI-MODIFIED [' in p.read_text(encoding='utf-8')

    def test_ai_edit_exception_propagates(self, world):
        p = _write_action(world)
        def boom(text, instr, fpath):
            raise RuntimeError('ai down')
        with pytest.raises(RuntimeError):
            author_action('myapp.demo', 'x', repo_root=str(world),
                          ai_edit=boom)
        assert '# AI-MODIFIED [' in p.read_text(encoding='utf-8')

    def test_ai_edit_applied_modified(self, world):
        p = _write_action(world)
        edited = _ACT.replace('print(1)', 'print("patched by ai")')
        r = author_action('myapp.demo', '改输出', repo_root=str(world),
                          ai_edit=lambda t, i, f: edited)
        assert r['ai_applied'] is True
        assert r['status'] == 'modified'
        assert 'patched by ai' in p.read_text(encoding='utf-8')

    def test_ai_edit_applied_but_invalid_needs_fix(self, world):
        p = _write_action(world)
        broken = _ACT.replace('"entry": "main"', '"entry": "nope"')
        r = author_action('myapp.demo', '改坏', repo_root=str(world),
                          ai_edit=lambda t, i, f: broken)
        assert r['status'] == 'needs_fix'
        assert p.read_text(encoding='utf-8') == broken


# ═══════════════════════════════════════════════════════════════════
# publish_action
# ═══════════════════════════════════════════════════════════════════

class TestPublishAction:
    def test_not_found(self, world):
        with pytest.raises(ActionError):
            publish_action('ghost.act', repo_root=str(world))

    def test_invalid_rejected(self, world, monkeypatch):
        p = _write_action(world)
        monkeypatch.setattr(
            "vools.actus.author.validate_action",
            lambda a: ['semantic: nope'])
        r = publish_action('myapp.demo', repo_root=str(world))
        assert r['status'] == 'rejected'

    def test_audit_needs_human_confirm(self, world, monkeypatch):
        p = _write_action(world)
        text = p.read_text(encoding='utf-8').replace(
            '"trust": "sandbox"', '"trust": "audit"')
        p.write_text(text, encoding='utf-8')
        # audit 动作需测试绑定才过 schema 校验——此处聚焦信任分派：校验与干跑均放行
        monkeypatch.setattr("vools.actus.author.validate_action", lambda a: [])
        monkeypatch.setattr("vools.actus.executor.preview",
                            lambda aid, actions_dir=None, **kw: {'blocks': []})
        r = publish_action('myapp.demo', repo_root=str(world))
        assert r['status'] == 'needs_human_confirm'
        assert '人类确认' in r['message']

    def test_published_into_index(self, world):
        _write_action(world)
        r = publish_action('myapp.demo', repo_root=str(world))
        assert r['status'] == 'published'
        assert r['index_status'] == 'valid'
        assert '入索引' in r['message']

    def test_index_error_falls_back_rejected(self, world, monkeypatch):
        _write_action(world)
        from vools.actus import indexer as ix
        def boom(meta_dir=None, **kw):
            raise RuntimeError('index down')
        monkeypatch.setattr(ix, 'build_index', boom)
        r = publish_action('myapp.demo', repo_root=str(world))
        assert r['status'] == 'rejected'
        assert 'index_error' in str(r['index_status'])


# ═══════════════════════════════════════════════════════════════════
# _find_action_file
# ═══════════════════════════════════════════════════════════════════

class TestFindActionFile:
    def test_delegates_to_resolver(self, world):
        p = _write_action(world)
        assert am._find_action_file('myapp.demo', str(world)) == str(p)

    def test_missing_returns_none(self, world):
        assert am._find_action_file('ghost.act', str(world)) is None

    def test_resolver_exception_swallowed(self, world, monkeypatch):
        from vools.actus import resolver as rv
        def boom(aid, actions_dir):
            raise RuntimeError('resolver down')
        monkeypatch.setattr(rv, 'find_action_file', boom)
        assert am._find_action_file('myapp.demo', str(world)) is None


def test_all_exports():
    assert set(am.__all__) == {'author_action', 'publish_action', 'Pipeline',
                               'run_pipeline'}
