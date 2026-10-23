"""scattered.py — 动作零散化：任意路径 `.actus.md` / `.actus/` 即插即用（docs/41 §5 主题 C）。

设计要点（逐条对齐 docs/41 §C）：

C1 默认私有
    零散动作未声明 `visibility` 时按 `private` 处理；未声明 `trust` 时按 `audit`
    （首次执行需人类确认）。作者可在 `#!cfg` 里显式声明覆盖 —— 公开必须显式操作。

C2 解析管线（run / check 共用同一条）
    1 形态判定：`<id>.actus.md` 单文件；`<id>.actus/` 目录，入口 `main.actus.md`；
    2 规范校验：docs/03 §6 全套（schema/entry/语言路由/args）+ 依赖无环；
       deps 支持**相对路径引用**（`./other.actus.md` / `./lib.actus/`）与**动作库 id**
       两种形式；路径引用解析后必须落在授权根目录内；
    3 有效性判定：校验通过 + （可选）试运行 `status=ok` → 有效；否则逐项报告，不静默降级；
    4 执行：按 entry 走**正常生命周期与信任策略**（不另起一条执行链）。

C3 核心依赖自动注入
    `vools` / `actuscore`（本包）/ `sigma`（可选，来自 `vools.actus.sigma`）以
    **执行期白名单 + 版本锁定**方式注入，不污染宿主全局环境；额外依赖必须在
    零散动作根目录的 `project.actus.toml` 里显式声明，未声明即拒绝。

为什么放在 vools.actus 而不是只放 Actus 的 engine/actuscore：
    docs/41 §A2 的落点理由是「任何装了 vools-actus 的机器/零散运行时都能直接用，
    不必绑定 actus 主仓」。零散化正是这条理由的直接受益者，所以本体在这里；
    `engine/actuscore/scattered.py` 只做 re-export shim（与 trust_model.py 同形态）。
"""


__all__ = [
    'ScatteredError', 'ScatteredAction',
    'resolve_scattered', 'check_scattered', 'run_scattered',
    'authorized_root_for', 'is_scattered_path',
    'CORE_DEPENDENCY_WHITELIST', 'injection_report', 'build_injection_env',
    'load_project_deps', 'PROJECT_DEPS_FILENAME', 'ENTRY_FILENAME',
    'SCATTERED_FILE_SUFFIX', 'SCATTERED_DIR_SUFFIX',
]

import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# ── 常量 ────────────────────────────────────────────────────────────────

#: 单文件形态后缀（docs/08 §1 的动作文件后缀）
SCATTERED_FILE_SUFFIX = '.actus.md'
#: 目录形态后缀：`<id>.actus/`
SCATTERED_DIR_SUFFIX = '.actus'
#: 目录形态的入口文件名（docs/41 §C2 step 1）
ENTRY_FILENAME = 'main.actus.md'
#: 零散动作根目录里声明额外依赖的文件名（docs/41 §C3 / §2 兼容 35）
PROJECT_DEPS_FILENAME = 'project.actus.toml'

#: 执行期自动注入的核心依赖白名单（docs/41 §C3）。
#: 键是**动作里可 import 的名字**，值是提供它的顶层包。
CORE_DEPENDENCY_WHITELIST = {
    'vools': 'vools',
    'actuscore': 'actuscore',
    'sigma': 'vools.actus.sigma',
}

#: 声明式依赖前缀（`project.actus.toml` 里 <key> 的合法名）。
_DECLARABLE_DEP_KEYS = ('pip', 'npm', 'system', 'env')

#: 路径形态依赖的前缀：`./x` 或 `../x`
_PATH_DEP_PREFIXES = ('./', '../', '.\\', '..\\')

#: 引擎既有的其它依赖前缀（validate_graph 的 known-prefix 口径），
#: 这些不按"动作 id"处理，也不属于本模块要背书的声明式依赖。
_KNOWN_ENGINE_DEP_PREFIXES = ('lang:', 'mcp:', 'action:', 'cs_', 'build:')


