"""动作发现与索引（docs/08 §1/§2）：扫描 actions/ → 校验 → _meta/actions.index.json。"""

__all__ = ['scan_actions', 'build_index', 'load_index', 'get_action']

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict

from .errors import ActionError
from .model import parse_cfg_from_file, Action
from .validate import validate_action, validate_graph

_TZ = timezone(timedelta(hours=8))
ACTION_SUFFIX = '.actus.md'


def _repo_root() -> str:
    """仓库根。可被 ACTUS_REPO_ROOT 环境变量覆盖（测试/多仓库场景）。"""
    env = os.environ.get('ACTUS_REPO_ROOT')
    if env:
        return env
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def scan_actions(actions_dir: str = None, validate: bool = True) -> Dict[str, Action]:
    """递归扫描 actions/ 下所有 .actus.md，解析 #!cfg 生成动作清单。

    - 文件后缀必须为 .actus.md（docs/08 §1）；
    - id 重复或解析失败的动作记入 problems（附着在函数属性上，供索引展示），
      不中断其余动作的发现；
    - validate=True 时逐个做契约校验（失败标记 invalid 而非中断扫描）。
    """
    root = actions_dir or os.path.join(_repo_root(), 'actions')
    actions: Dict[str, Action] = {}
    problems = {}

    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            if not fn.endswith(ACTION_SUFFIX):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, os.path.dirname(root)).replace(os.sep, '/')
            try:
                action = parse_cfg_from_file(full)
            except ActionError as e:
                problems[rel] = f'parse: {e.message}'
                continue
            aid = action.meta.get('id')
            if not aid:
                problems[rel] = 'parse: #!cfg 缺少 id'
                continue
            if aid in actions:
                problems[rel] = f'conflict: id 与 {actions[aid].path} 重复'
                continue
            actions[aid] = action

    if validate:
        for aid, action in actions.items():
            errs = validate_action(action)
            if errs:
                action.meta['_validation_errors'] = errs

    scan_actions.problems = problems  # type: ignore[attr-defined]
    return actions


def build_index(actions_dir: str = None, meta_dir: str = None) -> dict:
    """扫描 + 全量校验 + 依赖图校验 + 索引落盘 _meta/actions.index.json。

    依赖图存在环时：索引照常落盘，所有动作标记 invalid 并附错误
    （docs/05 §5.1：不合规动作从 MCP tools 下架，不得静默执行）。
    """
    root = actions_dir or os.path.join(_repo_root(), 'actions')
    meta = meta_dir or os.path.join(_repo_root(), '_meta')
    actions = scan_actions(root, validate=False)

    graph_error = None
    try:
        valid_actions = {aid: a for aid, a in actions.items()
                         if not validate_action(a)}
        validate_graph(valid_actions)
    except ActionError as e:
        graph_error = e.to_payload()

    entries = {}
    problems = dict(getattr(scan_actions, 'problems', {}))
    for aid, action in actions.items():
        errs = action.meta.get('_validation_errors') or []
        brief = action.brief()
        brief['status'] = 'invalid' if errs else 'valid'
        if errs:
            brief['errors'] = errs
        entries[aid] = brief

    for rel, why in problems.items():
        entries[f'_invalid:{rel}'] = {'path': rel, 'status': 'invalid', 'errors': [why]}

    if graph_error:
        for e in entries.values():
            e['status'] = 'invalid'
            e.setdefault('errors', []).append(
                f"dependency graph: {graph_error['message']}")

    index = {
        'schema_version': '1.0.0',
        'generated_at': datetime.now(_TZ).isoformat(timespec='seconds'),
        'actions': entries,
    }
    if graph_error:
        index['dependency_graph'] = graph_error

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
