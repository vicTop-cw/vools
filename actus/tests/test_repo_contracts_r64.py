# -*- coding: utf-8 -*-
"""repo.py 契约测试 (Round 58)。

覆盖：RepoError 结构化 payload、仓名/仓根双条件判定、parse_ref 全形态
（owner/name/补后缀/[bracket]/:colon/.git 剥离/空引用/点号 owner 拒绝）、
repo_url、registry 读写（双文件名兼容/坏 JSON/非 dict）、ActionRepo
（status/as_dict/action_files）、create_repo（命名硬约束/overwrite/README）、
list_repos、仓级 gated 密钥三函数、run_git（真实 git + token 脱敏 + rc=-1
归因 dependency_missing + 异常兜底）。
"""

import json

import pytest

from vools.actus import repo as rmod
from vools.actus.repo import (
    ActionRepo,
    REGISTRY_FILENAMES,
    REPO_SUFFIX,
    RepoError,
    create_repo,
    grant_repo_key,
    is_dev_repo,
    is_dev_repo_name,
    list_repos,
    load_registry,
    parse_ref,
    registry_path,
    repo_key_status,
    repo_url,
    revoke_repo_key,
    run_git,
    save_registry,
)


# ---------------------------------------------------------------- RepoError

class TestRepoError:
    def test_attributes(self):
        e = RepoError('action_invalid', 'bad', {'x': 1})
        assert e.code == 'action_invalid'
        assert e.message == 'bad'
        assert e.details == {'x': 1}
        assert str(e) == 'bad'

    def test_to_payload(self):
        assert RepoError('c', 'm').to_payload() == {'code': 'c', 'message': 'm', 'details': {}}

    def test_defaults_details_empty(self):
        e = RepoError('c', 'm')
        assert e.details == {}


# ---------------------------------------------------------------- naming

class TestIsDevRepoName:
    @pytest.mark.parametrize('name', [
        'foo.actus', 'owner/foo.actus', 'foo.actus.git', 'a.actus/',
    ])
    def test_valid(self, name):
        assert is_dev_repo_name(name) is True

    @pytest.mark.parametrize('name', ['foo', '.actus', '', 'foo.git', 'actus'])
    def test_invalid(self, name):
        assert is_dev_repo_name(name) is False

    def test_git_suffix_stripped(self):
        # 'foo.actus.git' 剥掉 .git 后仍以 .actus 结尾
        assert is_dev_repo_name('owner/bar.actus.git') is True

    def test_bare_suffix_rejected(self):
        # 只有后缀本身不算仓名（len(base) > len(suffix)）
        assert is_dev_repo_name('.actus') is False


# ---------------------------------------------------------------- registry path / repo check

class TestRegistryPath:
    def test_dotless_preferred(self, tmp_path):
        (tmp_path / 'actus.registry.json').write_text('{}', encoding='utf-8')
        assert registry_path(str(tmp_path)) == str(tmp_path / 'actus.registry.json')

    def test_dotted_fallback(self, tmp_path):
        (tmp_path / '.actus.registry.json').write_text('{}', encoding='utf-8')
        assert registry_path(str(tmp_path)) == str(tmp_path / '.actus.registry.json')

    def test_none_when_missing(self, tmp_path):
        assert registry_path(str(tmp_path)) is None


class TestIsDevRepo:
    def test_both_conditions(self, tmp_path):
        p = tmp_path / 'demo.actus'
        p.mkdir()
        (p / 'actus.registry.json').write_text('{}', encoding='utf-8')
        assert is_dev_repo(str(p)) is True

    def test_name_without_registry(self, tmp_path):
        p = tmp_path / 'demo.actus'
        p.mkdir()
        assert is_dev_repo(str(p)) is False

    def test_missing_dir(self, tmp_path):
        assert is_dev_repo(str(tmp_path / 'nope.actus')) is False

    def test_empty_root(self):
        assert is_dev_repo('') is False

    def test_trailing_slash_basename(self, tmp_path):
        p = tmp_path / 'demo.actus'
        p.mkdir()
        (p / 'actus.registry.json').write_text('{}', encoding='utf-8')
        assert is_dev_repo(str(p) + '/') is True


# ---------------------------------------------------------------- parse_ref

