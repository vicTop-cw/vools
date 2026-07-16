"""
vools.bridge.core.tracker - 编译记录追踪器

基于 SQLite 数据库管理编译记录，支持代码变更检测。
"""

import os
import sys
import time
import json
import hashlib
import sqlite3
import threading
import inspect

# 兼容 Python 3.6
if sys.version_info >= (3, 7):
    from datetime import datetime, timezone
else:
    from datetime import datetime


class CompileTracker:
    """编译记录追踪器。

    使用 SQLite 数据库记录每次编译的元信息（源码 MD5、编译产物路径、编译时间等）。
    支持基于 record_key 的代码变更检测，用于 WHEN_CHANGE_JUST / WHEN_CHANGE_AND_RUN 模式。

    数据库位置：
        Windows: %LOCALAPPDATA%/vools/bridge_records.db
        Linux/macOS: ~/.local/share/vools/bridge_records.db

    用法：
        tracker = CompileTracker()
        record = tracker.get_record('mymodule:add_numbers')
        if tracker.is_changed('mymodule:add_numbers', source_md5):
            # 需要重新编译
            tracker.upsert_record('mymodule:add_numbers', { ... })
    """

    def __init__(self, db_path=None):
        """初始化编译记录追踪器。

        参数：
            db_path: 数据库文件路径，为 None 时使用默认路径。
        """
        if db_path is None:
            db_path = self._default_db_path()
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_db()

    @staticmethod
    def _default_db_path():
        """获取默认数据库文件路径。"""
        if os.name == 'nt':
            base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        else:
            base = os.environ.get('XDG_DATA_HOME',
                                  os.path.join(os.path.expanduser('~'), '.local', 'share'))
        data_dir = os.path.join(base, 'vools')
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        return os.path.join(data_dir, 'bridge_records.db')

    def _ensure_db(self):
        """确保数据库和表结构存在。"""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS compile_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        record_key TEXT NOT NULL UNIQUE,
                        language TEXT NOT NULL,
                        lang_type TEXT NOT NULL DEFAULT 'compiled',
                        func_name TEXT NOT NULL,
                        source_md5 TEXT NOT NULL,
                        source_path TEXT DEFAULT '',
                        lib_path TEXT DEFAULT '',
                        compile_mode TEXT NOT NULL,
                        compiled_at TEXT NOT NULL,
                        compile_duration_ms INTEGER DEFAULT 0,
                        python_module TEXT DEFAULT '',
                        python_file TEXT DEFAULT '',
                        extra TEXT DEFAULT '{}'
                    )
                ''')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS language_registry (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        language TEXT NOT NULL UNIQUE,
                        lang_type TEXT NOT NULL,
                        compiler_path TEXT DEFAULT '',
                        compiler_version TEXT DEFAULT '',
                        is_available INTEGER DEFAULT 0,
                        last_checked TEXT DEFAULT '',
                        extra TEXT DEFAULT '{}'
                    )
                ''')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS compile_errors (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        record_key TEXT NOT NULL,
                        error_message TEXT DEFAULT '',
                        error_code INTEGER DEFAULT 0,
                        occurred_at TEXT NOT NULL,
                        extra TEXT DEFAULT '{}'
                    )
                ''')
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_record_key
                    ON compile_records(record_key)
                ''')
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_language
                    ON compile_records(language)
                ''')
                conn.commit()
            finally:
                conn.close()

    @staticmethod
    def _now_iso():
        """获取当前时间的 ISO 格式字符串。"""
        if sys.version_info >= (3, 7):
            return datetime.now(timezone.utc).isoformat()
        else:
            return datetime.utcnow().isoformat() + 'Z'

    @staticmethod
    def make_record_key(func):
        """从被装饰的函数生成 record_key。

        key 格式：{module}:{qualname}
        示例：mypackage.utils.math:add_numbers

        参数：
            func: 被装饰的 Python 函数对象。

        返回：
            str: record_key 字符串。
        """
        module = getattr(func, '__module__', '__main__')
        qualname = getattr(func, '__qualname__', func.__name__)
        return '{}:{}'.format(module, qualname)

    def get_record(self, record_key):
        """查询指定 record_key 的编译记录。

        参数：
            record_key: 唯一标识。

        返回：
            dict 或 None: 记录字典，不存在时返回 None。
        """
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    'SELECT * FROM compile_records WHERE record_key = ?',
                    (record_key,)
                ).fetchone()
                if row is None:
                    return None
                return dict(row)
            finally:
                conn.close()

    def upsert_record(self, record_key, **fields):
        """插入或更新编译记录。

        参数：
            record_key: 唯一标识。
            **fields: 要更新的字段（language, lang_type, func_name, source_md5,
                      source_path, lib_path, compile_mode, compile_duration_ms,
                      python_module, python_file, extra）。
        """
        # 使用 INSERT OR REPLACE 避免并发竞态
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                compiled_at = self._now_iso()
                conn.execute(
                    '''INSERT OR REPLACE INTO compile_records
                       (record_key, language, lang_type, func_name,
                        source_md5, source_path, lib_path, compile_mode,
                        compiled_at, compile_duration_ms,
                        python_module, python_file, extra)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        record_key,
                        fields.get('language', ''),
                        fields.get('lang_type', 'compiled'),
                        fields.get('func_name', ''),
                        fields.get('source_md5', ''),
                        fields.get('source_path', ''),
                        fields.get('lib_path', ''),
                        fields.get('compile_mode', 'NORMAL'),
                        compiled_at,
                        fields.get('compile_duration_ms', 0),
                        fields.get('python_module', ''),
                        fields.get('python_file', ''),
                        json.dumps(fields.get('extra', {}), ensure_ascii=False),
                    )
                )
                conn.commit()
            finally:
                conn.close()

    def is_changed(self, record_key, source_md5):
        """检查代码是否发生变更。

        对比数据库中的 source_md5 与当前传入的 source_md5。

        参数：
            record_key: 唯一标识。
            source_md5: 当前源码的 MD5 哈希值。

        返回：
            bool: True 表示代码已变更或不存在记录（需要重新编译）。
        """
        record = self.get_record(record_key)
        if record is None:
            return True
        return record.get('source_md5', '') != source_md5

    def log_error(self, record_key, error_message, error_code=0):
        """记录编译错误。

        参数：
            record_key: 关联的编译记录 key。
            error_message: 错误信息。
            error_code: 错误码。
        """
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                conn.execute(
                    '''INSERT INTO compile_errors
                       (record_key, error_message, error_code, occurred_at)
                       VALUES (?, ?, ?, ?)''',
                    (record_key, error_message, error_code, self._now_iso())
                )
                conn.commit()
            finally:
                conn.close()

    def get_db_path(self):
        """获取数据库文件路径。"""
        return self._db_path

    def close(self):
        """关闭数据库连接（SQLite 在每次操作后自动关闭，此方法保留用于显式清理）。"""
        pass


# 全局单例
_default_tracker = None
_tracker_lock = threading.Lock()


def get_tracker():
    """获取全局 CompileTracker 单例。"""
    global _default_tracker
    if _default_tracker is None:
        with _tracker_lock:
            if _default_tracker is None:
                _default_tracker = CompileTracker()
    return _default_tracker