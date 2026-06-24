"""
vools.sql.core.decorators - SQL 装饰器

提供 @sql_function 和 @sql_module 装饰器，简化 SQL 操作函数定义。
支持从类型注解自动推断参数类型、自动转换参数和返回值、便捷的连接传递等。
"""

import functools
import inspect
import typing

from .types import SqlTypeMapper
from .result import ResultSet, Row


_FUNC_NAME_ATTR = '_sql_func_name'
_SQL_INFO_ATTR = '_sql_info'


def _get_signature_info(func):
    """
    从函数签名中提取参数类型和返回类型信息。

    参数：
        func: 要分析的函数

    返回：
        (param_names, param_types, return_type) 元组
        param_names: 参数名称列表
        param_types: 参数类型列表（与 param_names 对应），
                     无注解的参数类型为 None
        return_type: 返回类型注解，无注解则为 None
    """
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return [], [], None

    param_names = []
    param_types = []
    for name, param in sig.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        param_names.append(name)
        if param.annotation is not param.empty:
            param_types.append(param.annotation)
        else:
            param_types.append(None)

    return_type = None
    if sig.return_annotation is not sig.empty:
        return_type = sig.return_annotation

    return param_names, param_types, return_type


def _resolve_sql_types(param_types, return_type):
    """
    将 Python 类型解析为 SQL 类型。

    参数：
        param_types: Python 参数类型列表
        return_type: Python 返回类型

    返回：
        (sql_param_types, sql_return_type) 元组
        sql_param_types: SQL 参数类型字符串列表
        sql_return_type: SQL 返回类型字符串，可能为 None
    """
    sql_param_types = []
    for py_type in param_types:
        if py_type is None:
            sql_param_types.append(None)
        else:
            sql_type = SqlTypeMapper.get_sql_type(py_type)
            if sql_type is None:
                sql_param_types.append('VARCHAR')
            else:
                sql_param_types.append(sql_type)

    sql_return_type = SqlTypeMapper.infer_ret_type(return_type)

    return sql_param_types, sql_return_type


def _convert_args(args, param_types):
    """
    转换参数为 SQL 兼容格式。

    使用 SqlTypeMapper 进行参数类型转换，
    确保参数值符合 SQL 执行的要求。

    参数：
        args: 原始参数值列表
        param_types: Python 参数类型列表

    返回：
        转换后的参数列表
    """
    sql_types, _ = _resolve_sql_types(param_types, None)
    return SqlTypeMapper.convert_args(args, sql_types)


def _convert_result(result, return_type):
    """
    转换 SQL 结果以匹配 Python 类型期望。

    支持的转换：
        - ResultSet -> list[dict]：当返回类型注解为 list 时
        - ResultSet -> dict：当返回类型注解为 dict 时（取第一行）
        - ResultSet -> Row：当返回类型注解为 Row 时（取第一行）
        - ResultSet -> 标量值：当返回类型为基本类型时，取第一行第一列
        - ResultSet -> int：当返回类型注解为 int 且无行时返回 rowcount

    参数：
        result: 原始返回值（通常是 ResultSet）
        return_type: Python 返回类型注解

    返回：
        转换后的返回值
    """
    if return_type is None or return_type is type(None):
        return result

    if not isinstance(result, ResultSet):
        return SqlTypeMapper.convert_result(result, return_type)

    origin = typing.get_origin(return_type)
    args = typing.get_args(return_type)

    if return_type is list or origin is list:
        return result.to_list()

    if return_type is dict or origin is dict:
        row = result.first()
        if row is None:
            return {}
        return row.as_dict()

    if return_type is Row:
        return result.first()

    if return_type in (int, float, str, bool, bytes):
        value = result.scalar()
        if value is None:
            if return_type is int:
                return result.rowcount
            return None
        return SqlTypeMapper.convert_result(value, return_type)

    return result


def _get_connection(args, kwargs, default_connection=None):
    """
    从参数中提取连接对象。

    检查策略：
        1. 关键字参数 connection
        2. 第一个位置参数是否为 Connection 实例
        3. 默认连接

    参数：
        args: 位置参数列表
        kwargs: 关键字参数字典
        default_connection: 默认连接对象

    返回：
        (connection, remaining_args, remaining_kwargs) 元组
    """
    connection = kwargs.pop('connection', None)

    if connection is None and args:
        from .connection import Connection
        first_arg = args[0]
        if isinstance(first_arg, Connection):
            connection = first_arg
            args = args[1:]

    if connection is None:
        connection = default_connection

    return connection, args, kwargs


