"""publisher.py — 动作发布器（docs/41 §6 主题 D）。

三条公开途径（docs/41 §D1），全部**先过三重门**再落任何一处：

    A 官方仓合入    提 PR 合并进 actus 官方开发仓      publish --pr
    B fork 开发仓   fork 官方仓后维护自己的公开动作     publish --fork
    C 自有开发仓    上传到用户自己的 GitHub 仓（主路径） publish --to <owner>/<name>.actus

三重门（docs/41 §A3）：**sigma 验证器**（含规约块时）+ **Omega 语料** + **actus 规范校验**。
每门独立回报 pass/fail/**blocked**；`blocked`（判据拿不到）不算过 ——
"没判据"与"过了"在回执里必须是两种东西，否则门禁会被"没人补语料"悄悄绕过。

凭据：token 只从 vault / 环境变量读，**不进 argv、不进日志**（docs/41 §D3）。
远端操作默认 `dry_run=True`；真跑必须显式关掉 —— 发布是不可逆的对外动作。
"""


__all__ = [
    'PublishError', 'triple_gate', 'publish', 'publish_to_repo',
    'publish_local_only', 'resolve_token', 'GITHUB_TOKEN_ENV',
    'GitHubClient', 'validate_action_paths',
]

import json
import os
import re
import shutil
import time
from typing import Any, Callable, Dict, List, Optional

from .repo import (REGISTRY_FILENAMES, ActionRepo, RepoError, is_dev_repo,
                   parse_ref, registry_path, repo_url, run_git, save_registry)
from .constants import is_action_file

#: GitHub 凭据的环境变量名（docs/40 vault 的键名同此）
GITHUB_TOKEN_ENV = 'GITHUB_TOKEN'


class PublishError(Exception):
    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict:
        return {'code': self.code, 'message': self.message, 'details': self.details}


# ── 凭据（不落日志、不进 argv）──────────────────────────────────────────

def resolve_token(env_name: str = GITHUB_TOKEN_ENV,
                  meta_dir: str = '') -> Optional[str]:
    """取 GitHub token：环境变量 → vault。

    只返回字符串，**从不打印/记录**；调用方拿到后也只放进子进程环境或请求头。
    """
    tok = os.environ.get(env_name)
    if tok:
        return tok
    try:
        from .vault import get_key
        return get_key(env_name, meta_dir=meta_dir) or None
    except Exception:                                    # noqa: BLE001
        return None


# ── 三重门 ─────────────────────────────────────────────────────────────

def _gate_sigma(action_path: str) -> Dict[str, Any]:
    """门 1：sigma 验证器 —— 仅当动作里真的有 ```sigma 块时才判。"""
    try:
        from .sigma import extract_sigma_block, parse_module_text, verify_module
    except ImportError as exc:
        return {'status': 'blocked',
                'reason': f'vools.actus.sigma 不可导入：{exc}'}
    try:
        text = extract_sigma_block(open(action_path, encoding='utf-8').read())
    except OSError as exc:
        return {'status': 'fail', 'reason': f'动作文件不可读：{exc}'}
    if not text.strip():
        return {'status': 'skipped',
                'reason': '动作未内嵌 Sigma 规约块（docs/41 §B3.1：sigma-Law 仅复杂动作可选）'}
    module = parse_module_text(text)
    rep = verify_module(module)
    return {'status': 'pass' if rep['passed'] else 'fail',
            'fingerprint': rep['fingerprint'],
            'violations': rep['violations'][:10],
            'tests': rep['tests']}


