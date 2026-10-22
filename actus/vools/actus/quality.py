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
    """维护活跃度：文件 mtime 在 within_days 内 → True。

    V-09（寻虫 2026-10-22）：只捕 OSError 时 is_maintained(None) 抛 TypeError，
    公开 API 的容错承诺落空——补 TypeError（None/非路径入参统一按"不可判"降级）。
    """
    try:
        mtime = os.path.getmtime(path)
        age_days = (time.time() - mtime) / 86400.0
        return age_days <= within_days
    except (OSError, TypeError):
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

    # ── V-07（寻虫 2026-10-22）：internal 等级此前是死代码——判定分支
    # 永不产出，filter_by_quality('internal') 恒空。引擎/系统动作（visibility
    # 声明 internal，或落在 actus 包内 actions/ 的种子路径）最先短路。 ──
    vis = str(action.meta.get('visibility') or '').strip().lower()
    if vis == 'internal':
        return {
            'quality': 'internal',
            'evidence': {'action_id': aid, 'signed': None,
                         'has_omega_spec': None, 'exec_count': None,
                         'success_rate': None, 'maintained_30d': None,
                         'reason': 'visibility=internal（引擎/系统动作）'},
        }

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
    """Omega spec 存在性——复用 omega._find_omega_spec 单一真源。

    V-06（寻虫 2026-10-22）：旧实现扫 `_meta/specs/*.json`——全仓没有任何
    写入方往那里放文件（omega spec 真源在 actions/*/omega/*.spec.json，
    见 omega._find_omega_spec），且 `aid in fn` 子串匹配让 'foo.bar' 被
    'foo.bar.baz.spec.json' 冒领（虚报判据）。两错叠加 → has_omega 恒 False，
    platinum/gold 永久不可达，文档承诺的四级阶梯只剩三级。
    现在直接问 omega 自己："这个动作的 spec 在不在？"——判定口径与
    Ω-gate 执行侧逐字一致（同一函数），冒领面随之消除。
    """
    aid = action.meta.get('id') or ''
    if not aid:
        return False
    try:
        from .omega import _find_omega_spec
        return bool(_find_omega_spec(aid, None))
    except Exception:
        return False


# 质量计算自身写指标时的 caller 标识（V-08 已接线：_probe_metrics 把
# 它作为 exclude_callers 传给 aggregate_metrics，自刷的指标不计入判据）
_SELF_TOOLS = ('actus_quality', 'quality_scale')


def _probe_metrics(aid: str, meta_dir: Optional[str] = None) -> dict:
    """执行指标（惰性导入 calllog，失败返回零值；排除 self-call）。

    V-08（寻虫 2026-10-22）：设计原则 3 的"自指排除"此前未接线——
    _SELF_TOOLS 全仓零使用，旧的 unique_callers<=0 门槛与 total==0 等价
    （executor 写行恒带 caller）。改按 caller 过滤：aggregate_metrics 传
    exclude_callers=_SELF_CALLERS，质量计算自身刷的指标不计入
    exec_count/success_rate。
    """
    if not aid:
        return {'total': 0, 'success_rate': 0.0}
    try:
        from .calllog import aggregate_metrics
        agg = aggregate_metrics(aid, meta_dir=meta_dir,
                                exclude_callers=_SELF_TOOLS)
        return {'total': agg.get('total', 0), 'success_rate': agg.get('success_rate', 0.0)}
    except Exception:
        return {'total': 0, 'success_rate': 0.0}
