"""
安全模块
提供安全相关的工具和功能
"""
from .safe_eval import safe_eval, SafeEvalError

__all__ = ['safe_eval', 'SafeEvalError']