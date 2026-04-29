"""
自定义异常类
"""
class VoolsError(Exception):
    """vools 基础异常"""
    pass

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