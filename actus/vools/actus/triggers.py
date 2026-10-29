"""triggers.py —— 触发器系统（docs/10 §C）。

五种触发器类型：
- cron：定时执行（cron 表达式）
- watch：文件/文件夹监控（创建/修改/删除）
- webhook：HTTP 端点监听
- hotkey：全局热键触发
- on_startup：系统启动时触发

架构：
- Trigger：触发器数据模型
- TriggerEngine：调度引擎（线程驱动，支持 start/stop/pause）
- 各类型执行器：CronScheduler / FileWatcher / WebhookServer / HotkeyListener
"""

__all__ = [
    'Trigger',
    'TriggerEngine',
    'CronScheduler',
    'FileWatcher',
    'HotkeyListener',
    'parse_triggers',
    'validate_trigger',
]

import json
import logging
import os
import re
import sys
import threading
import time

logger = logging.getLogger(__name__)
from typing import Callable, Dict, List, Optional


# ── Cron 表达式解析 ──

class CronExpr:
    """5 字段 cron 表达式解析器。

    字段：分 时 日 月 周
    支持：* , - /
    """

    FIELD_NAMES = ['minute', 'hour', 'day', 'month', 'weekday']
    FIELD_RANGES = [
        (0, 59),   # minute
        (0, 23),   # hour
        (1, 31),   # day
        (1, 12),   # month
        (0, 6),    # weekday (0=Sunday)
    ]

    def __init__(self, expr: str):
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f'Cron 表达式需 5 字段，得到 {len(parts)}: {expr!r}')
        self.raw = expr
        self.fields: List[set] = [self._parse_field(p, r) for p, r in zip(parts, self.FIELD_RANGES)]

    @staticmethod
    def _parse_field(field: str, value_range: tuple) -> set:
        """解析单个 cron 字段。

        边界一律响亮报错——此前静默产出空集合，导致触发器永不触发且零提示：
          - step 必须 ≥1（`*/0` 抛裸 `range() arg 3 must not be zero`；
            `*/-1` **静默产出空集合**）
          - 范围必须升序（`5-3` **静默产出空集合**）
          - 空项（`1,,2`）与非整数（`*/abc`）给出带字段名的错误
        """
        min_val, max_val = value_range
        values = set()

        def _int(token: str, what: str) -> int:
            try:
                return int(token)
            except ValueError:
                raise ValueError(
                    f'Cron 字段 {field!r} 的{what}不是整数: {token!r}') from None

        for part in field.split(','):
            part = part.strip()
            if not part:
                raise ValueError(f'Cron 字段含空项（多余的逗号）: {field!r}')

            # 步进 /
            if '/' in part:
                range_part, step_token = part.split('/', 1)
                step = _int(step_token, '步进')
                if step < 1:
                    raise ValueError(
                        f'Cron 字段 {field!r} 的步进必须 ≥1，得到 {step}')
                if range_part == '*':
                    start, end = min_val, max_val
                elif '-' in range_part:
                    a, b = range_part.split('-', 1)
                    start, end = _int(a, '范围起点'), _int(b, '范围终点')
                else:
                    start = _int(range_part, '起点')
                    end = max_val
                if start > end:
                    raise ValueError(
                        f'Cron 字段 {field!r} 的范围倒序: {start} > {end}')
                for v in range(start, end + 1, step):
                    values.add(v)
            # 范围 -
            elif '-' in part:
                a, b = part.split('-', 1)
                start, end = _int(a, '范围起点'), _int(b, '范围终点')
                if start > end:
                    raise ValueError(
                        f'Cron 字段 {field!r} 的范围倒序: {start} > {end}')
                for v in range(start, end + 1):
                    values.add(v)
            # 通配 *
            elif part == '*':
                for v in range(min_val, max_val + 1):
                    values.add(v)
            # 具体值
            else:
                values.add(_int(part, '值'))

        # 校验范围
        for v in values:
            if v < min_val or v > max_val:
                raise ValueError(f'值 {v} 超出范围 [{min_val}, {max_val}]')
        return values

    def matches(self, t: time.struct_time) -> bool:
        """检查时间是否匹配 cron 表达式。

        **星期换算**：cron 标准 0=周日、6=周六，而 `time.struct_time.tm_wday`
        是 0=周一、6=周日。此前直接用 `t.tm_wday` 比对，导致按星期配置的触发器
        **整体偏移一天**（实测 `'0 12 * * 0'`（周日）在周一匹配、周日反而不匹配）。
        这里把 tm_wday 换算成 cron 编号：周一0→1 … 周六5→6、周日6→0。
        """
        cron_weekday = (t.tm_wday + 1) % 7
        checks = [
            t.tm_min in self.fields[0],
            t.tm_hour in self.fields[1],
            t.tm_mday in self.fields[2],
            t.tm_mon in self.fields[3],
            cron_weekday in self.fields[4],
        ]
        return all(checks)

    #: 硬保底：最多向前搜 1 年（分钟数）。超限返回 None，绝不无限扫。
    _MAX_NEXT_FIRE_MINUTES = 366 * 24 * 60

    def _calendar_possible(self) -> bool:
        """快速判定"日期组合在日历上是否可能出现"。

        `0 0 31 2 *`（2 月 31 日）这类表达式**永远**不匹配，旧实现仍会
        扫 4 年 × 2.1M 次（实测 3.68s，public API 卡调用方线程）。这里先做
        廉价判别：只要存在一个合法 (month, day) 组合就继续搜；2 月按 29 天
        算（闰年可能出现），不误杀 `0 0 29 2 *`。
        """
        max_days = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30,
                    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
        return any(day <= max_days[month]
                   for month in self.fields[3] for day in self.fields[2])

    def next_fire(self, after: Optional[float] = None) -> Optional[float]:
        """计算下一次触发时间（Unix 时间戳）；搜索上限 1 年，超限返回 None。

        返回 None 的两种情形（调用方必须显式处理，别再当"下一分钟"）：
          1. 日期组合在日历上不可能（如 2 月 31 日）；
          2. 1 年内没有匹配点（极稀疏表达式/星期错位）。
        """
        if after is None:
            after = time.time()
        if not self._calendar_possible():
            return None
        t = time.localtime(after + 1)  # 至少 1 秒后
        for _ in range(self._MAX_NEXT_FIRE_MINUTES):
            if self.matches(t):
                return time.mktime(t)
            t = time.localtime(time.mktime(t) + 60)
        return None


