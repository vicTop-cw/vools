"""repo.py — `.actus` 用户开发仓管理（docs/41 §6 主题 D）。

仓判定（docs/41 §D2，**双条件**，缺一不可）：
  1. 仓名必须以 `.actus` 结尾（如 `victo.actions.actus`），否则不参与检索、搜不到；
  2. 仓根必须含 `actus.registry.json`（owner、动作清单、签名、trust 基线）。

第 2 条实测要兼容既有产物：现行 `registry.ActionRegistry.build_from_directory`
写出的是**点前缀** `.actus.registry.json`（`registry.py:101-103`），而 docs/41:191-192
写的是不带点的 `actus.registry.json`。两者都认，并优先不带点的那个 —— 只认其中一个
会让"按文档建好的仓"或"按现状建好的仓"必有一半判定失败。

仓结构（docs/41 §D2）：`actions/` + `actus.registry.json` + `README.md`。
"""


__all__ = [
    'RepoError', 'ActionRepo', 'REGISTRY_FILENAMES', 'REPO_SUFFIX',
    'is_dev_repo_name', 'is_dev_repo', 'create_repo', 'list_repos',
    'parse_ref', 'repo_url', 'registry_path', 'load_registry', 'save_registry',
    'grant_repo_key', 'revoke_repo_key', 'repo_key_status',
]

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from .constants import is_action_file
from typing import Any, Dict, List, Optional, Tuple

from .visibility import GatedKeyStore
from ._proc import run_cmd_safe

#: 命名硬约束后缀（docs/41 §D2）
REPO_SUFFIX = '.actus'

#: 仓判定标志文件名：不带点的优先（docs/41 口径），带点的兼容现行产物
REGISTRY_FILENAMES = ('actus.registry.json', '.actus.registry.json')

#: 仓内动作归档目录
ACTIONS_DIRNAME = 'actions'

#: `<owner>/<name>.actus[:<action_id>]` 引用解析
_REF_RE = re.compile(
    r'^(?:(?P<owner>[A-Za-z0-9_.-]+)/)?(?P<name>[A-Za-z0-9_.-]+?)'
    r'(?:\.actus)?(?:\[(?P<action>[A-Za-z0-9_.-]+)\]|:(?P<action2>[a-z0-9_.]+))?$')


class RepoError(Exception):
    """仓操作的失败（结构化 code 口径与 docs/08 §5 对齐）。"""

    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict:
        return {'code': self.code, 'message': self.message, 'details': self.details}


# ── D2：仓判定 ──────────────────────────────────────────────────────────

def is_dev_repo_name(name: str) -> bool:
    """仓名是否符合 `.actus` 结尾的硬约束。"""
    base = (name or '').rstrip('/').rsplit('/', 1)[-1]
    if base.endswith('.git'):
        base = base[:-4]
    return base.endswith(REPO_SUFFIX) and len(base) > len(REPO_SUFFIX)


def registry_path(root: str) -> Optional[str]:
    """返回仓根实际使用的 registry 文件路径（无则 None）。"""
    for fn in REGISTRY_FILENAMES:
        p = os.path.join(root, fn)
        if os.path.isfile(p):
            return p
    return None


def is_dev_repo(root: str) -> bool:
    """双条件判定：目录名以 `.actus` 结尾 **且** 根下有 registry 文件。"""
    if not root or not os.path.isdir(root):
        return False
    return is_dev_repo_name(os.path.basename(os.path.abspath(root.rstrip('\\/')))) \
        and registry_path(root) is not None


def parse_ref(ref: str) -> Dict[str, Optional[str]]:
    """解析 `<owner>/<name>.actus[:<action_id>]`。

    返回 {'owner','name','repo','action_id'}；`repo` 是补全 `.actus` 后的仓名。
    解析不了抛 RepoError（**不返回 None 让调用方"猜"**）。
    """
    raw = (ref or '').strip().rstrip('/')
    if not raw:
        raise RepoError('action_not_found', '仓引用为空')
    if raw.endswith('.git'):
        raw = raw[:-4]
    m = _REF_RE.match(raw)
    if not m:
        raise RepoError('action_not_found',
                        f'无法解析仓引用：{ref!r}（期望 <owner>/<name>.actus[:action_id]）',
                        {'ref': ref})
    owner = m.group('owner')
    name = m.group('name')
    if not name.endswith(REPO_SUFFIX):
        name = name + REPO_SUFFIX
    action_id = m.group('action') or m.group('action2')
    return {'owner': owner, 'name': name, 'repo': name, 'action_id': action_id}


def repo_url(owner: Optional[str], name: str, host: str = 'github.com') -> str:
    """仓的 HTTPS 克隆地址。owner 缺省时只给仓名（本地/相对场景）。"""
    if owner:
        return f'https://{host}/{owner}/{name}.git'
    return name


