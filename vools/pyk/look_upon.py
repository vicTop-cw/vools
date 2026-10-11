import contextlib
import time
import re
import os
import logging
from pyspark.sql import SparkSession,DataFrame
import copy
from typing import List, Any, Optional, Callable, Dict
from functools import partial,wraps

# pyk 内部依赖（双路径 import：既可作 vools.pyk.look_upon 用，也可被外部直接 import）
try:
    from .configs import pg_credentials, upon_sql_file, share_dir
    from .core import get_spark
    from ..data.vtext import VText as _VText
    from ..data.vtext import VText as _vicText
    from ..data.vtext import VText as _get_content_wrapper
except ImportError:  # pragma: no cover - 外部独立运行 fallback
    from vools.pyk.configs import pg_credentials, upon_sql_file, share_dir
    from vools.pyk.core import get_spark
    from vools.data.vtext import VText as _VText
    from vools.data.vtext import VText as _vicText
    from vools.data.vtext import VText as _get_content_wrapper


def _get_content(file_path: str):
    """legacy get_content 兼容：返回带 .text 的 VText。"""
    return _VText(_VText.get_content_fromfile(file_path=file_path, to_text=True))


import json as _json  # noqa: E402


def payload_encode(data: Optional[dict]) -> str:
    """把 dict 编码成 JSON 字符串（用于写入 look_upon 表的 payload JSONB 列）。

    规则（业务约定）：
    - key 保留明文；
    - value 用 ``VText.toZipB64`` 压缩编码（返回 "Z:..." 或 "R:..."），
      这样大文本 / 含特殊字符的任务参数也能安全塞进 JSONB。

    Args:
        data: dict；None 返回 "{}"。

    Returns:
        JSON 字符串，如 ``{"sql": "Z:xxxx", "ds": "Z:yyy"}``。
    """
    if not data:
        return "{}"
    out = {}
    for k, v in data.items():
        if v is None:
            raw = ""
        elif isinstance(v, str):
            raw = v
        else:
            # 非字符串 value（int/float/list/dict）统一 JSON 序列化后再压缩
            raw = _json.dumps(v, ensure_ascii=False)
        out[k] = str(_VText(raw).toZipB64())
    return _json.dumps(out, ensure_ascii=False)


def payload_decode(raw: Any) -> dict:
    """把 payload JSONB 内容解回 dict。

    兼容三种形态：
    - 已解析的 dict（psycopg2 JSONB）；
    - dict 的 list/tuple 包装（[ {...} ]）；
    - JSON 字符串（JVM JDBC getString 常见返回）。

    Returns:
        dict，value 已用 ``unZipB64`` 还原为原文。
    """
    data = raw
    if isinstance(data, (list, tuple)):
        data = data[0] if data else None
    if isinstance(data, str):
        try:
            data = _json.loads(data)
        except Exception:
            return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        out[k] = str(_VText("" if v is None else str(v)).unZipB64())
    return out
__all__ = ["TaskFunctionError", "TaskAlreadyLocked", "MaxRetriesExceeded", "LookUpon",'LU',"init_tasks","add_tasks","query_tasks","run_until_done",'get_replaced_sql','run_done','run_doneEx','reset_tasks','update_failed_to_pending', "payload_encode", "payload_decode"]
# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
class TaskFunctionError(Exception):    
    """任务函数执行异常"""    
    pass
class TaskAlreadyLocked(Exception):
    """任务已被锁定异常"""
    pass

class MaxRetriesExceeded(Exception):
    """任务重试次数超过上限异常"""
    pass

