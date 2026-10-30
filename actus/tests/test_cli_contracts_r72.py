# -*- coding: utf-8 -*-
"""cli.py 契约测试 batch 2（r72）：config/reg/team/private/visibility/registry/
install/uninstall/sign/publish/search/sync/list-installed/rollback/check-update/
keygen/sign/verify/approve/pending/artifacts 直调分发层。

隔离约定与套件一致（conftest 已隔离 ACTUS_META_DIR/ACTUS_REPO_ROOT/HOME）；
本文件额外用 monkeypatch.setenv('ACTUS_CONFIG_DIR', tmp) 隔离
RegistryManager/TeamManager/VisibilityEngine 的配置目录。
"""
import importlib
import json
import os
import sys
import types

import pytest

import _ai_local_bootstrap  # noqa: F401  (必须先于 vools.actus 导入)

cli = importlib.import_module('vools.actus.cli')
vis_mod = importlib.import_module('vools.actus.visibility')
reg_mod = importlib.import_module('vools.actus.registry')
inst_mod = importlib.import_module('vools.actus.installer')
tm_mod = importlib.import_module('vools.actus.trust_model')
pkg = importlib.import_module('vools.actus')


def NS(**kw):
    return types.SimpleNamespace(**kw)


def _cfg_dir(tmp_path, monkeypatch):
    d = tmp_path / 'viscfg'
    d.mkdir(exist_ok=True)
    monkeypatch.setenv('ACTUS_CONFIG_DIR', str(d))
    return str(d)


# ── _gen_config ──

class TestGenConfig:
    @pytest.mark.parametrize('client', ['claude', 'cursor', 'cline', 'vscode'])
    def test_ok(self, client, capsys):
        assert cli._gen_config(client) == 0
        out = capsys.readouterr().out
        assert sys.executable and (json.dumps(sys.executable) in out)
        assert '"-m"' in out  # json.dumps(["-m", "actus", "mcp"])
        assert '重启 AI 客户端' in out

    def test_vscode_shape(self, capsys):
        assert cli._gen_config('vscode') == 0
        out = capsys.readouterr().out
        assert '"mcp.servers"' in out and '"type": "stdio"' in out

    def test_outputs_differ(self, capsys):
        outs = []
        for c in ('claude', 'cursor'):
            cli._gen_config(c)
            outs.append(capsys.readouterr().out)
        assert outs[0] != outs[1]


# ── _cmd_reg（真 RegistryManager，ACTUS_CONFIG_DIR 隔离）──