# ── registry 读写 ──────────────────────────────────────────────────────

def _empty_registry(name: str, owner: str, description: str = '',
                    license_: str = 'MIT') -> Dict[str, Any]:
    return {
        'name': name,
        'version': '1.0.0',
        'description': description,
        'author': owner or 'unknown',
        'owner': owner or 'unknown',
        'license': license_,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'actions': [],
        # trust 基线（docs/41 §D2）：仓级默认信任档，安装时与动作自身 trust 取更严
        'trust_baseline': 'community',
        'fork_of': None,
    }


def load_registry(root: str) -> Dict[str, Any]:
    p = registry_path(root)
    if p is None:
        raise RepoError('action_not_found',
                        f'不是 actus 开发仓（缺 {" 或 ".join(REGISTRY_FILENAMES)}）：{root}',
                        {'root': os.path.abspath(root).replace(os.sep, '/')})
    try:
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
    except ValueError as exc:
        raise RepoError('action_invalid',
                        f'registry 不是合法 JSON：{p}',
                        {'path': p.replace(os.sep, '/'), 'reason': str(exc)})
    if not isinstance(data, dict):
        raise RepoError('action_invalid', 'registry 顶层必须是 object',
                        {'path': p.replace(os.sep, '/')})
    data.setdefault('actions', [])
    return data


def save_registry(root: str, data: Dict[str, Any]) -> str:
    """写回 registry。**沿用仓里已有的文件名**（不带点优先），不擅自改名。"""
    p = registry_path(root) or os.path.join(root, REGISTRY_FILENAMES[0])
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return p


class ActionRepo:
    """一个 `.actus` 用户开发仓。"""

    def __init__(self, root: str, name: Optional[str] = None,
                 owner: Optional[str] = None):
        self.root = os.path.abspath(root)
        self.name = name or os.path.basename(self.root.rstrip('\\/'))
        self.owner = owner or 'unknown'

    # 视图

    @property
    def actions_dir(self) -> str:
        return os.path.join(self.root, ACTIONS_DIRNAME)

    def exists(self) -> bool:
        return is_dev_repo(self.root)

    def registry(self) -> Dict[str, Any]:
        return load_registry(self.root)

    def action_files(self) -> List[str]:
        """仓内动作文件（相对仓根的 posix 路径）。"""
        out: List[str] = []
        base = self.actions_dir if os.path.isdir(self.actions_dir) else self.root
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != '__pycache__']
            for fn in sorted(filenames):
                if not is_action_file(fn):
                    continue
                out.append(os.path.relpath(os.path.join(dirpath, fn), self.root)
                           .replace(os.sep, '/'))
        return sorted(out)

    def status(self) -> Dict[str, Any]:
        reg = None
        err = None
        try:
            reg = self.registry()
        except RepoError as exc:
            err = exc.to_payload()
        return {
            'root': self.root.replace(os.sep, '/'),
            'name': self.name,
            'owner': (reg or {}).get('owner') or self.owner,
            'is_dev_repo': self.exists(),
            'name_ok': is_dev_repo_name(self.name),
            'registry': (registry_path(self.root) or '').replace(os.sep, '/') or None,
            'actions': len(self.action_files()),
            'trust_baseline': (reg or {}).get('trust_baseline'),
            'fork_of': (reg or {}).get('fork_of'),
            'error': err,
        }

    def as_dict(self) -> dict:
        return self.status()


def create_repo(root: str, name: Optional[str] = None, owner: str = 'unknown',
                description: str = '', license_: str = 'MIT',
                overwrite: bool = False) -> Dict[str, Any]:
    """建仓（docs/41 §D4 `actus repo create`）。

    命名硬约束在建仓时就挡住：名字不以 `.actus` 结尾 → 直接拒。
    这条约束如果留到检索时才发现，作者的仓会"建好了但搜不到"，现象与"没建"一样。
    """
    root = os.path.abspath(root)
    repo_name = name or os.path.basename(root.rstrip('\\/'))
    if not is_dev_repo_name(repo_name):
        raise RepoError(
            'action_invalid',
            f'仓名必须以 {REPO_SUFFIX} 结尾（当前 {repo_name!r}）—— '
            f'否则不参与检索（docs/41 §D2）',
            {'name': repo_name, 'suffix': REPO_SUFFIX})

    os.makedirs(root, exist_ok=True)
    os.makedirs(os.path.join(root, ACTIONS_DIRNAME), exist_ok=True)
    existing = registry_path(root)
    if existing and not overwrite:
        raise RepoError('action_invalid',
                        f'仓已存在 registry：{existing}（要重建请 overwrite=True）',
                        {'path': existing.replace(os.sep, '/')})

    reg = _empty_registry(repo_name, owner, description, license_)
    reg['actions'] = []
    rp = save_registry(root, reg)

    readme = os.path.join(root, 'README.md')
    if not os.path.isfile(readme):
        with open(readme, 'w', encoding='utf-8') as f:
            f.write(f'# {repo_name}\n\n'
                    f'Actus 用户开发仓（docs/41 §6 主题 D）。\n\n'
                    f'- owner: {owner}\n'
                    f'- 动作归档目录: `{ACTIONS_DIRNAME}/`\n'
                    f'- 仓清单: `{os.path.basename(rp)}`\n\n'
                    f'## 发布\n\n'
                    f'```\nactus publish <path> --to {owner}/{repo_name}\n```\n')
    return {'created': True, 'root': root.replace(os.sep, '/'),
            'registry': rp.replace(os.sep, '/'), 'name': repo_name, 'owner': owner}


