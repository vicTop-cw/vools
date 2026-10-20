"""curator.py —— 社区策展模块（docs/03 §5.4，借鉴 HACS + Quicker 动作单）。

三个策展面：
1. default_repos：默认优质仓列表（HACS 式，存 ~/.actus/config/default_repos.json）；
2. collections：用户策展集合（Quicker 动作单，JSON 文件可 Git 分享）；
3. featured：从真实使用指标计算的精选动作（非人工榜单，杜绝虚报）。

设计原则：
- 策展是**推荐**不是**门槛**（避免 Zapier 式封闭审核——杀社区贡献）；
- best-effort：文件读写失败不抛出，返回空/False；
- 集合格式与 .actus.registry.json 同目录存放，复用 publisher/installer 管线分享。
"""

__all__ = [
    'add_default_repo', 'remove_default_repo', 'list_default_repos',
    'create_collection', 'load_collection', 'list_collections',
    'share_collection', 'get_featured',
]

import json
import os
from typing import Dict, List, Optional

_CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.actus', 'config')
_DEFAULT_REPOS_FILE = os.path.join(_CONFIG_DIR, 'default_repos.json')
_COLLECTIONS_DIR = os.path.join(_CONFIG_DIR, 'collections')


def _ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)


def _read_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path: str, data) -> bool:
    try:
        _ensure_dir(path)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


# ═══════════════════════════════════════════════════════════════
# default_repos（HACS 式默认仓）
# ═══════════════════════════════════════════════════════════════

def add_default_repo(repo_url: str, name: str = '') -> bool:
    """追加默认仓（幂等：已存在返回 False，不重复添加）。"""
    repos = _read_json(_DEFAULT_REPOS_FILE, [])
    if not isinstance(repos, list):
        repos = []
    if any(r.get('url') == repo_url for r in repos):
        return False
    repos.append({'url': repo_url, 'name': name or repo_url.rsplit('/', 1)[-1]})
    return _write_json(_DEFAULT_REPOS_FILE, repos)


def remove_default_repo(repo_url: str) -> bool:
    """移除默认仓；不存在返回 False。"""
    repos = _read_json(_DEFAULT_REPOS_FILE, [])
    if not isinstance(repos, list):
        return False
    filtered = [r for r in repos if r.get('url') != repo_url]
    if len(filtered) == len(repos):
        return False
    return _write_json(_DEFAULT_REPOS_FILE, filtered)


def list_default_repos() -> List[dict]:
    """列出默认仓（缺文件返回空列表）。"""
    repos = _read_json(_DEFAULT_REPOS_FILE, [])
    return repos if isinstance(repos, list) else []


# ═══════════════════════════════════════════════════════════════
# collections（Quicker 动作单）
# ═══════════════════════════════════════════════════════════════

def _collection_path(name: str) -> str:
    safe = ''.join(c for c in (name or '') if c.isalnum() or c in '-_.')
    return os.path.join(_COLLECTIONS_DIR, f'{safe or "unnamed"}.json')


def create_collection(name: str, action_ids: List[str],
                      description: str = '') -> bool:
    """创建/覆盖本地集合（幂等：同名覆盖，含创建时间与描述）。"""
    from datetime import datetime, timezone, timedelta
    data = {
        'name': name,
        'description': description,
        'action_ids': [a for a in (action_ids or []) if a],
        'created_at': datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),
    }
    return _write_json(_collection_path(name), data)


def load_collection(name: str) -> Optional[dict]:
    """读取集合；不存在返回 None。"""
    return _read_json(_collection_path(name), None)


def list_collections() -> List[dict]:
    """列出全部本地集合（含 name/action_count/created_at 摘要）。"""
    out: List[dict] = []
    if not os.path.isdir(_COLLECTIONS_DIR):
        return out
    for fn in sorted(os.listdir(_COLLECTIONS_DIR)):
        if not fn.endswith('.json'):
            continue
        data = _read_json(os.path.join(_COLLECTIONS_DIR, fn), None)
        if not isinstance(data, dict):
            continue
        out.append({
            'name': data.get('name') or fn[:-5],
            'action_count': len(data.get('action_ids') or []),
            'created_at': data.get('created_at', ''),
            'description': data.get('description', ''),
        })
    return out


def share_collection(name: str, target_dir: str) -> Optional[str]:
    """把集合复制到目标目录（Git 仓分享用，复用 publisher 管线的分享形态）。

    Returns:
        写出的文件路径；集合不存在或写出失败返回 None。
    """
    data = load_collection(name)
    if data is None:
        return None
    target = os.path.join(target_dir, os.path.basename(_collection_path(name)))
    try:
        _ensure_dir(target)
        with open(target, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return target
    except OSError:
        return None


# ═══════════════════════════════════════════════════════════════
# featured（从真实使用指标计算的精选动作）
# ═══════════════════════════════════════════════════════════════

def get_featured(limit: int = 10, meta_dir: Optional[str] = None) -> List[dict]:
    """精选动作 = popular ∩ trending（docs/03 §5.4）。

    两条腿走路：popular 保证"被广泛使用"，trending 保证"近期活跃"——
    避免纯安装量榜单把死动作顶在前面。无指标数据时返回空列表（不伪造）。
    """
    from .calllog import popular_actions, trending_actions

    popular = popular_actions(limit=max(limit * 2, 10), meta_dir=meta_dir)
    trending = {t['action_id']: t for t in trending_actions(limit=max(limit * 2, 10),
                                                            meta_dir=meta_dir)}
    if not popular:
        return []

    scored = []
    for p in popular:
        aid = p['action_id']
        t = trending.get(aid)
        growth = t['growth'] if t else 0.0
        # 综合分：执行计数为主，增长率为辅（对数压缩防头部垄断）
        import math
        score = math.log1p(p['count']) * 0.7 + growth * 0.3
        scored.append({
            'action_id': aid,
            'count': p['count'],
            'growth': growth,
            'success_rate': p['success_rate'],
            'score': round(score, 4),
        })
    scored.sort(key=lambda r: -r['score'])
    return scored[:limit]
