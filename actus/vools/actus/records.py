"""执行留痕（docs/07 §4）：_meta/runs/<exec_id>.json 与追加式日志。"""

__all__ = ['write_run_record', 'append_log', 'load_run_record', 'load_status',
           'update_status', 'export_records', 'list_run_records',
           'load_artifacts_registry', 'list_artifacts', 'get_artifact',
           'cleanup_artifacts']

import json
import os
import shutil
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict

_TZ = timezone(timedelta(hours=8))  # 项目文档时区 +08:00


def _default_meta() -> str:
    """缺省 _meta 目录 = 仓库根/_meta（ACTUS_REPO_ROOT 可覆盖）。"""
    root = os.environ.get('ACTUS_REPO_ROOT')
    if root:
        return os.path.join(root, '_meta')
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), '_meta')


def _now_iso() -> str:
    return datetime.now(_TZ).isoformat(timespec='seconds')


def write_run_record(meta_dir: str, record: dict) -> str:
    """写单次执行记录 _meta/runs/<exec_id>.json（存在则覆盖为最新状态机快照）。"""
    runs_dir = os.path.join(meta_dir, 'runs')
    os.makedirs(runs_dir, exist_ok=True)
    path = os.path.join(runs_dir, f"{record['exec_id']}.json")
    record.setdefault('timestamp', _now_iso())
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return path