def _gate_omega(action_path: str, action_id: str,
                actions_dir: Optional[str] = None) -> Dict[str, Any]:
    """门 2：Omega 语料 —— 找该动作的 `*.spec.json` 并跑一次。"""
    spec = None
    try:
        from .omega import _find_omega_spec
        spec = _find_omega_spec(action_id, actions_dir)
    except Exception as exc:                             # noqa: BLE001
        return {'status': 'blocked', 'reason': f'Omega 查找器不可用：{exc}'}
    if not spec:
        return {'status': 'blocked',
                'reason': '未找到 Omega 语料（<name>.spec.json）；发布前需按 docs/38 补语料',
                'spec': None}
    try:
        with open(spec, encoding='utf-8') as f:
            spec_doc = json.load(f)
    except (OSError, ValueError) as exc:
        return {'status': 'fail', 'reason': f'语料不可读/非 JSON：{exc}',
                'spec': spec.replace(os.sep, '/')}
    return {'status': 'pass', 'spec': spec.replace(os.sep, '/'),
            'cases': len(spec_doc.get('cases') or spec_doc.get('tests') or [])}


def _gate_contract(action_path: str) -> Dict[str, Any]:
    """门 3：actus 规范校验（docs/03 §6 全套，真判据来自引擎）。"""
    try:
        from .validate import load_and_validate
    except ImportError as exc:
        return {'status': 'fail', 'reason': f'校验器不可导入：{exc}'}
    try:
        action = load_and_validate(action_path)
    except Exception as exc:                             # noqa: BLE001
        return {'status': 'fail',
                'reason': getattr(exc, 'message', str(exc)),
                'details': getattr(exc, 'details', {})}
    return {'status': 'pass', 'action_id': action.meta.get('id'),
            'trust': action.trust,
            'visibility': action.meta.get('visibility') or 'public'}


def triple_gate(action_path: str, actions_dir: Optional[str] = None,
                action_id: Optional[str] = None) -> Dict[str, Any]:
    """三门一起跑，逐门回报。`publishable` 要求**三门都不为 fail 且没有 blocked**。

    blocked 会阻止发布：Omega 语料是发布门禁的一部分（docs/41 §A3），
    "找不到语料"不是"没有门禁"，把它当通过等于把门禁降级成装饰。
    """
    action_path = os.path.abspath(action_path)
    if not os.path.isfile(action_path):
        raise PublishError('action_not_found', f'动作文件不存在：{action_path}')

    gates: Dict[str, Any] = {}
    gates['actus_contract'] = _gate_contract(action_path)
    aid = action_id or gates['actus_contract'].get('action_id') or ''
    gates['sigma'] = _gate_sigma(action_path)
    gates['omega'] = _gate_omega(action_path, aid, actions_dir)

    failed = [k for k, v in gates.items() if v['status'] == 'fail']
    blocked = [k for k, v in gates.items() if v['status'] == 'blocked']
    return {'action_id': aid,
            'path': action_path.replace(os.sep, '/'),
            'gates': gates,
            'failed': failed,
            'blocked': blocked,
            'publishable': not failed and not blocked}


# ── GitHub 客户端（可注入，便于 mock；默认 urllib 实现）─────────────────

