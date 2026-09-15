"""author.py —— AI 修改已有动作 + 7 步自动校验流水线（docs/10 §D.3）。

职责：
1. `author_action(id, instruction)` —— 根据自然语言指令修改动作的代码块或元数据；
2. `publish_action(id)` —— 校验通过 → 入索引 → 上 MCP；
3. 7 步自动校验流水线（parse → schema → entry → args → graph → dry_run → sandbox_trial）。

本模块是"薄壳"——修改逻辑由 AI 调用方实现（此处提供程序化修改接口），
本模块负责驱动校验流水线和留痕。
"""

__all__ = ['author_action', 'publish_action', 'Pipeline', 'run_pipeline']

import json
import os
import time
from typing import Callable, Dict, List, Optional

from .errors import ActionError
from .model import Action, parse_cfg_from_file
from .validate import validate_action


class Pipeline:
    """7 步自动校验流水线（docs/10 §D.3）。

    步骤:
        1. parse_cfg        → #!cfg 必须可解析为合法 JSON
        2. schema_validate  → 符合 action.schema.json
        3. entry_block      → entry tag 指向真实代码块
        4. args_schema      → args 是合法 JSON Schema
        5. graph_validate   → 依赖图无环（在索引构建时已校验）
        6. dry_run          → 展示将要执行的块,不执行
        7. sandbox_trial    → sandbox 级执行入口块,验证无致命错误 (超时 30s)

    每步产生一条记录: {step, name, ok, message, duration_ms}
    """

    STEPS = [
        ('parse_cfg', '解析 #!cfg 元数据'),
        ('schema_validate', 'schema 校验'),
        ('entry_block', 'entry 代码块校验'),
        ('args_schema', 'args 契约校验'),
        ('graph_validate', '依赖图校验'),
        ('dry_run', '干跑预览'),
        ('sandbox_trial', '沙箱试跑'),
    ]

    def __init__(self, action: Action, repo_root: Optional[str] = None):
        self.action = action
        self.repo_root = repo_root or os.getcwd()
        self.records: List[Dict] = []
        self._current_step: Optional[str] = None
        self._start_time: float = 0

    def _begin(self, step: str):
        self._current_step = step
        self._start_time = time.time()

    def _end(self, ok: bool, message: str = '') -> Dict:
        record = {
            'step': self._current_step,
            'name': dict(self.STEPS).get(self._current_step, ''),
            'ok': ok,
            'message': message,
            'duration_ms': round((time.time() - self._start_time) * 1000, 1),
        }
        self.records.append(record)
        self._current_step = None
        return record

    def run(self, dry_run_only: bool = False) -> Dict:
        """执行全部 7 步。

        支持双格式：
        - 旧格式（#!cfg JSON）：走 validate_action
        - 新格式（.actus.schema.md）：走 validate_schema_md

        参数:
            dry_run_only: 仅执行到第 6 步（不执行 sandbox 试跑）。

        返回:
            Dict: {
                'action_id': 动作 id,
                'valid': 是否全部通过,
                'steps': [每步记录],
                'total_ms': 总耗时,
            }
        """
        aid = self.action.meta.get('id', '<unknown>')

        # 检测格式
        from .model import parse_action_from_schema_md
        is_schema_md = self.action.path and self.action.path.endswith('.actus.schema.md')

        # 1) parse_cfg（已在 Action 解析时完成，此处重验）
        self._begin('parse_cfg')
        if self.action.meta:
            format_label = 'YAML front-matter' if is_schema_md else '#!cfg JSON'
            self._end(True, f'成功解析 {format_label}，id={aid}')
        else:
            self._end(False, 'cfg 解析失败')

        # 2) schema_validate
        self._begin('schema_validate')
        if is_schema_md:
            from .validate import validate_schema_md
            errs = validate_schema_md(self.action)
        else:
            errs = validate_action(self.action)
        if errs:
            self._end(False, f'校验失败: {"; ".join(errs)}')
        else:
            self._end(True, 'schema 与语义校验全部通过')

        # 3) entry_block（已含在 schema_validate 中，此处显式报告）
        self._begin('entry_block')
        from .validate import check_entry_block
        entry_errs = check_entry_block(self.action)
        self._end(not entry_errs,
                  'entry 校验通过' if not entry_errs else f'entry 错误: {"; ".join(entry_errs)}')

        # 4) args_schema
        self._begin('args_schema')
        from .validate import check_args_schema
        args_errs = check_args_schema(self.action.meta)
        self._end(not args_errs,
                  'args 契约合法' if not args_errs else f'args 错误: {"; ".join(args_errs)}')

        # 5) graph_validate（单动作级别：仅校验 deps 存在性）
        self._begin('graph_validate')
        missing = []
        for dep in self.action.meta.get('deps', []) or []:
            # 在仓库内查找依赖
            dep_path = _find_action_file(dep, self.repo_root)
            if dep_path is None:
                missing.append(dep)
        self._end(not missing,
                  '依赖全部存在' if not missing else f'缺少依赖: {missing}')

        # 6) dry_run（预览将要执行的块）
        self._begin('dry_run')
        try:
            from .executor import preview
            actions_dir = os.path.join(self.repo_root, 'actions')
            prev = preview(self.action.meta.get('id', ''),
                           actions_dir=actions_dir if os.path.isdir(actions_dir) else None)
            self._end(True, f'干跑预览成功: {len(prev.get("blocks", []))} 个块将执行')
        except Exception as e:
            self._end(False, f'干跑预览失败: {e}')

        # 7) sandbox_trial（可选）
        if not dry_run_only:
            self._begin('sandbox_trial')
            try:
                from .executor import execute
                actions_dir = os.path.join(self.repo_root, 'actions')
                res = execute(self.action.meta.get('id', ''), {},
                              actions_dir=actions_dir if os.path.isdir(actions_dir) else None,
                              confirmed=True)
                ok = res.get('status') in ('ok', 'awaiting_confirmation')
                self._end(ok, f'沙箱试跑: {res.get("status")}')
            except Exception as e:
                self._end(False, f'沙箱试跑失败: {e}')
        else:
            self._begin('sandbox_trial')
            self._end(True, '跳过（dry_run_only=True）')

        valid = all(r['ok'] for r in self.records)
        total_ms = sum(r['duration_ms'] for r in self.records)

        return {
            'action_id': aid,
            'valid': valid,
            'steps': self.records,
            'total_ms': round(total_ms, 1),
        }


