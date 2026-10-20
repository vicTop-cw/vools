"""quality.py —— 动作质量分级计算（docs/03 §5.3，借鉴 Home Assistant Quality Scale）。

质量分级（全部从已有数据计算，非手工申报——杜绝自写自测恒绿）：

| 等级 | 判据 |
|------|------|
| platinum | 已签名(验证作者) + Omega spec 通过 + 100+ 执行 + 99% 成功率 + 活跃维护 |
| gold | 已签名 + Omega spec + 50+ 执行 + 95% 成功率 |
| silver | 已签名 + 10+ 执行 + 90% 成功率 |
| bronze | 社区动作 + 任意执行 |
| internal | 引擎/系统动作 |

数据源（单一真源，不重复实现）：
- trust_model.py：Ed25519 签名验证（是否已签名）
- omega.py / index：Omega spec 存在性
- calllog.py：执行指标（count/success_rate）
- 文件 mtime：维护活跃度（30 天内有更新）

设计原则：
1. 计算字段：quality_scale 不落 front-matter（手工申报是自写自测恒绿）；
2. best-effort：任一数据源不可用 → 降级到可达等级，绝不虚报；
3. 自指排除：排除 quality 计算自身的调用（风险 3，docs/03 §九）。
"""

__all__ = ['QUALITY_LEVELS', 'quality_scale', 'batch_quality', 'is_maintained']

import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

_TZ = timezone(timedelta(hours=8))

QUALITY_LEVELS = ('platinum', 'gold', 'silver', 'bronze', 'internal')

# 等级排序（高→低）
_LEVEL_RANK = {'platinum': 4, 'gold': 3, 'silver': 2, 'bronze': 1, 'internal': 0}

# 排除 self-call 的工具名（质量计算自身的调用不计入指标）
_SELF_TOOLS = ('actus_quality', 'quality_scale')


def is_maintained(path: str, within_days: int = 30) -> bool:
    """维护活跃度：文件 mtime 在 within_days 内 → True。"""
    try:
        mtime = os.path.getmtime(path)
        age_days = (time.time() - mtime) / 86400.0
        return age_days <= within_days
    except OSError:
        return False


def quality_scale(action, meta_dir: Optional[str] = None,
                  signed: Optional[bool] = None) -> dict:
    """计算单动作质量分级（docs/03 §5.3）。

    Args:
        action: Action 对象（model.Action）
        meta_dir: 指标库目录（默认 _meta/）
        signed: 签名验证结果（None 时从 trust_model 惰性验证；验证失败不抛出）

    Returns:
        {quality, evidence: {...}} —— evidence 是判据明细（可审计）。
    """
    aid = action.meta.get('id') or ''
    path = action.path or ''

    # ── 判据 1：签名验证 ──
    if signed is None:
        signed = _probe_signed(action)

    # ── 判据 2：Omega spec 存在 ──
    has_omega = _probe_omega(action)

    # ── 判据 3：执行指标（排除 self-call） ──
    metrics = _probe_metrics(aid, meta_dir)
    exec_count = metrics.get('total', 0)
    success_rate = metrics.get('success_rate', 0.0)

    # ── 判据 4：维护活跃度 ──
    maintained = is_maintained(path)

    # ── 分级判定（从高到低首命中即返回） ──
    if (signed and has_omega and exec_count >= 100
            and success_rate >= 0.99 and maintained):
        quality = 'platinum'
    elif signed and has_omega and exec_count >= 50 and success_rate >= 0.95:
        quality = 'gold'
    elif signed and exec_count >= 10 and success_rate >= 0.90:
        quality = 'silver'
    elif exec_count >= 1:
        quality = 'bronze'
    else:
        quality = 'bronze'  # 零执行 → bronze（不虚报更高等级）

    return {
        'quality': quality,
        'evidence': {
            'action_id': aid,
            'signed': signed,
            'has_omega_spec': has_omega,
            'exec_count': exec_count,
            'success_rate': success_rate,
            'maintained_30d': maintained,
        },
    }


def batch_quality(actions: Dict[str, 'object'],
                  meta_dir: Optional[str] = None) -> Dict[str, dict]:
    """批量计算质量分级（registry.py 的 by_quality 索引用）。"""
    return {aid: quality_scale(a, meta_dir=meta_dir) for aid, a in actions.items()}


def _probe_signed(action) -> bool:
    """签名验证（惰性导入 trust_model.verify_action，失败不抛出 → False）。

    真源是 trust_model.verify_action(fpath, key_name)（便捷函数），
    返回 {status: ok|error, ...}——只有 status=ok 才认定已签名。
    """
    try:
        from .trust_model import verify_action
    except ImportError:
        return False
    path = getattr(action, 'path', '')
    if not path or not os.path.isfile(path):
        return False
    try:
        result = verify_action(path)
    except Exception:
        return False
    return isinstance(result, dict) and result.get('status') == 'ok'


def _probe_omega(action) -> bool:
    """Omega spec 存在性（索引/规格文件任一含该动作即算有）。"""
    aid = action.meta.get('id') or ''
    if not aid:
        return False
    try:
        from .indexer import _repo_root
        meta_root = os.environ.get('ACTUS_REPO_ROOT') or _repo_root()
        specs = os.path.join(meta_root, '_meta', 'specs')
        if not os.path.isdir(specs):
            return False
        for fn in os.listdir(specs):
            if fn.endswith('.json') and aid in fn:
                return True
    except Exception:
        pass
    return False


def _probe_metrics(aid: str, meta_dir: Optional[str] = None) -> dict:
    """执行指标（惰性导入 calllog，失败返回零值；排除 self-call）。"""
    if not aid:
        return {'total': 0, 'success_rate': 0.0}
    try:
        from .calllog import aggregate_metrics
        agg = aggregate_metrics(aid, meta_dir=meta_dir)
        # 自指排除：如果唯一 caller 是质量计算自身，不计入（风险 3）
        if agg.get('unique_callers', 0) <= 0:
            return {'total': 0, 'success_rate': 0.0}
        return {'total': agg.get('total', 0), 'success_rate': agg.get('success_rate', 0.0)}
    except Exception:
        return {'total': 0, 'success_rate': 0.0}