# ── 触发器模型 ──

def _default_watch_root() -> str:
    """watch 路径的默认根：仓库根（`ACTUS_REPO_ROOT > __file__ 推导`）。"""
    from .paths import repo_root
    return repo_root()


def validate_watch_path(path, root: Optional[str] = None,
                        allow_outside_root: bool = False) -> Optional[str]:
    """校验 watch 触发器 path 是否被约束在 root 下。

    返回 None 表示通过，否则返回可读错误串（调用方拼接/上报，不在这里抛）。
    规则（第 41 轮 #9，默认严格；跨根必须显式 `allow_outside_root: true`）：
      * `../` 上跳、绝对路径（Windows 盘符/UNC/`\\` 开头）一律拒绝；
      * `realpath` 后逃出 root（含 symlink 间接逃逸）拒绝；
      * 相对路径按 root 解析；**不要求路径已存在**（watch 可先注册后创建）；
      * 含 `${...}` 模板占位符时注册期跳过——运行时解析成具体路径后，
        `FileWatcher.add` 会再走一次本校验（消费点复查，防绕过）。
    """
    if allow_outside_root:
        return None
    if not isinstance(path, str) or not path.strip():
        return 'watch 路径为空'
    raw = path.strip()
    if '${' in raw:
        return None  # 模板占位符：注册期无法判定，运行时解析后再校验
    if os.path.isabs(raw) or raw.startswith(('/', '\\')) \
            or os.path.splitdrive(raw)[0]:
        return f'watch 路径必须是相对路径（收到绝对路径: {path!r}）'
    norm = raw.replace('\\', '/')
    if any(seg == '..' for seg in norm.split('/')):
        return f'watch 路径不允许 `..` 上跳: {path!r}'
    root_real = os.path.realpath(root or _default_watch_root())
    target = os.path.realpath(os.path.join(root_real, norm))
    try:
        common = os.path.commonpath([os.path.normcase(root_real),
                                     os.path.normcase(target)])
    except ValueError:
        return f'watch 路径与根不在同一盘符: {path!r}'
    if os.path.normcase(common) != os.path.normcase(root_real):
        return f'watch 路径逃出允许根 {root_real!r}: {path!r}'
    return None