def run_pipeline(action_path: str, repo_root: Optional[str] = None,
                 dry_run_only: bool = False) -> Dict:
    """便捷入口：从文件路径解析 + 运行 7 步流水线。"""
    action = parse_cfg_from_file(action_path)
    pipeline = Pipeline(action, repo_root=repo_root)
    return pipeline.run(dry_run_only=dry_run_only)


def author_action(action_id: str, instruction: str,
                  repo_root: Optional[str] = None) -> dict:
    """根据自然语言指令修改已有动作。

    当前实现：将 instruction 写入动作文件的 TODO 注释区，
              调用 AI 回调（由上层注入，或默认只记录指令）。

    完整实现（docs/10 §D.2）：
        AI 客户端读取动作文件 → 理解 instruction → 调用文件系统编辑动作
              → 重新走 7 步流水线 → 校验通过则入索引。

    本函数提供"修改指令记录 + 重新校验"骨架，实际的代码编辑由 AI 完成
    （通过 MCP actus_author 工具暴露给 AI）。

    参数:
        action_id: 要修改的动作 id。
        instruction: 自然语言修改指令。
        repo_root: 仓库根目录。

    返回:
        dict: {
            'action_id': 动作 id,
            'instruction': 指令,
            'file_path': 动作文件路径,
            'pipeline': 7 步流水线结果,
            'status': 'modified' | 'failed',
            'message': 说明,
        }
    """
    repo_root = repo_root or os.getcwd()

    # 定位动作文件
    file_path = _find_action_file(action_id, repo_root)
    if file_path is None:
        raise ActionError('action_not_found',
                          f'找不到动作文件: {action_id}',
                          {'searched': os.path.join(repo_root, 'actions')})

    # 读取并修改动作文件（在 entry 块顶部追加修改记录注释）
    with open(file_path, 'r', encoding='utf-8') as f:
        original = f.read()

    timestamp = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    record = f'# AI-MODIFIED [{timestamp}] instruction: {instruction}\n'

    # 在 entry tag 块的第一行后插入修改记录
    entry = None
    action = parse_cfg_from_file(file_path)
    entry = action.meta.get('entry', '')

    modified = original
    if entry:
        # 找到 entry 块的 ``` 开头后第一行，插入注释
        tag_pattern = f'#!run tag={entry}'
        idx = modified.find(tag_pattern)
        if idx != -1:
            # 在 tag 行后插入
            nl = modified.find('\n', idx)
            if nl != -1:
                modified = modified[:nl + 1] + record + modified[nl + 1:]

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(modified)

    # 重新解析并运行流水线
    new_action = parse_cfg_from_file(file_path)
    pipeline = Pipeline(new_action, repo_root=repo_root)
    result = pipeline.run(dry_run_only=True)  # author 只做 dry_run，不实际试跑

    return {
        'action_id': action_id,
        'instruction': instruction,
        'file_path': os.path.abspath(file_path),
        'pipeline': result,
        'status': 'modified' if result['valid'] else 'needs_fix',
        'message': '修改已记录，校验通过' if result['valid'] else f'校验需修复: {[s for s in result["steps"] if not s["ok"]]}',
    }


