"""
vools 配置文件模板

请复制此文件为 config.py 并填写相应的配置值
"""

# Spark 配置
SPARK_CONFIG = {
    'gateway_port': None,      # Spark Gateway 端口，需要填写
    'auth_token': None,        # Spark 认证令牌，需要填写
    'version': 140,            # Spark 版本，默认 1.4.0
    'path': None,              # 自定义路径，需要填写
}

# 数据库配置（如果需要）
DATABASE_CONFIG = {
    'host': None,              # 数据库主机，需要填写
    'port': None,              # 数据库端口，需要填写
    'user': None,              # 数据库用户，需要填写
    'password': None,          # 数据库密码，需要填写
    'database': None,          # 数据库名称，需要填写
}

# 其他配置
OTHER_CONFIG = {
    'cache_duration': 3,       # 缓存持续时间（秒）
    'max_workers': 10,         # 最大工作线程数
    'retry_times': 3,          # 重试次数
}

# 敏感路径配置
PATHS = {
    'base_path': None,         # 基础路径，需要填写
    'data_path': None,         # 数据路径，需要填写
    'output_path': None,       # 输出路径，需要填写
}
