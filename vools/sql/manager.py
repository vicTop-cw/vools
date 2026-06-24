"""
vools.sql.manager - SQL 方言统一管理器

提供各种数据库方言的统一注册、配置、实例化和查询接口。

核心功能：
1. 方言注册 - 注册方言类及其配置
2. 方言获取 - 获取方言类或创建方言实例
3. 可用性检测 - 检查方言驱动是否可用
4. 配置管理 - 获取、设置方言配置
5. 配置持久化 - 保存/加载配置到 JSON 文件
6. 实例缓存 - 方言实例的单例缓存

用法：
    from vools.sql.manager import manager, register_dialect

    # 注册方言
    register_dialect('mysql', MySQLDialect, {
        'driver': 'pymysql',
        'default_port': 3306,
    })

    # 查询状态
    print(manager.is_available('mysql'))  # True/False

    # 创建实例
    dialect = manager.create_dialect('mysql', host='localhost', user='root')

    # 配置管理
    manager.set_config('mysql', {'default_port': 3307})
    manager.save_config()
"""

import os
import json
import importlib
from typing import Dict, List, Optional, Type, Any

from vools.core.dataclass_compat import asdict

from .core.config import DialectConfig
from .core.dialect import Dialect
from .core.dialect import (
    register_dialect as _core_register,
    get_dialect as _core_get,
    list_dialects as _core_list,
    has_dialect as _core_has,
)


# ============================================================================
# DialectManager 类
# ============================================================================

