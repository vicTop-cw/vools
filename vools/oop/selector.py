"""
选择器模块

从 decorators.selector 导入 Selector, Overloads 和 overloads，
避免代码重复，保持项目结构的清晰性。
"""

from ..decorators import Selector, Overloads, overloads

__all__ = ['overloads', 'Overloads', 'Selector']

if __name__ == '__main__':
    @overloads
    def add(x, y):
        return x + y

    @add.register(returnOverload=1)
    def _x(x, y, z):
        return x + y + z

    @add.register
    def _y(x: int, y: int):
        return x * y

    @_x.register
    def _k(a, b, c, d):
        return a * b - c * d

    print(add(1, 2, 3))

    print(_x(1, 2, 3, 4), _x(1, 23.4, 4), _x(1)(2)(3))

    _x.delaied = True
    t = _x(1, 2, 3)

    print(type(t), t.delaied, t(), t(4)(), '-------------------------------')
    
    x = _x.toSelector() * 3
    print(x(1, 2, 3, 4).get_result())
