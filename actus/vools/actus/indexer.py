"""动作发现与索引（docs/08 §1/§2）：扫描 actions/ → 校验 → _meta/actions.index.json。

分类体系 v2.0（docs/03 §2.6）：索引含 by_kind/by_purpose/by_industry 反向索引，
filter_by_dimension 按维度过滤。
"""

__all__ = ['scan_actions', 'build_index', 'load_index', 'get_action',
           'filter_by_dimension', 'action_roots']

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List

from .errors import ActionError
from .model import parse_cfg_from_file, Action
from .validate import (
    validate_action, validate_graph, analyze_graph,
    resolve_test_binding, governance_notices,
)
from .constants import is_testish_id, is_action_file, ACTION_SUFFIXES

_TZ = timezone(timedelta(hours=8))
# 动作文件后缀真源在 constants（单一真源，docs/08 §1）：
# - .actus.md         旧格式（#!cfg JSON 元数据，形式 A）
# - .actus.schema.md  新格式（YAML front-matter 元数据，形式 B）
# 存量缺陷：此前只认 .actus.md，导致 basics/ 下 4 个 .actus.schema.md
# 从未进过引擎索引（扫不到 → 索引缺 → MCP 工具目录也没有）。
ACTION_SUFFIX = '.actus.md'  # 向后兼容别名（外部代码可能引用）

# 本模块内的判定别名（历史名 _is_action_file，保留防外部引用）
_is_action_file = is_action_file


def _inject_cached_path(rel: str, roots: List[str]) -> str:
    """缓存命中时恢复动作绝对路径（rel 形如 r0/actions/x.actus.md）。"""
    parts = rel.split('/')
    idx = parts[0][1:] if len(parts) > 1 and parts[0].startswith('r') else '0'
    root = roots[int(idx)] if idx.isdigit() and int(idx) < len(roots) else roots[0]
    return os.path.join(root, *parts[1:])


def _repo_root() -> str:
    """仓库根。可被 ACTUS_REPO_ROOT 环境变量覆盖（测试/多仓库场景）。"""
    env = os.environ.get('ACTUS_REPO_ROOT')
    if env:
        return env
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _seed_actions_dir() -> str:
    """包内种子动作目录（vools/actus/actions/，随 wheel 分发）。

    三层动作边界（docs/08 §1）：
      1. 基座自带种子动作：vools/actus/actions/（wheel 内，pip 装上就有）
      2. 用户项目动作：<ACTUS_REPO_ROOT>/actions/（Git 仓，优先）
      3. 社区仓动作：default_repos.json 指向的远程仓（curator 发现）
    缺目录（源码树异常形态）时返回空串，调用方跳过。
    """
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'actions')


def _action_roots(actions_dir: str = None) -> List[str]:
    """汇总全部动作扫描根（去重、保序：用户项目优先于包内种子）。"""
    roots: List[str] = []
    if actions_dir:
        roots.append(actions_dir)
    else:
        roots.append(os.path.join(_repo_root(), 'actions'))
        seed = _seed_actions_dir()
        if os.path.isdir(seed) and seed not in roots:
            roots.append(seed)
    # 去重保序
    seen = set()
    out = []
    for r in roots:
        norm = os.path.normpath(r)
        if norm not in seen:
            seen.add(norm)
            out.append(r)
    return out


# 公开别名（外部/测试查询扫描根用）
action_roots = _action_roots


_MTIMES_CACHE = 'actions.mtimes.json'  # mtime 缓存（_meta/ 下）