class TestParseRef:
    def test_owner_and_name(self):
        r = parse_ref('alice/toolbox.actus')
        assert r == {'owner': 'alice', 'name': 'toolbox.actus',
                     'repo': 'toolbox.actus', 'action_id': None}

    def test_suffix_completed(self):
        r = parse_ref('toolbox')
        assert r['repo'] == 'toolbox.actus'

    def test_bracket_action(self):
        assert parse_ref('a/b.actus[deploy]')['action_id'] == 'deploy'

    def test_colon_action(self):
        assert parse_ref('a/b.actus:deploy')['action_id'] == 'deploy'

    def test_no_owner(self):
        assert parse_ref('b.actus')['owner'] is None

    def test_git_suffix_stripped(self):
        assert parse_ref('https_x/b.actus.git')['repo'] == 'b.actus'

    def test_trailing_slash_stripped(self):
        assert parse_ref('b.actus/')['repo'] == 'b.actus'

    def test_empty_raises(self):
        with pytest.raises(RepoError) as ei:
            parse_ref('  ')
        assert ei.value.code == 'action_not_found'

    def test_dot_owner_rejected(self):
        # 审计修复佐证：owner 为纯点号（. / ..）直接拒
        with pytest.raises(RepoError) as ei:
            parse_ref('../evil.actus')
        assert 'owner' in ei.value.details

    def test_invalid_chars_raise(self):
        with pytest.raises(RepoError):
            parse_ref('a b/c!')


def test_repo_url():
    assert repo_url('alice', 'x.actus') == 'https://github.com/alice/x.actus.git'
    assert repo_url('alice', 'x.actus', 'gitcode.com') == 'https://gitcode.com/alice/x.actus.git'
    assert repo_url(None, 'x.actus') == 'x.actus'


# ---------------------------------------------------------------- registry io

class TestLoadRegistry:
    def test_missing_raises(self, tmp_path):
        with pytest.raises(RepoError) as ei:
            load_registry(str(tmp_path))
        assert ei.value.code == 'action_not_found'
        assert 'actus.registry.json' in ei.value.message

    def test_bad_json(self, tmp_path):
        (tmp_path / 'actus.registry.json').write_text('{bad', encoding='utf-8')
        with pytest.raises(RepoError) as ei:
            load_registry(str(tmp_path))
        assert ei.value.code == 'action_invalid'
        assert ei.value.details['reason']

    def test_non_dict_top(self, tmp_path):
        (tmp_path / 'actus.registry.json').write_text('[1,2]', encoding='utf-8')
        with pytest.raises(RepoError) as ei:
            load_registry(str(tmp_path))
        assert '顶层必须是 object' in ei.value.message

    def test_actions_default(self, tmp_path):
        (tmp_path / 'actus.registry.json').write_text('{"name": "x"}', encoding='utf-8')
        assert load_registry(str(tmp_path))['actions'] == []


class TestSaveRegistry:
    def test_new_uses_dotless(self, tmp_path):
        p = save_registry(str(tmp_path), {'name': 'x'})
        assert p.endswith('actus.registry.json')
        assert json.loads((tmp_path / 'actus.registry.json').read_text(encoding='utf-8')) == {'name': 'x'}

    def test_existing_dotless_reused(self, tmp_path):
        (tmp_path / 'actus.registry.json').write_text('{"v": 1}', encoding='utf-8')
        save_registry(str(tmp_path), {'v': 2})
        assert not (tmp_path / '.actus.registry.json').exists()

    def test_existing_dotted_reused(self, tmp_path):
        (tmp_path / '.actus.registry.json').write_text('{"v": 1}', encoding='utf-8')
        p = save_registry(str(tmp_path), {'v': 2})
        assert p.endswith('.actus.registry.json')


# ---------------------------------------------------------------- ActionRepo

def _make_repo(tmp_path, name='demo.actus'):
    root = tmp_path / name
    root.mkdir()
    (root / 'actus.registry.json').write_text(
        json.dumps({'name': name, 'owner': 'own', 'trust_baseline': 'community',
                    'fork_of': None}), encoding='utf-8')
    return root


