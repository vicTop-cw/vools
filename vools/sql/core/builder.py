"""
vools.sql.core.builder - SQL 构建器抽象与基础实现

提供 SQL 构建器的抽象基类与基础实现，支持链式调用构建 SQL 语句，
采用参数化查询避免 SQL 注入，具体方言可通过继承并重写相关方法实现。
"""

import abc
import re
from typing import Tuple, List, Any, Callable, Optional


class SqlBuilder(abc.ABC):
    """
    SQL 构建器抽象基类

    定义了所有链式调用接口，具体实现由子类提供。
    所有方法均返回 self 以支持链式调用。

    用法：
        builder = ConcreteBuilder()
        sql, params = builder.select('id', 'name').from_('users').where('id > ?', 1).build()
    """

    @abc.abstractmethod
    def select(self, *columns: str) -> 'SqlBuilder':
        """
        指定查询列

        参数：
            *columns: 列名，可变参数

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def from_(self, *tables: str) -> 'SqlBuilder':
        """
        指定查询表

        参数：
            *tables: 表名，可变参数

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def where(self, condition: str, *params: Any) -> 'SqlBuilder':
        """
        WHERE 条件，多个条件默认用 AND 连接

        参数：
            condition: 条件表达式字符串
            *params: 条件参数值，可变参数

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def and_(self, condition: str, *params: Any) -> 'SqlBuilder':
        """
        添加 AND 条件

        参数：
            condition: 条件表达式字符串
            *params: 条件参数值，可变参数

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def or_(self, condition: str, *params: Any) -> 'SqlBuilder':
        """
        添加 OR 条件

        参数：
            condition: 条件表达式字符串
            *params: 条件参数值，可变参数

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def order_by(self, *columns: str) -> 'SqlBuilder':
        """
        ORDER BY 排序

        参数：
            *columns: 排序列名，可变参数

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def group_by(self, *columns: str) -> 'SqlBuilder':
        """
        GROUP BY 分组

        参数：
            *columns: 分组列名，可变参数

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def having(self, condition: str, *params: Any) -> 'SqlBuilder':
        """
        HAVING 条件

        参数：
            condition: 条件表达式字符串
            *params: 条件参数值，可变参数

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def limit(self, count: int) -> 'SqlBuilder':
        """
        LIMIT 限制返回行数

        参数：
            count: 行数限制

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def offset(self, count: int) -> 'SqlBuilder':
        """
        OFFSET 偏移量

        参数：
            count: 偏移量

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def insert_into(self, table: str) -> 'SqlBuilder':
        """
        INSERT INTO 插入数据

        参数：
            table: 表名

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def values(self, **kwargs: Any) -> 'SqlBuilder':
        """
        VALUES 插入值

        参数：
            **kwargs: 列名-值对

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def update(self, table: str) -> 'SqlBuilder':
        """
        UPDATE 更新数据

        参数：
            table: 表名

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def set_(self, **kwargs: Any) -> 'SqlBuilder':
        """
        SET 设置更新值

        参数：
            **kwargs: 列名-值对

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def delete_from(self, table: str) -> 'SqlBuilder':
        """
        DELETE FROM 删除数据

        参数：
            table: 表名

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def join(self, table: str, on_condition: str, join_type: str = 'INNER') -> 'SqlBuilder':
        """
        JOIN 连接表

        参数：
            table: 要连接的表名
            on_condition: 连接条件
            join_type: 连接类型，默认 'INNER'

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def left_join(self, table: str, on_condition: str) -> 'SqlBuilder':
        """
        LEFT JOIN 左连接

        参数：
            table: 要连接的表名
            on_condition: 连接条件

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def right_join(self, table: str, on_condition: str) -> 'SqlBuilder':
        """
        RIGHT JOIN 右连接

        参数：
            table: 要连接的表名
            on_condition: 连接条件

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def inner_join(self, table: str, on_condition: str) -> 'SqlBuilder':
        """
        INNER JOIN 内连接

        参数：
            table: 要连接的表名
            on_condition: 连接条件

        返回：
            self，支持链式调用
        """
        ...

    @abc.abstractmethod
    def build(self) -> Tuple[str, tuple]:
        """
        构建 SQL 语句

        返回：
            (sql_string, params) 元组，sql_string 为 SQL 字符串，
            params 为参数元组，用于参数化查询
        """
        ...


