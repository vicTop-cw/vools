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
    'parse_triggers',
    'validate_trigger',
]

import os
import re
import threading
import time
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
        """解析单个 cron 字段。"""
        min_val, max_val = value_range
        values = set()

        for part in field.split(','):
            # 步进 /
            if '/' in part:
                range_part, step = part.split('/', 1)
                step = int(step)
                if range_part == '*':
                    start, end = min_val, max_val
                elif '-' in range_part:
                    start, end = map(int, range_part.split('-', 1))
                else:
                    start = int(range_part)
                    end = max_val
                for v in range(start, end + 1, step):
                    values.add(v)
            # 范围 -
            elif '-' in part:
                start, end = map(int, part.split('-', 1))
                for v in range(start, end + 1):
                    values.add(v)
            # 通配 *
            elif part == '*':
                for v in range(min_val, max_val + 1):
                    values.add(v)
            # 具体值
            else:
                values.add(int(part))

        # 校验范围
        for v in values:
            if v < min_val or v > max_val:
                raise ValueError(f'值 {v} 超出范围 [{min_val}, {max_val}]')
        return values

    def matches(self, t: time.struct_time) -> bool:
        """检查时间是否匹配 cron 表达式。"""
        checks = [
            t.tm_min in self.fields[0],
            t.tm_hour in self.fields[1],
            t.tm_mday in self.fields[2],
            t.tm_mon in self.fields[3],
            t.tm_wday in self.fields[4],
        ]
        return all(checks)

    def next_fire(self, after: Optional[float] = None) -> float:
        """计算下一次触发时间（Unix 时间戳）。"""
        if after is None:
            after = time.time()
        t = time.localtime(after + 1)  # 至少 1 秒后

        # 向前搜索，最多 4 年
        for _ in range(366 * 24 * 60 * 4):
            if self.matches(t):
                return time.mktime(t)
            # 增加 1 分钟
            t = time.localtime(time.mktime(t) + 60)
        return after + 60  # 兜底


# ── 触发器模型 ──

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
                        except Exception:
                            pass  # 触发失败不影响调度器

            # 睡眠到下一分钟
            time.sleep(60 - time.localtime().tm_sec)


# ── 文件监控器 ──

class FileWatcher:
    """文件/文件夹监控器。

    使用轮询 + mtime 检测文件变化（跨平台，零依赖）。
    """

    def __init__(self, poll_interval: float = 1.0):
        self._poll_interval = poll_interval
        self._watches: List[dict] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._file_states: Dict[str, float] = {}  # path -> mtime

    def add(self, trigger: Trigger, callback: Callable):
        """添加监控任务。"""
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

    def _scan_dir(self, dir_path: str, recursive: bool):
        """扫描目录获取所有文件的 mtime。"""
        try:
            for entry in os.scandir(dir_path):
                if entry.is_file():
                    self._file_states[entry.path] = entry.stat().st_mtime
                elif recursive and entry.is_dir():
                    self._scan_dir(entry.path, recursive)
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
                    except Exception:
                        pass

    def _detect_changes(self, trigger: Trigger) -> List[dict]:
        """检测文件变化，返回变化列表。"""
        path = trigger.path
        changes = []

        # 先保存旧状态快照
        old_states = dict(self._file_states)

        if os.path.isdir(path):
            # 扫描更新 _file_states
            self._scan_dir(path, trigger.recursive)
            current_states = dict(self._file_states)
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

        # 检测删除
        if 'delete' in trigger.events:
            for fp in list(old_states.keys()):
                if fp not in current_states and not os.path.exists(fp):
                    changes.append({'type': 'delete', 'path': fp})
                    self._file_states.pop(fp, None)

        # 更新状态
        self._file_states.update(current_states)
        return changes


# ── 触发器引擎（统一入口） ──

class TriggerEngine:
    """触发器引擎：统一管理所有触发器类型。

    用法：
        engine = TriggerEngine(executor)
        engine.load_from_index(meta_dir)
        engine.start()
        # ...
        engine.stop()
    """

    def __init__(self, executor: Callable, meta_dir: str = ''):
        """
        参数:
            executor: 回调函数 (trigger, event) -> None
            meta_dir: 仓库 _meta 目录。
        """
        self._executor = executor
        self._meta_dir = meta_dir
        self._cron = CronScheduler()
        self._watcher = FileWatcher()
        self._triggers: Dict[str, List[Trigger]] = {}

    def add_trigger(self, trigger: Trigger):
        """添加单个触发器。"""
        if trigger.action_id not in self._triggers:
            self._triggers[trigger.action_id] = []
        self._triggers[trigger.action_id].append(trigger)

        if trigger.ttype == 'cron':
            self._cron.add(trigger, self._executor)
        elif trigger.ttype == 'watch':
            self._watcher.add(trigger, self._executor)
        # webhook / hotkey / on_startup 由上层处理

    def remove_trigger(self, action_id: str):
        """移除指定动作的所有触发器。"""
        self._triggers.pop(action_id, None)
        self._cron.remove(action_id)
        self._watcher.remove(action_id)

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
            triggers_raw = info.get('triggers', [])
            if triggers_raw:
                for t_config in triggers_raw:
                    trigger = Trigger(aid, t_config)
                    self.add_trigger(trigger)

    def start(self):
        """启动引擎。"""
        self._cron.start()
        self._watcher.start()

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
                    except Exception:
                        pass

    def stop(self):
        """停止引擎。"""
        self._cron.stop()
        self._watcher.stop()

    def status(self) -> dict:
        """获取引擎状态。"""
        return {
            'cron_jobs': len(self._cron._jobs),
            'watch_tasks': len(self._watcher._watches),
            'total_triggers': sum(len(v) for v in self._triggers.values()),
        }


# ── 辅助函数 ──

def parse_triggers(action_meta: dict, action_id: str = '') -> List[Trigger]:
    """从动作元数据解析触发器列表。"""
    raw = action_meta.get('triggers', [])
    return [Trigger(action_id, t) for t in raw]


def validate_trigger(config: dict) -> List[str]:
    """校验单个触发器配置。"""
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

    elif ttype == 'hotkey':
        if 'key' not in config:
            errors.append('hotkey 触发器缺少 key')

    return errors
