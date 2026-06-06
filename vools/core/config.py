"""
配置管理模块
支持多环境配置和动态配置
"""

__all__ = ['DatabaseConfig', 'CacheConfig', 'AppConfig', 'ConfigManager']

import os
from typing import Dict, Optional

try:
    from dataclasses import dataclass
except ImportError:
    from attr import attrs, attrib

    def dataclass(cls):
        """兼容 dataclass 的装饰器（使用 attrs）"""
        return attrs(cls)


@dataclass
class DatabaseConfig:
    """数据库配置"""
    host: str = "localhost"
    port: int = 5432
    user: str = ""
    password: str = ""
    database: str = ""


@dataclass
class CacheConfig:
    """缓存配置"""
    duration: int = 3
    max_size: int = 1000
    enabled: bool = True


@dataclass
class AppConfig:
    """应用配置"""
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"


class ConfigManager:
    """配置管理器"""

    def __init__(self):
        self._env = os.environ.get("VOOLS_ENV", "development")
        self._load_config()

    def _load_config(self):
        """加载配置"""
        self.database = DatabaseConfig()
        self.cache = CacheConfig()
        self.app = AppConfig(environment=self._env)

        self._load_from_env()

    def _load_from_env(self):
        """从环境变量加载配置"""
        if os.environ.get("DB_HOST"):
            self.database.host = os.environ["DB_HOST"]
        if os.environ.get("DB_PORT"):
            self.database.port = int(os.environ["DB_PORT"])
        if os.environ.get("DB_USER"):
            self.database.user = os.environ["DB_USER"]
        if os.environ.get("DB_PASSWORD"):
            self.database.password = os.environ["DB_PASSWORD"]
        if os.environ.get("DB_NAME"):
            self.database.database = os.environ["DB_NAME"]

        if os.environ.get("CACHE_DURATION"):
            self.cache.duration = int(os.environ["CACHE_DURATION"])
        if os.environ.get("CACHE_MAX_SIZE"):
            self.cache.max_size = int(os.environ["CACHE_MAX_SIZE"])

        if os.environ.get("DEBUG"):
            self.app.debug = os.environ["DEBUG"].lower() == "true"
        if os.environ.get("LOG_LEVEL"):
            self.app.log_level = os.environ["LOG_LEVEL"]

    def load_from_file(self, filepath: str):
        """从文件加载配置"""
        import yaml
        with open(filepath, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)

        if 'database' in config_data:
            for key, value in config_data['database'].items():
                setattr(self.database, key, value)
        if 'cache' in config_data:
            for key, value in config_data['cache'].items():
                setattr(self.cache, key, value)
        if 'app' in config_data:
            for key, value in config_data['app'].items():
                setattr(self.app, key, value)