class BaseSqlBuilder(SqlBuilder):
    """基础 SQL 构建器实现（占位符按 `_paramstyle` 生成）。"""

    #: `join()` 允许的连接类型（BUG-395）
    _VALID_JOIN_TYPES = ('INNER', 'LEFT', 'RIGHT', 'OUTER', 'FULL', 'CROSS')

    """
    SQL 构建器基础实现类

    提供通用的 SQL 构建逻辑，包括状态管理和 SQL 字符串组装。
    具体方言可以继承此类并重写相关方法实现特定语法。

    属性：
        _paramstyle: 参数风格，默认 'pyformat'
        _params: 参数列表，按顺序收集参数

    用法：
        builder = BaseSqlBuilder()
        sql, params = builder.select('id', 'name').from_('users').where('id > %s', 1).build()
    """

    _paramstyle: str = 'pyformat'

    _PLACEHOLDER_PATTERN = re.compile(r'\?|%s|%\w+|:\w+')

    def __init__(self):
        """
        初始化构建器，重置所有内部状态
        """
        self._reset()

    def _reset(self) -> None:
        """
        重置内部状态
        """
        self._columns: List[str] = []
        self._tables: List[str] = []
        self._joins: List[Tuple[str, str, str]] = []
        self._where_conditions: List[Tuple[str, tuple]] = []
        self._order_by: List[str] = []
        self._group_by: List[str] = []
        self._having_conditions: List[Tuple[str, tuple]] = []
        self._limit: int = None
        self._offset: int = None
        self._insert_table: str = None
        self._insert_values: dict = {}
        self._update_table: str = None
        self._update_values: dict = {}
        self._delete_table: str = None
        self._params: List[Any] = []

    def _placeholder(self, idx: int) -> str:
        """
        根据 paramstyle 生成占位符

        参数：
            idx: 参数索引（从 0 开始）

        返回：
            占位符字符串
        """
        style = self._paramstyle
        if style == 'qmark':
            return '?'
        elif style == 'format':
            return '%s'
        elif style == 'pyformat':
            return '%s'
        elif style == 'numeric':
            return f':{idx + 1}'
        elif style == 'named':
            return f':param_{idx}'
        else:
            return '%s'

    @staticmethod
    def _split_by_quotes(condition: str) -> List[Tuple[bool, str]]:
        """把条件串切成 [(是否引号内, 片段), ...]。

        BUG-232: 占位符替换必须避开字符串字面量——否则 "'what?'"、
        "'12:30:00'"、LIKE 模式等字面量文本被误改写成占位符，SQL 文本静默
        损坏（带参数时还会令参数索引整体错位）。单引号字面量按 SQL 标准
        ``''`` 转义处理；双引号标识符同样视为字面量原样保留。
        """
        parts: List[Tuple[bool, str]] = []
        buf: List[str] = []
        quote: Optional[str] = None
        i, n = 0, len(condition)
        while i < n:
            ch = condition[i]
            if quote is None:
                if ch in ("'", '"'):
                    if buf:
                        parts.append((False, ''.join(buf)))
                        buf = []
                    quote = ch
                    buf.append(ch)
                else:
                    buf.append(ch)
            else:
                buf.append(ch)
                if ch == quote:
                    # '' / "" 转义：连续同引号是字面量内容
                    if i + 1 < n and condition[i + 1] == quote:
                        buf.append(condition[i + 1])
                        i += 2
                        continue
                    parts.append((True, ''.join(buf)))
                    buf = []
                    quote = None
            i += 1
        if buf:
            parts.append((quote is not None, ''.join(buf)))
        return parts

    def _sub_placeholders(self, condition: str, repl: Callable[[Any], str]) -> str:
        """仅在引号外片段做占位符替换（BUG-232）。"""
        out: List[str] = []
        for is_quoted, text in self._split_by_quotes(condition):
            out.append(text if is_quoted
                       else self._PLACEHOLDER_PATTERN.sub(repl, text))
        return ''.join(out)

    def _normalize_condition(self, condition: str, params: tuple) -> Tuple[str, tuple]:
        """
        标准化条件表达式中的占位符

        将条件中的占位符统一替换为当前 paramstyle 的占位符，
        确保参数顺序正确。

        参数：
            condition: 条件表达式
            params: 参数值元组

        返回：
            (normalized_condition, params) 元组

        异常：
            TypeError: condition 不是字符串
            ValueError: condition 为空/仅空白（原实现会生成 `... WHERE ` 这种
                语法非法的 SQL —— BUG-395）
        """
        # BUG-395: 原实现不校验空条件，build() 输出 `SELECT * FROM t WHERE `
        # 这种非法 SQL，到执行阶段才报错且信息晦涩。入口直接拒绝。
        if not isinstance(condition, str):
            raise TypeError(
                f"条件表达式必须是 str，收到 {type(condition).__name__}: {condition!r}")
        if not condition.strip():
            raise ValueError("条件表达式不能为空（会生成非法的 WHERE/HAVING 子句）")

        param_idx = 0

        def replace_placeholder(match):
            nonlocal param_idx
            placeholder = self._placeholder(param_idx)
            param_idx += 1
            return placeholder

        # BUG-232: 只替换引号外的占位符，字面量文本原样保留
        normalized = self._sub_placeholders(condition, replace_placeholder)
        return normalized, params

    def select(self, *columns: str) -> 'BaseSqlBuilder':
        """
        指定查询列

        参数：
            *columns: 列名，可变参数

        返回：
            self，支持链式调用
        """
        self._columns.extend(columns)
        return self

    def from_(self, *tables: str) -> 'BaseSqlBuilder':
        """
        指定查询表

        参数：
            *tables: 表名，可变参数

        返回：
            self，支持链式调用
        """
        self._tables.extend(tables)
        return self

    def where(self, condition: str, *params: Any) -> 'BaseSqlBuilder':
        """
        WHERE 条件，多个条件默认用 AND 连接

        参数：
            condition: 条件表达式字符串
            *params: 条件参数值，可变参数

        返回：
            self，支持链式调用
        """
        normalized_cond, normalized_params = self._normalize_condition(condition, params)
        self._where_conditions.append((normalized_cond, normalized_params))
        return self

    def and_(self, condition: str, *params: Any) -> 'BaseSqlBuilder':
        """
        添加 AND 条件

        参数：
            condition: 条件表达式字符串
            *params: 条件参数值，可变参数

        返回：
            self，支持链式调用
        """
        normalized_cond, normalized_params = self._normalize_condition(condition, params)
        self._where_conditions.append((normalized_cond, normalized_params))
        return self

    def or_(self, condition: str, *params: Any) -> 'BaseSqlBuilder':
        """
        添加 OR 条件

        将最后一个条件与新条件用 OR 连接，并用括号包裹。

        参数：
            condition: 条件表达式字符串
            *params: 条件参数值，可变参数

        返回：
            self，支持链式调用
        """
        normalized_cond, normalized_params = self._normalize_condition(condition, params)
        if self._where_conditions:
            last_cond, last_params = self._where_conditions.pop()
            combined_cond = f"({last_cond} OR {normalized_cond})"
            combined_params = last_params + normalized_params
            self._where_conditions.append((combined_cond, combined_params))
        else:
            self._where_conditions.append((normalized_cond, normalized_params))
        return self

    def order_by(self, *columns: str) -> 'BaseSqlBuilder':
        """
        ORDER BY 排序

        参数：
            *columns: 排序列名，可变参数

        返回：
            self，支持链式调用
        """
        self._order_by.extend(columns)
        return self

    def group_by(self, *columns: str) -> 'BaseSqlBuilder':
        """
        GROUP BY 分组

        参数：
            *columns: 分组列名，可变参数

        返回：
            self，支持链式调用
        """
        self._group_by.extend(columns)
        return self

    def having(self, condition: str, *params: Any) -> 'BaseSqlBuilder':
        """
        HAVING 条件

        参数：
            condition: 条件表达式字符串
            *params: 条件参数值，可变参数

        返回：
            self，支持链式调用
        """
        normalized_cond, normalized_params = self._normalize_condition(condition, params)
        self._having_conditions.append((normalized_cond, normalized_params))
        return self

    def limit(self, count: int) -> 'BaseSqlBuilder':
        """
        LIMIT 限制返回行数

        参数：
            count: 行数限制

        返回：
            self，支持链式调用
        """
        # BUG-395: 原实现直接存值——limit(-1) 在多数数据库语义异常、limit('10')
        # 静默把字符串当参数透传。这里要求非负整数（0 合法：返回空集）。
        if not isinstance(count, int) or isinstance(count, bool):
            raise TypeError(f"limit 需要 int，收到 {type(count).__name__}: {count!r}")
        if count < 0:
            raise ValueError(f"limit 不能为负，收到 {count}")
        self._limit = count
        return self

    def offset(self, count: int) -> 'BaseSqlBuilder':
        """
        OFFSET 偏移量

        参数：
            count: 偏移量

        返回：
            self，支持链式调用
        """
        # BUG-395: 同 limit —— 要求非负整数
        if not isinstance(count, int) or isinstance(count, bool):
            raise TypeError(f"offset 需要 int，收到 {type(count).__name__}: {count!r}")
        if count < 0:
            raise ValueError(f"offset 不能为负，收到 {count}")
        self._offset = count
        return self

    def insert_into(self, table: str) -> 'BaseSqlBuilder':
        """
        INSERT INTO 插入数据

        参数：
            table: 表名

        返回：
            self，支持链式调用
        """
        self._insert_table = table
        return self

    def values(self, **kwargs: Any) -> 'BaseSqlBuilder':
        """
        VALUES 插入值

        参数：
            **kwargs: 列名-值对

        返回：
            self，支持链式调用
        """
        self._insert_values.update(kwargs)
        return self

    def update(self, table: str) -> 'BaseSqlBuilder':
        """
        UPDATE 更新数据

        参数：
            table: 表名

        返回：
            self，支持链式调用
        """
        self._update_table = table
        return self

    def set_(self, **kwargs: Any) -> 'BaseSqlBuilder':
        """
        SET 设置更新值

        参数：
            **kwargs: 列名-值对

        返回：
            self，支持链式调用
        """
        self._update_values.update(kwargs)
        return self

    def delete_from(self, table: str) -> 'BaseSqlBuilder':
        """
        DELETE FROM 删除数据

        参数：
            table: 表名

        返回：
            self，支持链式调用
        """
        self._delete_table = table
        return self

    def join(self, table: str, on_condition: str, join_type: str = 'INNER') -> 'BaseSqlBuilder':
        """
        JOIN 连接表

        参数：
            table: 要连接的表名
            on_condition: 连接条件
            join_type: 连接类型，默认 'INNER'

        返回：
            self，支持链式调用
        """
        # BUG-395: 原实现只做 .upper()，非法 join_type 会生成
        # `SELECT * FROM a BOGUS JOIN b ...` —— 语法非法却毫无提示。
        _jt = join_type.strip().upper() if isinstance(join_type, str) else None
        if _jt not in self._VALID_JOIN_TYPES:
            raise ValueError(
                f"join_type 只支持 {'/'.join(self._VALID_JOIN_TYPES)}，"
                f"收到 {join_type!r}")
        self._joins.append((_jt, table, on_condition))
        return self

    def left_join(self, table: str, on_condition: str) -> 'BaseSqlBuilder':
        """
        LEFT JOIN 左连接

        参数：
            table: 要连接的表名
            on_condition: 连接条件

        返回：
            self，支持链式调用
        """
        return self.join(table, on_condition, 'LEFT')

    def right_join(self, table: str, on_condition: str) -> 'BaseSqlBuilder':
        """
        RIGHT JOIN 右连接

        参数：
            table: 要连接的表名
            on_condition: 连接条件

        返回：
            self，支持链式调用
        """
        return self.join(table, on_condition, 'RIGHT')

    def inner_join(self, table: str, on_condition: str) -> 'BaseSqlBuilder':
        """
        INNER JOIN 内连接

        参数：
            table: 要连接的表名
            on_condition: 连接条件

        返回：
            self，支持链式调用
        """
        return self.join(table, on_condition, 'INNER')

    def build(self) -> Tuple[str, tuple]:
        """
        构建 SQL 语句

        根据当前内部状态组装 SQL 字符串和参数列表。
        支持 SELECT、INSERT、UPDATE、DELETE 四种语句类型。

        返回：
            (sql_string, params) 元组，sql_string 为 SQL 字符串，
            params 为参数元组，用于参数化查询
        """
        self._params = []

        if self._insert_table:
            return self._build_insert()
        elif self._update_table:
            return self._build_update()
        elif self._delete_table:
            return self._build_delete()
        else:
            return self._build_select()

    def _collect_condition_params(self, conditions: List[Tuple[str, tuple]]) -> Tuple[str, List[Any]]:
        """
        收集条件表达式和参数

        将多个条件用 AND 连接，同时收集所有参数。

        BUG-298（寻虫 2026-10-22）：`param_offset` 原为局部变量，每次调用
        从 0 开始——WHERE 和 HAVING 同时存在时，HAVING 的占位符编号会
        从 :1 重新开始，但 `self._params` 是连续的（WHERE 参数在前）。
        导致 numeric/named 风格的 HAVING 占位符指向错误参数，DB 报
        Incorrect number of bindings。
        修复：用 `len(self._params)` 作为起始偏移量，保证编号连续。

        参数：
            conditions: 条件列表，每个元素为 (condition_str, params_tuple)

        返回：
            (joined_conditions, params_list) 元组
        """
        if not conditions:
            return '', []

        condition_strs = []
        all_params = []
        param_offset = len(self._params)  # BUG-298：从当前 params 长度开始编号

        for cond, params in conditions:
            # BUG-351: 占位符数量与参数数量不匹配时，原实现静默产出
            # "占位符多/参数少" 的 SQL，直到 DB 执行才报 driver 级错误
            # （如 sqlite: Incorrect number of bindings supplied），难以定位。
            # 这里在 build 期按**引号感知**计数并显式报错。
            _count = 0

            def _count_placeholder(match):
                nonlocal _count
                _count += 1
                return match.group(0)

            self._sub_placeholders(cond, _count_placeholder)
            if _count != len(params):
                raise ValueError(
                    f"条件占位符与参数数量不匹配：条件 {cond!r} 含 {_count} 个占位符，"
                    f"但传入 {len(params)} 个参数 {params!r}")

            def replace_placeholder(match):
                nonlocal param_offset
                placeholder = self._placeholder(param_offset)
                param_offset += 1
                return placeholder

            # BUG-232: 只重编号引号外的占位符，字面量文本原样保留
            reindexed_cond = self._sub_placeholders(cond, replace_placeholder)
            condition_strs.append(reindexed_cond)
            all_params.extend(params)

        return ' AND '.join(condition_strs), all_params

    def _build_select(self) -> Tuple[str, tuple]:
        """
        构建 SELECT 语句

        返回：
            (sql_string, params) 元组
        """
        parts = []

        columns = ', '.join(self._columns) if self._columns else '*'
        parts.append(f"SELECT {columns}")

        if self._tables:
            parts.append(f"FROM {', '.join(self._tables)}")

        for join_type, table, on_condition in self._joins:
            parts.append(f"{join_type} JOIN {table} ON {on_condition}")

        if self._where_conditions:
            where_str, where_params = self._collect_condition_params(self._where_conditions)
            self._params.extend(where_params)
            parts.append(f"WHERE {where_str}")

        if self._group_by:
            parts.append(f"GROUP BY {', '.join(self._group_by)}")

        if self._having_conditions:
            having_str, having_params = self._collect_condition_params(self._having_conditions)
            self._params.extend(having_params)
            parts.append(f"HAVING {having_str}")

        if self._order_by:
            parts.append(f"ORDER BY {', '.join(self._order_by)}")

        if self._limit is not None:
            self._params.append(self._limit)
            parts.append(f"LIMIT {self._placeholder(len(self._params) - 1)}")

        if self._offset is not None:
            self._params.append(self._offset)
            parts.append(f"OFFSET {self._placeholder(len(self._params) - 1)}")

        sql = ' '.join(parts)
        return sql, tuple(self._params)

    def _build_insert(self) -> Tuple[str, tuple]:
        """
        构建 INSERT 语句

        返回：
            (sql_string, params) 元组
        """
        if not self._insert_values:
            return f"INSERT INTO {self._insert_table} DEFAULT VALUES", tuple()

        columns = list(self._insert_values.keys())
        placeholders = []
        self._params = []

        for i, col in enumerate(columns):
            self._params.append(self._insert_values[col])
            placeholders.append(self._placeholder(i))

        columns_str = ', '.join(columns)
        placeholders_str = ', '.join(placeholders)

        sql = f"INSERT INTO {self._insert_table} ({columns_str}) VALUES ({placeholders_str})"
        return sql, tuple(self._params)

    def _build_update(self) -> Tuple[str, tuple]:
        """
        构建 UPDATE 语句

        返回：
            (sql_string, params) 元组

        Raises:
            ValueError: 未设置任何更新字段（BUG-286）
        """
        # BUG-286: 原实现无 SET 字段时静默产出非法 SQL 'UPDATE t'——build()
        # 承诺组装可用语句，缺 SET 的 UPDATE 在任何数据库都语法错误，且错误
        # 暴露在被 distant 的 execute 端。与 BUG-284/BUG-129 同口径显式报错。
        if not self._update_values:
            raise ValueError(
                "UPDATE 语句缺少 SET 字段：请先调用 set_(列=值, ...) 提供更新字段")

        parts = [f"UPDATE {self._update_table}"]
        self._params = []

        if self._update_values:
            set_clauses = []

            for i, (col, val) in enumerate(self._update_values.items()):
                self._params.append(val)
                set_clauses.append(f"{col} = {self._placeholder(i)}")

            parts.append(f"SET {', '.join(set_clauses)}")

        if self._where_conditions:
            where_str, where_params = self._collect_condition_params(self._where_conditions)
            self._params.extend(where_params)
            parts.append(f"WHERE {where_str}")

        sql = ' '.join(parts)
        return sql, tuple(self._params)

    def _build_delete(self) -> Tuple[str, tuple]:
        """
        构建 DELETE 语句

        返回：
            (sql_string, params) 元组
        """
        parts = [f"DELETE FROM {self._delete_table}"]
        self._params = []

        if self._where_conditions:
            where_str, where_params = self._collect_condition_params(self._where_conditions)
            self._params.extend(where_params)
            parts.append(f"WHERE {where_str}")

        sql = ' '.join(parts)
        return sql, tuple(self._params)


__all__ = [
    'BaseSqlBuilder',
    'SqlBuilder'
]