class TestActionRepo:
    def test_init_defaults(self, tmp_path):
        root = _make_repo(tmp_path)
        repo = ActionRepo(str(root))
        assert repo.name == 'demo.actus'
        assert repo.owner == 'unknown'
        assert repo.actions_dir == str(root / 'actions')

    def test_explicit_name_owner(self, tmp_path):
        repo = ActionRepo(str(tmp_path), name='x.actus', owner='o')
        assert repo.name == 'x.actus' and repo.owner == 'o'

    def test_exists(self, tmp_path):
        root = _make_repo(tmp_path)
        assert ActionRepo(str(root)).exists() is True

    def test_registry(self, tmp_path):
        root = _make_repo(tmp_path)
        assert ActionRepo(str(root)).registry()['name'] == 'demo.actus'

    def test_action_files_prefers_actions_dir(self, tmp_path):
        root = _make_repo(tmp_path)
        (root / 'actions').mkdir()
        (root / 'actions' / 'b.actus.md').write_text('x=1', encoding='utf-8')
        (root / 'actions' / 'a.actus.md').write_text('x=1', encoding='utf-8')
        (root / 'notes.md').write_text('x', encoding='utf-8')
        (root / 'actions' / '__pycache__').mkdir()
        (root / 'actions' / '__pycache__' / 'c.actus.md').write_text('x', encoding='utf-8')
        files = ActionRepo(str(root)).action_files()
        assert files == ['actions/a.actus.md', 'actions/b.actus.md']

    def test_action_files_root_fallback(self, tmp_path):
        root = tmp_path / 'r.actus'
        root.mkdir()
        (root / 'main.actus.md').write_text('x=1', encoding='utf-8')
        (root / 'readme.md').write_text('x', encoding='utf-8')
        assert ActionRepo(str(root)).action_files() == ['main.actus.md']

    def test_action_files_schema_suffix(self, tmp_path):
        root = _make_repo(tmp_path)
        (root / 's.actus.schema.md').write_text('x=1', encoding='utf-8')
        assert ActionRepo(str(root)).action_files() == ['s.actus.schema.md']

    def test_status_ok(self, tmp_path):
        root = _make_repo(tmp_path)
        s = ActionRepo(str(root)).status()
        assert s['is_dev_repo'] is True
        assert s['name_ok'] is True
        assert s['owner'] == 'own'
        assert s['trust_baseline'] == 'community'
        assert s['fork_of'] is None
        assert s['error'] is None
        assert s['registry'].endswith('actus.registry.json')

    def test_status_error_payload(self, tmp_path):
        root = tmp_path / 'bad.actus'
        root.mkdir()
        (root / 'actus.registry.json').write_text('{', encoding='utf-8')
        s = ActionRepo(str(root)).status()
        assert s['is_dev_repo'] is True
        assert s['error']['code'] == 'action_invalid'

    def test_as_dict_alias(self, tmp_path):
        root = _make_repo(tmp_path)
        assert ActionRepo(str(root)).as_dict() == ActionRepo(str(root)).status()


# ---------------------------------------------------------------- create_repo

class TestCreateRepo:
    def test_bad_name_rejected(self, tmp_path):
        with pytest.raises(RepoError) as ei:
            create_repo(str(tmp_path / 'plainname'))
        assert '仓名必须以' in ei.value.message
        assert ei.value.details['suffix'] == REPO_SUFFIX

    def test_ok_creates_structure(self, tmp_path):
        root = tmp_path / 'new.actus'
        out = create_repo(str(root), owner='alice', description='d')
        assert out['created'] is True
        assert (root / 'actions').is_dir()
        reg = json.loads((root / 'actus.registry.json').read_text(encoding='utf-8'))
        assert reg['name'] == 'new.actus'
        assert reg['owner'] == 'alice'
        assert reg['trust_baseline'] == 'community'
        assert reg['actions'] == []
        assert 'new.actus' in (root / 'README.md').read_text(encoding='utf-8')

    def test_existing_registry_without_overwrite(self, tmp_path):
        root = _make_repo(tmp_path)
        with pytest.raises(RepoError) as ei:
            create_repo(str(root))
        assert '仓已存在 registry' in ei.value.message

    def test_overwrite_rewrites_registry(self, tmp_path):
        root = _make_repo(tmp_path)
        out = create_repo(str(root), owner='bob', overwrite=True)
        assert out['created'] is True
        assert json.loads((root / 'actus.registry.json').read_text(
            encoding='utf-8'))['owner'] == 'bob'

    def test_readme_not_overwritten(self, tmp_path):
        root = tmp_path / 'n2.actus'
        root.mkdir()
        (root / 'README.md').write_text('CUSTOM', encoding='utf-8')
        create_repo(str(root))
        assert (root / 'README.md').read_text(encoding='utf-8') == 'CUSTOM'


# ---------------------------------------------------------------- list_repos

class TestListRepos:
    def test_missing_base(self, tmp_path):
        assert list_repos(str(tmp_path / 'nope')) == []

    def test_filters_and_sorts(self, tmp_path):
        for n in ('b.actus', 'a.actus', 'plain'):
            d = tmp_path / n
            d.mkdir()
            (d / 'actus.registry.json').write_text('{}', encoding='utf-8')
        (tmp_path / 'plain' / 'actus.registry.json').unlink()
        out = list_repos(str(tmp_path))
        assert [r['name'] for r in out] == ['a.actus', 'b.actus']
        assert all(r['is_dev_repo'] for r in out)

    def test_name_ok_repo_without_registry_listed_as_not_repo(self, tmp_path):
        # 名字合规但没 registry → status 里 is_dev_repo=False，但仍列出
        (tmp_path / 'c.actus').mkdir()
        out = list_repos(str(tmp_path))
        assert [r['name'] for r in out] == ['c.actus']
        assert out[0]['is_dev_repo'] is False