class DialectManager:
    """
    SQL 方言统一管理器

    提供方言类的注册、查询、实例化以及配置管理的统一接口。
    采用单例模式，确保全局只有一个管理器实例。

    用法：
        manager = DialectManager()

        # 注册方言
        manager.register('mysql', MySQLDialect, DialectConfig(
            name='mysql',
            driver='pymysql',
            default_port=3306,
        ))

        # 查询可用性
        if manager.is_available('mysql'):
            dialect = manager.create_dialect('mysql', host='localhost')

        # 配置持久化
        manager.save_config('dialects.json')
        manager.load_config('dialects.json')
    """

    _instance: Optional['DialectManager'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._dialects: Dict[str, Type[Dialect]] = {}
        self._configs: Dict[str, DialectConfig] = {}
        self._instances: Dict[str, Dialect] = {}
        self._config_file: Optional[str] = None

    # ------------------------------------------------------------------------
    # 注册和注销
    # ------------------------------------------------------------------------

    def register(
        self,
        name: str,
        dialect_class: Type[Dialect],
        config: Optional[DialectConfig] = None,
    ) -> None:
        """
        注册方言

        参数：
            name: 方言名称
            dialect_class: 方言类（Dialect 的子类）
            config: 方言配置，为 None 则使用默认配置
        """
        name_lower = name.lower()

        if config is None:
            config = DialectConfig(
                name=name_lower,
                driver=name_lower,
            )
        else:
            config.name = name_lower

        self._dialects[name_lower] = dialect_class
        self._configs[name_lower] = config

        _core_register(name_lower, dialect_class)

        self._instances.pop(name_lower, None)

    def unregister(self, name: str) -> bool:
        """
        取消注册方言

        参数：
            name: 方言名称

        返回：
            是否成功取消
        """
        name_lower = name.lower()
        existed = name_lower in self._dialects

        self._dialects.pop(name_lower, None)
        self._configs.pop(name_lower, None)
        self._instances.pop(name_lower, None)

        return existed

    # ------------------------------------------------------------------------
    # 方言类获取
    # ------------------------------------------------------------------------

    def get_dialect(self, name: str) -> Type[Dialect]:
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
        if name_lower not in self._dialects:
            raise KeyError(f"Dialect '{name}' not registered")
        return self._dialects[name_lower]

    # ------------------------------------------------------------------------
    # 方言实例创建
    # ------------------------------------------------------------------------

    def create_dialect(self, name: str, **kwargs) -> Dialect:
        """
        创建方言实例

        参数：
            name: 方言名称
            **kwargs: 传递给方言构造函数的参数

        返回：
            方言实例

        异常：
            KeyError: 方言未注册
        """
        name_lower = name.lower()
        dialect_class = self.get_dialect(name_lower)

        cache_key = name_lower + ':' + _make_cache_key(kwargs)
        if cache_key in self._instances:
            return self._instances[cache_key]

        instance = dialect_class(**kwargs)
        self._instances[cache_key] = instance
        return instance

    # ------------------------------------------------------------------------
    # 可用性检测
    # ------------------------------------------------------------------------

    def is_available(self, name: str) -> bool:
        """
        检查方言是否可用（驱动是否可导入）

        参数：
            name: 方言名称

        返回：
            是否可用
        """
        name_lower = name.lower()
        config = self._configs.get(name_lower)
        if not config:
            return False

        try:
            importlib.import_module(config.driver)
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------------
    # 列表查询
    # ------------------------------------------------------------------------

    def list_dialects(self) -> List[str]:
        """
        列出所有已注册方言

        返回：
            方言名称列表
        """
        return list(self._dialects.keys())

    def list_available(self) -> List[str]:
        """
        列出所有可用方言

        返回：
            可用的方言名称列表
        """
        return [name for name in self._dialects if self.is_available(name)]

    # ------------------------------------------------------------------------
    # 配置管理
    # ------------------------------------------------------------------------

    def get_config(self, name: str) -> Optional[DialectConfig]:
        """
        获取方言配置

        参数：
            name: 方言名称

        返回：
            DialectConfig 实例，不存在返回 None
        """
        return self._configs.get(name.lower())

    def set_config(self, name: str, config: Any) -> bool:
        """
        设置方言配置

        参数：
            name: 方言名称
            config: 配置，可以是 DialectConfig 实例或 dict

        返回：
            是否成功
        """
        name_lower = name.lower()
        if name_lower not in self._dialects:
            return False

        if isinstance(config, dict):
            existing = self._configs.get(name_lower)
            if existing:
                for key, value in config.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
            else:
                self._configs[name_lower] = DialectConfig(
                    name=name_lower,
                    driver=config.get('driver', name_lower),
                    **{k: v for k, v in config.items() if k != 'name' and k != 'driver'}
                )
        elif isinstance(config, DialectConfig):
            config.name = name_lower
            self._configs[name_lower] = config
        else:
            return False

        self._instances.clear()
        return True

    # ------------------------------------------------------------------------
    # 配置持久化
    # ------------------------------------------------------------------------

    def save_config(self, file_path: Optional[str] = None) -> str:
        """
        保存配置到文件（JSON 格式）

        参数：
            file_path: 配置文件路径，为 None 则使用默认路径或上次加载的路径

        返回：
            保存的文件路径
        """
        if file_path is None:
            file_path = self._config_file
            if file_path is None:
                config_dir = os.path.join(os.path.expanduser('~'), '.vools')
                os.makedirs(config_dir, exist_ok=True)
                file_path = os.path.join(config_dir, 'sql_dialects.json')

        config_data = {}
        for name, config in self._configs.items():
            config_data[name] = asdict(config)

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        self._config_file = file_path
        return file_path

    def load_config(self, file_path: Optional[str] = None) -> int:
        """
        从文件加载配置（JSON 格式）

        参数：
            file_path: 配置文件路径，为 None 则使用默认路径或上次保存的路径

        返回：
            加载的配置项数量
        """
        if file_path is None:
            file_path = self._config_file
            if file_path is None:
                config_dir = os.path.join(os.path.expanduser('~'), '.vools')
                file_path = os.path.join(config_dir, 'sql_dialects.json')

        if not os.path.exists(file_path):
            return 0

        with open(file_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        count = 0
        for name, data in config_data.items():
            config = DialectConfig(
                name=data.get('name', name),
                driver=data.get('driver', name),
                default_port=data.get('default_port', 0),
                default_host=data.get('default_host', 'localhost'),
                default_user=data.get('default_user', ''),
                default_database=data.get('default_database', ''),
                connection_params=data.get('connection_params', {}),
                paramstyle=data.get('paramstyle', 'pyformat'),
                identifier_quote=data.get('identifier_quote', '"'),
                string_quote=data.get('string_quote', "'"),
                extra_config=data.get('extra_config', {}),
            )
            self._configs[name.lower()] = config
            count += 1

        self._config_file = file_path
        self._instances.clear()
        return count

    def get_config_file_path(self) -> Optional[str]:
        """
        获取当前配置文件路径

        返回：
            配置文件路径，未设置则返回 None
        """
        return self._config_file

    # ------------------------------------------------------------------------
    # 缓存管理
    # ------------------------------------------------------------------------

    def clear_instance_cache(self, name: Optional[str] = None) -> None:
        """
        清除方言实例缓存

        参数：
            name: 方言名称，为 None 则清除所有缓存
        """
        if name:
            name_lower = name.lower()
            keys_to_remove = [
                k for k in self._instances
                if k.startswith(name_lower + ':') or k == name_lower
            ]
            for k in keys_to_remove:
                del self._instances[k]
        else:
            self._instances.clear()


# ============================================================================
# 内部工具函数
# ============================================================================

def _make_cache_key(kwargs: Dict[str, Any]) -> str:
    """
    根据关键字参数生成缓存键

    参数：
        kwargs: 关键字参数字典

    返回：
        缓存键字符串
    """
    if not kwargs:
        return 'default'
    sorted_items = sorted(kwargs.items(), key=lambda x: x[0])
    return ','.join(f"{k}={v}" for k, v in sorted_items)


# ============================================================================
# 全局管理器实例
# ============================================================================

manager = DialectManager()


# ============================================================================
# 模块级便捷函数
# ============================================================================

def register_dialect(
    name: str,
    dialect_class: Type[Dialect],
    config: Optional[DialectConfig] = None,
) -> None:
    """
    便捷函数：注册方言

    参数：
        name: 方言名称
        dialect_class: 方言类
        config: 方言配置
    """
    manager.register(name, dialect_class, config)


def get_dialect(name: str) -> Type[Dialect]:
    """
    便捷函数：获取方言类

    参数：
        name: 方言名称

    返回：
        方言类
    """
    return manager.get_dialect(name)


def create_dialect(name: str, **kwargs) -> Dialect:
    """
    便捷函数：创建方言实例

    参数：
        name: 方言名称
        **kwargs: 构造参数

    返回：
        方言实例
    """
    return manager.create_dialect(name, **kwargs)


def is_available(name: str) -> bool:
    """
    便捷函数：检查方言是否可用

    参数：
        name: 方言名称

    返回：
        是否可用
    """
    return manager.is_available(name)


def list_dialects() -> List[str]:
    """
    便捷函数：列出所有已注册方言

    返回：
        方言名称列表
    """
    return manager.list_dialects()


def list_available() -> List[str]:
    """
    便捷函数：列出所有可用方言

    返回：
        可用方言名称列表
    """
    return manager.list_available()


def get_config(name: str) -> Optional[DialectConfig]:
    """
    便捷函数：获取方言配置

    参数：
        name: 方言名称

    返回：
        DialectConfig 实例
    """
    return manager.get_config(name)


def set_config(name: str, config: Any) -> bool:
    """
    便捷函数：设置方言配置

    参数：
        name: 方言名称
        config: 配置（DialectConfig 或 dict）

    返回：
        是否成功
    """
    return manager.set_config(name, config)


def save_config(file_path: Optional[str] = None) -> str:
    """
    便捷函数：保存配置到文件

    参数：
        file_path: 文件路径

    返回：
        保存的文件路径
    """
    return manager.save_config(file_path)


def load_config(file_path: Optional[str] = None) -> int:
    """
    便捷函数：从文件加载配置

    参数：
        file_path: 文件路径

    返回：
        加载的配置项数量
    """
    return manager.load_config(file_path)