class TestCmdReg:
    def test_no_command(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_reg(NS()) == 1
        assert '用法' in capsys.readouterr().err

    def test_list_defaults(self, tmp_path, monkeypatch, capsys):
        # RegistryManager 出厂自带 private/public 两个默认注册表（非空清单）
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_reg(NS(reg_command='list')) == 0
        out = capsys.readouterr().out
        assert '已配置注册表 (2)' in out
        assert 'private' in out and 'public' in out

    def test_add_then_list(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        a = NS(reg_command='add', name='main', url='https://x',
               type='public', branch='main', priority=5)
        assert cli._cmd_reg(a) == 0
        assert '已添加注册表' in capsys.readouterr().out
        assert cli._cmd_reg(NS(reg_command='list')) == 0
        out = capsys.readouterr().out
        assert 'main' in out and 'https://x' in out and 'priority=5' in out

    def test_add_duplicate(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        a = NS(reg_command='add', name='main', url='https://x',
               type='public', branch='main', priority=10)
        cli._cmd_reg(a)
        assert cli._cmd_reg(a) == 1
        assert '已存在' in capsys.readouterr().err

    def test_remove_missing(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_reg(NS(reg_command='remove', name='nope')) == 1
        assert '不存在' in capsys.readouterr().err

    def test_remove_ok(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        cli._cmd_reg(NS(reg_command='add', name='r1', url='u',
                        type='public', branch='main', priority=1))
        capsys.readouterr()
        assert cli._cmd_reg(NS(reg_command='remove', name='r1')) == 0
        assert '已移除' in capsys.readouterr().out

    def test_unknown(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_reg(NS(reg_command='bogus')) == 1


# ── _cmd_team（真 TeamManager）──

class TestCmdTeam:
    def test_no_command(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_team(NS()) == 1

    def test_list_empty(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_team(NS(team_command='list')) == 0
        assert '暂无团队' in capsys.readouterr().out

    def test_create_and_list(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_team(NS(team_command='create', name='core',
                                creator='boss')) == 0
        assert '已创建团队' in capsys.readouterr().out
        assert cli._cmd_team(NS(team_command='list')) == 0
        assert 'core' in capsys.readouterr().out

    def test_create_duplicate(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        cli._cmd_team(NS(team_command='create', name='core', creator='boss'))
        capsys.readouterr()
        assert cli._cmd_team(NS(team_command='create', name='core',
                                creator='boss')) == 1
        assert '已存在' in capsys.readouterr().err

    def test_list_get_missing(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_team(NS(team_command='list', team='ghost')) == 1

    def test_add_remove_member(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        cli._cmd_team(NS(team_command='create', name='core', creator='boss'))
        capsys.readouterr()
        assert cli._cmd_team(NS(team_command='add-member', team='core',
                                user='alice', role='member')) == 0
        assert cli._cmd_team(NS(team_command='add-member', team='core',
                                user='alice', role='member')) == 1  # 已在
        # 写侧校验：非法 role 直接拒（MEMBER_ROLES = admin/member/viewer）
        assert cli._cmd_team(NS(team_command='add-member', team='core',
                                user='bob', role='dev')) == 1
        assert cli._cmd_team(NS(team_command='list', team='core')) == 0
        assert 'alice' in capsys.readouterr().out
        assert cli._cmd_team(NS(team_command='remove-member', team='core',
                                user='alice')) == 0
        assert cli._cmd_team(NS(team_command='remove-member', team='core',
                                user='ghost')) == 1

    def test_add_member_missing_team(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_team(NS(team_command='add-member', team='ghost',
                                user='a', role='member')) == 1

    def test_unknown(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_team(NS(team_command='zzz')) == 1


# ── _cmd_private（真 VisibilityEngine）──

class TestCmdPrivate:
    def test_no_command(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_private(NS()) == 1

    def test_list_empty(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_private(NS(private_command='list')) == 0
        assert '暂无私有动作' in capsys.readouterr().out

    def test_add_list_remove(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_private(NS(private_command='add',
                                   action_id='a.b', author='me',
                                   path='actions/a.actus.md')) == 0
        assert cli._cmd_private(NS(private_command='list')) == 0
        out = capsys.readouterr().out
        assert 'a.b' in out and 'author=me' in out
        assert cli._cmd_private(NS(private_command='remove',
                                   action_id='a.b')) == 0
        assert cli._cmd_private(NS(private_command='remove',
                                   action_id='a.b')) == 1

    def test_add_without_metadata(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_private(NS(private_command='add',
                                   action_id='a.b')) == 0
        assert cli._cmd_private(NS(private_command='list')) == 0
        assert 'a.b' in capsys.readouterr().out

    def test_unknown(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_private(NS(private_command='zz')) == 1


# ── _cmd_visibility ──

class TestCmdVisibility:
    def _ns_get(self, aid='x.y', json_mode=False):
        return NS(visibility_command='get', action_id=aid, json_output=json_mode)

    def _ns_set(self, level='public', team=None, json_mode=False, aid='x.y'):
        return NS(visibility_command='set', action_id=aid, level=level,
                  team=team, json_output=json_mode)

    def test_no_command(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_visibility(NS()) == 1

    def test_get_private_index_priority(self, tmp_path, monkeypatch, capsys):
        d = _cfg_dir(tmp_path, monkeypatch)
        vis_mod.VisibilityEngine(config_dir=d).add_private_action('p.a', {})
        assert cli._cmd_visibility(self._ns_get('p.a')) == 0
        assert 'private' in capsys.readouterr().out

    def test_get_from_action_json(self, tmp_path, monkeypatch):
        _cfg_dir(tmp_path, monkeypatch)
        act = types.SimpleNamespace(meta={'visibility': 'Trusted', 'team': 'core'},
                                    path='')
        monkeypatch.setattr(pkg, 'get_action', lambda aid: act, raising=False)
        assert cli._cmd_visibility(self._ns_get('x.y', True)) == 0

    def test_get_from_action_human(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        act = types.SimpleNamespace(meta={'visibility': 'public', 'team': ''},
                                    path='')
        monkeypatch.setattr(pkg, 'get_action', lambda aid: act, raising=False)
        assert cli._cmd_visibility(self._ns_get()) == 0
        assert 'public' in capsys.readouterr().out

    def test_get_action_error(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        def boom(aid):
            raise RuntimeError('io')
        monkeypatch.setattr(pkg, 'get_action', boom, raising=False)
        assert cli._cmd_visibility(self._ns_get()) == 1
        assert '无法读取动作' in capsys.readouterr().err

    def test_set_team_needs_team_arg(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_visibility(self._ns_set('team', None)) == 1
        assert '--team' in capsys.readouterr().err

    def test_set_team_missing_team(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_visibility(self._ns_set('team', 'ghost')) == 1
        assert '团队不存在' in capsys.readouterr().err

    def test_set_get_action_error(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        monkeypatch.setattr(pkg, 'get_action',
                            lambda a: (_ for _ in ()).throw(RuntimeError('x')),
                            raising=False)
        assert cli._cmd_visibility(self._ns_set('public')) == 1

    def test_set_no_path(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        act = types.SimpleNamespace(meta={}, path='')
        monkeypatch.setattr(pkg, 'get_action', lambda a: act, raising=False)
        assert cli._cmd_visibility(self._ns_set('public')) == 1
        assert '找不到动作文件' in capsys.readouterr().err

    def test_set_write_fail(self, tmp_path, monkeypatch):
        _cfg_dir(tmp_path, monkeypatch)
        f = tmp_path / 'a.actus.md'
        f.write_text('#!cfg\n{"id":"x.y","name":"X","version":"1.0.0",'
                     '"trust":"safe","entry":"python -c print(1)"}\n#!cfg\n',
                     encoding='utf-8')
        act = types.SimpleNamespace(meta={'visibility': 'public'}, path=str(f))
        monkeypatch.setattr(pkg, 'get_action', lambda a: act, raising=False)
        monkeypatch.setattr(cli, '_write_action_visibility',
                            lambda *a, **k: (False, 'boom'), raising=False)
        assert cli._cmd_visibility(self._ns_set('public', json_mode=True)) == 1
        assert cli._cmd_visibility(self._ns_set('public')) == 1

    def test_set_write_ok_json(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        f = tmp_path / 'a.actus.md'
        f.write_text('x', encoding='utf-8')
        act = types.SimpleNamespace(meta={'visibility': 'public'}, path=str(f))
        monkeypatch.setattr(pkg, 'get_action', lambda a: act, raising=False)
        monkeypatch.setattr(cli, '_write_action_visibility',
                            lambda *a, **k: (True, 'ok'), raising=False)
        assert cli._cmd_visibility(self._ns_set('trusted', json_mode=True)) == 0

    def test_set_write_ok_human(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        f = tmp_path / 'a.actus.md'
        f.write_text('x', encoding='utf-8')
        act = types.SimpleNamespace(meta={}, path=str(f))
        monkeypatch.setattr(pkg, 'get_action', lambda a: act, raising=False)
        monkeypatch.setattr(cli, '_write_action_visibility',
                            lambda *a, **k: (True, 'ok'), raising=False)
        assert cli._cmd_visibility(self._ns_set('public')) == 0
        assert '可见性已更新' in capsys.readouterr().out

    def test_set_team_ok_writes_team(self, tmp_path, monkeypatch, capsys):
        d = _cfg_dir(tmp_path, monkeypatch)
        vis_mod.TeamManager(d).create_team('core', 'boss')  # set 前置：团队须存在
        f = tmp_path / 'a.actus.md'
        f.write_text('x', encoding='utf-8')
        act = types.SimpleNamespace(meta={}, path=str(f))
        monkeypatch.setattr(pkg, 'get_action', lambda a: act, raising=False)
        seen = {}
        def fake_write(path, level, team=None):
            seen['team'] = team
            return (True, 'ok')
        monkeypatch.setattr(cli, '_write_action_visibility', fake_write,
                            raising=False)
        assert cli._cmd_visibility(self._ns_set('team', 'core')) == 0
        assert seen['team'] == 'core'
        assert '团队: core' in capsys.readouterr().out

    def test_unknown_command(self, tmp_path, monkeypatch, capsys):
        _cfg_dir(tmp_path, monkeypatch)
        assert cli._cmd_visibility(NS(visibility_command='zz')) == 1


# ── _cmd_registry（假 ActionRegistry/RegistryEntry）──

class _FakeReg:
    def __init__(self, index=None):
        self.calls = []
        self._index = index if index is not None else {'actions': []}

    def build_from_directory(self, repo_dir, write=False):
        self.calls.append(('build', repo_dir, write))
        return self._index

    def load_from_file(self, path):
        self.calls.append(('load', path))
        return self._index

    def write_index(self, index, repo_dir):
        self.calls.append(('write', repo_dir))
        return os.path.join(repo_dir, '.actus.registry.json')

    def load_from_repo(self, root):
        self.calls.append(('load_repo', root))
        return self._index

    def search(self, **kw):
        self.calls.append(('search', kw))
        return self._results

    def load_cached_index(self, url):
        self.calls.append(('cached', url))
        return self._cached

    _results = []
    _cached = None

    def validate_entry(self, entry, repo_dir):
        self.calls.append(('validate', entry.id))
        return (True, '')


def _patch_reg(monkeypatch, index=None, results=None, cached=None):
    reg = _FakeReg(index)
    reg._results = results or []
    reg._cached = cached
    monkeypatch.setattr(reg_mod, 'ActionRegistry', lambda: reg, raising=False)
    return reg


class TestCmdRegistry:
    @staticmethod
    def _idx_file(tmp_path, obj):
        p = tmp_path / 'idx.json'
        p.write_text(json.dumps(obj), encoding='utf-8')
        return str(p)

    def test_build_json(self, tmp_path, monkeypatch, capsys):
        reg = _patch_reg(monkeypatch, {'actions': [{'id': 'a'}]})
        rc = cli._cmd_registry(NS(registry_command='build', output=None,
                                  json_output=True))
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['status'] == 'ok' and payload['count'] == 1
        assert reg.calls[0][0] == 'build'

    def test_build_human(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch, {'actions': []})
        assert cli._cmd_registry(NS(registry_command='build', output='o.json',
                                    json_output=False)) == 0
        assert '注册表索引已构建' in capsys.readouterr().out

    def test_validate_missing_index(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch)
        ns = NS(registry_command='validate',
                index=str(tmp_path / 'nope.json'), json_output=True)
        assert cli._cmd_registry(ns) == 1

    def test_validate_corrupt(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch, {'corrupt': True,
                                 'problems': {'e1': 'bad id'}})
        idx = self._idx_file(tmp_path, {})
        rc = cli._cmd_registry(NS(registry_command='validate',
                                  index=idx, json_output=True))
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload['problems'][0]['key'] == 'e1'

    def test_validate_empty(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch, {'actions': []})
        idx = self._idx_file(tmp_path, {})
        rc = cli._cmd_registry(NS(registry_command='validate',
                                  index=idx, json_output=True))
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['total'] == 0 and payload['valid'] == 0

    def _patch_entry(self, monkeypatch):
        class E:
            # 仿 dataclass：cli 用 __dataclass_fields__ 过滤未知键
            __dataclass_fields__ = {'id': None, 'name': None, 'version': None,
                                    'path': None, 'checksum': None}

            def __init__(self, **kw):
                self.__dict__.update(kw)
                self.id = kw.get('id', '?')
        monkeypatch.setattr(reg_mod, 'RegistryEntry', E, raising=False)

    def test_validate_valid(self, tmp_path, monkeypatch, capsys):
        reg = _patch_reg(monkeypatch, {'actions': [
            {'id': 'a.b', 'name': 'X', 'version': '1.0.0',
             'path': 'actions/x.actus.md', 'checksum': 'c'}]})
        self._patch_entry(monkeypatch)
        idx = self._idx_file(tmp_path, {})
        rc = cli._cmd_registry(NS(registry_command='validate',
                                  index=idx, json_output=True))
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['valid'] == 1 and payload['invalid'] == []

    def test_validate_invalid_entry(self, tmp_path, monkeypatch, capsys):
        reg = _patch_reg(monkeypatch)
        reg.validate_entry = lambda e, r: (False, 'id 坏')
        self._patch_entry(monkeypatch)
        reg._index = {'actions': [{'id': 'BAD', 'name': 'x'}]}
        idx = self._idx_file(tmp_path, {})
        rc = cli._cmd_registry(NS(registry_command='validate',
                                  index=idx, json_output=True))
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload['invalid'][0]['id'] == 'BAD'

    def test_validate_non_dict_entry(self, tmp_path, monkeypatch, capsys):
        reg = _patch_reg(monkeypatch, {'actions': ['not-a-dict']})
        self._patch_entry(monkeypatch)
        idx = self._idx_file(tmp_path, {})
        rc = cli._cmd_registry(NS(registry_command='validate',
                                  index=idx, json_output=True))
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload['invalid'][0]['id'] == '?'

    def test_validate_human_invalid(self, tmp_path, monkeypatch, capsys):
        reg = _patch_reg(monkeypatch)
        reg.validate_entry = lambda e, r: (False, 'id 坏')
        self._patch_entry(monkeypatch)
        reg._index = {'actions': [{'id': 'BAD'}]}
        idx = self._idx_file(tmp_path, {})
        assert cli._cmd_registry(NS(registry_command='validate',
                                    index=idx, json_output=False)) == 1
        assert '校验失败' in capsys.readouterr().out

    def test_validate_human_ok(self, tmp_path, monkeypatch, capsys):
        reg = _patch_reg(monkeypatch, {'actions': [{'id': 'a.b'}]})
        self._patch_entry(monkeypatch)
        idx = self._idx_file(tmp_path, {})
        assert cli._cmd_registry(NS(registry_command='validate',
                                    index=idx, json_output=False)) == 0
        assert '校验通过' in capsys.readouterr().out

    def test_info_missing(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch)
        assert cli._cmd_registry(NS(registry_command='info',
                                    index=str(tmp_path / 'no.json'))) == 1

    def test_info_json(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch, {'name': 'official', 'version': '2',
                                 'author': 'a', 'description': 'd',
                                 'actions': [{'id': 'a.b', 'version': '1'}]})
        idx = self._idx_file(tmp_path, {})
        assert cli._cmd_registry(NS(registry_command='info', index=idx,
                                    json_output=True)) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['name'] == 'official' and payload['count'] == 1

    def test_info_human(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch, {'name': 'official', 'version': '2',
                                 'author': 'a', 'description': 'd',
                                 'actions': [{'id': 'a.b', 'version': '1'}]})
        idx = self._idx_file(tmp_path, {})
        assert cli._cmd_registry(NS(registry_command='info', index=idx,
                                    json_output=False)) == 0
        assert '📦' in capsys.readouterr().out

    def test_unknown(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch)
        assert cli._cmd_registry(NS(registry_command='zz')) == 1


# ── _cmd_install / _cmd_uninstall（假 ActionInstaller）──

class _FakeInstaller:
    def __init__(self):
        self.calls = []

    def install(self, **kw):
        self.calls.append(('install', kw))
        return self._install_result

    def uninstall(self, **kw):
        self.calls.append(('uninstall', kw))
        return self._uninstall_result

    def list_installed(self):
        return self._manifests

    def update(self, **kw):
        self.calls.append(('update', kw))
        return self._update_result

    def sync_all(self):
        return self._sync_results

    def rollback(self, **kw):
        self.calls.append(('rollback', kw))
        return self._rollback_result

    def check_update(self, **kw):
        self.calls.append(('check', kw))
        return self._check_result

    _install_result = {'status': 'ok', 'name': 'r', 'path': '/p',
                       'action_count': 2, 'actions': ['a.b', 'c.d']}
    _uninstall_result = {'status': 'ok', 'removed': '/p'}
    _manifests = []
    _update_result = {'status': 'ok', 'name': 'r'}
    _sync_results = []
    _rollback_result = {'status': 'ok', 'commit': 'abc', 'message': 'm'}
    _check_result = {'status': 'ok', 'has_update': False,
                     'local_commit': 'a' * 40}


def _patch_installer(monkeypatch, inst=None):
    inst = inst or _FakeInstaller()
    monkeypatch.setattr(inst_mod, 'ActionInstaller', lambda: inst,
                        raising=False)
    return inst


class TestCmdInstallUninstall:
    def test_install_ok(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        ns = NS(url='u', branch='b', tag='t', commit='c', scope='team',
                dir='d', overwrite_config=True)
        assert cli._cmd_install(ns) == 0
        kw = inst.calls[0][1]
        assert kw['repo_url'] == 'u' and kw['branch'] == 'b'
        assert kw['tag'] == 't' and kw['commit'] == 'c'
        assert kw['scope'] == 'team' and kw['install_dir'] == 'd'
        assert kw['overwrite_config'] is True
        out = capsys.readouterr().out
        assert '安装成功' in out and 'a.b' in out

    def test_install_minimal_kwargs(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        assert cli._cmd_install(NS(url='u', branch=None, tag=None,
                                   commit=None, scope=None, dir=None,
                                   overwrite_config=False)) == 0
        assert inst.calls[0][1] == {'repo_url': 'u'}

    def test_install_fail(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        inst._install_result = {'status': 'error', 'message': 'clone 失败'}
        assert cli._cmd_install(NS(url='u', branch=None, tag=None,
                                   commit=None, scope=None, dir=None,
                                   overwrite_config=False)) == 1
        assert 'clone 失败' in capsys.readouterr().out

    def test_uninstall_ok(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        assert cli._cmd_uninstall(NS(url='u', name='n', force=True)) == 0
        assert inst.calls[0][1] == {'repo_url': 'u', 'name': 'n', 'force': True}
        assert '已卸载' in capsys.readouterr().out

    def test_uninstall_fail(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        inst._uninstall_result = {'status': 'error', 'message': '不在清单'}
        assert cli._cmd_uninstall(NS(url=None, name='n', force=False)) == 1


# ── _publish_sign_actions / _cmd_publish ──

class TestPublishSignActions:
    def _verifier(self, monkeypatch, mode):
        class V:
            def sign_file(self, path, key_name=None):
                self.last = (path, key_name)
                if mode == 'ok':
                    return {'status': 'ok', 'output': 'out.sig'}
                return {'status': 'error', 'message': 'no key'}
        monkeypatch.setattr(tm_mod, 'SignatureVerifier', V, raising=False)
        return V

    def test_missing_file(self, tmp_path, monkeypatch):
        self._verifier(monkeypatch, 'ok')
        signed, failures = cli._publish_sign_actions(
            {'actions': [{'id': 'a', 'path': 'nope.actus.md'}]}, str(tmp_path), 'k')
        assert signed == [] and '找不到动作文件' in failures[0][1]

    def test_missing_path_field(self, tmp_path, monkeypatch):
        self._verifier(monkeypatch, 'ok')
        signed, failures = cli._publish_sign_actions(
            {'actions': [{'id': 'a'}]}, str(tmp_path), 'k')
        assert 'path 缺失' in failures[0][1]

    def test_non_dict_skipped(self, tmp_path, monkeypatch):
        self._verifier(monkeypatch, 'ok')
        signed, failures = cli._publish_sign_actions(
            {'actions': ['x']}, str(tmp_path), 'k')
        assert signed == [] and failures == []

    def test_sign_ok(self, tmp_path, monkeypatch):
        self._verifier(monkeypatch, 'ok')
        f = tmp_path / 'x.actus.md'
        f.write_text('x', encoding='utf-8')
        signed, failures = cli._publish_sign_actions(
            {'actions': [{'id': 'a', 'path': 'x.actus.md'}]},
            str(tmp_path), 'k1')
        assert signed == [('a', 'out.sig')] and failures == []

    def test_sign_fail(self, tmp_path, monkeypatch):
        self._verifier(monkeypatch, 'fail')
        f = tmp_path / 'x.actus.md'
        f.write_text('x', encoding='utf-8')
        signed, failures = cli._publish_sign_actions(
            {'actions': [{'id': 'a', 'path': 'x.actus.md'}]},
            str(tmp_path), 'k')
        assert signed == [] and failures[0][1] == 'no key'


class TestCmdPublish:
    def test_dry_run(self, tmp_path, monkeypatch, capsys):
        reg = _patch_reg(monkeypatch, {'actions': [{'id': 'a.b',
                                                    'version': '1'}]})
        assert cli._cmd_publish(NS(dry_run=True, sign=False, key=None)) == 0
        assert all(c[0] == 'build' for c in reg.calls)  # 不写盘
        assert '干跑模式' in capsys.readouterr().out

    def test_publish_ok(self, tmp_path, monkeypatch, capsys):
        reg = _patch_reg(monkeypatch, {'actions': []})
        assert cli._cmd_publish(NS(dry_run=False, sign=False, key=None)) == 0
        assert reg.calls[-1][0] == 'write'
        assert '发布步骤' in capsys.readouterr().out

    def test_sign_failure_exits_1(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch, {'actions': []})
        monkeypatch.setattr(cli, '_publish_sign_actions',
                            lambda *a: ([], [('a.b', 'no key')]),
                            raising=False)
        assert cli._cmd_publish(NS(dry_run=False, sign=True, key='k')) == 1
        captured = capsys.readouterr()
        assert '✅' not in captured.out

    def test_sign_ok(self, tmp_path, monkeypatch, capsys):
        reg = _patch_reg(monkeypatch, {'actions': []})
        monkeypatch.setattr(cli, '_publish_sign_actions',
                            lambda *a: ([('a.b', 'out')], []), raising=False)
        assert cli._cmd_publish(NS(dry_run=False, sign=True, key='k')) == 0
        assert reg.calls[-1][0] == 'write'


# ── _cmd_search / _cmd_sync / _cmd_list_installed ──

def _entry(i=1):
    return types.SimpleNamespace(
        id='a.%d' % i, name='A%d' % i, version='1.0.%d' % i,
        trust_level='safe', description='d' * 10, author='me',
        category='cat', tags=['t1'])


class TestCmdSearch:
    def test_local_json(self, tmp_path, monkeypatch, capsys):
        reg = _patch_reg(monkeypatch, results=[_entry()])
        assert cli._cmd_search(NS(source='local', url=None, query='a',
                                  category=None, author=None, tag='t1,t2',
                                  limit=5, json_output=True)) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['count'] == 1 and payload['actions'][0]['id'] == 'a.1'
        assert reg.calls[-1][1]['tags'] == ['t1', 't2']
        assert reg.calls[-1][1]['limit'] == 5

    def test_local_empty_human(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch, results=[])
        assert cli._cmd_search(NS(source='local', url=None, query='a',
                                  category=None, author=None, tag=None,
                                  limit=20, json_output=False)) == 0
        assert '未找到' in capsys.readouterr().out

    def test_local_nonempty_human(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch, results=[_entry()])
        assert cli._cmd_search(NS(source='local', url=None, query='a',
                                  category=None, author=None, tag=None,
                                  limit=20, json_output=False)) == 0
        assert '找到 1 个动作' in capsys.readouterr().out

    def test_installed_source(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        inst._manifests = [{'local_path': str(tmp_path)}, {'local_path': ''}]
        reg = _patch_reg(monkeypatch, results=[])
        assert cli._cmd_search(NS(source='installed', url=None, query='a',
                                  category=None, author=None, tag=None,
                                  limit=20, json_output=False)) == 0
        repo_calls = [c for c in reg.calls if c[0] == 'load_repo']
        assert len(repo_calls) == 1 and repo_calls[0][1] == str(tmp_path)

    def test_url_no_cache(self, tmp_path, monkeypatch, capsys):
        reg = _patch_reg(monkeypatch, cached=None)
        assert cli._cmd_search(NS(source='url', url='https://x', query='a',
                                  category=None, author=None, tag=None,
                                  limit=20, json_output=False)) == 1
        assert '先安装' in capsys.readouterr().out

    def test_url_cached(self, tmp_path, monkeypatch, capsys):
        _patch_reg(monkeypatch, cached={'actions': []}, results=[])
        assert cli._cmd_search(NS(source='url', url='https://x', query='a',
                                  category=None, author=None, tag=None,
                                  limit=20, json_output=False)) == 0


class TestCmdSync:
    def test_force(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        inst._manifests = [{'url': 'u1', 'branch': 'b1'}, {'url': None}]
        assert cli._cmd_sync(NS(force=True, url=None, name=None)) == 0
        assert inst.calls[0] == ('install', {'repo_url': 'u1',
                                             'branch': 'b1'})

    def test_update_ok(self, tmp_path, monkeypatch, capsys):
        _patch_installer(monkeypatch)
        assert cli._cmd_sync(NS(force=False, url='u', name='n')) == 0
        assert '更新成功' in capsys.readouterr().out

    def test_update_fail(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        inst._update_result = {'status': 'error', 'message': 'no repo'}
        assert cli._cmd_sync(NS(force=False, url='u', name=None)) == 1

    def test_sync_all(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        inst._sync_results = [
            {'url': 'u1', 'result': {'status': 'ok'}},
            {'name': 'n2', 'result': {'status': 'error'}}]
        assert cli._cmd_sync(NS(force=False, url=None, name=None)) == 0
        out = capsys.readouterr().out
        assert '同步 2 个仓库' in out and '✅' in out and '❌' in out


class TestCmdListInstalled:
    def test_empty(self, tmp_path, monkeypatch, capsys):
        _patch_installer(monkeypatch)
        assert cli._cmd_list_installed(NS()) == 0
        assert '未安装' in capsys.readouterr().out

    def test_nonempty(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        inst._manifests = [{'cache_key': 'k', 'url': 'u', 'branch': 'b',
                            'local_path': '/p', 'actions': ['a']}]
        assert cli._cmd_list_installed(NS()) == 0
        out = capsys.readouterr().out
        assert 'k' in out and '已安装 1 个仓库' in out


class TestCmdRollbackCheckUpdate:
    def test_rollback_ok(self, tmp_path, monkeypatch, capsys):
        _patch_installer(monkeypatch)
        assert cli._cmd_rollback(NS(url='u', name='n', version='1')) == 0
        assert '回滚成功' in capsys.readouterr().out

    def test_rollback_fail(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        inst._rollback_result = {'status': 'error', 'message': 'nf'}
        assert cli._cmd_rollback(NS(url=None, name='n', version='1')) == 1

    def test_check_no_update(self, tmp_path, monkeypatch, capsys):
        _patch_installer(monkeypatch)
        assert cli._cmd_check_update(NS(url='u', name='n')) == 0
        assert '已是最新版本' in capsys.readouterr().out

    def test_check_has_update(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        inst._check_result = {'status': 'ok', 'has_update': True,
                              'local_commit': 'a' * 40,
                              'remote_commit': 'b' * 40}
        assert cli._cmd_check_update(NS(url='u', name='n')) == 0
        out = capsys.readouterr().out
        assert '有新版本可用' in out

    def test_check_fail(self, tmp_path, monkeypatch, capsys):
        inst = _patch_installer(monkeypatch)
        inst._check_result = {'status': 'error', 'message': 'git 坏'}
        assert cli._cmd_check_update(NS(url=None, name='n')) == 1


# ── keygen（真 KeyManager + tmp 目录）/ sign / verify / approve / pending ──

class TestCmdTrust:
    def test_keygen_real(self, tmp_path, monkeypatch, capsys):
        out_dir = str(tmp_path / 'keys')
        assert cli._cmd_keygen(NS(name='cli-test', output=out_dir)) == 0
        out = capsys.readouterr().out
        assert '密钥对已生成' in out
        assert os.path.isfile(out_dir + '/cli-test.key')

    def test_sign_ok(self, tmp_path, monkeypatch, capsys):
        class V:
            def sign_file(self, path, key_name=None):
                return {'status': 'ok', 'output': 'out.sig', 'signature': 'S'}
        monkeypatch.setattr(tm_mod, 'SignatureVerifier', V, raising=False)
        assert cli._cmd_sign(NS(path='p.actus.md', key='k')) == 0
        assert '签名成功' in capsys.readouterr().out

    def test_sign_fail(self, tmp_path, monkeypatch, capsys):
        class V:
            def sign_file(self, path, key_name=None):
                return {'status': 'error', 'message': 'no key'}
        monkeypatch.setattr(tm_mod, 'SignatureVerifier', V, raising=False)
        assert cli._cmd_sign(NS(path='p', key='k')) == 1

    def test_verify_ok(self, tmp_path, monkeypatch, capsys):
        class V:
            def verify_file(self, path, key_name=None):
                return {'status': 'ok', 'signer': 'me', 'algorithm': 'RSA'}
        monkeypatch.setattr(tm_mod, 'SignatureVerifier', V, raising=False)
        assert cli._cmd_verify(NS(path='p', key='k')) == 0
        assert '验证通过' in capsys.readouterr().out

    def test_verify_fail(self, tmp_path, monkeypatch, capsys):
        class V:
            def verify_file(self, path, key_name=None):
                return {'status': 'error', 'message': 'bad sig'}
        monkeypatch.setattr(tm_mod, 'SignatureVerifier', V, raising=False)
        assert cli._cmd_verify(NS(path='p', key='k')) == 1

    def test_approve_reject_found(self, tmp_path, monkeypatch, capsys):
        class AM:
            def reject(self, aid, reason=None):
                return {'action_id': aid}
            def approve(self, aid):
                return None
        monkeypatch.setattr(tm_mod, 'ApprovalManager', AM, raising=False)
        assert cli._cmd_approve(NS(action_id='a', reject=True,
                                   reason='r')) == 0
        assert '已拒绝' in capsys.readouterr().out

    def test_approve_reject_missing(self, tmp_path, monkeypatch, capsys):
        class AM:
            def reject(self, aid, reason=None):
                return None
            def approve(self, aid):
                return None
        monkeypatch.setattr(tm_mod, 'ApprovalManager', AM, raising=False)
        assert cli._cmd_approve(NS(action_id='a', reject=True,
                                   reason=None)) == 1
        assert '未找到审批记录' in capsys.readouterr().out

    def test_approve_ok(self, tmp_path, monkeypatch, capsys):
        class AM:
            def approve(self, aid):
                return {'action_id': aid}
        monkeypatch.setattr(tm_mod, 'ApprovalManager', AM, raising=False)
        assert cli._cmd_approve(NS(action_id='a', reject=False,
                                   reason=None)) == 0
        assert '已批准' in capsys.readouterr().out

    def test_approve_missing(self, tmp_path, monkeypatch, capsys):
        class AM:
            def approve(self, aid):
                return None
        monkeypatch.setattr(tm_mod, 'ApprovalManager', AM, raising=False)
        assert cli._cmd_approve(NS(action_id='a', reject=False,
                                   reason=None)) == 1

    def test_pending_empty(self, tmp_path, monkeypatch, capsys):
        class AM:
            def list_pending(self):
                return []
        monkeypatch.setattr(tm_mod, 'ApprovalManager', AM, raising=False)
        assert cli._cmd_pending(NS()) == 0
        assert '没有待审批' in capsys.readouterr().out

    def test_pending_nonempty(self, tmp_path, monkeypatch, capsys):
        class AM:
            def list_pending(self):
                return [{'action_id': 'a', 'source_url': 'u',
                         'permissions': ['p1', 'p2']}]
        monkeypatch.setattr(tm_mod, 'ApprovalManager', AM, raising=False)
        assert cli._cmd_pending(NS()) == 0
        out = capsys.readouterr().out
        assert 'a' in out and 'p1, p2' in out


# ── _dispatch_artifacts（真 records，conftest 已隔离 meta）──

class TestDispatchArtifacts:
    def test_list(self, capsys):
        ns = NS(artifacts_command='list', action_id=None, exec_id=None,
                type=None)
        assert cli._dispatch_artifacts(ns) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['status'] == 'ok' and 'artifacts' in payload

    def test_cleanup(self, capsys):
        ns = NS(artifacts_command='cleanup', max_age_days=3650,
                max_count=5)
        assert cli._dispatch_artifacts(ns) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload['status'] == 'ok'

    def test_invalid(self, capsys):
        ns = NS(artifacts_command='zz', action_id=None, exec_id=None,
                type=None)
        assert cli._dispatch_artifacts(ns) == 2
