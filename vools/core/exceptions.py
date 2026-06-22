"""
自定义异常类
"""

__all__ = ['VoolsError', 'SafeEvalError', 'ConfigurationError', 'CacheError', 'ValidationError', 'ImportError']


class VoolsError(Exception):
    """vools 基础异常"""
    def do(self, f=print, pre_f=None, sub_f=None):
        """Apply a function for side effects, return self for chaining.

        Args:
            f: Function to apply (default print)
            pre_f: Pre-processing function applied before f
            sub_f: Post-processing function applied after f (no return expected)

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


class SafeEvalError(VoolsError):
    """安全求值异常"""
    pass


class ConfigurationError(VoolsError):
    """配置错误"""
    pass


class CacheError(VoolsError):
    """缓存错误"""
    pass


class ValidationError(VoolsError):
    """验证错误"""
    pass


class ImportError(VoolsError):
    """导入错误"""
    pass
