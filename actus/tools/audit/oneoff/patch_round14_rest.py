# -*- coding: utf-8 -*-
"""第 14 轮（续）：omega repair / 命名修正 / B 类 makedirs / resolver 读路径 / AST 文档。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)


def patch(path, old, new, count=1):
    p = os.path.join(ROOT, path)
    s = io.open(p, encoding='utf-8').read()
    assert old in s, '%s 未匹配:\n%s' % (path, old[:200])
    s = s.replace(old, new, count)
    io.open(p, 'w', encoding='utf-8').write(s)
    print('patched:', path)


# ═══ 3) omega_strong.load_ledger(repair=False) ═══
patch('vools/actus/omega_strong.py',
"""def load_ledger(task_id: str, meta_dir: Optional[str] = None) -> Dict[str, Any]:
    \"\"\"读账本。缺失 → 空账本；**损坏 → 备份为 `.corrupt-<ts>` + 返回带 corrupt 标记的
    空账本（写侧会拒绝覆盖，绝不静默清空历史）**。""",
"""def load_ledger(task_id: str, meta_dir: Optional[str] = None,
                repair: bool = False) -> Dict[str, Any]:
    \"\"\"读账本。缺失 → 空账本；损坏 → 返回带 corrupt 标记的空账本。

    `repair=False`（默认，第 14 轮审计修复）：**只读**，不把损坏账本改名备份
    （旧实现 `load_` 会在读路径 `os.replace` 改用户数据目录，只读 FS 直接失败）。
    写路径调用方（`_append`/`_update_status`）显式传 `repair=True` 保留备份语义。""")
patch('vools/actus/omega_strong.py',
"""    except (OSError, ValueError) as exc:
        backup = '%s.corrupt-%d' % (path, int(time.time()))
        try:
            os.replace(path, backup)
        except OSError:
            backup = None
        _load_ledger_state.update({'corrupt': True, 'path': path})
        broken = dict(empty)
        broken.update({'corrupt': True, 'corrupt_backup': backup,
                       'corrupt_reason': '%s: %s' % (type(exc).__name__, exc)})
        return broken""",
"""    except (OSError, ValueError) as exc:
        backup = None
        if repair:
            backup = '%s.corrupt-%d' % (path, int(time.time()))
            try:
                os.replace(path, backup)
            except OSError:
                backup = None
        _load_ledger_state.update({'corrupt': True, 'path': path})
        broken = dict(empty)
        broken.update({'corrupt': True, 'corrupt_backup': backup,
                       'corrupt_reason': '%s: %s%s' % (
                           type(exc).__name__, exc,
                           '' if repair else '（repair=False：未自动备份，只读返回）')})
        return broken""")
patch('vools/actus/omega_strong.py',
"""    def _load(self) -> Dict[str, Any]:
        return load_ledger(self.task_id, self.meta_dir)""",
"""    def _load(self, repair: bool = False) -> Dict[str, Any]:
        return load_ledger(self.task_id, self.meta_dir, repair=repair)""")
patch('vools/actus/omega_strong.py',
"""        with _ledger_lock(_ledger_path(self.task_id, self.meta_dir)):
            data = self._load()
            data['max_rounds'] = self.max_rounds""",
"""        with _ledger_lock(_ledger_path(self.task_id, self.meta_dir)):
            data = self._load(repair=True)      # 写路径保留损坏备份语义
            data['max_rounds'] = self.max_rounds""")
patch('vools/actus/omega_strong.py',
"""        with _ledger_lock(_ledger_path(self.task_id, self.meta_dir)):
            data = self._load()
            for r in data['records']:""",
"""        with _ledger_lock(_ledger_path(self.task_id, self.meta_dir)):
            data = self._load(repair=True)      # 写路径保留损坏备份语义
            for r in data['records']:""")

# ── 命名修正：check_record → record_check（保留旧名 deprecated 别名）──
patch('vools/actus/omega_strong.py',
"""    # ── 外部命令判据（[gate:required]） ──
    def check_record(self, check: dict) -> Dict[str, Any]:
        \"\"\"记录一次外部命令检查结果。""",
"""    # ── 外部命令判据（[gate:required]） ──
    def record_check(self, check: dict) -> Dict[str, Any]:
        \"\"\"**写账本**：记录一次外部命令检查结果（`check_` 前缀易误认为只读，
        第 14 轮改名 `record_check`；旧名 `check_record` 保留为 deprecated 别名）。""")
patch('vools/actus/omega_strong.py',
"""        return out

    # ── 内部：结果校验 ──""",
"""        return out

    def check_record(self, check: dict) -> Dict[str, Any]:
        \"\"\"Deprecated 别名（第 14 轮）：语义是**写账本**，请用 `record_check`。\"\"\"
        return self.record_check(check)

    # ── 内部：结果校验 ──""")

# ═══ 命名修正：resolve_all → ensure_all（保留旧名别名）════
patch('vools/actus/importsys.py',
"""    def resolve_all(self, decls: List[ImportDecl]) -> Tuple[bool, List[str], Dict[str, Path]]:""",
"""    def ensure_all(self, decls: List[ImportDecl]) -> Tuple[bool, List[str], Dict[str, Path]]:
        \"\"\"解析并**安装/写入 vendor 目录**的依赖（会写盘；第 14 轮从 `resolve_all`
        改名，`resolve_all` 保留为 deprecated 别名）。\"\"\"""")
patch('vools/actus/importsys.py',
"""        ok, missing, results = resolver.resolve_all(decls)""",
"""        ok, missing, results = resolver.ensure_all(decls)""")

