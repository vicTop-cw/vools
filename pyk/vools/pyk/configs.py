"""
pyk.configs - PySpark 专用配置（vools-pyk）

注意：本模块与 ``vools/config.py``（通用工具配置）**不是同一个**。
此处集中存放 pyspark / SparkSession / Hive / PostgreSQL / 生产路径 相关的默认配置，
供 pyk、look_upon 等 spark 层模块使用。

公开库安全约定：
- 本文件**不得出现**任何生产环境的明文连接串 / 账号 / 密码 / 内网路径。
- 生产 PostgreSQL 的账号、密码一律以**密文**常量存放（见 ``PG_*_CIPHER``），
  运行时通过 ``vools`` 核心库的 ``VText.decrypt`` 解出明文再连接；
  解密密钥从环境变量 ``PYK_SECRET_KEY`` 注入，代码里不落明文密钥。
- 生产路径（共享目录 / 默认库名等）一律走环境变量 ``PYK_*`` 或本文件显式覆写变量，
  未配置时用中性默认值（公开库可跑通但不连生产）。

用法:
    from vools.pyk.configs import pg_credentials, share_dir, default_db
    url, user, password = pg_credentials()
    from vools.pyk import get_spark
    spark = get_spark(**get_spark_conf(app_name="my_app"))
"""

from __future__ import absolute_import

__all__ = [
    # spark 基础
    "SPARK_APP_NAME",
    "SPARK_MASTER",
    "ENABLE_HIVE",
    "BIND_ADDRESS",
    "WAREHOUSE_PATH",
    "METASTORE_URIS",
    "DEFAULT_SPARK_CONF",
    "get_spark_conf",
    "load_config",
    # 生产连接 / 路径（密文 + 环境变量）
    "PG_URL_CIPHER",
    "PG_USER_CIPHER",
    "PG_PASSWORD_CIPHER",
    "PG_URL_PLAIN",
    "PG_USER_PLAIN",
    "PG_PASSWORD_PLAIN",
    "pg_credentials",
    "secret_key",
    "share_dir",
    "default_db",
    "UPON_SQL_FILE",
    "upon_sql_file",
    "PG_JAR",
    "pg_jar",
    "encrypt_secret",
    "decrypt_secret",
]

import os
from typing import Any, Dict, Optional, Tuple


# ============================================================================
# 一、中性默认值（不含任何生产信息）
# ============================================================================

SPARK_APP_NAME = "vools_pyk"          # 应用名，生产可用 env PYK_SPARK_APP_NAME 覆盖
SPARK_MASTER: Optional[str] = None    # None = 交 pyspark 默认
ENABLE_HIVE = True                    # 是否 enableHiveSupport()
BIND_ADDRESS = "127.0.0.1"            # driver bind/host
WAREHOUSE_PATH: Optional[str] = None  # Hive warehouse；默认交 spark
METASTORE_URIS: Optional[str] = None  # Hive metastore；默认无（本地 derby）


# ============================================================================
# 二、生产 PostgreSQL 连接（**密文**存放；公开库留空）
# ============================================================================
# 说明：
#   - 生产部署时把下列 *_CIPHER 常量替换为真实密文（用 encrypt_secret 生成）；
#     或者通过环境变量 PYK_PG_URL_CIPHER / PYK_PG_USER_CIPHER / PYK_PG_PASSWORD_CIPHER 注入。
#   - 明文默认值 *_PLAIN 仅用于本地 / 无密文场景，生产请设为 "" 走密文。
#   - 解密密钥 PYK_SECRET_KEY 只从环境变量读取，**代码里绝不写死**。

PG_URL_CIPHER: str = ""              # 生产 JDBC url 密文（F:.../A:.../E:...）
PG_USER_CIPHER: str = ""             # 生产用户名密文
PG_PASSWORD_CIPHER: str = ""         # 生产密码密文

# 明文默认（本地测试用；生产保持空串以强制走密文）
PG_URL_PLAIN: str = "jdbc:postgresql://localhost:5432/default_db"
PG_USER_PLAIN: str = "postgres"
PG_PASSWORD_PLAIN: str = ""


# ============================================================================
# 三、生产路径 / 名称（变量化，走环境变量）
# ============================================================================

# 生产共享目录（look_upon 落 CSV/Parquet/错误日志用）；默认中性路径
_SHARE_DIR: str = "file:///tmp/vools_share"