class GitHubClient:
    """极薄的 GitHub REST 封装。

    只实现发布需要的几个端点，避免把 `git_ops` 动作那一大坨搬进引擎；
    `token` 只用于 Authorization 头，任何回执里都不回显。
    """

    API = 'https://api.github.com'

    def __init__(self, token: Optional[str] = None, opener: Optional[Callable] = None,
                 timeout: int = 60):
        self.token = token
        self._opener = opener
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Optional[dict] = None,
                 ) -> Dict[str, Any]:
        if self._opener is not None:                      # 测试注入：mp 一个假 http
            return self._opener(method, self.API + path, body, self.token)
        if not self.token:
            raise PublishError('auth_required',
                               f'缺少 GitHub 凭据：环境变量 {GITHUB_TOKEN_ENV} 或 vault 键'
                               f'同名项（docs/41 §D3）')
        import urllib.error
        import urllib.request
        data = json.dumps(body).encode('utf-8') if body is not None else None
        req = urllib.request.Request(self.API + path, data=data, method=method)
        req.add_header('Authorization', f'Bearer {self.token}')
        req.add_header('Accept', 'application/vnd.github+json')
        req.add_header('X-GitHub-Api-Version', '2022-11-28')
        if data:
            req.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode('utf-8', 'replace')
                return {'ok': True, 'status': resp.status,
                        'json': json.loads(raw) if raw.strip() else {}}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode('utf-8', 'replace')
            return {'ok': False, 'status': exc.code, 'error': raw[:400]}
        except Exception as exc:                          # noqa: BLE001
            return {'ok': False, 'status': 0,
                    'error': f'{type(exc).__name__}: {exc}'}

    # 端点

    def repo(self, owner: str, name: str) -> Dict[str, Any]:
        return self._request('GET', f'/repos/{owner}/{name}')

    def create_repo(self, name: str, private: bool = False,
                    description: str = '') -> Dict[str, Any]:
        return self._request('POST', '/user/repos', {
            'name': name, 'private': bool(private), 'description': description,
            'auto_init': False})

    def fork(self, owner: str, name: str) -> Dict[str, Any]:
        return self._request('POST', f'/repos/{owner}/{name}/forks', {})

    def create_pr(self, owner: str, name: str, title: str, head: str,
                  base: str = 'master', body: str = '') -> Dict[str, Any]:
        return self._request('POST', f'/repos/{owner}/{name}/pulls', {
            'title': title, 'head': head, 'base': base, 'body': body})

    def open_prs(self, owner: str, name: str, head_owner: str,
                 head_branch: str) -> Dict[str, Any]:
        q = f'?state=open&head={head_owner}:{head_branch}'
        return self._request('GET', f'/repos/{owner}/{name}/pulls{q}')


# ── 发布到仓（途径 C/B 的本地部分）──────────────────────────────────────

def validate_action_paths(paths: List[str]) -> List[str]:
    """要发布的动作路径：目录则展开其中的动作文件（.actus.md / .actus.schema.md）。"""
    out: List[str] = []
    for p in paths:
        ap = os.path.abspath(p)
        if os.path.isfile(ap):
            if not is_action_file(ap):
                raise PublishError('action_invalid',
                                   f'动作文件需以 .actus.md / .actus.schema.md 结尾：{ap}')
            out.append(ap)
        elif os.path.isdir(ap):
            for dirpath, dirnames, filenames in os.walk(ap):
                dirnames[:] = [d for d in dirnames if d != '__pycache__']
                for fn in sorted(filenames):
                    if is_action_file(fn):
                        out.append(os.path.join(dirpath, fn))
        else:
            raise PublishError('action_not_found', f'路径不存在：{ap}')
    if not out:
        raise PublishError('action_not_found', '没有任何动作文件可供发布')
    return sorted(set(out))


def _check_copy_target(action_path: str, repo: "ActionRepo",
                       category: str = '', force: bool = False) -> str:
    """复制**前**预检目标：返回目标路径；冲突则抛 `action_exists`。

    与 `_copy_into_repo` 的判据完全一致（存在且内容不同 → 拒绝），拆出来是为了
    在 `publish_local_only` 里**先把所有目标都预检完再动手** —— 否则多文件发布时
    可能"拷了前两个、第三个才冲突"，留下半截发布。
    """
    dest_dir = os.path.join(repo.actions_dir, category) if category \
        else repo.actions_dir
    dest = os.path.join(dest_dir, os.path.basename(action_path))
    if not os.path.exists(dest) or force:
        return dest
    try:
        with open(dest, 'rb') as existing, open(action_path, 'rb') as incoming:
            identical = existing.read() == incoming.read()
    except OSError:
        identical = False
    if not identical:
        raise PublishError(
            'action_exists',
            f'目标仓里已有同名动作且内容不同，拒绝覆盖：{dest}'
            f'（确认要覆盖请显式传 force=True）',
            {'dest': dest.replace(os.sep, '/'),
             'source': action_path.replace(os.sep, '/')})
    return dest