# ═══ 5) B 类 makedirs：cost 读路径不建目录；visibility 惰性创建移到显式写入 ═══
patch('vools/actus/cost.py',
"""    \"\"\"
    _ensure_dir()
    if month is None:""",
"""    \"\"\"
    # 第 14 轮审计：`get_cost_summary` 是只读汇总，不再 `_ensure_dir()`（旧实现
    # 会在只读 FS 上因 mkdir 失败）；账本目录不存在时下面 os.path.exists 直接
    # 返回空汇总即可。目录创建只在写路径（record_cost）发生。
    if month is None:""")
patch('vools/actus/visibility.py',
"""    def get_private_dir(self) -> str:
        \"\"\"获取私有目录路径。\"\"\"
        os.makedirs(self._private_dir, exist_ok=True)
        return self._private_dir""",
"""    def get_private_dir(self, create: bool = False) -> str:
        \"\"\"获取私有目录路径（第 14 轮：只读路径不再 makedirs）。

        `create=False`（默认）只返回路径——`makedirs` 移到显式写入口
        （调用方准备写入时传 `create=True`），避免只读命令/只读文件系统失败。
        \"\"\"
        if create:
            os.makedirs(self._private_dir, exist_ok=True)
        return self._private_dir""")

# ═══ 4/命名+读路径：resolver.resolve_target 不建索引（内存扫描），docstring 显式写盘 ═══
patch('vools/actus/resolver.py',
"""def resolve_target(target: str, allow_hosts: List[str] = None,
                   expect_digest: Optional[str] = None,
                   expect_signature_key: Optional[str] = None) -> ResolvedTarget:
    \"\"\"解析目标字符串为 ResolvedTarget（ACTUS_REFACTOR_PLAN.md §3.1 优先级链）。""",
"""def resolve_target(target: str, allow_hosts: List[str] = None,
                   expect_digest: Optional[str] = None,
                   expect_signature_key: Optional[str] = None) -> ResolvedTarget:
    \"\"\"⚠️ **本函数可能写盘**：action_id / md5 分支**不再建索引落盘**（索引缺失时
    内存扫描，write_cache=False）；**URL 分支会 `_download_url` 下载到磁盘**
    （远程动作源解析的固有行为，调用方需自己负责白名单/指纹/签名）。

    解析目标字符串为 ResolvedTarget（ACTUS_REFACTOR_PLAN.md §3.1 优先级链）。""")
patch('vools/actus/resolver.py',
"""        result.action_id = raw
        # 验证 id 是否存在于索引
        index = load_index()
        if raw not in (index.get('actions') or {}):
            raise ActionError(
                'action_not_found',
                f'动作 id 不存在: {raw}',
                {'source': 'id', 'known': sorted((index.get('actions') or {}).keys())[:20]},
            )
        return result""",
"""        result.action_id = raw
        # 验证 id 是否存在（只读：索引缺失时内存扫描，不落盘）
        known = _known_action_ids()
        if raw not in known:
            raise ActionError(
                'action_not_found',
                f'动作 id 不存在: {raw}',
                {'source': 'id', 'known': sorted(known.keys())[:20]},
            )
        return result""")
patch('vools/actus/resolver.py',
"""    # 优先级 3: 32 位 hex 指纹
    if _is_hex32(raw):
        index = load_index()
        aid = _lookup_by_md5(raw, index)""",
"""    # 优先级 3: 32 位 hex 指纹
    if _is_hex32(raw):
        aid = _lookup_by_md5(raw, _known_index())""")
# 插入只读查找辅助（在 resolve_target 之前）
patch('vools/actus/resolver.py',
"""def resolve_target(target: str, allow_hosts: List[str] = None,""",
"""def _known_index() -> dict:
    \"\"\"只读取索引：索引存在 → 直接读；缺失/为空 → 内存扫描（不写缓存/不建索引）。\"\"\"
    from .indexer import load_index, scan_actions
    index = load_index(build=False)
    if index.get('actions'):
        return index
    scanned = scan_actions(validate=False, write_cache=False)
    return {'actions': {aid: action.brief() for aid, action in scanned.items()}}


def _known_action_ids() -> dict:
    return _known_index().get('actions') or {}


def resolve_target(target: str, allow_hosts: List[str] = None,""")

# ═══ 6) AST 扫描器文档化（已知局限）═══
patch('build/audit/readonly_name_writes.py',
"""\"\"\"只读命名审计：找出"名字像只读、实际有写副作用"的函数（AST + 调用传递闭包）。

用法:
    python build/audit/readonly_name_writes.py [--depth 3] [--json out.json]

输出：候选函数 + 直接写符号 + 传递写符号（带调用链），按写严重度排序。
\"\"\"""",
"""\"\"\"只读命名审计：找出"名字像只读、实际有写副作用"的函数（AST + 调用传递闭包）。

用法:
    python build/audit/readonly_name_writes.py [--depth 3] [--json out.json]

输出：候选函数 + 直接写符号 + 传递写符号（带调用链），按写严重度排序。
建议在 CI 中作为**告警**运行（不要 fail），新出现的"名实不符"能被看到。

已知局限（第 13/14 轮审计实感）：
  * **kwarg 常量**：看不到 `add_trigger(..., _persist=False)` 这类"传参关闭写"，
    会把 `triggers.load_registry` 误报为写（已人工标注）。
  * **三方库语义**：`subprocess.run` / `Path.unlink` 等按名字归类，不区分
    实际参数是否只读命令；`json.dump(StringIO())` 也会被当作写。
  * **动态分派/反射**：`getattr(mod, name)()`、插件注册表调用无法解析。
  * **只覆盖 `vools/actus/`**：`vools/core/` 等下层写操作不会展开。
误报请人工确认后在报告里标注，不要为了"清零"而放宽检测。
\"\"\"""")

print('done')