class Trigger:
    """单个触发器定义。"""

    def __init__(self, action_id: str, config: dict):
        self.action_id = action_id
        self.config = config
        self.ttype = config.get('type', '')
        self.expr = config.get('expr', '')
        self.path = config.get('path', '')
        self.events = config.get('events') or ['create', 'modify']
        self.recursive = bool(config.get('recursive', False))
        self.debounce_ms = int(config.get('debounce_ms', 500))
        self.method = config.get('method', 'POST')
        self.key = config.get('key', '')
        self.args = config.get('args', {})
        # #9 逃生阀：跨根监控必须显式声明（默认严格）
        self.allow_outside_root = bool(config.get('allow_outside_root', False))

    def __repr__(self):
        return f'Trigger({self.action_id}, type={self.ttype})'


# ── Cron 调度器 ──

class CronScheduler:
    """Cron 触发调度器。

    使用轮询（1 分钟间隔）检查 cron 表达式，触发匹配的回调。
    """

    def __init__(self):
        self._jobs: List[dict] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def add(self, trigger: Trigger, callback: Callable):
        """添加 cron 任务。"""
        cron = CronExpr(trigger.expr)
        with self._lock:
            self._jobs.append({
                'trigger': trigger,
                'cron': cron,
                'callback': callback,
                'last_fired': 0.0,
            })

    def remove(self, action_id: str):
        """移除指定动作的所有 cron 任务。"""
        with self._lock:
            self._jobs = [j for j in self._jobs if j['trigger'].action_id != action_id]

    def start(self):
        """启动调度器。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止调度器。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self):
        """调度主循环。"""
        while self._running:
            now = time.time()
            t = time.localtime(now)

            with self._lock:
                for job in self._jobs:
                    # 避免同一分钟内重复触发
                    if now - job['last_fired'] < 60:
                        continue
                    if job['cron'].matches(t):
                        job['last_fired'] = now
                        try:
                            threading.Thread(
                                target=job['callback'],
                                args=(job['trigger'],),
                                daemon=True
                            ).start()
                        except Exception as exc:
                            logger.warning('cron 触发失败 %s: %s',
                                           job['trigger'].action_id, exc)

            # 睡眠到下一分钟
            time.sleep(60 - time.localtime().tm_sec)


# ── 文件监控器 ──

class FileWatcher:
    """文件/文件夹监控器。

    使用轮询 + mtime 检测文件变化（跨平台，零依赖）。
    """

    def __init__(self, poll_interval: float = 1.0, watch_root: Optional[str] = None):
        self._poll_interval = poll_interval
        self._watch_root = watch_root
        self._watches: List[dict] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._file_states: Dict[str, float] = {}  # path -> mtime

    def add(self, trigger: Trigger, callback: Callable):
        """添加监控任务。

        消费点复查（#9）：注册期可能用模板占位符跳过校验，运行时若已是具体
        路径，必须在真正 `os.scandir` 前再校验一次；同时把相对路径按 watch_root
        展开，避免「校验的是 root/rel、实际扫的是 cwd/rel」两套真源。
        """
        if trigger.ttype == 'watch':
            err = validate_watch_path(trigger.path, self._watch_root,
                                      trigger.allow_outside_root)
            if err:
                raise ValueError(f'watch 触发器 path 非法: {err}')
            if '${' not in trigger.path and not os.path.isabs(trigger.path):
                trigger.path = os.path.join(
                    self._watch_root or _default_watch_root(), trigger.path)
        with self._lock:
            self._watches.append({
                'trigger': trigger,
                'callback': callback,
                'debounce_until': 0.0,
            })

    def remove(self, action_id: str):
        """移除指定动作的监控任务。"""
        with self._lock:
            self._watches = [w for w in self._watches
                            if w['trigger'].action_id != action_id]

    def start(self):
        """启动监控。"""
        if self._running:
            return
        self._running = True
        # 初始化文件状态
        self._init_states()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止监控。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _init_states(self):
        """初始化文件状态快照。"""
        with self._lock:
            for watch in self._watches:
                path = watch['trigger'].path
                if os.path.exists(path):
                    if os.path.isdir(path):
                        self._scan_dir(path, watch['trigger'].recursive)
                    else:
                        self._file_states[path] = self._get_mtime(path)

    def _scan_dir(self, dir_path: str, recursive: bool,
                  out: Optional[dict] = None):
        """扫描目录获取所有文件的 mtime。

        `out` 允许传入一次性快照字典（`_detect_changes` 用）；不传则写
        `self._file_states`（`_init_states` 用）。**只增不删是 #1 的根因**：
        删除检测必须基于"本次快照"，不能基于从未清理过的全局状态。
        """
        target = self._file_states if out is None else out
        try:
            for entry in os.scandir(dir_path):
                if entry.is_file():
                    target[entry.path] = entry.stat().st_mtime
                elif recursive and entry.is_dir():
                    self._scan_dir(entry.path, recursive, target)
        except PermissionError:
            pass

    @staticmethod
    def _get_mtime(path: str) -> float:
        try:
            return os.stat(path).st_mtime
        except OSError:
            return 0.0

    def _loop(self):
        """监控主循环。"""
        while self._running:
            self._check()
            time.sleep(self._poll_interval)

    def _check(self):
        """检查所有监控任务的文件变化。"""
        now = time.time()

        with self._lock:
            for watch in self._watches:
                trigger = watch['trigger']

                # 防抖
                if now < watch['debounce_until']:
                    continue

                changes = self._detect_changes(trigger)
                if changes:
                    watch['debounce_until'] = now + trigger.debounce_ms / 1000.0
                    try:
                        threading.Thread(
                            target=watch['callback'],
                            args=(trigger, changes),
                            daemon=True
                        ).start()
                    except Exception as exc:
                        logger.warning('watch 触发失败 %s: %s',
                                       trigger.action_id, exc)

    def _detect_changes(self, trigger: Trigger) -> List[dict]:
        """检测文件变化，返回变化列表。"""
        path = trigger.path
        changes = []

        # 先保存旧状态快照
        old_states = dict(self._file_states)

        if os.path.isdir(path):
            # 本次快照（不读全局 _file_states：它只增不删，会让删除检测失效）
            current_states = {}
            self._scan_dir(path, trigger.recursive, current_states)
        elif os.path.isfile(path):
            mtime = self._get_mtime(path)
            current_states = {path: mtime}
        else:
            current_states = {}

        # 检测新增和修改（用 old_states 判断）
        for fp, mtime in current_states.items():
            old_mtime = old_states.get(fp, 0)
            if old_mtime == 0 and 'create' in trigger.events:
                changes.append({'type': 'create', 'path': fp})
            elif mtime > old_mtime and 'modify' in trigger.events:
                changes.append({'type': 'modify', 'path': fp})

        # 删除检测只在本 watch 根下进行（防止 A watch 删除 B watch 的文件时
        # 给 A 误报；此前用全局 old_states 判会把别人的文件也算进来）。
        root_abs = os.path.normcase(os.path.abspath(path))

        def _under_watch(fp: str) -> bool:
            fp_abs = os.path.normcase(os.path.abspath(fp))
            return fp_abs == root_abs or fp_abs.startswith(root_abs + os.sep)

        if 'delete' in trigger.events:
            for fp in list(old_states.keys()):
                if _under_watch(fp) and fp not in current_states \
                        and not os.path.exists(fp):
                    changes.append({'type': 'delete', 'path': fp})
                    self._file_states.pop(fp, None)

        # 更新状态：本 watch 根下的陈旧项也清掉，避免 _file_states 无限增长
        for fp in list(self._file_states):
            if _under_watch(fp) and fp not in current_states:
                self._file_states.pop(fp, None)
        self._file_states.update(current_states)
        return changes


# ── 触发器引擎（统一入口） ──

# ── 全局热键监听器 ──

class HotkeyListener:
    """全局热键触发器（Windows）。

    底座 = user32.GetAsyncKeyState 轮询（与 vools _PollingKeyboardBackend
    同一 API，零 vools 依赖，绕过 RegisterHotKey 的 ctypes 兼容性问题）。
    用 50ms 轮询窗口跟踪修饰键状态，主键按下且全部修饰键就位时触发。

    语义：
    - add() 仅入队；start() 才启动轮询线程（与 cron/watch 同语义）；
    - 非 win32 平台：start 时对每个热键记录 error，不抛出；
    - 同一热键主键释放前不重复触发（MOD_NOREPEAT 等价）；
    - 同一热键回调未结束前的重复触发被丢弃（防弹窗堆积）；
    - 回调在独立 daemon 线程执行（不阻塞轮询线程）。
    """

    POLL_INTERVAL = 0.05  # 50ms，与 vools polling backend 对齐
    VK_MOD_MAP = {
        'ctrl': 0x11, 'control': 0x11,   # VK_CONTROL
        'alt': 0x12, 'menu': 0x12,        # VK_MENU
        'shift': 0x10,                     # VK_SHIFT
        'win': 0x5B, 'lwin': 0x5B, 'rwin': 0x5C, 'meta': 0x5B,
        'cmd': 0x5B,
    }

    def __init__(self):
        self._entries: List[dict] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._inflight: Dict[int, bool] = {}
        # 防抖：每 entry 记录上一周期主键是否已按下
        self._key_was_down: Dict[int, bool] = {}

    # ── 组合键解析 ──

    @classmethod
    def parse_combo(cls, key: str):
        """'ctrl+alt+k' → (mod_vks: list, main_vk: int, 错误列表)。"""
        errors = []
        if not key or not isinstance(key, str):
            return [], 0, ['热键组合为空']
        parts = [p.strip().lower() for p in key.split('+') if p.strip()]
        if not parts:
            return [], 0, [f'热键组合非法: {key!r}']
        try:
            from vools.reactive.monitoring.keyboard import _name_to_vk_code
        except Exception as e:
            return [], 0, [f'vools 键盘底座不可用: {e}']
        mod_vks = []
        for p in parts[:-1]:
            vk = cls.VK_MOD_MAP.get(p)
            if vk is None:
                errors.append(f'未知修饰键: {p}')
            elif vk not in mod_vks:
                mod_vks.append(vk)
        main_vk = _name_to_vk_code(parts[-1])
        if not main_vk:
            errors.append(f'未知主键: {parts[-1]}')
        return mod_vks, main_vk, errors

    # ── 管理接口 ──

    def add(self, trigger: Trigger, callback: Callable):
        mod_vks, main_vk, errors = self.parse_combo(trigger.key or '')
        with self._lock:
            self._entries.append({
                'trigger': trigger, 'callback': callback,
                'mod_vks': mod_vks, 'main_vk': main_vk,
                'errors': errors, 'armed': False,
            })
        return errors

    def remove(self, action_id: str):
        with self._lock:
            self._entries = [e for e in self._entries
                           if e['trigger'].action_id != action_id]

    def start(self):
        if self._running:
            return
        if sys.platform != 'win32':
            with self._lock:
                for e in self._entries:
                    if not e['errors']:
                        e['errors'] = ['热键监听仅支持 Windows']
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        with self._lock:
            self._entries.clear()
            self._key_was_down.clear()
            self._inflight.clear()

    def status(self) -> dict:
        with self._lock:
            return {
                'hotkeys': len(self._entries),
                'armed': sum(1 for e in self._entries if not e['errors']),
                'errors': sum(1 for e in self._entries if e['errors']),
                'running': self._running,
            }

    # ── 轮询线程 ──

    def _poll_loop(self):
        import ctypes
        _GetAsyncKeyState = ctypes.windll.user32.GetAsyncKeyState
        while self._running:
            with self._lock:
                entries = list(enumerate(self._entries))
            for idx, e in entries:
                if e['errors'] or not e['main_vk']:
                    continue
                # 修饰键全部就位？
                all_mods = all(_GetAsyncKeyState(vk) & 0x8000
                               for vk in e['mod_vks'])
                key_down = bool(_GetAsyncKeyState(e['main_vk']) & 0x8000)
                was_down = self._key_was_down.get(idx, False)
                self._key_was_down[idx] = key_down
                # 下降沿：刚按下 → 触发（防抖）
                if key_down and not was_down and all_mods:
                    self._fire(idx)
            time.sleep(self.POLL_INTERVAL)

    def _fire(self, idx: int):
        with self._lock:
            if self._inflight.get(idx):
                return
            self._inflight[idx] = True
            e = self._entries[idx] if idx < len(self._entries) else None
        if e is None:
            return

        def _run():
            try:
                e['callback'](e['trigger'])
            except Exception as exc:
                logger.warning('hotkey 触发失败 %s: %s',
                               e['trigger'].action_id, exc)
            finally:
                with self._lock:
                    self._inflight[idx] = False

        try:
            threading.Thread(target=_run, daemon=True).start()
        except Exception as exc:
            with self._lock:
                self._inflight[idx] = False
            logger.warning('hotkey 触发线程启动失败 %s: %s',
                           e['trigger'].action_id, exc)


class TriggerEngine:
    """触发器引擎：统一管理所有触发器类型。

    用法：
        engine = TriggerEngine(executor)
        engine.load_from_index(meta_dir)
        engine.start()
        # ...
        engine.stop()
    """

    def __init__(self, executor: Callable, meta_dir: str = '',
                 watch_root: Optional[str] = None):
        """
        参数:
            executor: 回调函数 (trigger, event) -> None
            meta_dir: 仓库 _meta 目录。
            watch_root: watch 触发器允许的根（缺省 paths.repo_root()；#9）。
        """
        self._executor = executor
        self._meta_dir = meta_dir
        self._watch_root = watch_root
        self._cron = CronScheduler()
        self._watcher = FileWatcher(watch_root=watch_root)
        self._hotkeys = HotkeyListener()
        self._webhooks = None  # lazy: WebhookServer 创建时注入
        self._webhook_error: Optional[str] = None  # #5：依赖缺失原因，供 add_trigger 报错
        self._triggers: Dict[str, List[Trigger]] = {}

    def add_trigger(self, trigger: Trigger, _persist: bool = True):
        """添加单个触发器（默认持久化到注册表；内部加载传 _persist=False）。

        **顺序很关键（#4）**：先让子调度器注册/校验，全部成功后才写入
        `self._triggers`。旧实现先 append 再校验，非法 cron 抛错后会留下
        "幽灵触发器"（status 计数含它、后续 save_registry 还会把非法配置写盘）。
        """
        if trigger.ttype == 'cron':
            self._cron.add(trigger, self._executor)
        elif trigger.ttype == 'watch':
            # #9：注册期先校验（load_registry/load_from_index 也走这里，防绕过
            # validate_trigger）；越界直接拒绝，必须显式 allow_outside_root。
            err = validate_watch_path(trigger.path, self._watch_root,
                                      trigger.allow_outside_root)
            if err:
                raise ValueError(f'watch 触发器 path 非法: {err}')
            self._watcher.add(trigger, self._executor)
        elif trigger.ttype == 'hotkey':
            self._hotkeys.add(trigger, self._executor)
        elif trigger.ttype == 'webhook':
            if self._webhooks is None:
                self._init_webhooks()
            if self._webhooks is None:
                raise RuntimeError(self._webhook_error
                                   or 'webhook 支持不可用（依赖缺失）')
            self._webhooks.add(trigger, self._executor)
        # on_startup 由 start() 处理
        self._triggers.setdefault(trigger.action_id, []).append(trigger)
        if _persist:
            self.save_registry()

    def remove_trigger(self, action_id: str):
        """移除指定动作的所有触发器。"""
        self._triggers.pop(action_id, None)
        self._cron.remove(action_id)
        self._watcher.remove(action_id)
        self._hotkeys.remove(action_id)
        if self._webhooks is not None:
            self._webhooks.remove(action_id)
        self.save_registry()

    # ── 注册表持久化（_meta/triggers.json，CLI 与 MCP 共享同一份）──

    @property
    def registry_path(self) -> str:
        return os.path.join(self._meta_dir, 'triggers.json')

    def save_registry(self):
        """把运行时触发器写入注册表（meta_dir 为空或不可写时静默跳过）。"""
        if not self._meta_dir:
            return
        data = {aid: [t.config for t in ts]
                for aid, ts in self._triggers.items()}
        try:
            os.makedirs(self._meta_dir, exist_ok=True)
            with open(self.registry_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def load_registry(self):
        """从注册表加载动态注册的触发器（已存在的 action 不覆盖）。"""
        path = self.registry_path
        if not os.path.isfile(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f) or {}
        except (OSError, ValueError):
            return
        for aid, cfgs in data.items():
            if aid in self._triggers:
                continue
            for cfg in cfgs or []:
                try:
                    self.add_trigger(Trigger(aid, cfg), _persist=False)
                except Exception:
                    pass

    def load_from_index(self, meta_dir: str = ''):
        """从索引加载所有带 triggers 的动作。"""
        if meta_dir:
            self._meta_dir = meta_dir

        index_path = os.path.join(self._meta_dir, 'actions.index.json')
        if not os.path.isfile(index_path):
            return

        with open(index_path, 'r', encoding='utf-8') as f:
            index = json.load(f)

        for aid, info in index.get('actions', {}).items():
            triggers_raw = info.get('triggers', []) or []
            for t_config in triggers_raw:
                # 单条坏配置只跳过自己并留 warning；旧实现一条坏就中止全部，
                # 且中止前已部分载入（幽灵项）—— 与 load_registry 的逐条语义不一致。
                try:
                    self.add_trigger(Trigger(aid, t_config))
                except Exception as exc:
                    logger.warning('load_from_index: 跳过非法触发器 %s: %s',
                                   aid, exc)

    def _init_webhooks(self):
        """懒初始化 WebhookServer（首次注册 webhook 触发器时创建）。"""
        if self._webhooks is not None:
            return
        try:
            from .webhook_server import WebhookServer
            self._webhooks = WebhookServer()
            self._webhook_error = None
        except Exception as exc:
            # 依赖缺失时不阻断引擎，但**必须保留可读原因**：add_trigger 要用它
            # 抛 RuntimeError，而不是让调用方撞 None.add 的 AttributeError。
            self._webhooks = None
            self._webhook_error = f'webhook 支持不可用：{exc}'
            logger.warning(self._webhook_error)

    def start(self):
        """启动引擎。"""
        self._cron.start()
        self._watcher.start()
        self._hotkeys.start()
        if self._webhooks is not None:
            self._webhooks.start()

        # 触发 on_startup
        for triggers in self._triggers.values():
            for t in triggers:
                if t.ttype == 'on_startup':
                    try:
                        threading.Thread(
                            target=self._executor,
                            args=(t,),
                            daemon=True
                        ).start()
                    except Exception as exc:
                        logger.warning('on_startup 触发失败 %s: %s',
                                       t.action_id, exc)

    def stop(self):
        """停止引擎。"""
        self._cron.stop()
        self._watcher.stop()
        self._hotkeys.stop()
        if self._webhooks is not None:
            self._webhooks.stop()

    def status(self) -> dict:
        """获取引擎状态。"""
        return {
            'cron_jobs': len(self._cron._jobs),
            'watch_tasks': len(self._watcher._watches),
            'hotkeys': self._hotkeys.status(),
            'webhooks': self._webhooks.status() if self._webhooks else {},
            'total_triggers': sum(len(v) for v in self._triggers.values()),
        }


# ── 辅助函数 ──

def parse_triggers(action_meta: dict, action_id: str = '') -> List[Trigger]:
    """从动作元数据解析触发器列表。"""
    raw = action_meta.get('triggers', [])
    return [Trigger(action_id, t) for t in raw]


def validate_trigger(config: dict, root: Optional[str] = None) -> List[str]:
    """校验单个触发器配置。

    root：watch 路径允许的根（缺省 paths.repo_root()）；显式传 tmp 根即可
    在隔离环境里验证 #9 的越界规则。
    """
    errors = []
    ttype = config.get('type', '')
    valid_types = ('cron', 'watch', 'webhook', 'hotkey', 'on_startup')
    if ttype not in valid_types:
        errors.append(f'触发器类型非法: {ttype}')
        return errors

    if ttype == 'cron':
        if 'expr' not in config:
            errors.append('cron 触发器缺少 expr')
        else:
            try:
                CronExpr(config['expr'])
            except ValueError as e:
                errors.append(f'cron 表达式错误: {e}')

    elif ttype == 'watch':
        if 'path' not in config:
            errors.append('watch 触发器缺少 path')
        else:
            err = validate_watch_path(
                config.get('path'), root,
                bool(config.get('allow_outside_root', False)))
            if err:
                errors.append(f'watch 路径非法: {err}')

    elif ttype == 'hotkey':
        if 'key' not in config:
            errors.append('hotkey 触发器缺少 key')

    elif ttype == 'webhook':
        if 'key' not in config:
            errors.append('webhook 触发器缺少 key（event_type）')

    return errors
