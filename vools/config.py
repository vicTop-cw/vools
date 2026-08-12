"""
vools 配置模块

提供全局配置管理功能，支持数据库连接、缓存策略、线程池等配置项。

所有配置项都有详细说明，包括：
- 配置项用途
- 默认值
- 应用模块
- 可选值范围
"""

__all__ = ['DATABASE_CONFIG', 'OTHER_CONFIG', 'PATHS', 'ConfigManager', 'config']

# ============================================================================
# 数据库配置
# ============================================================================
# 用于数据库相关功能（如 persist 装饰器的持久化存储）
# 当前主要作为预留配置，实际使用时需要填写真实连接信息
# ============================================================================

DATABASE_CONFIG = {
    'host': None,              # 数据库主机地址，如 'localhost' 或 '127.0.0.1'
    'port': None,              # 数据库端口，如 MySQL 默认 3306，PostgreSQL 默认 5432
    'user': None,              # 数据库用户名
    'password': None,          # 数据库密码
    'database': None,          # 数据库名称
}

# ============================================================================
# 运行时配置
# ============================================================================
# 控制 vools 库的运行时行为，影响多个模块的默认行为
# ============================================================================

OTHER_CONFIG = {
    # 缓存相关
    'cache_duration': 3,       # 缓存持续时间（秒），应用于 memorize 装饰器的默认缓存时长
    'default_force_when': None, # 默认强制刷新条件，应用于 cache.py 的 persist 装饰器
    'default_target_folder': None, # 默认目标文件夹，应用于 cache.py 的 persist 装饰器
    
    # 并发相关
    'max_workers': 10,         # 最大工作线程数，应用于 TaskQueue 和 WorkerPool 的默认值
    
    # 重试相关
    'retry_times': 3,          # 默认重试次数，应用于 retry 装饰器的默认值
    
    # 数据处理相关
    'NONE_is_None': False,     # 是否将 NONE 占位符视为 None，应用于 data/seq.py 的 Seq 类
}

# ============================================================================
# 路径配置
# ============================================================================
# 用于文件操作相关功能，指定数据存储和输出的基础路径
# ============================================================================

PATHS = {
    'base_path': None,         # 项目基础路径，所有相对路径的基准目录
    'data_path': None,         # 数据文件存储路径，如 CSV、JSON 文件的读取位置
    'output_path': None,       # 输出文件路径，如生成报告、导出数据的保存位置
}

# ============================================================================
# 配置管理器类
# ============================================================================
# 提供统一的配置访问接口，支持属性式访问
# ============================================================================

class ConfigManager:
    """
    配置管理器
    
    提供全局配置的统一访问接口，支持通过属性方式访问各配置项。
    
    Example:
        from vools.config import config
        
        # 访问配置
        print(config.database.host)
        print(config.other.cache_duration)
        print(config.paths.base_path)
        
        # 修改配置
        config.other.cache_duration = 5
        config.paths.base_path = '/data'
    """

    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.
        
        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function
            sub_f: Post-processing function (no return value expected)
        
        Returns:
            self, for chaining
        """
        rs = self
        if pre_f:
            rs = pre_f(rs)
        rs = f(rs)
        if sub_f:
            sub_f(rs)
        return self

    def __init__(self):
        self.database = DATABASE_CONFIG
        self.other = OTHER_CONFIG
        self.paths = PATHS

# ============================================================================
# 全局配置实例
# ============================================================================
# 推荐使用此实例访问和修改配置
# ============================================================================

config = ConfigManager()
# Global config instance, unified config access interface.
# Usage: from vools.config import config

# ============================================================================
# 配置项影响的模块汇总
# ============================================================================
# | 配置项 | 影响模块 | 说明 |
# |--------|----------|------|
# | cache_duration | decorators/cache.py | memorize 装饰器默认缓存时长 |
# | max_workers | task/core/queue.py | TaskQueue 和 WorkerPool 默认线程数 |
# | retry_times | decorators/control.py | retry 装饰器默认重试次数 |
# | default_force_when | decorators/cache.py | persist 装饰器默认强制刷新条件 |
# | default_target_folder | decorators/cache.py | persist 装饰器默认目标文件夹 |
# | NONE_is_None | data/seq.py | Seq 类处理 NONE 占位符的方式 |
# | database.* | decorators/cache.py | persist 装饰器数据库持久化（预留） |
# | paths.* | 多个模块 | 文件读写操作的基础路径 |
