"""
vools.sql.core.config - SQL 方言配置

提供 SQL 方言的配置数据类，包含连接参数、语法特征等配置信息。
"""

from typing import Dict

from vools.core.dataclass_compat import dataclass, field


@dataclass
class DialectConfig:
    """
    SQL 方言配置

    属性：
        name: 方言名称（如 'mysql', 'postgres', 'sqlite'）
        driver: 驱动模块名（如 'pymysql', 'psycopg2', 'sqlite3'）
        default_port: 默认端口（sqlite 等文件数据库为 0）
        default_host: 默认主机
        default_user: 默认用户名
        default_database: 默认数据库
        connection_params: 额外连接参数
        paramstyle: 参数占位符风格（'qmark', 'format', 'pyformat', 'numeric', 'named'）
        identifier_quote: 标识符引用符
        string_quote: 字符串引用符
        extra_config: 额外配置
    """
    name: str
    driver: str
    default_port: int = 0
    default_host: str = 'localhost'
    default_user: str = ''
    default_database: str = ''
    connection_params: Dict = field(default_factory=dict)
    paramstyle: str = 'pyformat'
    identifier_quote: str = '"'
    string_quote: str = "'"
    extra_config: Dict = field(default_factory=dict)

    def __post_init__(self):
        self.name = self.name.lower()
        if not self.driver:
            raise ValueError("driver must not be empty")