class ScatteredError(Exception):
    """零散动作解析/校验阶段的错误。

    code 走 actus 的结构化错误码口径（docs/08 §5），供 CLI/MCP 直接分流：
      * path_escaped    路径逃逸出授权根
      * action_not_found 路径不存在/形态不可识别
      * action_invalid  规范校验不过（details.errors 逐项）
      * dependency_missing 声明式依赖未声明
    """

    def __init__(self, code: str, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict:
        return {'code': self.code, 'message': self.message, 'details': self.details}


class ScatteredAction:
    """解析后的零散动作（尚未执行）。"""

    def __init__(self, path: str, root: str, kind: str,
                 entry_path: Optional[str] = None):
        self.path = os.path.abspath(path)          # 真正承载动作的 .actus.md
        self.root = os.path.abspath(root)          # 授权根（路径引用的边界）
        self.kind = kind                           # 'file' | 'dir'
        self.entry_path = os.path.abspath(entry_path) if entry_path else None
        self.defaults_applied: Dict[str, Any] = {}

    def as_dict(self) -> dict:
        return {'path': self.path.replace(os.sep, '/'),
                'root': self.root.replace(os.sep, '/'),
                'kind': self.kind,
                'entry_path': (self.entry_path or '').replace(os.sep, '/'),
                'defaults_applied': self.defaults_applied}

    def __repr__(self) -> str:                     # pragma: no cover - 调试用
        return 'ScatteredAction(path=%r, kind=%r)' % (self.path, self.kind)


# ── C1/C2.1：形态判定与路径安全 ─────────────────────────────────────────

def is_scattered_path(path: str) -> bool:
    """路径看起来像零散动作（单文件 `<id>.actus.md` / `<id>.actus.schema.md` 或目录 `<id>.actus/`）。

    单文件判定走 `constants.is_action_file`（双后缀单一真源）——此前只认
    `.actus.md`，新格式 `.actus.schema.md` 的散落路径一律判 False。
    """
    p = (path or '').rstrip('\\/')
    base = os.path.basename(p)
    from .constants import is_action_file
    if is_action_file(base):
        return True
    return base.endswith(SCATTERED_DIR_SUFFIX) and os.path.isdir(p)


def authorized_root_for(path: str) -> str:
    """默认授权根。

    * 单文件形态：文件所在目录（同级 `./lib.actus/` 之类的相对依赖是合法用法）；
    * 目录形态：`.actus/` 目录自身（`main.actus.md` 与它的 `lib/` 都在里面）。

    授权根是**路径引用的边界**：`./` 允许、`../` 只有在解析后仍落在根内才允许。
    """
    p = os.path.abspath(path)
    if os.path.isdir(p) and p.rstrip('\\/').endswith(SCATTERED_DIR_SUFFIX):
        return p
    return os.path.dirname(p)


def _assert_inside(root: str, target: str, what: str = 'path') -> str:
    """解析后的绝对路径必须落在 root 内；否则抛 path_escaped。

    用 `os.path.realpath` 而不是 `abspath`：`abspath` 不解析符号链接，
    软链接可以把它拉出授权根（`ln -s /etc x` 之后 `x/passwd` 看着在根内）。
    """
    t = os.path.realpath(target)
    r = os.path.realpath(root)
    if t == r or t.startswith(r + os.sep):
        return t
    raise ScatteredError(
        'path_escaped',
        f'{what} 逃逸出授权根目录：{target}',
        {'root': r.replace(os.sep, '/'), 'resolved': t.replace(os.sep, '/')})


def resolve_scattered(path: str, authorized_root: Optional[str] = None) -> ScatteredAction:
    """C2.1 形态判定：把任意路径解析成一个零散动作。

    不接受「不存在的路径」与「既非 .actus.md 也非 .actus/ 的路径」——
    这两种情况显式报错，不当成"没有动作"静默返回（docs/41 §C2 step 3）。
    """
    if not path:
        raise ScatteredError('action_not_found', '路径为空')
    raw = os.path.abspath(path)
    root = os.path.abspath(authorized_root) if authorized_root else authorized_root_for(raw)

    if os.path.isfile(raw):
        from .constants import is_action_file
        if not is_action_file(os.path.basename(raw)):
            raise ScatteredError(
                'action_not_found',
                f'不是零散动作文件（需以 {SCATTERED_FILE_SUFFIX} 或 '
                f'.actus.schema.md 结尾）：{raw}',
                {'path': raw.replace(os.sep, '/')})
        _assert_inside(root, raw, '动作文件')
        return ScatteredAction(raw, root, 'file')

    if os.path.isdir(raw):
        base = raw.rstrip('\\/')
        if not os.path.basename(base).endswith(SCATTERED_DIR_SUFFIX):
            raise ScatteredError(
                'action_not_found',
                f'不是零散动作目录（需以 {SCATTERED_DIR_SUFFIX} 结尾）：{raw}',
                {'path': raw.replace(os.sep, '/')})
        entry = os.path.join(base, ENTRY_FILENAME)
        if not os.path.isfile(entry):
            raise ScatteredError(
                'action_not_found',
                f'复杂动作目录缺少入口 {ENTRY_FILENAME}：{raw}',
                {'path': base.replace(os.sep, '/'), 'expected_entry': ENTRY_FILENAME})
        return ScatteredAction(entry, root, 'dir', entry_path=entry)

    raise ScatteredError('action_not_found', f'路径不存在：{raw}',
                         {'path': raw.replace(os.sep, '/')})


# ── C3：依赖注入与声明式依赖 ────────────────────────────────────────────

def _core_injection_roots() -> List[str]:
    """算出能让 `import vools / actuscore / sigma` 成立的 PYTHONPATH 目录。

    只取**本进程实际在用**的那些包的位置（版本锁定：注入的就是当前解释器里
    正在跑的这一份，不做"另找一份"的隐式动作），因此不会引入第二份孪生引擎。
    """
    roots: List[str] = []
    try:
        import vools  # noqa: F401
        vools_file = getattr(sys.modules['vools'], '__file__', '') or ''
        if vools_file:
            roots.append(os.path.dirname(os.path.dirname(os.path.abspath(vools_file))))
    except Exception:                                    # noqa: BLE001
        pass
    # 本文件所在包的上三级 = 该 vools 子树的根（.../actus/vools/actus/scattered.py）
    here = os.path.dirname(os.path.abspath(__file__))                  # .../vools/actus
    subtree_root = os.path.dirname(here)                              # .../actus
    if os.path.isdir(subtree_root):
        roots.append(subtree_root)
    # engine/（actuscore 与 python -m actus 的落点）
    repo = os.environ.get('ACTUS_REPO_ROOT')
    if repo:
        eng = os.path.join(repo, 'engine')
        if os.path.isdir(eng):
            roots.append(eng)
    seen, out = set(), []
    for r in roots:
        rp = os.path.realpath(r)
        if rp not in seen and os.path.isdir(rp):
            seen.add(rp)
            out.append(rp)
    return out


def build_injection_env(base_env: Optional[dict] = None) -> Dict[str, str]:
    """C3：构造执行期环境（白名单注入 + 版本锁定），**不修改宿主环境**。

    返回的是新 dict，调用方决定何时/是否套用；这样"零散动作注入核心依赖"
    不会顺带把宿主 Python 的 import 拓扑改掉。
    """
    env = dict(base_env if base_env is not None else os.environ)
    roots = _core_injection_roots()
    parts = [p for p in (env.get('PYTHONPATH') or '').split(os.pathsep) if p]
    head = [r for r in roots if r not in parts]
    env['PYTHONPATH'] = os.pathsep.join(head + parts)
    env['ACTUS_SCATTERED'] = '1'          # 子进程可据此知道自己跑在零散模式
    env['ACTUS_INJECTED_CORE'] = ','.join(sorted(CORE_DEPENDENCY_WHITELIST))
    return env


def injection_report() -> Dict[str, Any]:
    """注入项 + 版本（docs/41 §C3「版本锁定」的可核验读数）。"""
    import importlib

    rep: Dict[str, Any] = {'roots': [r.replace(os.sep, '/') for r in _core_injection_roots()],
                           'injected': {}, 'unavailable': []}
    for alias, dotted in CORE_DEPENDENCY_WHITELIST.items():
        try:
            # 用 importlib 取**目标模块本身**：`__import__('vools.actus.sigma')`
            # 返回的是顶层 vools，据此报的 file/version 会是 vools 而非 sigma。
            mod = importlib.import_module(dotted)
        except Exception as exc:                        # noqa: BLE001
            rep['unavailable'].append({'name': alias, 'provider': dotted,
                                       'reason': f'{type(exc).__name__}: {exc}'})
            continue
        rep['injected'][alias] = {
            'provider': dotted,
            'version': getattr(mod, '__version__', None),
            'file': (getattr(mod, '__file__', '') or '').replace(os.sep, '/'),
        }
    return rep


def load_project_deps(root: str) -> Dict[str, Any]:
    """读零散动作根目录的 `project.actus.toml`（docs/41 §C3）。

    无文件 → 返回空声明（此时任何额外依赖都会被拒，见 check_declared_deps）。
    有文件但解析不了 → **显式抛错**：把"配置写坏了"读成"没依赖"，会静默放行
    未声明的依赖，正是 docs/35 要挡的那类降级。
    """
    path = os.path.join(os.path.abspath(root), PROJECT_DEPS_FILENAME)
    if not os.path.isfile(path):
        return {'_path': path.replace(os.sep, '/'), '_present': False}

    raw = open(path, encoding='utf-8').read()
    data: Dict[str, Any] = {}
    parser = None
    try:
        import tomllib                                  # py3.11+
        parser = 'tomllib'
        try:
            data = tomllib.loads(raw)
        except Exception as exc:                        # TOMLDecodeError
            raise ScatteredError(
                'action_invalid',
                f'{PROJECT_DEPS_FILENAME} 解析失败：{exc}',
                {'path': path.replace(os.sep, '/')}) from exc
    except ImportError:
        try:
            import tomli                                  # 第三方兜底
            parser = 'tomli'
            try:
                data = tomli.loads(raw)
            except Exception as exc:
                raise ScatteredError(
                    'action_invalid',
                    f'{PROJECT_DEPS_FILENAME} 解析失败：{exc}',
                    {'path': path.replace(os.sep, '/')}) from exc
        except ImportError:
            parser = 'fallback'
    if parser == 'fallback':
        # 极简解析：只支持 `key = ["a", "b"]` 与 `[table]` + `key = value` 的常见形态。
        # 解析不了的行**不猜**：直接报错，让作者改用受支持的写法或装 tomllib/tomli。
        data = _parse_toml_subset(raw, path)
    if not isinstance(data, dict):
        raise ScatteredError('action_invalid',
                             f'{PROJECT_DEPS_FILENAME} 顶层必须是 table',
                             {'path': path.replace(os.sep, '/')})
    out = {k: v for k, v in data.items() if k in _DECLARABLE_DEP_KEYS}
    out['_path'] = path.replace(os.sep, '/')
    out['_present'] = True
    out['_parser'] = parser
    out['_unknown_keys'] = sorted(k for k in data if k not in _DECLARABLE_DEP_KEYS)
    return out


def _parse_toml_subset(raw: str, path: str) -> Dict[str, Any]:
    """`project.actus.toml` 的最小可读子集（无 tomllib 时的确定性兜底）。"""
    out: Dict[str, Any] = {}
    table = out
    for i, line in enumerate(raw.splitlines(), 1):
        s = line.split('#', 1)[0].strip()
        if not s:
            continue
        if s.startswith('[') and s.endswith(']'):
            name = s[1:-1].strip()
            if not name:
                raise ScatteredError('action_invalid',
                                     f'{path}:{i} 空 table 名',
                                     {'path': path})
            table = out.setdefault(name, {})
            continue
        if '=' not in s:
            raise ScatteredError(
                'action_invalid',
                f'{path}:{i} 无法解析（需要 tomllib/tomli，或写成 key = "值"/key = ["值"]）',
                {'path': path, 'line': line})
        k, v = s.split('=', 1)
        k, v = k.strip(), v.strip()
        if v.startswith('[') and v.endswith(']'):
            items = [x.strip().strip('"').strip("'") for x in v[1:-1].split(',') if x.strip()]
            table[k] = items
        elif v.startswith('"') and v.endswith('"') or v.startswith("'") and v.endswith("'"):
            table[k] = v[1:-1]
        elif v.lower() in ('true', 'false'):
            table[k] = v.lower() == 'true'
        else:
            try:
                table[k] = int(v)
            except ValueError:
                raise ScatteredError('action_invalid',
                                     f'{path}:{i} 无法解析值 {v!r}',
                                     {'path': path, 'line': line})
    return out


def declared_dep_tokens(deps_doc: Dict[str, Any]) -> List[str]:
    """把声明式依赖摊平成 token 列表（`pip:requests` / `npm:x` / `system:git`）。"""
    tokens: List[str] = []
    for key in _DECLARABLE_DEP_KEYS:
        val = deps_doc.get(key)
        if val is None:
            continue
        items = val if isinstance(val, list) else [val]
        for it in items:
            if isinstance(it, str) and it.strip():
                tokens.append(f'{key}:{it.strip()}')
    return tokens


def declared_env_names(deps_doc: Dict[str, Any]) -> List[str]:
    val = deps_doc.get('env')
    if val is None:
        return []
    items = val if isinstance(val, list) else [val]
    return [str(x).strip() for x in items if str(x).strip()]


# ── C2.2：依赖落点校验（相对路径 + id 两种形式）──────────────────────────

def _split_deps(raw_deps: List[str]) -> Tuple[List[str], List[str], List[str], List[str]]:
    """把 deps 分成 (路径引用, 声明式依赖, 动作 id 引用, 核心白名单)。

    路径引用会被解析成实际文件并检查是否仍在授权根内；这一步在**校验阶段**
    就做完 —— 留到执行阶段才判，错误现场已经离配置很远了。

    `pip:`/`npm:`/`system:`/`env:` 这类是**声明式依赖**（要 project.actus.toml 背书），
    不能混进动作 id 桶 —— 混进去会被判成"依赖的动作 id 不在动作库里"，
    报错方向整个错掉（实测踩到过）。
    """
    path_deps: List[str] = []
    declared_deps: List[str] = []
    id_deps: List[str] = []
    core: List[str] = []
    for d in raw_deps or []:
        if not isinstance(d, str) or not d.strip():
            continue
        tok = d.strip()
        if tok.startswith(_PATH_DEP_PREFIXES):
            path_deps.append(tok)
        elif tok in CORE_DEPENDENCY_WHITELIST:
            core.append(tok)
        elif ':' in tok and tok.split(':', 1)[0] in _DECLARABLE_DEP_KEYS:
            declared_deps.append(tok)
        elif ':' in tok and tok.split(':', 1)[0] in _KNOWN_ENGINE_DEP_PREFIXES:
            # 引擎已识别的其它前缀（lang:/mcp:/action:）按其原有链路处理，不在此另判
            id_deps.append(tok)
        else:
            id_deps.append(tok)
    return path_deps, declared_deps, id_deps, core


def _pick_executor():
    """选执行器：优先 actuscore（CLI/MCP 跑的那一份），退回本包的 executor。

    两份 executor 存在已知差异（actuscore 侧多 `vault://` 解析与 `entry_no_output`
    契约），所以零散动作**跟着调用方的引擎走**：从 Actus 仓调用就走 actuscore，
    只有 vools 独立安装时才退回 vools 那份。这里不 import actuscore 顶层，
    否则纯 vools 环境会直接 ImportError。
    """
    try:
        import actuscore.executor as _ac
        if getattr(_ac, 'execute', None) is not None:
            return _ac.execute
    except Exception:                                    # noqa: BLE001
        pass
    from .executor import execute as _vx
    return _vx


def _resolve_path_dep(token: str, action_dir: str, root: str) -> Dict[str, Any]:
    """解析一条相对路径依赖，校验存在性与授权根边界。"""
    target = os.path.normpath(os.path.join(action_dir, token))
    info: Dict[str, Any] = {'ref': token, 'target': target.replace(os.sep, '/')}
    _assert_inside(root, target, f'依赖引用 {token}')
    base = os.path.basename(target.rstrip('\\/'))
    if base.endswith(SCATTERED_DIR_SUFFIX):
        entry = os.path.join(target, ENTRY_FILENAME)
        if not os.path.isfile(entry):
            raise ScatteredError(
                'dependency_missing',
                f'依赖目录缺少入口 {ENTRY_FILENAME}：{token}',
                {'ref': token, 'resolved': target.replace(os.sep, '/')})
        info['kind'] = 'dir'
        info['entry'] = entry.replace(os.sep, '/')
    elif base.endswith(SCATTERED_FILE_SUFFIX):
        if not os.path.isfile(target):
            raise ScatteredError('dependency_missing',
                                 f'依赖文件不存在：{token}',
                                 {'ref': token, 'resolved': target.replace(os.sep, '/')})
        info['kind'] = 'file'
    else:
        raise ScatteredError(
            'dependency_missing',
            f'路径依赖必须指向 {SCATTERED_FILE_SUFFIX} 文件或 {SCATTERED_DIR_SUFFIX} 目录：{token}',
            {'ref': token})
    return info


def _detect_path_cycle(edges: Dict[str, List[str]], start: str) -> Optional[List[str]]:
    """在路径依赖图上找一条回到起点的链（DFS 三色）。"""
    color: Dict[str, int] = {}
    stack: List[str] = []

    def dfs(node: str) -> Optional[List[str]]:
        color[node] = 1
        stack.append(node)
        for nxt in edges.get(node, []):
            c = color.get(nxt, 0)
            if c == 1:
                return stack[stack.index(nxt):] + [nxt]
            if c == 0:
                got = dfs(nxt)
                if got:
                    return got
        stack.pop()
        color[node] = 2
        return None

    return dfs(start)


def _collect_path_dep_graph(start_entry: str, root: str,
                            limit: int = 64) -> Dict[str, List[str]]:
    """从入口开始，沿相对路径依赖建图（用于无环判定）。

    limit 是硬上限：零散动作可能互相引用成一个很大的图，但判环只需要有限深度；
    超过上限就明确报错，而不是无限递归。
    """
    from .model import parse_cfg_from_file

    edges: Dict[str, List[str]] = {}
    queue = [os.path.abspath(start_entry)]
    seen = set()
    while queue:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        if len(seen) > limit:
            raise ScatteredError(
                'action_invalid',
                f'路径依赖展开超过 {limit} 个动作，疑似环或过深引用链',
                {'entry': start_entry.replace(os.sep, '/'), 'seen': len(seen)})
        edges.setdefault(cur, [])
        try:
            action = parse_cfg_from_file(cur)
        except Exception:                                # noqa: BLE001
            continue                                     # 解析失败留给动作自身的校验报
        raw = list(action.meta.get('deps') or [])
        path_deps, _decl, _ids, _core = _split_deps(raw)
        for tok in path_deps:
            info = _resolve_path_dep(tok, os.path.dirname(cur), root)
            nxt = info.get('entry') or info['target']
            edges[cur].append(nxt)
            queue.append(nxt)
    return edges


# ── C2.2/C2.3：check ───────────────────────────────────────────────────

def _apply_scattered_defaults(action, sc: ScatteredAction) -> None:
    """C1：补齐零散动作缺省值，并记录**补了什么**（便于调用方知情）。"""
    meta = action.meta
    if not meta.get('visibility'):
        meta['visibility'] = 'private'
        sc.defaults_applied['visibility'] = 'private'
    if not meta.get('trust'):
        meta['trust'] = 'audit'
        sc.defaults_applied['trust'] = 'audit'


def check_scattered(path: str, authorized_root: Optional[str] = None,
                    with_deps: bool = True) -> Dict[str, Any]:
    """C2.2 + C2.3：解析 + 规范校验 +（可选）路径依赖检查。

    只校验不执行（docs/41 §C2 的 `actus check`）。返回结构化报告；
    `valid=False` 时 `errors` 逐项列出，不用一句"校验失败"盖掉细节。
    """
    report: Dict[str, Any] = {'path': path, 'valid': False, 'errors': [],
                              'warnings': [], 'deps': {}, 'form': None,
                              'defaults_applied': {}, 'injection': injection_report()}
    try:
        sc = resolve_scattered(path, authorized_root)
    except ScatteredError as exc:
        report['errors'].append({'code': exc.code, 'message': exc.message,
                                 'details': exc.details})
        return report
    report['form'] = sc.as_dict()
    report['authorized_root'] = sc.root.replace(os.sep, '/')

    from .model import parse_cfg_from_file
    from .validate import validate_action

    try:
        action = parse_cfg_from_file(sc.path)
    except Exception as exc:                              # noqa: BLE001
        report['errors'].append({'code': getattr(exc, 'code', 'action_invalid'),
                                 'message': getattr(exc, 'message', str(exc)),
                                 'details': getattr(exc, 'details', {})})
        return report

    _apply_scattered_defaults(action, sc)
    report['defaults_applied'] = dict(sc.defaults_applied)
    report['action'] = {'id': action.meta.get('id'),
                        'trust': action.meta.get('trust'),
                        'visibility': action.meta.get('visibility'),
                        'entry': action.meta.get('entry')}

    errs = validate_action(action)
    if errs:
        report['errors'].append({'code': 'action_invalid',
                                 'message': f'规范校验失败：{len(errs)} 项',
                                 'details': {'errors': errs}})

    raw_deps = list(action.meta.get('deps') or [])
    path_deps, declared_deps, id_deps, core_deps = _split_deps(raw_deps)
    action_dir = os.path.dirname(sc.path)

    # C3：额外依赖（pip/npm/system/env）必须在 project.actus.toml 显式声明，未声明即拒。
    deps_doc = {}
    try:
        deps_doc = load_project_deps(sc.root)
    except ScatteredError as exc:
        report['errors'].append({'code': exc.code, 'message': exc.message,
                                 'details': exc.details})
    declared = set(declared_dep_tokens(deps_doc))
    undeclared = [d for d in declared_deps if d not in declared]
    if undeclared:
        report['errors'].append({
            'code': 'dependency_missing',
            'message': ('以下依赖未在 %s 声明：%s（docs/41 §C3 / docs/35：'
                        '未声明即拒，不做隐式安装）'
                        % (PROJECT_DEPS_FILENAME, ', '.join(undeclared))),
            'details': {'undeclared': undeclared,
                        'declared': sorted(declared),
                        'config': deps_doc.get('_path'),
                        'hint': '在 %s 里写 pip = ["..."] / npm = ["..."] / '
                                'system = ["..."]' % PROJECT_DEPS_FILENAME}})
    report['deps']['declared'] = sorted(declared)
    report['deps']['declared_by_action'] = declared_deps
    report['deps']['project_config'] = deps_doc.get('_path')
    report['deps']['project_config_present'] = bool(deps_doc.get('_present'))
    report['deps']['declared_env'] = declared_env_names(deps_doc)

    resolved_paths = []
    for tok in path_deps:
        try:
            resolved_paths.append(_resolve_path_dep(tok, action_dir, sc.root))
        except ScatteredError as exc:
            report['errors'].append({'code': exc.code, 'message': exc.message,
                                     'details': exc.details})
    report['deps']['path'] = resolved_paths
    report['deps']['action_ids'] = id_deps
    report['deps']['core_injected'] = core_deps

    # id 形式依赖：交给仓库依赖图判存在性与无环（不在授权根内解析）
    if id_deps:
        try:
            from .indexer import scan_actions
            from .validate import validate_graph
            known = scan_actions(None, validate=False)
            sub = {aid: a for aid, a in known.items()
                   if aid == action.meta.get('id') or aid in id_deps}
            missing = [d for d in id_deps if d not in known]
            if missing:
                report['errors'].append({
                    'code': 'dependency_missing',
                    'message': '依赖的动作 id 不在动作库里：%s' % ', '.join(missing),
                    'details': {'missing': missing}})
            elif sub:
                validate_graph(sub)
        except Exception as exc:                          # noqa: BLE001
            report['errors'].append({'code': getattr(exc, 'code', 'dependency_missing'),
                                     'message': getattr(exc, 'message', str(exc)),
                                     'details': getattr(exc, 'details', {})})

    # 路径引用也要判环（id 侧由 validate_graph 判）
    if with_deps and resolved_paths:
        try:
            edges = _collect_path_dep_graph(sc.path, sc.root)
            cycle = _detect_path_cycle(edges, os.path.abspath(sc.path))
            if cycle:
                report['errors'].append({
                    'code': 'dependency_cycle',
                    'message': '零散动作路径依赖成环',
                    'details': {'cycle': [c.replace(os.sep, '/') for c in cycle]}})
        except ScatteredError as exc:
            report['errors'].append({'code': exc.code, 'message': exc.message,
                                     'details': exc.details})

    if not sc.root == os.path.dirname(sc.path) and sc.kind == 'file':
        report['warnings'].append(
            '授权根不是动作所在目录：相对依赖只能引用该根内的文件')

    report['valid'] = not report['errors']
    return report


# ── C2.4：run（复用正常生命周期）───────────────────────────────────────

def run_scattered(path: str, params: Optional[dict] = None, confirmed: bool = False,
                  authorized_root: Optional[str] = None,
                  meta_dir: Optional[str] = None,
                  artifacts_dir: Optional[str] = None,
                  check_first: bool = True) -> Dict[str, Any]:
    """跑一个零散动作：先按 C2.2 校验，再走**引擎正常执行链**。

    `check_first=True`（默认）时校验不过就直接返回，
    不让"没校验的动作"溜进执行阶段；置 False 只给明确知道自己在做什么的调用方用。

    执行经 `actuscore.executor.execute`，因此 trust/sandbox/Ω 门禁/留痕/
    并发槽位这套策略一条都不少 —— 零散化只改"动作从哪来"，不改"动作怎么跑"。
    """
    params = params if params is not None else {}
    chk = check_scattered(path, authorized_root)
    if check_first and not chk['valid']:
        return {'status': 'failed', 'data': None,
                'error': {'code': 'action_invalid',
                          'message': '零散动作校验未通过，未进入执行',
                          'details': {'errors': chk['errors'],
                                      'form': chk.get('form'),
                                      'defaults_applied': chk.get('defaults_applied', {})}},
                'scattered': chk}

    if not chk.get('form'):
        return {'status': 'failed', 'data': None,
                'error': {'code': 'action_not_found',
                          'message': '无法解析零散动作路径',
                          'details': {'errors': chk['errors']}},
                'scattered': chk}

    sc = resolve_scattered(path, authorized_root)
    action_id = (chk.get('action') or {}).get('id')
    if not action_id:
        return {'status': 'failed', 'data': None,
                'error': {'code': 'action_invalid',
                          'message': '零散动作缺少 id，无法进入执行链',
                          'details': {'path': sc.path}},
                'scattered': chk}

    # 执行链按 id + actions_dir 解析动作：把授权根当动作目录传进去，
    # 这样 scan_actions/get_action 能找到这个"不在 actions/ 下"的动作。
    executor = _pick_executor()

    # 关键：把**已补缺省值的那份 Action 对象**一起递进去（preparsed_action）。
    # 若让 execute 自己从磁盘 re-parse，C1 的缺省值（trust=audit / visibility=private）
    # 会在校验前被丢掉，动作直接报"trust 缺失"—— 缺省值等于没生效。
    from .model import parse_cfg_from_file
    try:
        action_obj = parse_cfg_from_file(sc.path)
        _apply_scattered_defaults(action_obj, sc)
    except Exception:                                    # noqa: BLE001
        action_obj = None                                # 交给 execute 自己报解析错

    exec_dirs = None
    exec_meta = meta_dir
    if sc.kind == 'dir':
        # 目录形态：授权根就是动作目录本身，入口是 main.actus.md；
        # executor 按 `*.actus.md` 递归扫描，main.actus.md 满足后缀。
        exec_dirs = sc.root
    else:
        exec_dirs = os.path.dirname(sc.path)

    # 核心依赖注入：只在本次执行前后生效，跑完还原宿主环境（C3「不污染宿主」）
    injected = build_injection_env()
    touched = {k: os.environ.get(k) for k in ('PYTHONPATH', 'ACTUS_SCATTERED',
                                              'ACTUS_INJECTED_CORE')}
    try:
        for k in ('PYTHONPATH', 'ACTUS_SCATTERED', 'ACTUS_INJECTED_CORE'):
            os.environ[k] = injected[k]
        kwargs = dict(confirmed=confirmed, meta_dir=exec_meta,
                      actions_dir=exec_dirs, artifacts_dir=artifacts_dir)
        if action_obj is not None:
            kwargs['preparsed_action'] = action_obj
        result = executor(action_id, params, **kwargs)
    finally:
        for k, v in touched.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    result['scattered'] = {
        'form': sc.as_dict(),
        'defaults_applied': chk.get('defaults_applied', {}),
        'deps': chk.get('deps', {}),
        'injection': chk.get('injection', {}),
    }
    return result