def publish_action(action_id: str, repo_root: Optional[str] = None,
                   force: bool = False) -> dict:
    """校验通过 → 入索引 → 上 MCP（docs/10 §D.1）。

    参数:
        action_id: 要发布的动作 id。
        repo_root: 仓库根目录。
        force: 强制发布（跳过人类确认，需配置 trust_policy=auto_promote）。

    返回:
        dict: {
            'action_id': 动作 id,
            'status': 'published' | 'rejected' | 'needs_human_confirm',
            'pipeline': 7 步流水线结果,
            'message': 说明,
        }
    """
    repo_root = repo_root or os.getcwd()
    file_path = _find_action_file(action_id, repo_root)

    if file_path is None:
        raise ActionError('action_not_found', f'找不到动作: {action_id}')

    action = parse_cfg_from_file(file_path)
    pipeline = Pipeline(action, repo_root=repo_root)
    result = pipeline.run(dry_run_only=True)

    if not result['valid']:
        return {
            'action_id': action_id,
            'status': 'rejected',
            'pipeline': result,
            'message': '校验未通过，拒绝发布',
        }

    # 检查信任级别
    trust = action.meta.get('trust', 'audit')
    ai_generated = action.meta.get('ai', {}).get('generated', False)

    if trust == 'audit' and not force:
        return {
            'action_id': action_id,
            'status': 'needs_human_confirm',
            'pipeline': result,
            'message': f'audit 级动作需人类确认（运行 actus publish {action_id} --force 或人工标记为 trusted）',
        }

    # 入索引
    try:
        from . import indexer
        idx = indexer.build_index(meta_dir=os.path.join(repo_root, '_meta'))
        in_index = action_id in idx['actions']
        idx_status = idx['actions'].get(action_id, {}).get('status', 'unknown')
    except Exception as e:
        in_index = False
        idx_status = f'index_error: {e}'

    return {
        'action_id': action_id,
        'status': 'published' if in_index and idx_status == 'valid' else 'rejected',
        'pipeline': result,
        'index_status': idx_status,
        'message': '已入索引，下次 MCP server 启动时自动生效' if in_index else '入索引失败',
    }


def _find_action_file(action_id: str, repo_root: str) -> Optional[str]:
    """根据 action_id 在 actions/ 目录中查找对应的动作文件。

    支持双格式：
    - 旧格式：.actus.md
    - 新格式：.actus.schema.md
    """
    actions_dir = os.path.join(repo_root, 'actions')
    if not os.path.isdir(actions_dir):
        return None

    # 从 id 推算文件名（最后一段）
    last_segment = action_id.rsplit('.', 1)[-1]
    candidates = [
        os.path.join(actions_dir, f'{last_segment}.actus.schema.md'),
        os.path.join(actions_dir, f'{last_segment}.actus.md'),
        os.path.join(actions_dir, last_segment, 'index.actus.schema.md'),
        os.path.join(actions_dir, last_segment, 'index.actus.md'),
    ]

    # 递归搜索
    for root, dirs, files in os.walk(actions_dir):
        for fname in files:
            if fname.endswith('.actus.schema.md') or fname.endswith('.actus.md'):
                full = os.path.join(root, fname)
                candidates.append(full)

    for path in candidates:
        if os.path.isfile(path):
            try:
                a = parse_cfg_from_file(path)
                if a.meta.get('id') == action_id:
                    return path
            except Exception:
                continue
    return None
