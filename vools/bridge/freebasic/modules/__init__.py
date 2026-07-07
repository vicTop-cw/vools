"""
vools.bridge.freebasic.modules - FreeBASIC 封装模块

提供对 sqlite3、cairo、SDL3 等第三方 DLL 的 FreeBASIC 端简化封装，
用户可在 @fbc 装饰器中通过 module_code 引入这些 .bas 包装。

可用封装模块：
- sqlite3_wrapper.bas : SQLite3 数据库（database/inc/ 头文件依赖）
- cairo_wrapper.bas   : Cairo 2D 图形（graphics/inc/ 头文件依赖）
- sdl3_wrapper.bas    : SDL3 多媒体（multimedia/inc/ 头文件依赖）
- scintilla_wrapper.bas : Scintilla 代码编辑控件（gui/inc/scintilla/ 头文件依赖）

每个模块的 docstring 中有详细使用说明。
"""

import os

MODULES_DIR = os.path.dirname(os.path.abspath(__file__))

# 各模块的默认头文件搜索路径（相对 win64 类别目录）
_INC_PATHS = {
    'sqlite3_wrapper': [
        os.path.join(MODULES_DIR, '..', 'libs', 'win64', 'database', 'inc'),
        os.path.join(MODULES_DIR, '..', 'libs', 'win64', 'database', 'inc', 'mysql'),
    ],
    'cairo_wrapper': [
        os.path.join(MODULES_DIR, '..', 'libs', 'win64', 'graphics', 'inc'),
    ],
    'sdl3_wrapper': [
        os.path.join(MODULES_DIR, '..', 'libs', 'win64', 'multimedia', 'inc'),
    ],
    'scintilla_wrapper': [
        os.path.join(MODULES_DIR, '..', 'libs', 'win64', 'gui', 'inc', 'scintilla'),
    ],
}


def get_module(name: str) -> str:
    """
    读取一个 .bas 封装模块的源码内容

    参数：
        name: 模块名（不含 .bas 后缀），如 'sqlite3_wrapper'

    返回：
        模块源码字符串

    抛出：
        FileNotFoundError: 模块不存在
    """
    path = os.path.join(MODULES_DIR, f'{name}.bas')
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f'FreeBASIC 封装模块不存在: {path}\n'
            f'可用模块: {list_modules()}'
        )
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def list_modules() -> list:
    """
    列出所有可用的 .bas 封装模块

    返回：
        模块名列表（不含 .bas 后缀）
    """
    return [f[:-4] for f in os.listdir(MODULES_DIR) if f.endswith('.bas')]


def get_inc_paths(name: str) -> list:
    """
    获取指定封装模块需要的头文件搜索路径

    参数：
        name: 模块名，如 'sqlite3_wrapper'

    返回：
        头文件路径列表（绝对路径）
    """
    return _INC_PATHS.get(name, [])


def get_lib_paths(name: str) -> list:
    """
    获取指定封装模块需要的库搜索路径（DLL 所在目录）

    参数：
        name: 模块名

    返回：
        库路径列表（绝对路径），通过 -p 参数传给 fbc
    """
    out = []
    if name in ('sqlite3_wrapper',):
        out.append(os.path.join(MODULES_DIR, '..', 'libs', 'win64', 'database'))
    elif name in ('cairo_wrapper',):
        out.append(os.path.join(MODULES_DIR, '..', 'libs', 'win64', 'graphics'))
    elif name in ('sdl3_wrapper',):
        out.append(os.path.join(MODULES_DIR, '..', 'libs', 'win64', 'multimedia'))
        out.append(os.path.join(MODULES_DIR, '..', 'libs', 'win64', 'multimedia', 'inc'))
    elif name in ('scintilla_wrapper',):
        out.append(os.path.join(MODULES_DIR, '..', 'libs', 'win64', 'gui'))
    return out


__all__ = [
    'MODULES_DIR',
    'get_module',
    'list_modules',
    'get_inc_paths',
    'get_lib_paths',
]