# 生产默认数据库名（临时表默认落库）；默认中性名
_DEFAULT_DB: str = "default"

# look_upon 默认 SQL 文件路径（get_replaced_sql / run_doneEx 用）；
# 生产填 env PYK_UPON_SQL_FILE 或显式覆写，公开库留空（未配置时 look_upon 会明确报错）
UPON_SQL_FILE: str = ""

# PostgreSQL JDBC 驱动 jar 路径（look_upon query / spark 侧 JDBC 读 PG 用）；
# 生产填 env PYK_PG_JAR 或显式覆写，公开库留空（未配置时 look_upon 会明确报错）
PG_JAR: str = ""


# ============================================================================
# 四、密钥 / 加解密（走 vools 核心库 VText.encrypt/decrypt）
# ============================================================================

def secret_key() -> bytes:
    """取解密密钥（环境变量 PYK_SECRET_KEY 优先，未设置抛错——绝不回退到内建默认）。

    生产明文密钥只存在于环境变量里；公开库代码内没有默认密钥，
    因此未配置时直接报错而不是用弱默认值。
    """
    raw = os.environ.get("PYK_SECRET_KEY")
    if not raw:
        raise RuntimeError(
            "缺少解密密钥：请设置环境变量 PYK_SECRET_KEY（与生成密文时一致）。"
        )
    return raw.encode("utf-8")


def encrypt_secret(plaintext: str, way: Optional[str] = None) -> str:
    """把明文加密成密文串（用于生成 configs 里的 PG_*_CIPHER 常量）。

    Args:
        plaintext: 明文。
        way: "fernet"（默认，需 cryptography）/ "xor"（纯标准库，弱）/ "aes"。

    Returns:
        带前缀密文串（F:/A:/E:）。
    """
    from ..data.vtext import VText
    return str(VText(plaintext).encrypt(way=way or "fernet", key=secret_key()))


def decrypt_secret(ciphertext: str) -> str:
    """用 vools 核心库解密带前缀密文串，返回明文。

    Args:
        ciphertext: "F:..."/"A:..."/"E:..." 密文；空串返回空串。

    Returns:
        明文 str。
    """
    from ..data.vtext import VText
    if not ciphertext:
        return ""
    return str(VText(ciphertext).decrypt(way=None, key=secret_key()))


# ============================================================================
# 五、对外取配置的便捷函数
# ============================================================================

def pg_credentials() -> Tuple[str, str, str]:
    """返回 (url, user, password) 三元组（运行时已解密为明文）。

    优先级：环境变量 PYK_PG_*_CIPHER > 本文件 PG_*_CIPHER > 环境变量 PYK_PG_* > *_PLAIN。
    """
    url_c = (
        os.environ.get("PYK_PG_URL_CIPHER", "")
        or PG_URL_CIPHER
    )
    user_c = (
        os.environ.get("PYK_PG_USER_CIPHER", "")
        or PG_USER_CIPHER
    )
    pass_c = (
        os.environ.get("PYK_PG_PASSWORD_CIPHER", "")
        or PG_PASSWORD_CIPHER
    )
    if url_c or user_c or pass_c:
        # 有密文就必须能解（否则拒绝运行，避免拿到错凭据）
        return (
            decrypt_secret(url_c) if url_c else "",
            decrypt_secret(user_c) if user_c else "",
            decrypt_secret(pass_c) if pass_c else "",
        )
    # 无密文：回退明文默认 / 环境变量明文
    return (
        os.environ.get("PYK_PG_URL", PG_URL_PLAIN),
        os.environ.get("PYK_PG_USER", PG_USER_PLAIN),
        os.environ.get("PYK_PG_PASSWORD", PG_PASSWORD_PLAIN),
    )


def share_dir() -> str:
    """取生产共享目录（env PYK_SHARE_DIR 优先，其次覆写 _SHARE_DIR，最后中性默认）。"""
    return os.environ.get("PYK_SHARE_DIR", _SHARE_DIR)


def default_db() -> str:
    """取生产默认库名（env PYK_DEFAULT_DB 优先，其次覆写 _DEFAULT_DB，最后中性默认）。"""
    return os.environ.get("PYK_DEFAULT_DB", _DEFAULT_DB)