def scan_actions(actions_dir: str = None, validate: bool = True,
                 use_cache: bool = True) -> Dict[str, Action]:
    """递归扫描动作根下所有 .actus.md / .actus.schema.md，生成动作清单。

    - 文件后缀双轨：.actus.md（形式 A #!cfg JSON）+ .actus.schema.md（形式 B YAML）；
    - 扫描根多层：<ACTUS_REPO_ROOT>/actions/（用户项目）+ vools/actus/actions/（包内种子）；
    - id 重复或解析失败的动作记入 problems（附着在函数属性上，供索引展示），
      不中断其余动作的发现；
    - validate=True 时逐个做契约校验（失败标记 invalid 而非中断扫描）。
    - use_cache=True（默认）：基于文件 mtime 增量缓存，仅重解析变更文件，
      冷启动从 ~2.4s 降至 ~0.3s（首次后）。
    """
    roots = _action_roots(actions_dir)
    actions: Dict[str, Action] = {}
    problems = {}

    # ── 加载 mtime 缓存 ──
    mtimes_cache: Dict[str, float] = {}
    if use_cache:
        meta_dir = os.path.join(_repo_root(), '_meta')
        cache_path = os.path.join(meta_dir, _MTIMES_CACHE)
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                mtimes_cache = json.load(f)
        except (OSError, ValueError):
            pass

    new_mtimes: Dict[str, float] = {}
    cached_actions: Dict[str, Action] = {}
    changed_files = []

    for root_idx, root in enumerate(roots):
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in sorted(filenames):
                if not _is_action_file(fn):
                    continue
                full = os.path.join(dirpath, fn)
                # rel 带 root 序号前缀，保证多扫描根下不碰撞
                # （旧实现用 dirname(root) 相对化，两个 actions/ 根会产生
                #  同名 'actions/...' 前缀，缓存与 conflict 判定互相污染）
                rel = f'r{root_idx}/' + os.path.relpath(full, root).replace(os.sep, '/')
                try:
                    mtime = os.path.getmtime(full)
                except OSError:
                    continue
                new_mtimes[rel] = mtime

                # 缓存命中：mtime 未变 → 跳过解析
                if use_cache and rel in mtimes_cache and mtimes_cache[rel] == mtime:
                    try:
                        action = parse_cfg_from_file(full)
                        cached_actions[rel] = action
                        continue
                    except Exception:
                        pass  # 缓存损坏，重新解析

                # 解析（新文件或变更文件）
                try:
                    action = parse_cfg_from_file(full)
                except ActionError as e:
                    # `.demo.` 文档页是 kind: demo 的非可执行教学资产
                    # （对应主动作在 xxx.actus.schema.md），无 #!cfg 块属正常，
                    # 不按无效动作上报。
                    if '.demo.' in fn:
                        continue
                    problems[rel] = f'parse: {e.message}'
                    continue
                aid = action.meta.get('id')
                if not aid:
                    problems[rel] = 'parse: #!cfg 缺少 id'
                    continue
                if aid in actions:
                    problems[rel] = f'conflict: id 与 {actions[aid].path} 重复'
                    continue
                action.meta['_path'] = full   # 供自包含/测试绑定定位（docs/47）
                actions[aid] = action
                changed_files.append(rel)

    # 合并缓存命中
    for rel, action in cached_actions.items():
        aid = action.meta.get('id')
        if aid and aid not in actions:
            action.meta['_path'] = _inject_cached_path(rel, roots)
            actions[aid] = action

    # ── 保存 mtime 缓存 ──
    if use_cache and new_mtimes:
        meta_dir = os.path.join(_repo_root(), '_meta')
        cache_path = os.path.join(meta_dir, _MTIMES_CACHE)
        try:
            os.makedirs(meta_dir, exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(new_mtimes, f)
        except OSError:
            pass

    if validate:
        for aid, action in actions.items():
            errs = validate_action(action)
            if errs:
                action.meta['_validation_errors'] = errs

    scan_actions.problems = problems  # type: ignore[attr-defined]
    scan_actions._changed = changed_files  # type: ignore[attr-defined]
    return actions


def build_index(actions_dir: str = None, meta_dir: str = None) -> dict:
    """扫描 + 全量校验 + 依赖图校验 + 索引落盘 _meta/actions.index.json。

    扫描默认走全部动作根（用户项目 + 包内种子，见 _action_roots）；
    显式传 actions_dir 时只扫该目录（测试/单仓场景）。

    依赖图存在环时：索引照常落盘，所有动作标记 invalid 并附错误
    （docs/05 §5.1：不合规动作从 MCP tools 下架，不得静默执行）。
    """
    meta = meta_dir or os.path.join(_repo_root(), '_meta')
    actions = scan_actions(actions_dir, validate=False)

    # 依赖图按节点分析：只标记真正受坏边/环影响的动作（属主 + 其下游锥），
    # 不再「一条坏依赖连坐整个动作市场」（历史上 validate_graph 首错即抛后
    # 把全部 entries 标 invalid，导致上百个无关动作从 MCP / LLM 目录下架）。
    valid_actions = {aid: a for aid, a in actions.items()
                     if not validate_action(a)}
    graph_issues = analyze_graph(valid_actions)

    entries = {}
    problems = dict(getattr(scan_actions, 'problems', {}))
    for aid, action in actions.items():
        errs = list(action.meta.get('_validation_errors') or [])
        issue = graph_issues.get(aid)
        if issue is not None:
            errs.append(f"dependency graph: {issue['message']}")
        brief = action.brief()
        brief['status'] = 'invalid' if errs else 'valid'
        if errs:
            brief['errors'] = errs

        # ── 资产化治理标注（docs/47 §7，future_plan §3 落地）────────
        # 1) 测试味 id 不进资产池（kind=demo/alias/template 豁免）：
        #    夹具/演示动作仍可被 validate 校验（不破坏引擎测试），
        #    但资产池消费方（MCP/curator/索引检索）据此过滤。
        kind = str(brief.get('kind') or 'exec').lower()
        if is_testish_id(aid) and kind not in ('demo', 'alias', 'template'):
            brief['asset_pool'] = 'excluded'
            brief['asset_pool_reason'] = (
                'testish_id: 含 test/generated/foo/example 等测试味片段，'
                '非资产池正式资产（docs/47 §3.4）')
        else:
            brief['asset_pool'] = 'included'

        # 2) trust↔测试绑定：verified / unverified / n-a
        trust = str(action.meta.get('trust') or '').lower()
        if kind in ('demo', 'template', 'alias', 'doc', 'link') or trust == 'sandbox':
            # sandbox 信任级动作（演示性/隔离性）不要求测试绑定
            brief['verification'] = 'n-a'
            if trust == 'sandbox':
                brief['verification_reason'] = 'trust=sandbox 豁免测试绑定'
        else:
            bound, refs = resolve_test_binding(action)
            brief['verification'] = 'verified' if bound else 'unverified'
            if refs:
                brief['test_refs'] = refs[:8]

        # 3) 治理警告（不判失败，随索引展示）
        notices = governance_notices(action.meta)
        if notices:
            brief['notices'] = notices

        entries[aid] = brief

    for rel, why in problems.items():
        entries[f'_invalid:{rel}'] = {'path': rel, 'status': 'invalid', 'errors': [why]}

    # ── 分类体系 v2.0：反向索引（docs/03 §2.6 索引扩展） ──
    # 多值字段归一后按值分组；无效动作也入组（标记 status），保证索引完整。
    by_kind: Dict[str, list] = {}
    by_purpose: Dict[str, list] = {}
    by_industry: Dict[str, list] = {}
    for aid, brief in entries.items():
        if aid.startswith('_invalid:'):
            continue
        kind = brief.get('kind') or 'exec'
        by_kind.setdefault(kind, []).append(aid)
        for p in (brief.get('purpose') or ['utility']):
            by_purpose.setdefault(p, []).append(aid)
        for ind in (brief.get('industry') or ['general']):
            by_industry.setdefault(ind, []).append(aid)

    index = {
        'schema_version': '2.0.0',
        'classification_version': '2.0',
        'generated_at': datetime.now(_TZ).isoformat(timespec='seconds'),
        'actions': entries,
        'by_kind': {k: sorted(v) for k, v in sorted(by_kind.items())},
        'by_purpose': {k: sorted(v) for k, v in sorted(by_purpose.items())},
        'by_industry': {k: sorted(v) for k, v in sorted(by_industry.items())},
    }
    if graph_issues:
        # 摘要保留，便于体检/排障；逐节点详情已在各 action.errors 里
        codes = sorted({v['code'] for v in graph_issues.values()})
        index['dependency_graph'] = {
            'code': 'dependency_issues',
            'codes': codes,
            'affected': sorted(graph_issues),
            'count': len(graph_issues),
        }

    os.makedirs(meta, exist_ok=True)
    with open(os.path.join(meta, 'actions.index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return index


def load_index(meta_dir: str = None) -> dict:
    """读取索引；不存在时先构建。"""
    meta = meta_dir or os.path.join(_repo_root(), '_meta')
    path = os.path.join(meta, 'actions.index.json')
    if not os.path.exists(path):
        return build_index(meta_dir=meta)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_action(action_id: str, actions_dir: str = None) -> Action:
    """按 id 取动作（实时解析文件，保证最新内容）；不存在抛 action_not_found。"""
    actions = scan_actions(actions_dir, validate=False)
    if action_id not in actions:
        raise ActionError('action_not_found', f'动作不存在: {action_id}',
                          {'known': sorted(actions.keys())})
    return actions[action_id]


def filter_by_dimension(dimension: str, value: str, meta_dir: str = None) -> list:
    """按分类维度过滤（docs/03 §2.6）。

    Args:
        dimension: "kind" | "purpose" | "industry"
        value: 维度值（如 "exec"、"transform"、"devops"）
        meta_dir: 索引目录（默认 _meta/）

    Returns:
        命中的动作 id 列表（已排序）；索引不存在时先构建。
        旧索引缺反向索引键时返回空列表（不报错，兼容旧格式）。
    """
    index = load_index(meta_dir=meta_dir)
    key = f'by_{dimension}'
    reverse = index.get(key) or {}
    return list(reverse.get(value) or [])
