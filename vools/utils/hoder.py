"""
工具模块

提供各种实用工具类：
- Hoder: 对象持有者，用于延迟加载和管理对象
"""

from typing import Any, Callable


class Hoder:
    """对象持有者，用于延迟加载和管理对象"""
    
    def __init__(self, obj=None, lazy: bool = False, creator: Callable = None):
        """
        初始化持有者
        
        Args:
            obj: 初始对象
            lazy: 是否延迟加载
            creator: 延迟加载的创建函数
        """
        self._obj = obj
        self._lazy = lazy
        self._creator = creator
        self._created = not lazy
    
    def get(self) -> Any:
        """获取对象"""
        if not self._created and self._creator:
            self._obj = self._creator()
            self._created = True
        return self._obj
    
    def set(self, obj: Any) -> 'Hoder':
        """设置对象"""
        self._obj = obj
        self._created = True
        return self
    
    def reset(self) -> 'Hoder':
        """重置对象"""
        self._created = False
        return self
    
    def is_created(self) -> bool:
        """检查对象是否已创建"""
        return self._created
    
    def __call__(self) -> Any:
        """调用时获取对象"""
        return self.get()
    
    def __getattr__(self, name: str) -> Any:
        """代理对象的属性访问"""
        return getattr(self.get(), name)
    
    def __setattr__(self, name: str, value: Any) -> None:
        """代理对象的属性设置"""
        if name.startswith('_'):
            super().__setattr__(name, value)
        else:
            setattr(self.get(), name, value)


__all__ = ['Hoder']