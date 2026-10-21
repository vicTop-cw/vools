"""vools.rhop.task.errors - 任务队列异常体系

所有异常都继承 RhopTaskError，方便调用方用一个 except 兜住队列层错误，
同时保留细分类型供上层做分支处理（如 DagValidationError 直接对应提交失败）。
"""

from __future__ import absolute_import


class RhopTaskError(Exception):
    """任务队列异常基类。"""


class DagValidationError(RhopTaskError):
    """依赖图校验失败：依赖的任务不存在，或依赖关系成环。"""


class TaskNotFound(RhopTaskError):
    """按 task_name 找不到任务。"""


class StoreUnavailable(RhopTaskError):
    """存储后端不可用：介质无法承载数据库（如 SFTP/Git/http-url 形态的 shared path）、
    或所在文件系统不可写、或所需驱动缺失。"""


class StoreError(RhopTaskError):
    """存储层读写失败：锁冲突重试耗尽、schema 不匹配、SQL 执行失败等。"""


class PayloadError(RhopTaskError):
    """载荷解密 / 解析失败：密钥不符、密文被篡改、结构不是合法 JSON。"""


class ExecDenied(RhopTaskError):
    """执行被白名单拒绝（exec.allow 未放行且 exec.allow_any 为假）。"""


class HeartbeatError(RhopTaskError):
    """心跳文件读写失败（介质不可达 / 内容非法）。"""


class SecretError(RhopTaskError):
    """配置敏感信息解析失败：密文解不开、缺少解密密钥、秘密节点写法非法。"""


class PlaintextSecretError(SecretError):
    """严格模式（strict）下检测到明文敏感信息。"""


__all__ = [
    "RhopTaskError",
    "DagValidationError",
    "TaskNotFound",
    "StoreUnavailable",
    "StoreError",
    "PayloadError",
    "ExecDenied",
    "HeartbeatError",
    "SecretError",
    "PlaintextSecretError",
]