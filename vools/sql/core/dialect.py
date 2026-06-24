"""
vools.sql.core.dialect - SQL 方言抽象基类与注册表

提供 SQL 方言的抽象基类，定义方言必须实现的接口，
以及全局方言注册表，用于注册和获取各种数据库方言。
"""

import abc
import importlib
from typing import Dict, List

from .config import DialectConfig
from .types import SqlTypeMapper


_DIALECT_REGISTRY: Dict[str, type] = {}


class Dialect(abc.ABC):
    """
    SQL 方言抽象基类

    定义了不同数据库方言必须实现的接口，包括类型映射、连接创建、
    标识符引用、SQL 构建器等。
    """

    @abc.abstractmethod
    def get_type_mapper(self) -> SqlTypeMapper:
        """
        获取方言的类型映射器

        返回：
            SqlTypeMapper 实例
        """
        ...

    @abc.abstractmethod
    def create_connection(self, **kwargs) -> 'Connection':
        """
        创建数据库连接

        参数：
            **kwargs: 连接参数

        返回：
            Connection 抽象类实例
        """
        ...

    @abc.abstractmethod
    def quote_identifier(self, identifier: str) -> str:
        """
        引用标识符（表名、列名等）

        参数：
            identifier: 标识符名称

        返回：
            引用后的标识符
        """
        ...

    @abc.abstractmethod
    def quote_string(self, value: str) -> str:
        """
        引用字符串值

        参数：
            value: 字符串值

        返回：
            引用后的字符串
        """
        ...

    @abc.abstractmethod
    def get_builder_class(self) -> type:
        """
        获取 SQL 构建器类

        返回：
            SQL 构建器类
        """
        ...

    @abc.abstractmethod
    def get_paramstyle(self) -> str:
        """
        获取参数占位符风格

        返回：
            参数风格字符串，如 'qmark', 'format', 'pyformat' 等
        """
        ...

    def is_available(self) -> bool:
        """
        检查驱动是否可用

        默认尝试 import driver 模块。

        返回：
            驱动是否可用
        """
        try:
            importlib.import_module(self.get_config().driver)
            return True
        except ImportError:
            return False

    def get_config(self) -> DialectConfig:
        """
        获取方言配置

        返回：
            DialectConfig 实例
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement get_config()"
        )


def register_dialect(name: str, dialect_class: type) -> None:
    """
    注册方言类

    参数：
        name: 方言名称
        dialect_class: 方言类（Dialect 的子类）
    """
    _DIALECT_REGISTRY[name.lower()] = dialect_class


def get_dialect(name: str) -> type:
    """
    获取方言类

    参数：
        name: 方言名称

    返回：
        方言类

    异常：
        KeyError: 方言未注册
    """
    name_lower = name.lower()
    if name_lower not in _DIALECT_REGISTRY:
        raise KeyError(f"Dialect '{name}' not registered")
    return _DIALECT_REGISTRY[name_lower]


def list_dialects() -> List[str]:
    """
    列出所有已注册方言

    返回：
        方言名称列表
    """
    return list(_DIALECT_REGISTRY.keys())


def has_dialect(name: str) -> bool:
    """
    检查方言是否已注册

    参数：
        name: 方言名称

    返回：
        是否已注册
    """
    return name.lower() in _DIALECT_REGISTRY