def load_run_record(meta_dir: str = None, exec_id: str = ''):
    meta = meta_dir or _default_meta()
    path = os.path.join(meta, 'runs', f'{exec_id}.json')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def update_status(meta_dir: str, exec_id: str, action_id: str, state: str,
                  error: str = None) -> None:
    """更新 _meta/status.json 汇总（最近执行 + 各动作最近状态 + 失败计数）。"""
    path = os.path.join(meta_dir, 'status.json')
    data = {'recent': [], 'actions': {}}
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    entry = {'exec_id': exec_id, 'action': action_id, 'state': state,
             'at': _now_iso()}
    if error:
        entry['error'] = error
    recent = [r for r in data.get('recent', []) if r.get('exec_id') != exec_id]
    recent.insert(0, entry)
    data['recent'] = recent[:50]

    acts = data.setdefault('actions', {})
    a = acts.setdefault(action_id, {'last_exec_id': None, 'last_state': None,
                                    'runs': 0, 'failures': 0})
    a['last_exec_id'] = exec_id
    a['last_state'] = state
    a['runs'] = int(a.get('runs', 0)) + 1
    if state in ('failed', 'cancelled'):
        a['failures'] = int(a.get('failures', 0)) + 1

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_status(meta_dir: str = None) -> dict:
    meta = meta_dir or _default_meta()
    path = os.path.join(meta, 'status.json')
    if not os.path.exists(path):
        return {'recent': [], 'actions': {}}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def append_log(meta_dir: str, line: str) -> None:
    """追加可读日志 _meta/logs/actus-<date>.log（docs/07 §4，追加式）。"""
    log_dir = os.path.join(meta_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now(_TZ).strftime('%Y%m%d')
    with open(os.path.join(log_dir, f'actus-{today}.log'), 'a', encoding='utf-8') as f:
        f.write(f'{_now_iso()} {line}\n')


# ── 执行记录导出 ──

def list_run_records(meta_dir: str = None, action_id: str = None,
                     limit: int = 50, offset: int = 0) -> List[dict]:
    """列出执行记录，按时间倒序。"""
    meta = meta_dir or _default_meta()
    runs_dir = os.path.join(meta, 'runs')
    if not os.path.isdir(runs_dir):
        return []

    records = []
    for fname in sorted(os.listdir(runs_dir), reverse=True):
        if not fname.endswith('.json'):
            continue
        path = os.path.join(runs_dir, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                rec = json.load(f)
            if action_id and rec.get('action') != action_id:
                continue
            records.append(rec)
        except (json.JSONDecodeError, OSError):
            continue

    return records[offset:offset + limit]


def export_records(meta_dir: str = None, action_id: str = None,
                   fmt: str = 'json', output: str = None, limit: int = 100,
                   offset: int = 0) -> dict:
    """导出执行记录。

    参数:
        meta_dir: 仓库 _meta 目录。
        action_id: 按动作 id 过滤（可选）。
        fmt: 输出格式 json|csv|summary。
        output: 输出文件路径（None 则返回数据）。
        limit: 最多导出条数。
        offset: 跳过条数。

    返回:
        dict 含导出的记录和元数据。
    """
    records = list_run_records(meta_dir, action_id, limit, offset)

    result = {
        'format': fmt,
        'total': len(records),
        'records': records,
    }

    if output:
        with open(output, 'w', encoding='utf-8') as f:
            if fmt == 'json':
                json.dump(result, f, ensure_ascii=False, indent=2)
            elif fmt == 'csv':
                import csv
                if records:
                    writer = csv.DictWriter(f, fieldnames=records[0].keys())
                    writer.writeheader()
                    writer.writerows(records)
                else:
                    f.write('exec_id,action,state,timestamp,stdout,stderr,exit_code\n')
            elif fmt == 'summary':
                summary = {'total': len(records),
                           'success': sum(1 for r in records if r.get('state') == 'ok'),
                           'failed': sum(1 for r in records if r.get('state') == 'failed')}
                json.dump(summary, f, ensure_ascii=False, indent=2)
    return result


# ── 产物管理 ──

def load_artifacts_registry(meta_dir: str = None) -> dict:
    """加载产物注册表 _meta/artifacts.json。"""
    meta = meta_dir or _default_meta()
    registry_path = os.path.join(meta, 'artifacts.json')
    if not os.path.isfile(registry_path):
        return {'artifacts': [], 'version': '1.0'}
    try:
        with open(registry_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {'artifacts': [], 'version': '1.0'}


def _save_artifacts_registry(meta_dir: str, registry: dict) -> None:
    """保存产物注册表。"""
    meta = meta_dir or _default_meta()
    os.makedirs(meta, exist_ok=True)  # 确保目录存在
    registry_path = os.path.join(meta, 'artifacts.json')
    with open(registry_path, 'w', encoding='utf-8') as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def register_artifact(meta_dir: str, exec_id: str, name: str, artifact_type: str,
                      path: str, action_id: str = '', description: str = '') -> dict:
    """注册产物。

    参数:
        exec_id: 关联的执行 ID。
        name: 产物名称。
        artifact_type: 产物类型（file|text|json|log）。
        path: 产物路径或内容。
        action_id: 关联的动作 ID（可选）。
        description: 产物描述。

    返回:
        产物记录。
    """
    registry = load_artifacts_registry(meta_dir)
    artifact = {
        'id': f'art_{exec_id}_{name}',
        'exec_id': exec_id,
        'action_id': action_id,
        'name': name,
        'type': artifact_type,
        'path': path,
        'description': description,
        'timestamp': _now_iso(),
    }
    registry['artifacts'].append(artifact)
    _save_artifacts_registry(meta_dir, registry)
    return artifact


def list_artifacts(meta_dir: str = None, action_id: str = None,
                   exec_id: str = None, artifact_type: str = None) -> List[dict]:
    """列出产物。"""
    registry = load_artifacts_registry(meta_dir)
    results = registry.get('artifacts', [])

    if action_id:
        results = [a for a in results if a.get('action_id') == action_id]
    if exec_id:
        results = [a for a in results if a.get('exec_id') == exec_id]
    if artifact_type:
        results = [a for a in results if a.get('type') == artifact_type]

    return results


def get_artifact(meta_dir: str = None, artifact_id: str = '') -> Optional[dict]:
    """获取单个产物。"""
    registry = load_artifacts_registry(meta_dir)
    for artifact in registry.get('artifacts', []):
        if artifact.get('id') == artifact_id:
            return artifact
    return None


def cleanup_artifacts(meta_dir: str, max_age_days: int = 30,
                      max_count: int = 1000) -> dict:
    """清理过期/过多产物。

    参数:
        max_age_days: 保留天数。
        max_count: 最多保留条数。

    返回:
        清理统计。"""
    registry = load_artifacts_registry(meta_dir)
    artifacts = registry.get('artifacts', [])
    total = len(artifacts)

    cutoff = datetime.now(_TZ) - timedelta(days=max_age_days)

    kept = []
    removed = 0
    for artifact in artifacts:
        try:
            ts = datetime.fromisoformat(artifact.get('timestamp', ''))
        except (ValueError, TypeError):
            ts = datetime.now(_TZ)

        if ts < cutoff or len(kept) >= max_count:
            removed += 1
        else:
            kept.append(artifact)

    registry['artifacts'] = kept
    _save_artifacts_registry(meta_dir, registry)

    return {
        'total_before': total,
        'removed': removed,
        'kept': len(kept),
    }