# ---------------------------------------------------------------- repo keys

class TestRepoKeys:
    def test_grant_and_status_roundtrip(self, tmp_path):
        cfg = str(tmp_path / 'cfg')
        out = grant_repo_key('demo.actus', config_dir=cfg)
        assert out['scope_kind'] == 'repo'
        assert out['repo'] == 'demo.actus'
        assert out['key']
        st = repo_key_status('demo.actus', config_dir=cfg)
        assert st['configured'] is True
        assert st['scopes'] and st['scopes'][0]['scope'] == 'repo:demo.actus'

    def test_grant_with_owner_prefix(self, tmp_path):
        out = grant_repo_key('demo.actus', config_dir=str(tmp_path / 'c'), owner='alice')
        assert out['repo'] == 'demo.actus'

    def test_grant_invalid_ref_falls_back(self, tmp_path):
        # parse_ref 失败时 fallback {'repo': repo}
        out = grant_repo_key('a b', config_dir=str(tmp_path / 'c'))
        assert out['repo'] == 'a b'

    def test_revoke(self, tmp_path):
        cfg = str(tmp_path / 'cfg')
        grant_repo_key('demo.actus', config_dir=cfg)
        assert revoke_repo_key('demo.actus', config_dir=cfg) is True
        assert repo_key_status('demo.actus', config_dir=cfg)['configured'] is False

    def test_revoke_missing_returns_false(self, tmp_path):
        assert revoke_repo_key('nope.actus', config_dir=str(tmp_path / 'c')) is False

    def test_revoke_invalid_ref_falls_back(self, tmp_path):
        assert revoke_repo_key('a b', config_dir=str(tmp_path / 'c')) is False

    def test_status_invalid_ref_falls_back(self, tmp_path):
        st = repo_key_status('a b', config_dir=str(tmp_path / 'c'))
        assert st == {'repo': 'a b', 'configured': False, 'scopes': []}


# ---------------------------------------------------------------- run_git

class TestRunGit:
    def test_real_git_init(self, tmp_path):
        out = run_git(str(tmp_path), ['init', '-q'])
        assert out['ok'] is True
        assert out['exit'] == 0
        assert (tmp_path / '.git').is_dir()

    def test_real_git_failure(self, tmp_path):
        out = run_git(str(tmp_path), ['rev-parse', '--verify', 'NOPE'])
        assert out['ok'] is False
        assert out['exit'] != 0

    def test_token_redacted_in_argv(self, tmp_path):
        out = run_git(str(tmp_path), ['clone', 'https://user:ghp_secret@github.com/a/b.git'])
        assert out['ok'] is False  # 真克隆会失败，但看 argv
        assert 'ghp_secret' not in out['argv'][1]
        assert '://***@' in out['argv'][1]

    def test_rc_minus_one_is_dependency_missing(self, tmp_path, monkeypatch):
        from types import SimpleNamespace

        def fake_run(args, cwd=None, timeout=None):
            return SimpleNamespace(returncode=-1, stdout='', stderr='git not found')

        monkeypatch.setattr(rmod, 'run_cmd_safe', fake_run)
        out = run_git(str(tmp_path), ['status'])
        assert out['code'] == 'dependency_missing'
        assert out['ok'] is False

    def test_rc_minus_one_empty_stderr_message(self, tmp_path, monkeypatch):
        from types import SimpleNamespace
        monkeypatch.setattr(rmod, 'run_cmd_safe',
                            lambda *a, **k: SimpleNamespace(returncode=-1, stdout='', stderr=''))
        out = run_git(str(tmp_path), ['status'])
        assert 'git 不可用' in out['message']

    def test_exception_fallback_timeout_code(self, tmp_path, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError('killed')

        monkeypatch.setattr(rmod, 'run_cmd_safe', boom)
        out = run_git(str(tmp_path), ['status'])
        assert out['code'] == 'timeout'
        assert 'killed' in out['message']


def test_all_exports():
    for name in ('ActionRepo', 'create_repo', 'parse_ref',
                 'grant_repo_key', 'revoke_repo_key', 'repo_key_status'):
        assert name in rmod.__all__


def test_run_git_not_exported():
    # run_git 是模块内工具（publisher 直接调），未列入 __all__
    assert 'run_git' not in rmod.__all__