def upon_sql_file() -> str:
    """取 look_upon 默认 SQL 文件路径（env PYK_UPON_SQL_FILE 优先，其次覆写 UPON_SQL_FILE）。

    未配置时返回空串——调用方应明确报错，而不是静默去读一个不存在/未知的路径。
    """
    return os.environ.get("PYK_UPON_SQL_FILE", UPON_SQL_FILE)


def pg_jar() -> str:
    """取 PostgreSQL JDBC 驱动 jar 路径。

    优先级：env PYK_PG_JAR > 本文件 PG_JAR。

    Returns:
        驱动 jar 完整路径；未配置返回 PG_JAR 默认。
    """
    return os.environ.get("PYK_PG_JAR", PG_JAR)


# ============================================================================
# 六、SparkConf 默认 + get_spark_conf（原有，保留）
# ============================================================================

_ENV_MAP: Dict[str, str] = {
    "PYK_SPARK_APP_NAME": "SPARK_APP_NAME",
    "PYK_SPARK_MASTER": "SPARK_MASTER",
    "PYK_ENABLE_HIVE": "ENABLE_HIVE",
    "PYK_BIND_ADDRESS": "BIND_ADDRESS",
    "PYK_WAREHOUSE_PATH": "WAREHOUSE_PATH",
    "PYK_METASTORE_URIS": "METASTORE_URIS",
    "SPARK_MASTER": "SPARK_MASTER",
    "SPARK_WAREHOUSE_PATH": "WAREHOUSE_PATH",
    "HIVE_METASTORE_URIS": "METASTORE_URIS",
}


def _to_bool(value: str) -> bool:
    """把环境变量字符串转成 bool，容忍常见写法。"""
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def load_config() -> Dict[str, Any]:
    """从环境变量加载 pyspark 配置（无生产硬编码，缺省用中性默认值）。"""
    cfg: Dict[str, Any] = {
        "SPARK_APP_NAME": SPARK_APP_NAME,
        "SPARK_MASTER": SPARK_MASTER,
        "ENABLE_HIVE": ENABLE_HIVE,
        "BIND_ADDRESS": BIND_ADDRESS,
        "WAREHOUSE_PATH": WAREHOUSE_PATH,
        "METASTORE_URIS": METASTORE_URIS,
    }
    for env_key, field in _ENV_MAP.items():
        raw = os.environ.get(env_key)
        if raw is None or raw == "":
            continue
        if field == "ENABLE_HIVE":
            cfg[field] = _to_bool(raw)
        else:
            cfg[field] = raw
    return cfg


DEFAULT_SPARK_CONF: Dict[str, Any] = {
    "spark.sql.shuffle.partitions": 200,
    "spark.sql.session.timeZone": "Asia/Shanghai",
    "spark.serializer": "org.apache.spark.serializer.KryoSerializer",
}


def get_spark_conf(app_name: Optional[str] = None, **overrides: Any) -> Dict[str, Any]:
    """返回可直接传给 ``pyk.get_spark`` 的关键字参数。

    Args:
        app_name: 覆盖应用名；None 则用配置里的 SPARK_APP_NAME。
        **overrides: 直接覆盖任意字段，如 ``master="yarn"``、``enable_hive=False``、
                     ``spark_conf={"spark.executor.memory": "4g"}``（会扁平展开为 SparkConf 项）。

    Returns:
        dict，可直接 ``get_spark(**get_spark_conf(...))``。
    """
    cfg = load_config()
    result: Dict[str, Any] = {
        "app_name": app_name or cfg["SPARK_APP_NAME"],
        "master": cfg["SPARK_MASTER"],
        "enable_hive": cfg["ENABLE_HIVE"],
        "bind_address": cfg["BIND_ADDRESS"],
    }
    # warehouse / metastore / 默认项全部扁平展开为 SparkConf 项
    spark_conf: Dict[str, Any] = dict(DEFAULT_SPARK_CONF)
    if cfg["WAREHOUSE_PATH"]:
        spark_conf["spark.sql.warehouse.dir"] = cfg["WAREHOUSE_PATH"]
    if cfg["METASTORE_URIS"]:
        spark_conf["hive.metastore.uris"] = cfg["METASTORE_URIS"]
    extra_conf = overrides.pop("spark_conf", None)
    if extra_conf:
        spark_conf.update(extra_conf)
    result.update(spark_conf)
    result.update(overrides)
    return result