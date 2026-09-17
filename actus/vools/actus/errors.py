"""统一错误类型：所有失败都收敛为 ActionError，携带 docs/08 §5 的结构化错误码。"""

__all__ = ['ActionError', 'ERROR_CODES']

# docs/08 §5 结构化错误码
ERROR_CODES = [
    'action_not_found', 'action_invalid', 'param_invalid',
    'dependency_missing', 'dependency_cycle', 'trust_rejected',
    'permission_denied', 'confirmation_timeout', 'timeout',
    'language_unavailable', 'internal',
]


class ActionError(Exception):
    """携带结构化错误码的统一异常。

    message: 人类可读说明（中文）
    code:    docs/08 §5 错误码
    details: 附加结构化信息（字段错误、环路径等）
    """

    def __init__(self, code: str, message: str, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details if details is not None else {}

    def to_payload(self) -> dict:
        """转为 docs/03 §7.2 的 error 载荷。"""
        return {'code': self.code, 'message': self.message, 'details': self.details}
