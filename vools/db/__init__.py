"""
vools.db — 数据库集成子包

提供 PostgreSQL 连接管理、连接池封装等功能。
子模块：
    postgresql  — PostgreSQL 连接管理与查询执行

用法：
    from vools.db.postgresql import PostgreSQLConnection
    conn = PostgreSQLConnection(host='localhost', port=5432, user='postgres')
    conn.execute('SELECT 1')
"""

__all__ = [
    "postgresql",
    "PostgreSQLConnection",
]

from .postgresql import PostgreSQLConnection