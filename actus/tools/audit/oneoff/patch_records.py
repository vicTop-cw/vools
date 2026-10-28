# -*- coding: utf-8 -*-
"""补丁：records.py 产物注册表统一格式 + 真清理（第 11 轮）。"""
import io

p = 'vools/actus/records.py'
s = io.open(p, encoding='utf-8').read()

# 1) 导出 register_artifact
s = s.replace(
    "__all__ = ['write_run_record', 'append_log', 'load_run_record', 'load_status',\n"
    "           'update_status', 'export_records', 'list_run_records',\n"
    "           'load_artifacts_registry', 'list_artifacts', 'get_artifact',\n"
    "           'cleanup_artifacts']",
    "__all__ = ['write_run_record', 'append_log', 'load_run_record', 'load_status',\n"
    "           'update_status', 'export_records', 'list_run_records',\n"
    "           'load_artifacts_registry', 'register_artifact', 'list_artifacts',\n"
    "           'get_artifact', 'cleanup_artifacts']", 1)

# 2) load_artifacts_registry 兼容 executor 旧格式
OLD_LOAD = '''def load_artifacts_registry(meta_dir: str = None) -> dict:
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
'''
NEW_LOAD = '''def load_artifacts_registry(meta_dir: str = None) -> dict:
    """加载产物注册表 _meta/artifacts.json。

    第 11 轮审计修复（双实现口径不一致）：executor 此前自己写
    `{"actions": {aid: {ver: {artifacts: {...}}}}}`，而本模块读
    `{"artifacts": [...]}` —— 实测 `list_artifacts()` 对真实执行产物**永远返回空**，
    `cleanup_artifacts()` 报成功但什么都没清。现在：
      * 规范化格式 = `{"artifacts": [...]}`；
      * 读取时兼容旧 executor 格式并**无损转换**（不丢 sha256/版本/block/来源 exec）；
      * 新写入统一走 `register_artifact()`（executor 已改为调用它）。
    """
    meta = meta_dir or _default_meta()
    registry_path = os.path.join(meta, 'artifacts.json')
    if not os.path.isfile(registry_path):
        return {'artifacts': [], 'version': '1.0'}
    try:
        with open(registry_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {'artifacts': [], 'version': '1.0'}
    if isinstance(data, dict) and isinstance(data.get('artifacts'), list):
        return data
    if isinstance(data, dict) and isinstance(data.get('actions'), dict):
        return _convert_executor_registry(data)
    return {'artifacts': [], 'version': '1.0'}


def _artifact_timestamp(path: str) -> str:
    """旧格式没有 timestamp：用文件 mtime 兜底（不存在则当前时间，避免误判过期）。"""
    try:
        if path and os.path.isfile(path):
            return datetime.fromtimestamp(os.path.getmtime(path), _TZ).isoformat(
                timespec='seconds')
    except OSError:
        pass
    return _now_iso()


def _convert_executor_registry(data: dict) -> dict:
    """把 executor 旧格式产物注册表转成规范化格式（只读兼容，不写盘）。"""
    artifacts = []
    for action_id, versions in (data.get('actions') or {}).items():
        if not isinstance(versions, dict):
            continue
        for version, payload in versions.items():
            if not isinstance(payload, dict):
                continue
            for name, info in (payload.get('artifacts') or {}).items():
                if not isinstance(info, dict):
                    continue
                source_exec = info.get('source_exec') or ''
                path = info.get('path') or ''
                artifacts.append({
                    'id': 'art_%s_%s_%s' % (source_exec or 'legacy', action_id, name),
                    'exec_id': source_exec,
                    'action_id': action_id,
                    'name': name,
                    'type': 'file' if path else 'text',
                    'path': path,
                    'description': 'legacy executor registry (converted)',
                    'sha256': info.get('sha256'),
                    'version': version,
                    'block': info.get('block'),
                    'timestamp': _artifact_timestamp(path),
                })
    return {'artifacts': artifacts, 'version': '1.0',
            'converted_from': 'executor-actions'}
'''
assert OLD_LOAD in s
s = s.replace(OLD_LOAD, NEW_LOAD, 1)

# 3) register_artifact 支持扩展字段
OLD_REG = '''    registry = load_artifacts_registry(meta_dir)
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
'''
NEW_REG = '''    registry = load_artifacts_registry(meta_dir)
    artifact = {
        'id': 'art_%s_%s' % (exec_id, name),
        'exec_id': exec_id,
        'action_id': action_id,
        'name': name,
        'type': artifact_type,
        'path': path,
        'description': description,
        'timestamp': _now_iso(),
    }
    for key, value in (extra or {}).items():
        if value is not None:
            artifact[key] = value
    if not isinstance(registry.get('artifacts'), list):
        registry['artifacts'] = []
    registry['artifacts'].append(artifact)
    _save_artifacts_registry(meta_dir, registry)
    return artifact
'''
assert OLD_REG in s
s = s.replace(OLD_REG, NEW_REG, 1)
s = s.replace(
    "def register_artifact(meta_dir: str, exec_id: str, name: str, artifact_type: str,\n"
    "                      path: str, action_id: str = '', description: str = '') -> dict:",
    "def register_artifact(meta_dir: str, exec_id: str, name: str, artifact_type: str,\n"
    "                      path: str, action_id: str = '', description: str = '',\n"
    "                      **extra) -> dict:", 1)

# 4) cleanup_artifacts：真删文件 + 回收字节统计
OLD_CLEAN = '''    kept = []
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
'''
NEW_CLEAN = '''    kept = []
    removed_entries = []
    for artifact in artifacts:
        try:
            ts = datetime.fromisoformat(artifact.get('timestamp', ''))
        except (ValueError, TypeError):
            ts = datetime.now(_TZ)

        if ts < cutoff or len(kept) >= max_count:
            removed_entries.append(artifact)
        else:
            kept.append(artifact)

    # 第 11 轮审计修复（假清理）：改前只删登记项、**不删磁盘文件** ——
    # "清理产物"后磁盘占用一点没少（实测 1KB 文件仍在）。现在真删文件并回报
    # 实际回收字节；仍被保留条目引用的路径不删（避免多版本共用同一文件时误删）。
    kept_paths = set()
    for artifact in kept:
        p = artifact.get('path')
        if p:
            try:
                kept_paths.add(os.path.realpath(p))
            except OSError:
                pass
    files_removed = 0
    reclaimed_bytes = 0
    file_errors = []
    for artifact in removed_entries:
        p = artifact.get('path')
        if artifact.get('type') != 'file' or not p:
            continue
        try:
            real = os.path.realpath(p)
        except OSError:
            continue
        if real in kept_paths:
            continue
        if not os.path.isfile(real):
            continue
        try:
            size = os.path.getsize(real)
            os.remove(real)
            files_removed += 1
            reclaimed_bytes += size
        except OSError as exc:
            file_errors.append({'path': p, 'error': str(exc)})

    registry['artifacts'] = kept
    _save_artifacts_registry(meta_dir, registry)

    return {
        'total_before': total,
        'removed': len(removed_entries),
        'kept': len(kept),
        'files_removed': files_removed,
        'reclaimed_bytes': reclaimed_bytes,
        'file_errors': file_errors,
    }
'''
assert OLD_CLEAN in s
s = s.replace(OLD_CLEAN, NEW_CLEAN, 1)

io.open(p, 'w', encoding='utf-8').write(s)
print('records.py patched OK')