class LookUpon:
    def __init__(self, task_function: Callable[[str], Any], dbtable: str, 
                 init: bool = False, tasks: Optional[List[str]] = None,
                 url: Optional[str] = None, user: Optional[str] = None, 
                 password: Optional[str] = None, driver: Optional[str] = None, 
                 spark: Optional[SparkSession] = None, dbName: str = "public",
                 max_retries: int = 3, retry_delay_min: int = 5, drop_if_exists: bool = False):
        """
        spark: SparkSession 实例
        task_function: 用户提供的单参数函数，接受任务值作为参数
        dbtable: 数据库表名
        url: JDBC 连接URL
        user: 数据库用户名
        password: 数据库密码
        dbName: 数据库名 (默认public)
        init: 是否初始化表
        tasks: 初始任务列表
        max_retries: 任务最大重试次数
        retry_delay_min: 重试延迟时间(分钟)
        """
        # 配置Spark会话
        self.spark = spark or self.__class__._get_spark_session()
        
        self.task_function = task_function
        dct = self.__class__._get_default_properties()
        self.url = url or dct.get("url")
        self.user = user or dct.get("user")
        self.password = password or dct.get("password")
        self.driver = driver or dct.get("driver")
        self.dbName = dbName
        self.max_retries = max_retries
        self.retry_delay_min = retry_delay_min
        
        # 获取JVM环境
        self.jvm = self.spark.sparkContext._gateway.jvm
        self.jvm.Class.forName(self.driver)
        self._conn = None
        # 处理dbtable格式
        if '.' in dbtable:
            self.dbtable = dbtable
        else:
            self.dbtable = f"{self.dbName}.{dbtable}"
        
        # 初始化数据库表
        if init:
            if drop_if_exists:
                self.drop()
            self._init_table()
            if tasks:
                self.add_tasks(tasks)
        
        self._conn = None
        
    def drop(self):
        """删除任务表"""
        sql = f"DROP TABLE IF EXISTS {self.dbtable}"
        self._execute_sql(sql, commit=True)
        logger.info(f"删除表 {self.dbtable} 成功")
    
    def execute_sql(self, sql: str, params: Optional[List[Any]] = None) -> Any:
        """执行SQL语句,自动提交"""
        results = self._execute_sql(sql, params, commit=True)
        if len(results) == 1:
            return results[0]
        return results
    
    @property
    def properties(self) -> Dict[str, str]:
        """获取数据库连接属性"""
        return {
            "url": self.url,
            "user": self.user,
            "password": self.password,
            "driver": self.driver  
        }
        
    def query(self, sql: str = "") -> Any:
        """执行查询并返回DataFrame"""
        # 处理不同形式的表名
        if not sql:
            sql = f"SELECT * FROM {self.dbtable}"
        
        # 简化表名查询
        if re.match(r"^[a-z][a-z_0-9]+\.[a-z_0-9]+$", sql.lower()):
            sql = f"SELECT * FROM {sql}"
        elif re.match(r"^[a-z][a-z_0-9]+$", sql.lower()):
            sql = f"SELECT * FROM public.{sql}"
        
        properties = copy.deepcopy(self.properties)
        properties["query"] = sql
        return self.spark.read.format("jdbc").options(**properties).load()
    
    def _result_set_to_list(self, result_set) -> list:
        """将JDBC ResultSet转换为Python列表"""
        try:
            meta_data = result_set.getMetaData()
            column_count = meta_data.getColumnCount()
            
            results = []
            while result_set.next():
                row = []
                for i in range(1, column_count + 1):
                    value = result_set.getObject(i)
                    row.append(value)
                results.append(row)
            
            return results
        except Exception as e:
            logger.error(f"结果集转换失败: {str(e)}")
            return []
    
    def _get_connection(self):
        """获取数据库连接（直接连接）"""
        try:
            if not self._conn or self._conn.isClosed():
                conn = self.jvm.java.sql.DriverManager.getConnection(
                    self.url, self.user, self.password)
                logger.debug("获取数据库连接成功")
                self._conn = conn
                return conn
            return self._conn
        except Exception as e:
            logger.error(f"获取数据库连接失败: {str(e)}")
            raise e
    
    def _execute_sql(self, sql: str, params: Optional[List[Any]] = None, 
                commit: bool = False) -> List[Any]:
        """安全执行SQL语句并返回结果"""
        conn = None
        try:
            conn = self._get_connection()
            conn.setAutoCommit(False)
            
            results = []
            
            # 检查是否有参数
            if params and len(params) > 0:
                # 使用参数化查询
                stmt = conn.prepareStatement(sql)
                
                # 绑定参数
                for i, param in enumerate(params, 1):
                    if isinstance(param, str):
                        stmt.setString(i, param)
                    elif isinstance(param, int):
                        stmt.setInt(i, param)
                    elif isinstance(param, float):
                        stmt.setDouble(i, param)
                    else:
                        stmt.setObject(i, param)
                
                # 执行
                if sql.strip().upper().startswith("SELECT"):
                    rs = stmt.executeQuery()
                    results = [self._result_set_to_list(rs)]
                else:
                    count = stmt.executeUpdate()
                    results = [count]
                    
                stmt.close()
            else:
                # 无参数查询
                stmt = conn.createStatement()
                if sql.strip().upper().startswith("SELECT"):
                    rs = stmt.executeQuery(sql)
                    results = [self._result_set_to_list(rs)]
                else:
                    count = stmt.executeUpdate(sql)
                    results = [count]
                stmt.close()
            
            # 提交事务
            if commit:
                conn.commit()

                
            return results
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"SQL执行错误: {str(e)}\nSQL: {sql}\nParams: {params}")
            raise e
        finally:
            # 注意：不要关闭连接，保持连接用于后续操作
            # 连接在close()方法中统一关闭
            pass

    
    def _init_table(self):
        """初始化任务表结构"""
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.dbtable} (
            task_id SERIAL PRIMARY KEY,
            value VARCHAR(200) NOT NULL UNIQUE,
            state VARCHAR(20) NOT NULL 
                CHECK (state IN ('PENDING', 'LOCKED', 'RUNNING', 'COMPLETED', 'FAILED', 'RETRY_PENDING')) 
                DEFAULT 'PENDING',
            worker_id VARCHAR(50),
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            retry_count INT DEFAULT 0,
            max_retries INT DEFAULT {self.max_retries},
            version INT DEFAULT 1,
            lock_time TIMESTAMP,
            last_error TEXT,
            extra_desc TEXT,
            payload JSONB,
            push_back_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_state ON {self.dbtable}(state);
        CREATE INDEX IF NOT EXISTS idx_lock_time ON {self.dbtable}(lock_time);
        CREATE INDEX IF NOT EXISTS idx_value ON {self.dbtable}(value);
        """
        # 已存在的表补列 (幂等)
        alter_sql = f"""
        ALTER TABLE {self.dbtable} ADD COLUMN IF NOT EXISTS extra_desc TEXT;
        ALTER TABLE {self.dbtable} ADD COLUMN IF NOT EXISTS payload JSONB;
        ALTER TABLE {self.dbtable} ADD COLUMN IF NOT EXISTS push_back_at TIMESTAMP;
        """
        # 确保建表操作提交
        try:
            self._execute_sql(sql, commit=True)
            # 已存在的表补列 (幂等)
            try:
                self._execute_sql(alter_sql, commit=True)
            except Exception as e:
                logger.debug(f"ALTER 补列忽略 (可能列已存在): {str(e)}")
            logger.info(f"初始化表 {self.dbtable} 完成")
            
            # 验证表是否真正创建成功
            verify_sql = f"SELECT 1 FROM {self.dbtable} LIMIT 1"
            self._execute_sql(verify_sql)
            logger.info(f"验证表 {self.dbtable} 存在成功")
            
        except Exception as e:
            logger.error(f"表初始化失败: {str(e)}")
            raise e
    
    # 在初始化后添加验证
    def _verify_table_exists(self):
        """验证表是否真正存在"""
        try:
            check_sql = f"""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = '{self.dbName}' 
                AND table_name = '{self.dbtable.split('.')[1]}'
            )
            """
            result = self._execute_sql(check_sql, commit=True)
            exists = result[0][0][0] if result else False
            logger.info(f"表存在验证结果: {exists}")
            return exists
        except Exception as e:
            logger.error(f"表验证失败: {str(e)}")
            return False
    
    def add_tasks(self, tasks: List[str]):
        """安全添加新任务到系统"""
        if not tasks:
            return
        
        # 获取现有任务
        existing = self._query_values(
            f"SELECT value FROM {self.dbtable} "
            "WHERE state NOT IN ('COMPLETED', 'FAILED')"
        )
        
        # 过滤新任务
        new_tasks = [str(t) for t in tasks if t not in existing]
        if not new_tasks:
            return
        
        # 使用批量插入优化
        batch_size = 100
        for i in range(0, len(new_tasks), batch_size):
            batch = new_tasks[i:i+batch_size]
            self._batch_insert_tasks(batch)
        
        logger.info(f"成功添加 {len(new_tasks)} 个新任务")

    def _batch_insert_tasks(self, tasks: List[str]):
        """执行批量插入任务"""
        if not tasks:
            return
            
        conn = None
        try:
            conn = self._get_connection()
            conn.setAutoCommit(False)
            
            # 使用PreparedStatement进行批量插入
            sql = f"INSERT INTO {self.dbtable} (value) VALUES (?) ON CONFLICT (value) DO NOTHING"
            
            stmt = conn.prepareStatement(sql)
            
            for task in tasks:
                stmt.setString(1, task)
                stmt.addBatch()  # 添加到批量
            
            # 执行批量插入
            stmt.executeBatch()
            conn.commit()
            
            logger.debug(f"批量插入 {len(tasks)} 个任务成功")
            
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"批量插入失败: {str(e)}")
            # 回退到逐条插入
            self._fallback_insert_tasks(tasks)
        finally:
            if conn:
                conn.close()

    def _fallback_insert_tasks(self, tasks: List[str]):
        """回退方法：逐条插入任务"""
        for task in tasks:
            try:
                sql = f"INSERT INTO {self.dbtable} (value) VALUES (?) ON CONFLICT (value) DO NOTHING"
                self._execute_sql(sql, params=[task], commit=True)
            except Exception as e:
                logger.error(f"任务 {task} 插入失败: {str(e)}")
    
    
    def _query_values(self, sql: str, params: Optional[List[Any]] = None) -> List[str]:
        """执行查询并返回值列表"""
        try:
            # 执行查询
            results = self._execute_sql(sql, params=params)
            if not results:
                return []
                
            # 提取值
            values = []
            for result in results:
                for row in result:
                    if row:
                        values.append(str(row[0]))
            return values
        except Exception as e:
            logger.error(f"查询错误: {str(e)}")
            return []
    
    def is_all_done(self) -> bool:
        """检查所有任务是否已完成"""
        count = self._query_values(
            f"SELECT value FROM {self.dbtable} "
            "WHERE state IN ('PENDING', 'LOCKED', 'RUNNING', 'RETRY_PENDING')"
        )
        return len(count) == 0
    
    @contextlib.contextmanager
    def _transaction(self):
        """事务上下文管理器"""
        conn = self._get_connection()
        conn.setAutoCommit(False)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            # 注意：不关闭连接，保持连接活跃
            pass
    
    def _acquire_task(self, worker_id: str, timeout_min: int = 5,states: Optional[str] = None) -> Optional[str]:
        """获取并锁定一个任务（带事务管理）"""
        try:
            with self._transaction() as conn:
                # 清理过期锁
                self.clean_stale_locks(timeout_min * 2)
                states = states.split(",") if states else ['PENDING','RETRY_PENDING']
                states_str = ",".join(f"'{s}'" for s in states)
                # 查询可处理任务并锁定
                sql = f"""
                SELECT value 
                FROM {self.dbtable} 
                WHERE state IN ({states_str})
                ORDER BY value
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
                
                stmt = conn.prepareStatement(sql)
                rs = stmt.executeQuery()
                
                if not rs.next():
                    return None
                
                task_value = rs.getString(1)
                
                # 立即锁定任务
                lock_sql = f"""
                UPDATE {self.dbtable} 
                SET 
                    state = 'LOCKED',
                    lock_time = CURRENT_TIMESTAMP,
                    worker_id = ?,
                    version = version + 1
                WHERE value = ?
                """
                
                lock_stmt = conn.prepareStatement(lock_sql)
                lock_stmt.setString(1, worker_id)
                lock_stmt.setString(2, task_value)
                lock_stmt.executeUpdate()
                
                # 提交事务前返回任务值
                return task_value
        except Exception as e:
            logger.error(f"获取任务失败: {str(e)}")
            return None
    
    def execute_task(self, value: str, worker_id: str,skip_states: Optional[str] = None):
        """强制执行单个任务（不论任何状态）"""
        try:
            # 开始事务
            states = skip_states.split(",") if skip_states else ['RUNNING']
            if len(states) == 0:
                cond = ""
            elif len(states) ==1:
                cond = f"and state <> '{states[0]}'"
            else:
                cond = f"and state not in {str(tuple(states))}"
            with self._transaction() as conn:
                # 更新为运行中状态
                sql = f"""
                UPDATE {self.dbtable}
                SET 
                    state = 'RUNNING',
                    start_time = CURRENT_TIMESTAMP,
                    worker_id = ?,
                    version = version + 1
                WHERE value = ?
                {cond}
                """
                stmt = conn.prepareStatement(sql)
                stmt.setString(1, worker_id)
                stmt.setString(2, value)
                stmt.executeUpdate()
            
            # 在事务外执行任务函数（避免长时间持有事务）
            # task_function 返回值可以是 dict (结构化结果)，写入 last_error
            task_result = None
            try:
                task_result = self.task_function(value)
            except Exception as e:
                raise TaskFunctionError(f"任务 {value} 执行失败: {str(e)}") from e
            
            # 标记为已完成
            with self._transaction() as conn:
                sql = f"""
                UPDATE {self.dbtable}
                SET 
                    state = 'COMPLETED',
                    end_time = CURRENT_TIMESTAMP,
                    last_error = ?,
                    version = version + 1
                WHERE value = ?
                """
                stmt = conn.prepareStatement(sql)
                # 结构化结果 → JSON 字符串
                if isinstance(task_result, dict):
                    import json as _json
                    last_error_str = _json.dumps(task_result, ensure_ascii=False)
                elif task_result is None:
                    last_error_str = None
                else:
                    last_error_str = str(task_result)
                if last_error_str is not None:
                    stmt.setString(1, last_error_str)
                else:
                    stmt.setNull(1, java.sql.Types.VARCHAR)
                stmt.setString(2, value)
                stmt.executeUpdate()
            
            return True
        except Exception as e:
            # 记录错误信息
            error_msg = str(e)
            if isinstance(e, TaskFunctionError):
                error_msg = f"任务函数执行失败: {error_msg}"
            logger.error(f"任务 {value} 执行失败: {error_msg}")
            
            # 标记为失败
            with self._transaction() as conn:
                sql = f"""
                UPDATE {self.dbtable}
                SET 
                    state = case when max_retries > retry_count then 'RETRY_PENDING' else 'FAILED' end,
                    retry_count = retry_count + 1,
                    end_time = CURRENT_TIMESTAMP,
                    last_error = ?,
                    version = version + 1
                WHERE value = ?
                """
                stmt = conn.prepareStatement(sql)
                stmt.setString(1, error_msg)
                stmt.setString(2, value)
                stmt.executeUpdate()
            
            return False
    
    def clean_stale_locks(self, timeout_min: int = 10):
        """清理过期的任务锁"""
        sql = f"""
        UPDATE {self.dbtable}
        SET 
            state = CASE 
                WHEN state = 'LOCKED' THEN 'PENDING' 
                WHEN state = 'RUNNING' THEN 'RETRY_PENDING'
            END,
            lock_time = NULL
        WHERE 
            lock_time < CURRENT_TIMESTAMP - INTERVAL '{timeout_min} minutes'
            AND state IN ('LOCKED', 'RUNNING')
        """
        self._execute_sql(sql, commit=True)
        logger.info("已清理过期任务锁")
    
    def run_until_done(self, worker_id: str, timeout_min: int = 5, interval: int = 10,states: Optional[str] = None):
        """持续运行任务直到全部完成"""
        logger.info(f"工作节点 {worker_id} 启动")
        
        while not self.is_all_done():
            try:
                # 获取并锁定一个任务
                task_value = self._acquire_task(worker_id, timeout_min,states=states)
                
                if task_value:
                    logger.info(f"获取任务: {task_value}")
                    
                    # 执行任务（强制执行，不论状态）
                    self.execute_task(task_value, worker_id)
                    logger.info(f"任务 {task_value} 完成")
                else:
                    logger.debug("无待处理任务，等待中...")
                    time.sleep(interval)
            
            except TaskAlreadyLocked as e:
                logger.warning(str(e))
                time.sleep(interval)
            
            except MaxRetriesExceeded as e:
                logger.error(str(e))
                time.sleep(interval)
            
            except Exception as e:
                logger.exception(f"处理任务时发生未预期错误: {str(e)}")
                time.sleep(interval)
        
        logger.info("所有任务已完成")
    
    def _get_payload(self, value: str) -> dict:
        """从任务表读取 payload JSONB (兼容无 payload 列的情况)。

        返回的 dict 里 value 已用 ``unZipB64`` 还原为原文（与 payload_encode 对称）。
        """
        try:
            sql = f"SELECT payload FROM {self.dbtable} WHERE value = ?"
            results = self._execute_sql(sql, params=[value])
            if results and results[0] and results[0][0]:
                row = results[0][0]
                raw = row[0] if isinstance(row, (list, tuple)) else row
                return payload_decode(raw)
        except Exception as e:
            logger.debug(f"读取 payload 失败 (可能表无此列): {str(e)}")
        return {}

    def set_payload(self, value: str, payload: Optional[dict]):
        """把任务的 payload 写入 JSONB 列（value 用 ``payload_encode`` 编码）。

        Args:
            value:   任务 key（task value）。
            payload: dict；None 时不动（不写）。
        """
        if payload is None:
            return
        sql = f"UPDATE {self.dbtable} SET payload = CAST(? AS jsonb) WHERE value = ?"
        self._execute_sql(sql, params=[payload_encode(payload), value], commit=True)
        logger.debug(f"写入 payload: {value}")
    
    def execute_task_with_result(self, value: str, worker_id: str, skip_states: Optional[str] = None):
        """执行任务。
        原 execute_task 已支持 task_function 返回结构化 dict，自动写入 last_error=JSON。
        此函数仅包装，兼容旧接口。
        """
        return self.execute_task(value, worker_id, skip_states=skip_states)
    
    def run_until_done_resident(self, worker_id: str, timeout_min: int = 5, 
                                interval: int = 10, states: Optional[str] = None):
        """常驻模式：任务全跑完也不退出，一直轮询新任务
        - 与原 run_until_done 区别：去掉 is_all_done 判断，while True 常驻
        - 使用 execute_task_with_result 以便成功后更新 last_error
        """
        logger.info(f"工作节点 {worker_id} 启动 (常驻模式)")
        
        while True:
            try:
                task_value = self._acquire_task(worker_id, timeout_min, states=states)
                
                if task_value:
                    logger.info(f"获取任务: {task_value}")
                    
                    # 执行任务（含成功后更新 last_error）
                    self.execute_task_with_result(task_value, worker_id)
                    logger.info(f"任务 {task_value} 完成")
                else:
                    logger.debug("无待处理任务，等待中...")
                    time.sleep(interval)
            
            except TaskAlreadyLocked as e:
                logger.warning(str(e))
                time.sleep(interval)
            
            except MaxRetriesExceeded as e:
                logger.error(str(e))
                time.sleep(interval)
            
            except Exception as e:
                logger.exception(f"处理任务时发生未预期错误: {str(e)}")
                time.sleep(interval)
    
    def close(self):
        """关闭连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("数据库连接已关闭")

    @classmethod
    def _get_spark_session(cls) -> SparkSession:
        """获取SparkSession"""
        return SparkSession.builder \
            .config("spark.jars", "/appcom/apps/postgresql-42.5.0.jar") \
            .config("spark.sql.autoBroadcastJoinThreshold", "-1") \
            .config("spark.default.parallelism", "10") \
            .getOrCreate()
    
    @classmethod
    def _get_default_properties(cls) -> dict:
        # 生产 PG 连接走 pyk.configs.pg_credentials（密文 + 环境变量），代码不留明文凭据
        from .configs import pg_credentials
        url, user, password = pg_credentials()
        return {
            'url': url,
            'user': user,
            'password': password,
            'driver': os.environ.get("PYK_PG_DRIVER", "org.postgresql.Driver"),
        }
        
    @classmethod
    def query(cls,sql:str) -> Any:
        """执行查询并返回DataFrame,注意是postgresql"""
        if  re.match(r"^[a-z][a-z_0-9]+\.[a-z_0-9]+$",sql.lower()):
            sql = f"select * from {sql}"
        elif re.match(r"^[a-z][a-z_0-9]+$",sql.lower()):
            sql = f"select * from public.{sql}"
        spark = cls._get_spark_session()
        dct = cls._get_default_properties()
        dct['query'] = sql
        return spark.read.format("jdbc").options(**dct).load()


def add_tasks(dbtable:str,tasks:List[str]) -> bool:
    """添加任务并获取任务"""
    try:
        lu = LookUpon(
            task_function=None,
            dbtable=dbtable,
            init=False,
            tasks=tasks,
            max_retries=3
        )
        lu.add_tasks(tasks)
        return True
    except Exception as e:
        logger.error(f"添加任务失败: {str(e)}")
        return False

def query_tasks(dbtable:str,where_cond:str = "") -> Optional[DataFrame]:
    """查询任务"""
    try:
        lu = LookUpon(
            task_function=None,
            dbtable=dbtable,
            init=False,
            tasks=[],
            max_retries=3
        )
        s =   "" if  where_cond.strip().lower().startswith("where ") else "where "
        where_cond = s + where_cond.strip() if where_cond.strip() else ""
        return lu.query(f"select * from {dbtable} {where_cond}")
    except Exception as e:
        logger.error(f"查询任务失败: {str(e)}")
        return None

def init_tasks(dbtable,tasks,drop_if_exists=False):
    """初始化任务系统"""
    return LookUpon(
        task_function=None,
        dbtable=dbtable,
        init=True,
        tasks=tasks,
        max_retries=3,
        drop_if_exists=drop_if_exists
    )

def _is_lookupon_table(dbtable:str):
    """判断表是否为LookUpon任务表"""
    lu = LookUpon(task_function=None, dbtable='lookupon', init=True)
    df = lu.query("select * from public.lookupon")
    tn = dbtable if '.' in dbtable else f"public.{dbtable}"
    tf = LookUpon.query(f"select * from {tn}")
    return df.columns == tf.columns

def run_until_done(task_function: Callable[[str], None],dbtable :str, worker_id:Optional[str] = None
                ,tasks :Optional[List[str]] =None, max_retries:int =3 
                ,timeout_min :int =5, interval :int =10,states: Optional[str] = None):
    try:
        if not _is_lookupon_table(dbtable):
            raise ValueError(f"表 {dbtable} 不是LookUpon任务表")
        task_system = LookUpon(
            task_function=task_function,
            dbtable=dbtable,
            tasks=tasks,
            init=False,
            max_retries=max_retries
        )
        if worker_id is None:
            cnt = task_system.query(f"select * from public.{dbtable} where worker_id is not null and state in ('COMPLETED', 'FAILED','RUNNING','LOCKED') ").groupBy("worker_id").count().count()
            worker_id = f"auto_wk_id_{cnt+1}"
        task_system.run_until_done(worker_id=worker_id, timeout_min=timeout_min, interval=interval,states=states)
    except Exception as e:
        logger.exception(f"运行失败: {str(e)}")
        raise e

def get_replaced_sql(ds,replace_func = None, spark=None,**kwargs):
    """当提供spark 执行sql，反之返回 str,默认 替换  文件中  {ds} 为 ds 
        replace_func =>> replace_func(sql,ds,**kwargs):pass
    """
    sql_file = upon_sql_file()
    if not sql_file:
        raise FileNotFoundError(
            "look_upon 未配置 SQL 文件：请设置环境变量 PYK_UPON_SQL_FILE，"
            "或在 pyk.configs.UPON_SQL_FILE 里显式覆写。公开库不硬编码生产路径。"
        )
    with open(sql_file, 'r', encoding="utf-8") as f:
        txt = f.read()
        run_date = kwargs.pop('run_date',None)
        if run_date :
            txt = _vicText(txt).replace_run_date(run_date).text
        sql = txt.replace(r"{ds}",ds) if replace_func is None else replace_func(txt,**{'ds':ds},**kwargs)
        return sql if spark is None else spark.sql(sql)
        
@wraps(run_until_done)
def run_done(replace_function,*args,**kwargs):
    """ privode replace_function instead  task_function 
        replace_func =>> replace_func(sql,ds,**kwargs):pass
    """
    ps = ['dbtable','worker_id','tasks','max_retries','timeout_min','interval','states'] 
    dct = { k:kwargs[k] for k in kwargs.keys() if k in ps }
    if not 'dbtable' in dct.keys():
        dct['dbtable'] = 'lookupon'
    if 'states' in dct.keys() and dct['states'] == 'FAILED':
        update_failed_to_pending(dct['dbtable'])

    kct = { k:kwargs[k] for k in kwargs.keys() if k not in ps }
    return run_until_done(partial(get_replaced_sql,replace_func=replace_function,**kct),*args,**dct)

def reset_tasks(tasks):
    """
    reset_tasks in table lookupon
    """
    lu = LookUpon((lambda x:x ),'lookupon')
    lu.execute_sql("truncate table public.lookupon ")
    lu.add_tasks(tasks)
    cnt = lu.query("select * from public.lookupon").count()
    if cnt != len(tasks):
        raise TaskFunctionError("reset_tasks failed ,please query table public.lookupon fro check !!!")
    print(f"Add {cnt} tasks Success in table public.lookupon!")

def run_doneEx(dbtable = None,**kwargs):
    """
    the value is run_date like yyyyMMdd or yyyy-MM-dd,auto replace all 'run_date' to value 
    all kwagrs is a callable function like function(run_date),to replace {ds},{end_ds}
    example:
        run_doneEx(ds = lambda x : get_week(x,0,7), end_ds = lambda x: get_month(x,0,1) )
        will replace {ds} and {end_ds}  in content from builder_sql_for_upon.sql file
    """
    dbtable = 'lookupon' if dbtable is None else dbtable
    path = kwargs.pop('path', upon_sql_file())
    if not path:
        raise FileNotFoundError(
            "look_upon 未配置 SQL 文件：请设置环境变量 PYK_UPON_SQL_FILE，"
            "或在 pyk.configs.UPON_SQL_FILE 里显式覆写。"
        )
    # with open(path,'r',encoding="utf-8") as f:
    #     txt = f.read()
    txt = _get_content(path).text
    factory = kwargs.pop('factory', get_spark())
    factory = factory.sql if isinstance(factory,SparkSession) else factory
    def do(run_date):
        sql = _vicText(txt)
        if "{run_date" in txt:
             sql = sql.replace_run_date(run_date)
        text = sql.text
        dct = dict()
        for k,v in kwargs.items():
            if '{' + k + '}' in text:
                v = v(run_date) if callable(v) else str(v)
                dct[k] = v
        if dct:
            sql = sql.build(dct)
        for s in sql.text.split(';'):
            s = s.strip()
            if s and factory :
                factory(s) 
    return run_until_done(do,dbtable)


def update_failed_to_pending(dbtable:str = None):
    dbtable = 'lookupon' if dbtable is None else dbtable
    LookUpon((lambda x:x ),dbtable).execute_sql(f"update  public.{dbtable}  set state = 'PENDING' , version = version + 1  where state = 'FAILED' ")

LU = LookUpon

if __name__ == '__main__':
    # 测试代码
    import random
    def process_task(value: str):
        """示例任务处理函数"""
        print(f"Processing task: {value}")
        # 模拟任务处理
        time.sleep(0.5)
        # 模拟随机失败
        if random.random() < 0.2:
            raise Exception("随机错误")

    # df = LookUpon.query('task_queue')
    # df.show()
    # spk = LookUpon._get_spark_session()
    # spk.sql("select 1 as id").show()
    # 创建任务系统
    task_system = LookUpon(
        task_function=process_task,
        dbtable="task_queue",
        init=True,
        tasks=[f"task_{i}" for i in range(100)],
        max_retries=3,
        drop_if_exists = True
    )

    try:
        # 启动工作节点
        task_system.run_until_done(worker_id="worker-1")
    finally:
        # 清理资源
        task_system.close()