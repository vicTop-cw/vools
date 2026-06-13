"""
String curried functions - 字符串操作柯里化函数

提供字符串操作的柯里化版本。
"""

from typing import TypeVar, Callable, Iterable, List

from ..decorators.curry_core import curry

A = TypeVar('A')

__all__ = [
    'join',
    'split',
    'strip',
    'lstrip',
    'rstrip',
    'lower',
    'upper',
    'capitalize',
    'title',
    'replace',
    'startswith',
    'endswith',
    'contains',
    'strip_prefix',
    'strip_suffix',
]


@curry
def join(sep: str, iterable: Iterable[str]) -> str:
    """
    使用分隔符连接字符串列表

    Args:
        sep: 分隔符
        iterable: 字符串可迭代对象

    Returns:
        连接后的字符串

    Example:
        >>> join('-', ['a', 'b', 'c'])
        'a-b-c'
        >>> join(', ', ['apple', 'banana', 'cherry'])
        'apple, banana, cherry'
        >>> join('')(['a', 'b', 'c'])
        'abc'
    """
    return sep.join(iterable)


@curry
def split(sep: str, s: str) -> List[str]:
    """
    分割字符串

    Args:
        sep: 分隔符
        s: 要分割的字符串

    Returns:
        分割后的字符串列表

    Example:
        >>> split('-', 'a-b-c')
        ['a', 'b', 'c']
        >>> split(' ', 'hello world')
        ['hello', 'world']
    """
    return s.split(sep)


@curry
def strip(s: str, chars: str = None) -> str:
    """
    去除字符串首尾空白或指定字符

    Args:
        s: 输入字符串
        chars: 要去除的字符集（可选）

    Returns:
        去除后的字符串

    Example:
        >>> strip('  hello  ')
        'hello'
        >>> strip('...hello...', '.')
        'hello'
    """
    return s.strip(chars)


@curry
def lstrip(s: str, chars: str = None) -> str:
    """
    去除字符串左侧空白或指定字符

    Args:
        s: 输入字符串
        chars: 要去除的字符集（可选）

    Returns:
        去除后的字符串
    """
    return s.lstrip(chars)


@curry
def rstrip(s: str, chars: str = None) -> str:
    """
    去除字符串右侧空白或指定字符

    Args:
        s: 输入字符串
        chars: 要去除的字符集（可选）

    Returns:
        去除后的字符串
    """
    return s.rstrip(chars)


@curry
def lower(s: str) -> str:
    """
    转换为小写

    Args:
        s: 输入字符串

    Returns:
        小写字符串

    Example:
        >>> lower('HELLO')
        'hello'
        >>> lower('Hello World')
        'hello world'
    """
    return s.lower()


@curry
def upper(s: str) -> str:
    """
    转换为大写

    Args:
        s: 输入字符串

    Returns:
        大写字符串

    Example:
        >>> upper('hello')
        'HELLO'
    """
    return s.upper()


@curry
def capitalize(s: str) -> str:
    """
    首字母大写，其余小写

    Args:
        s: 输入字符串

    Returns:
        首字母大写的字符串

    Example:
        >>> capitalize('hello world')
        'Hello world'
    """
    return s.capitalize()


@curry
def title(s: str) -> str:
    """
    转换为标题格式（每个单词首字母大写）

    Args:
        s: 输入字符串

    Returns:
        标题格式字符串

    Example:
        >>> title('hello world')
        'Hello World'
    """
    return s.title()


@curry
def replace(old: str, new: str, s: str, count: int = -1) -> str:
    """
    替换字符串中的子串

    Args:
        old: 要替换的子串
        new: 替换成的子串
        s: 输入字符串
        count: 替换次数，-1 表示全部替换

    Returns:
        替换后的字符串

    Example:
        >>> replace('o', '0', 'hello')
        'hell0'
        >>> replace('o', '0', 'hello', count=1)
        'hell0'
        >>> replace('a', 'b', 'aaa')
        'bbb'
    """
    return s.replace(old, new, count)


@curry
def startswith(prefix: str, s: str) -> bool:
    """
    检查字符串是否以指定前缀开头

    Args:
        prefix: 前缀
        s: 输入字符串

    Returns:
        如果以指定前缀开头返回 True

    Example:
        >>> startswith('he', 'hello')
        True
        >>> startswith('lo', 'hello')
        False
    """
    return s.startswith(prefix)


@curry
def endswith(suffix: str, s: str) -> bool:
    """
    检查字符串是否以指定后缀结尾

    Args:
        suffix: 后缀
        s: 输入字符串

    Returns:
        如果以指定后缀结尾返回 True

    Example:
        >>> endswith('lo', 'hello')
        True
        >>> endswith('he', 'hello')
        False
    """
    return s.endswith(suffix)


@curry
def contains(substr: str, s: str) -> bool:
    """
    检查字符串是否包含子串

    Args:
        substr: 子串
        s: 输入字符串

    Returns:
        如果包含子串返回 True

    Example:
        >>> contains('ell', 'hello')
        True
        >>> contains('world', 'hello')
        False
    """
    return substr in s


@curry
def strip_prefix(prefix: str, s: str) -> str:
    """
    去除字符串开头的前缀

    Args:
        prefix: 要去除的前缀
        s: 输入字符串

    Returns:
        去除前缀后的字符串

    Example:
        >>> strip_prefix('https://', 'https://example.com')
        'example.com'
        >>> strip_prefix('http://', 'https://example.com')
        'https://example.com'
    """
    if s.startswith(prefix):
        return s[len(prefix):]
    return s


@curry
def strip_suffix(suffix: str, s: str) -> str:
    """
    去除字符串结尾的后缀

    Args:
        suffix: 要去除的后缀
        s: 输入字符串

    Returns:
        去除后缀后的字符串

    Example:
        >>> strip_suffix('.py', 'script.py')
        'script'
        >>> strip_suffix('.txt', 'script.py')
        'script.py'
    """
    if s.endswith(suffix):
        return s[:-len(suffix)]
    return s


__all__ = [
    'join',
    'split',
    'strip',
    'lstrip',
    'rstrip',
    'lower',
    'upper',
    'capitalize',
    'title',
    'replace',
    'startswith',
    'endswith',
    'contains',
    'strip_prefix',
    'strip_suffix',
]