def _make_sql_wrapper(func, dialect=None, connection=None, sql=None,
                      auto_convert=True, skip_first_arg=False):
    """
    创建 SQL 函数包装器的内部辅助函数。

    参数：
        func: 原始函数
        dialect: 方言名称
        connection: 默认连接对象
        sql: SQL 语句模板
        auto_convert: 是否自动类型转换
        skip_first_arg: 是否跳过第一个参数（用于类方法的 self）

    返回：
        包装后的函数
    """
    param_names, param_types, return_type = _get_signature_info(func)

    if skip_first_arg and param_names:
        param_names = param_names[1:]
        param_types = param_types[1:]

    sql_param_types, sql_return_type = _resolve_sql_types(param_types, return_type)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        call_args = list(args)
        call_kwargs = dict(kwargs)

        if skip_first_arg:
            self_arg = call_args[0] if call_args else None
            call_args = call_args[1:]
        else:
            self_arg = None

        conn, remaining_args, remaining_kwargs = _get_connection(
            call_args, call_kwargs, connection
        )

        if auto_convert and param_types:
            num_convert = min(len(remaining_args), len(param_types))
            convert_args_list = list(remaining_args[:num_convert])
            convert_types = param_types[:num_convert]
            converted = _convert_args(convert_args_list, convert_types)
            remaining_args = converted + list(remaining_args[num_convert:])

        sql_stmt = sql
        if sql_stmt is None:
            if self_arg is not None:
                result = func(self_arg, *remaining_args, **remaining_kwargs)
            else:
                result = func(*remaining_args, **remaining_kwargs)

            if isinstance(result, str):
                sql_stmt = result
                params = []
            elif isinstance(result, tuple) and len(result) == 2:
                sql_stmt, params = result
            elif conn is None:
                return result
            else:
                return result
        else:
            params = remaining_args

        if conn is not None and isinstance(sql_stmt, str):
            exec_params = params if params else None
            result = conn.execute(sql_stmt, exec_params)

        if auto_convert and return_type is not None:
            result = _convert_result(result, return_type)

        return result

    wrapper._sql_info = {
        'dialect': dialect,
        'connection': connection,
        'sql': sql,
        'auto_convert': auto_convert,
        'param_names': param_names,
        'param_types': param_types,
        'return_type': return_type,
        'sql_param_types': sql_param_types,
        'sql_return_type': sql_return_type,
        'skip_first_arg': skip_first_arg,
    }

    return wrapper


def sql_function(dialect=None, connection=None, sql=None, auto_convert=True):
    """
    SQL 函数装饰器

    将一个 Python 函数标记为 SQL 操作函数。
    支持从函数签名的类型注解自动推断参数类型和返回类型，
    使用 SqlTypeMapper 进行类型映射，并自动处理参数和结果转换。

    连接传递方式：
        - 第一个位置参数为 Connection 对象
        - 关键字参数 connection=conn
        - 装饰器参数 connection=conn（默认连接）

    参数：
        dialect: 方言名称（可选）
        connection: 默认连接对象（可选，也可在调用时传入）
        sql: SQL 语句模板（可选，如果函数体不提供 SQL）
        auto_convert: 是否自动类型转换，默认为 True

    返回：
        装饰器函数

    用法：
        @sql_function()
        def get_user(user_id: int) -> dict:
            return "SELECT * FROM users WHERE id = %s", (user_id,)

        # 使用默认连接
        @sql_function(connection=my_conn)
        def list_users() -> list:
            return "SELECT * FROM users"

        # 直接传入连接调用
        result = get_user(conn, 1)
        result = get_user(1, connection=conn)
    """

    def decorator(func):
        return _make_sql_wrapper(
            func, dialect=dialect, connection=connection, sql=sql,
            auto_convert=auto_convert, skip_first_arg=False
        )

    return decorator


def sql_func_name(name):
    """
    指定 SQL 函数的名称标记。

    用于 @sql_module 中的方法，单独指定函数名标识。

    参数：
        name: 函数名称标识

    返回：
        装饰器函数

    用法：
        @sql_module(dialect="mysql")
        class UserRepo:
            @sql_func_name("get_user_by_id")
            def get_user(self, user_id: int) -> dict:
                return "SELECT * FROM users WHERE id = %s", (user_id,)
    """
    def decorator(func):
        setattr(func, _FUNC_NAME_ATTR, name)
        return func
    return decorator


def sql_module(dialect=None, connection=None, auto_convert=True):
    """
    SQL 模块装饰器

    将一个类标记为 SQL 模块，类中的所有公共方法自动使用 sql_function 装饰器包装。
    支持从方法签名的类型注解自动推断参数类型和返回类型。

    方法的第一个参数（self）会被自动跳过，不会作为 SQL 参数传递。

    参数：
        dialect: 方言名称（可选，类级别配置）
        connection: 默认连接对象（可选，类级别配置）
        auto_convert: 是否自动类型转换，默认为 True

    返回：
        装饰器函数

    用法：
        @sql_module(dialect="mysql", connection=my_conn)
        class UserRepository:
            def get_user(self, user_id: int) -> dict:
                return "SELECT * FROM users WHERE id = %s", (user_id,)

            def list_users(self) -> list:
                return "SELECT * FROM users"

            @sql_func_name("create_user")
            def add_user(self, name: str, age: int) -> int:
                return "INSERT INTO users (name, age) VALUES (%s, %s)", (name, age)
    """

    def decorator(cls):
        for name in dir(cls):
            if name.startswith('_'):
                continue

            attr = getattr(cls, name)
            if not callable(attr):
                continue

            if isinstance(attr, type):
                continue

            has_sql_info = hasattr(attr, _SQL_INFO_ATTR)
            if has_sql_info:
                continue

            custom_func_name = getattr(attr, _FUNC_NAME_ATTR, None)

            wrapped = _make_sql_wrapper(
                attr, dialect=dialect, connection=connection, sql=None,
                auto_convert=auto_convert, skip_first_arg=True
            )

            if custom_func_name is not None:
                wrapped._sql_info['func_name'] = custom_func_name

            setattr(cls, name, wrapped)

        return cls

    return decorator