def list_repos(base_dir: str) -> List[Dict[str, Any]]:
    """列出 base_dir 下的 `.actus` 仓（按名的硬约束 + registry 双条件过滤）。"""
    out: List[Dict[str, Any]] = []
    base = os.path.abspath(base_dir)
    if not os.path.isdir(base):
        return out
    for entry in sorted(os.listdir(base)):
        p = os.path.join(base, entry)
        if os.path.isdir(p) and is_dev_repo_name(entry):
            out.append(ActionRepo(p).status())
    return out


# ── D2：仓级 gated 密钥（docs/41 §B2.2 仓级粒度）────────────────────────

def grant_repo_key(repo: str, key: str = '', config_dir: str = None,
                   owner: Optional[str] = None) -> Dict[str, Any]:
    """生成/轮换**仓级** gated 密钥 —— 仓内全部 gated 动作共用。

    返回值里的明文 `key` 只出现这一次；仓里其它 public/unlisted 动作不受影响
    （docs/41 §B2.2「对 public/unlisted 动作无影响」）。
    """
    try:
        ref = parse_ref(f'{owner}/{repo}' if owner and '/' not in repo else repo)
    except RepoError:
        ref = {'repo': repo}
    repo_name = ref.get('repo') or repo
    out = GatedKeyStore(config_dir).grant(repo=repo_name, key=key)
    out['scope_kind'] = 'repo'
    out['repo'] = repo_name
    return out


def revoke_repo_key(repo: str, config_dir: str = None,
                    owner: Optional[str] = None) -> bool:
    try:
        ref = parse_ref(f'{owner}/{repo}' if owner and '/' not in repo else repo)
    except RepoError:
        ref = {'repo': repo}
    return GatedKeyStore(config_dir).revoke(repo=ref.get('repo') or repo)


def repo_key_status(repo: str, config_dir: str = None) -> Dict[str, Any]:
    store = GatedKeyStore(config_dir)
    try:
        ref = parse_ref(repo)
        repo_name = ref.get('repo') or repo
    except RepoError:
        repo_name = repo
    return {'repo': repo_name, 'configured': store.has_gate(repo=repo_name),
            'scopes': [s for s in store.list_scopes()
                       if s['scope'] == f'repo:{repo_name}']}


# ── D4：本地 git 操作（推远端由 publisher 调）────────────────────────────

def run_git(root: str, args: List[str], timeout: int = 120) -> Dict[str, Any]:
    """在本仓内跑一条 git 命令。

    与既有 `git_ops` 动作同形（subprocess + 显式 cwd），但**不打印 token**：
    远端凭据由调用方经环境注入（docs/41 §D3「禁止明文写入动作或日志」），
    所以这里只回显命令本身（不含任何 `user:token@` 形态的 URL）。
    """
    safe_args = [re.sub(r'://[^/@]*@', '://***@', a) for a in args]
    try:
        proc = run_cmd_safe(['git'] + list(args), cwd=root, timeout=timeout)
    except Exception as exc:
        # run_cmd_safe 内部已吞掉 Popen 异常（rc=-1 + stderr=异常消息），这里
        # 的 except 实际只在极罕见情形（如被 SIGKILL 前）触发，作兜底。
        return {'ok': False, 'code': 'timeout',
                'message': f'git 执行失败：{exc}', 'argv': safe_args}
    if proc.returncode == -1:
        # run_cmd_safe 把 Popen 抛的 FileNotFoundError 等吞成 rc=-1，
        # stderr 里是异常字符串。git 不存在时按 dependency_missing 报，
        # 而不是笼统 timeout（BUG-13.26）。
        msg = (proc.stderr or '').strip()
        return {'ok': False, 'code': 'dependency_missing',
                'message': msg or f'git 不可用（returncode=-1）', 'argv': safe_args}
    return {'ok': proc.returncode == 0, 'exit': proc.returncode,
            'stdout': (proc.stdout or '').strip(),
            'stderr': (proc.stderr or '').strip(),
            'argv': safe_args}