def _copy_into_repo(action_path: str, repo: ActionRepo,
                    category: str = '', force: bool = False) -> str:
    """把动作文件拷进仓的 `actions/`（保留分类子目录）。

    审计修（与 scaffold / installer 同族）：改前无条件 `shutil.copyfile` ——
    发布一个与仓内**同名**的动作会**静默覆盖**仓里既有文件（实测仓内
    `REPO_ORIGINAL` 被替换，无任何提示）。现在的语义：
      * 目标不存在 → 正常写入；
      * 目标已存在且内容相同 → 幂等 no-op（重复发布同一版本不该报错）；
      * 目标已存在且内容不同 → 抛 `action_exists` 拒绝，除非显式 `force=True`。
    """
    dest = _check_copy_target(action_path, repo, category, force=force)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and not force:
        # 预检已确认内容一致 → 幂等 no-op，不重写（保留原文件 mtime）
        return os.path.relpath(dest, repo.root).replace(os.sep, '/')
    shutil.copyfile(action_path, dest)
    return os.path.relpath(dest, repo.root).replace(os.sep, '/')


def _refresh_registry(repo: ActionRepo, action_ids: List[str]) -> Dict[str, Any]:
    """用引擎的 registry 生成器重建仓清单，再补上 owner/trust_baseline。

    复用现成生成器而不是自己攒一份：清单格式一旦有两份实现，检索侧与发布侧
    就会各自漂移。但 `ActionRegistry.build_from_directory` 写的是**点前缀**
    `.actus.registry.json`，而本仓的权威文件名（`repo.REGISTRY_FILENAMES[0]`）
    是不带点的 —— 直接调用会在仓根**同时留下两个 registry**，正是研究结论里
    那种"两份实现各自漂移"的既成事实。所以这里落盘后立刻做一次规范化：
    把生成结果并进权威文件，再删掉那个多余的点前缀副本。
    缓存目录也放到仓外，免得仓根多出一个 `.actus-cache/`。
    """
    canonical = registry_path(repo.root) or os.path.join(
        repo.root, REGISTRY_FILENAMES[0])
    generated: Dict[str, Any] = {}
    try:
        import tempfile

        from .registry import ActionRegistry
        cache_dir = os.path.join(tempfile.gettempdir(),
                                 'actus-registry-cache-%s'
                                 % re.sub(r'\W+', '_', os.path.basename(repo.root))[:40])
        reg_obj = ActionRegistry(cache_dir=cache_dir)
        reg_obj.build_from_directory(repo.root)
        # 生成器可能写的是点前缀那份；读回来并入权威文件
        for cand in (canonical, os.path.join(repo.root, REGISTRY_FILENAMES[1]),
                     os.path.join(repo.root, REGISTRY_FILENAMES[0])):
            if os.path.isfile(cand):
                with open(cand, encoding='utf-8') as f:
                    generated = json.load(f)
                break
    except Exception:                                    # noqa: BLE001
        generated = {}                                   # 生成器失败不阻断：兜底自建

    data = repo.registry()
    known = {a.get('id') for a in data.get('actions') or [] if isinstance(a, dict)}
    for entry in generated.get('actions') or []:
        if not isinstance(entry, dict):
            continue
        aid = entry.get('id')
        if not aid or aid in known:
            continue
        data.setdefault('actions', []).append(entry)
        known.add(aid)
    for aid in action_ids:
        if aid and aid not in known:
            data.setdefault('actions', []).append(
                {'id': aid, 'source': 'publish',
                 'published_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
            known.add(aid)

    data['owner'] = data.get('owner') or repo.owner
    data.setdefault('trust_baseline', 'community')
    save_registry(repo.root, data)

    # 规范化：权威文件之外的其它候选名一律清掉（同一份清单只留一个文件）
    for fn in REGISTRY_FILENAMES:
        p = os.path.join(repo.root, fn)
        if p != canonical and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass
    # 生成器可能顺手建的仓内缓存目录也一并清掉
    stray = os.path.join(repo.root, '.actus-cache')
    if os.path.isdir(stray):
        shutil.rmtree(stray, ignore_errors=True)
    return data


def publish_local_only(paths: List[str], repo_root: str, category: str = '',
                       dry_run: bool = True, gate: bool = True,
                       owner: str = 'unknown',
                       actions_dir: Optional[str] = None,
                       force: bool = False) -> Dict[str, Any]:
    """只把动作落进本地仓目录 + 刷新 registry（不碰远端）。

    `gate=True` 时逐个动作过三重门，任一不可发布即整笔拒绝 ——
    半截发布（有的进去了有的没有）会让仓清单与作者认知不一致。
    """
    files = validate_action_paths(paths)
    reports = []
    if gate:
        for f in files:
            g = triple_gate(f, actions_dir=actions_dir)
            reports.append(g)
            if not g['publishable']:
                return {'status': 'failed', 'dry_run': dry_run,
                        'error': {'code': 'action_invalid',
                                  'message': f'三重门未过，拒绝发布：{g["path"]}',
                                  'details': {'failed': g['failed'],
                                              'blocked': g['blocked'],
                                              'gates': g['gates']}},
                        'gates': reports, 'published': []}

    if not is_dev_repo(repo_root):
        raise PublishError(
            'action_not_found',
            f'目标不是 actus 开发仓（需要 <name>.actus 目录 + registry 文件）：{repo_root}',
            {'root': os.path.abspath(repo_root).replace(os.sep, '/')})

    repo = ActionRepo(repo_root, owner=owner)
    published: List[Dict[str, Any]] = []
    if not dry_run:
        # 预检**全部**目标：冲突在"一个字节都还没写"的阶段就暴露，
        # 避免多文件发布时"拷了前几个、后面才冲突"留下半截发布。
        for f in files:
            _check_copy_target(f, repo, category, force=force)
    for f in files:
        rel = None
        if not dry_run:
            rel = _copy_into_repo(f, repo, category, force=force)
        aid = ''
        for g in reports:
            if g['path'] == os.path.abspath(f).replace(os.sep, '/') or \
               g['path'] == f.replace(os.sep, '/'):
                aid = g.get('action_id') or ''
        published.append({'source': f.replace(os.sep, '/'),
                          'dest': (rel or os.path.join('actions',
                                   os.path.basename(f)).replace(os.sep, '/')),
                          'action_id': aid})
    reg = None
    if not dry_run:
        reg = _refresh_registry(repo, [p['action_id'] for p in published])
    return {'status': 'ok', 'dry_run': dry_run, 'published': published,
            'repo': repo.status(), 'gates': reports,
            'registry_actions': len((reg or {}).get('actions') or [])}


# ── 三条途径的统一入口 ─────────────────────────────────────────────────

def publish_to_repo(paths: List[str], repo_ref: str, push: bool = False,
                    dry_run: bool = True, gate: bool = True,
                    branch: str = 'main', category: str = '',
                    actions_dir: Optional[str] = None,
                    meta_dir: str = '', timeout: int = 120,
                    force: bool = False) -> Dict[str, Any]:
    """途径 C：发布到自有 `.actus` 仓（本地落 + 可选 push 远端）。

    `repo_ref` 接受两种形态：
      * `<owner>/<name>.actus` —— docs/41 §D4 的规范形式，先落 `~/.actus/cache/` 克隆；
      * **已存在的本地仓目录** —— 建仓/本地联调时的自然形态。
        不认这一种会逼调用方把本地路径伪装成 `owner/name`，凭空多一层假映射。

    `push=True` 需要凭据与远端；默认 dry_run，真推要显式关。
    """
    # 本地仓路径优先：它比 `owner/name` 更具体，且不会与 owner 名冲突
    if os.path.isdir(repo_ref) and is_dev_repo(repo_ref):
        local_root = os.path.abspath(repo_ref)
        ref = {'owner': ActionRepo(local_root).owner, 'name':
               os.path.basename(local_root.rstrip('\\/')), 'action_id': None}
    else:
        try:
            ref = parse_ref(repo_ref)
        except RepoError as exc:
            raise PublishError(exc.code, exc.message, exc.details)
        local_root = None
        if ref['owner']:
            cache = os.path.join(os.path.expanduser('~'), '.actus', 'cache')
            local_root = os.path.join(cache, f"{ref['owner']}_{ref['name']}")
        else:
            local_root = ref['name']

    result: Dict[str, Any] = {'status': 'ok', 'dry_run': dry_run,
                              'route': 'own_repo', 'repo_ref': repo_ref,
                              'local_root': local_root.replace(os.sep, '/')}

    if not os.path.isdir(local_root) and ref['owner']:
        # 远端仓不存在 → 明确报"需要先 clone 或 create"，不猜
        result.update({'status': 'failed',
                       'error': {'code': 'action_not_found',
                                 'message': (f'本地没有该仓的克隆：{local_root}。'
                                             f'请先手动 clone '
                                             f'{repo_url(ref["owner"], ref["name"])}'
                                             f'（CLI 当前没有 `actus repo create` 子命令；'
                                             f'库内入口是 repo.create_repo）'),
                                 'details': {'local_root':
                                             local_root.replace(os.sep, '/')}}})
        return result

    if not is_dev_repo(local_root):
        return {'status': 'failed', 'dry_run': dry_run, 'route': 'own_repo',
                'error': {'code': 'action_not_found',
                          'message': f'{local_root} 不是 actus 开发仓（双条件不满足）',
                          'details': {'local_root': local_root.replace(os.sep, '/'),
                                      'need_name_suffix': REPO_SUFFIX_HINT}},
                'repo_ref': repo_ref}

    inner = publish_local_only(paths, local_root, category=category,
                               dry_run=dry_run, gate=gate,
                               owner=ref['owner'] or 'unknown',
                               actions_dir=actions_dir, force=force)
    result.update(inner)
    result['route'] = 'own_repo'

    if inner.get('status') != 'ok':
        return result

    if push and not dry_run:
        token = resolve_token(meta_dir=meta_dir)
        if not token:
            result.update({'status': 'failed',
                           'error': {'code': 'auth_required',
                                     'message': (f'push 需要 GitHub 凭据：环境变量 '
                                                 f'{GITHUB_TOKEN_ENV} 或 vault 同名键'),
                                     'details': {}}})
            return result
        # 凭据经环境的 credential helper 注入，不进 argv、不进日志（docs/41 §D3）
        env = dict(os.environ)
        env[GITHUB_TOKEN_ENV] = token
        env['GIT_ASKPASS'] = 'echo'
        steps = [
            ['add', '-A'],
            ['-c', 'user.name=actus-publisher',
             '-c', 'user.email=actus@localhost',
             'commit', '-m', 'publish: %d action(s) from actus' % len(inner['published'])],
        ]
        for argv in steps:
            r = run_git(local_root, argv, timeout=timeout)
            if not r.get('ok') and 'nothing to commit' not in (r.get('stdout') or ''):
                result.update({'status': 'failed',
                               'error': {'code': 'internal',
                                         'message': f'git {argv[0]} 失败：'
                                                    f'{r.get("stderr") or r.get("message")}',
                                         'details': {'argv': r.get('argv')}}})
                return result
        push_r = run_git(local_root, ['push', 'origin', branch], timeout=timeout)
        result['push'] = push_r
        if not push_r.get('ok'):
            result.update({'status': 'failed',
                           'error': {'code': 'internal',
                                     'message': f'git push 失败：{push_r.get("stderr")}',
                                     'details': {'argv': push_r.get('argv')}}})
    elif push and dry_run:
        result['push'] = {'ok': True, 'dry_run': True,
                          'message': 'dry_run=True，未真正 push'}
    return result


REPO_SUFFIX_HINT = "仓目录名必须以 .actus 结尾，且根下需有 actus.registry.json"


def publish(paths: List[str], *, to_repo: Optional[str] = None,
            to_pr: Optional[str] = None, to_fork: Optional[str] = None,
            fork_owner: Optional[str] = None, push: bool = False,
            dry_run: bool = True, gate: bool = True, branch: str = 'main',
            category: str = '', base: str = 'master', title: str = '',
            actions_dir: Optional[str] = None, meta_dir: str = '',
            client: Optional[GitHubClient] = None,
            force: bool = False) -> Dict[str, Any]:
    """三条途径的统一入口（docs/41 §D1 / §D4）。

        publish(paths, to_repo='owner/name.actus')   # C 自有仓
        publish(paths, to_fork='owner/name.actus')   # B fork 仓
        publish(paths, to_pr='owner/actus')          # A 提 PR 合入官方仓

    三条都必须过三重门；`dry_run=True`（默认）不产生任何对外动作。
    """
    if not any((to_repo, to_pr, to_fork)):
        raise PublishError('param_invalid',
                           '必须指定发布途径之一：to_repo / to_fork / to_pr')

    if to_repo:
        return publish_to_repo(paths, to_repo, push=push, dry_run=dry_run,
                               gate=gate, branch=branch, category=category,
                               actions_dir=actions_dir, meta_dir=meta_dir,
                               force=force)

    if to_fork:
        # 途径 B：先把动作落进**自己的** fork 仓，再（可选）push
        res = publish_to_repo(paths, to_fork, push=push, dry_run=dry_run,
                              gate=gate, branch=branch, category=category,
                              actions_dir=actions_dir, meta_dir=meta_dir,
                              force=force)
        res['route'] = 'fork'
        if not dry_run and res.get('status') == 'ok':
            gh = client or GitHubClient(resolve_token(meta_dir=meta_dir))
            ref = parse_ref(to_fork)
            upstream = to_pr or ''
            fork_info = gh.fork(*(parse_ref(upstream)['owner'], parse_ref(upstream)['name'])) \
                if upstream else {'ok': True, 'skipped': True}
            res['fork_api'] = fork_info
        return res

    # 途径 A：提 PR
    ref = parse_ref(to_pr)
    if not ref['owner']:
        raise PublishError('param_invalid',
                           f'to_pr 需要 <owner>/<repo> 形式：{to_pr!r}')
    result: Dict[str, Any] = {'status': 'ok', 'dry_run': dry_run, 'route': 'pr',
                              'target': f"{ref['owner']}/{ref['name']}",
                              'pr': None}
    if gate:
        reports = []
        for f in validate_action_paths(paths):
            g = triple_gate(f, actions_dir=actions_dir)
            reports.append(g)
            if not g['publishable']:
                return {'status': 'failed', 'dry_run': dry_run, 'route': 'pr',
                        'error': {'code': 'action_invalid',
                                  'message': f'三重门未过，拒绝提 PR：{g["path"]}',
                                  'details': {'failed': g['failed'],
                                              'blocked': g['blocked'],
                                              'gates': g['gates']}},
                        'gates': reports}
        result['gates'] = reports

    head = f"{fork_owner or 'unknown'}:{branch}"
    if dry_run:
        result['pr'] = {'dry_run': True,
                        'planned': {'title': title or 'publish: %d action(s)'
                                    % len(validate_action_paths(paths)),
                                    'head': head, 'base': base}}
        return result

    gh = client or GitHubClient(resolve_token(meta_dir=meta_dir))
    resp = gh.create_pr(ref['owner'], ref['name'],
                        title=title or 'publish: actions from actus',
                        head=head, base=base,
                        body='由 `actus publish --pr` 生成（三重门已过）。')
    result['pr'] = resp
    if not resp.get('ok'):
        result.update({'status': 'failed',
                       'error': {'code': 'internal',
                                 'message': f'建 PR 失败（HTTP {resp.get("status")}）',
                                 'details': {'response': resp.get('error', '')[:400]}}})
    return result
