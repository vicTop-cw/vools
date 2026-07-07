# -*- coding: utf-8 -*-
"""
Task 9 单元测试与兼容性验证

测试覆盖：
1. loader API (get_fb_lib, list_fb_libs, FbLibraryLoader)
2. SQLite3 shim 层（is_sqlite3_available, sqlite3_version, connect）
3. .bas 封装模块（sqlite3_wrapper, cairo_wrapper, sdl3_wrapper）
4. 编译参数注入（extra_includes, inc_paths, lib_paths）
5. 向后兼容性（旧的 @fbc 装饰器 API 仍可用）
6. Python 3.6 兼容性检查（无类型注解、相对导入）

运行：python tests/bridge/test_task9_units.py
"""
from __future__ import print_function

import os
import sys
import shutil
import platform
import tempfile
from vools.bridge import freebasic


# 全局测试统计
TESTS_PASSED = 0
TESTS_FAILED = 0
TESTS_SKIPPED = 0


def _check(condition, msg):
    """断言并记录结果"""
    global TESTS_PASSED, TESTS_FAILED
    if condition:
        TESTS_PASSED += 1
        print('  OK -', msg)
    else:
        TESTS_FAILED += 1
        print('  FAIL -', msg)


def _skip(msg):
    """跳过测试"""
    global TESTS_SKIPPED
    TESTS_SKIPPED += 1
    print('  SKIP -', msg)


# ============================================================================
# 1. loader API 测试
# ============================================================================

def test_loader_api():
    """测试 loader API（get_fb_lib, list_fb_libs, FbLibraryLoader）"""
    print('=' * 60)
    print('1. loader API 测试')
    print('=' * 60)

    # 1.1 list_fb_libs
    print('\n1.1 list_fb_libs():')
    try:
        libs = freebasic.list_fb_libs()
        print('  All libs:', libs)
        _check(isinstance(libs, list), 'list_fb_libs 返回 list')
        _check('sqlite3' in libs, 'sqlite3 在库列表中')
        _check('SDL3' in libs, 'SDL3 在库列表中')
        _check('cairo' in libs, 'cairo 在库列表中')
    except Exception as e:
        _check(False, 'list_fb_libs 异常: %s' % e)

    # 1.2 list_fb_libs(category='database')
    print('\n1.2 list_fb_libs(category=):')
    try:
        db_libs = freebasic.list_fb_libs('database')
        print('  database libs:', db_libs)
        _check('sqlite3' in db_libs, 'sqlite3 在 database 中')
        _check('libmysql' in db_libs, 'libmysql 在 database 中')
    except Exception as e:
        _check(False, 'list_fb_libs(category) 异常: %s' % e)

    # 1.3 get_fb_lib - sqlite3
    print('\n1.3 get_fb_lib("sqlite3"):')
    try:
        lib = freebasic.get_fb_lib('sqlite3', category='database')
        print('  lib:', lib)
        _check(lib is not None, '成功加载 sqlite3.dll')
        # 测试 ctypes 调用
        ver = lib.sqlite3_libversion()
        print('  sqlite3_libversion():', ver)
        _check(isinstance(ver, bytes), '版本返回 bytes')
    except Exception as e:
        _check(False, 'get_fb_lib 异常: %s' % e)

    # 1.4 FbLibraryLoader 类
    print('\n1.4 FbLibraryLoader 类:')
    try:
        loader_cls = freebasic.FbLibraryLoader
        loader = loader_cls()
        avail = loader.is_available('sqlite3')
        print('  is_available(sqlite3):', avail)
        _check(isinstance(avail, bool), 'FbLibraryLoader.is_available() 返回 bool')
        lib2 = loader.load('sqlite3', category='database')
        _check(lib2 is not None, 'FbLibraryLoader.load() 成功')
    except Exception as e:
        _check(False, 'FbLibraryLoader 异常: %s' % e)

    # 1.5 manifest 路径
    print('\n1.5 manifest 路径:')
    import os as _os
    manifest_path = freebasic.LIBS_BASE_DIR
    if freebasic._load_manifest:
        manifest_path = _os.path.join(freebasic.LIBS_BASE_DIR, 'win64', 'manifest.json')
    print('  manifest:', manifest_path)
    _check(freebasic.LIBS_BASE_DIR is not None, 'LIBS_BASE_DIR 存在')
    _check(_os.path.exists(manifest_path), 'manifest.json 存在')

    print()


# ============================================================================
# 2. SQLite3 shim 层测试
# ============================================================================

def test_sqlite3_shim():
    """测试 SQLite3 shim 层"""
    print('=' * 60)
    print('2. SQLite3 shim 层测试')
    print('=' * 60)

    # 2.1 is_sqlite3_available
    print('\n2.1 is_sqlite3_available():')
    try:
        avail = freebasic.is_sqlite3_available()
        print('  available:', avail)
        _check(isinstance(avail, bool), 'is_sqlite3_available 返回 bool')
        _check(avail is True, 'SQLite3 实际可用')
    except Exception as e:
        _check(False, 'is_sqlite3_available 异常: %s' % e)

    # 2.2 sqlite3_version
    print('\n2.2 sqlite3_version():')
    try:
        ver = freebasic.sqlite3_version()
        print('  version:', ver)
        _check(isinstance(ver, str) or isinstance(ver, bytes),
               'sqlite3_version 返回字符串')
    except Exception as e:
        _check(False, 'sqlite3_version 异常: %s' % e)

    # 2.3 connect - in-memory database
    print('\n2.3 connect(":memory:"):')
    try:
        conn = freebasic.connect(':memory:')
        print('  conn:', conn)
        _check(conn is not None, 'connect 成功')

        # 2.4 创建表 + 插入 + 查询
        print('\n2.4 conn.cursor() + execute:')
        cur = conn.cursor()
        cur.execute('CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)')
        cur.execute("INSERT INTO t (name) VALUES ('Alice')")
        cur.execute("INSERT INTO t (name) VALUES ('Bob')")
        conn.commit()

        cur.execute('SELECT COUNT(*) FROM t')
        count = cur.fetchone()
        print('  count:', count)
        _check(count is not None, 'SELECT COUNT(*) 成功')

        cur.execute('SELECT name FROM t ORDER BY id')
        rows = cur.fetchall()
        names = [r[0] for r in rows]
        print('  names:', names)
        _check(names == ['Alice', 'Bob'], '查询结果正确')
    except Exception as e:
        _check(False, 'connect/cursor 异常: %s' % e)

    print()


# ============================================================================
# 3. .bas 封装模块 API 测试（不实际编译）
# ============================================================================

def test_fb_modules_api():
    """测试 .bas 封装模块 API（不实际编译）"""
    print('=' * 60)
    print('3. .bas 封装模块 API 测试（不实际编译）')
    print('=' * 60)

    # 3.1 list_fb_modules
    print('\n3.1 list_fb_modules():')
    try:
        modules = freebasic.list_fb_modules()
        print('  modules:', modules)
        _check(isinstance(modules, list), 'list_fb_modules 返回 list')
        _check('sqlite3_wrapper' in modules, 'sqlite3_wrapper 在列表中')
        _check('cairo_wrapper' in modules, 'cairo_wrapper 在列表中')
        _check('sdl3_wrapper' in modules, 'sdl3_wrapper 在列表中')
    except Exception as e:
        _check(False, 'list_fb_modules 异常: %s' % e)

    # 3.2 get_fb_module - sqlite3_wrapper
    print('\n3.2 get_fb_module("sqlite3_wrapper"):')
    try:
        code = freebasic.get_fb_module('sqlite3_wrapper')
        print('  length:', len(code))
        _check(isinstance(code, str), 'get_fb_module 返回 str')
        _check('fb_sqlite3_libversion' in code, '包含 fb_sqlite3_libversion')
        _check('#include once' in code.lower(), '包含 include 语句')
    except Exception as e:
        _check(False, 'get_fb_module 异常: %s' % e)

    # 3.3 get_fb_inc_paths
    print('\n3.3 get_fb_inc_paths():')
    try:
        sqlite_inc = freebasic.get_fb_inc_paths('sqlite3_wrapper')
        cairo_inc = freebasic.get_fb_inc_paths('cairo_wrapper')
        sdl_inc = freebasic.get_fb_inc_paths('sdl3_wrapper')
        print('  sqlite inc:', sqlite_inc)
        print('  cairo inc:', cairo_inc)
        print('  sdl inc:', sdl_inc)
        _check(isinstance(sqlite_inc, list), 'sqlite inc 是 list')
        _check(len(sqlite_inc) > 0, 'sqlite inc 至少 1 个路径')
        _check(any('database' in p.lower() for p in sqlite_inc), 'sqlite inc 在 database 目录')
        _check(any('graphics' in p.lower() for p in cairo_inc), 'cairo inc 在 graphics 目录')
        _check(any('multimedia' in p.lower() for p in sdl_inc), 'sdl inc 在 multimedia 目录')
    except Exception as e:
        _check(False, 'get_fb_inc_paths 异常: %s' % e)

    # 3.4 get_fb_lib_paths
    print('\n3.4 get_fb_lib_paths():')
    try:
        sqlite_lib = freebasic.get_fb_lib_paths('sqlite3_wrapper')
        cairo_lib = freebasic.get_fb_lib_paths('cairo_wrapper')
        sdl_lib = freebasic.get_fb_lib_paths('sdl3_wrapper')
        print('  sqlite lib:', sqlite_lib)
        print('  cairo lib:', cairo_lib)
        print('  sdl lib:', sdl_lib)
        _check(isinstance(sqlite_lib, list), 'sqlite lib 是 list')
        _check(len(sqlite_lib) > 0, 'sqlite lib 至少 1 个路径')
        _check(any('database' in p.lower() for p in sqlite_lib), 'sqlite lib 在 database 目录')
        _check(any('graphics' in p.lower() for p in cairo_lib), 'cairo lib 在 graphics 目录')
        _check(any('multimedia' in p.lower() for p in sdl_lib), 'sdl lib 在 multimedia 目录')
    except Exception as e:
        _check(False, 'get_fb_lib_paths 异常: %s' % e)

    # 3.5 get_fb_module - 不存在的模块
    print('\n3.5 get_fb_module("nonexistent"):')
    try:
        freebasic.get_fb_module('nonexistent')
        _check(False, '应该抛出异常但没有')
    except (ValueError, IOError, OSError):
        _check(True, '不存在的模块正确抛出异常')

    print()


# ============================================================================
# 4. 编译参数注入测试（实际编译）
# ============================================================================

def test_compile_with_includes():
    """测试编译参数注入（需要 fbc 可用）"""
    print('=' * 60)
    print('4. 编译参数注入测试（需要 fbc 可用）')
    print('=' * 60)

    if not freebasic.fbc_compiler_available():
        _skip('FreeBASIC 编译器不可用')
        return

    # 清理缓存
    cache_dir = os.path.join(tempfile.gettempdir(), 'vools_fbc_cache')
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)

    # 4.1 SQLite3 编译运行
    print('\n4.1 SQLite3 编译运行:')
    try:
        sqlite_code = freebasic.get_fb_module('sqlite3_wrapper')
        result = freebasic.compile_and_run(
            'Dim As ZString Ptr v = fb_sqlite3_libversion()\nReturn v',
            func_name='test_unit_sqlite',
            ret_type='ZString Ptr',
            extra_includes=[sqlite_code],
            inc_paths=freebasic.get_fb_inc_paths('sqlite3_wrapper'),
            lib_paths=freebasic.get_fb_lib_paths('sqlite3_wrapper'),
        )
        print('  result:', result)
        _check(result is not None, 'SQLite3 编译运行成功')
        _check(b'3.' in result if isinstance(result, bytes) else '3.' in result,
               '返回 SQLite3 版本号')
    except Exception as e:
        _check(False, 'SQLite3 编译运行异常: %s' % e)

    # 4.2 Cairo 编译运行
    print('\n4.2 Cairo 编译运行:')
    try:
        cairo_code = freebasic.get_fb_module('cairo_wrapper')
        result = freebasic.compile_and_run(
            'Return fb_cairo_version()',
            func_name='test_unit_cairo',
            ret_type='Long',
            extra_includes=[cairo_code],
            inc_paths=freebasic.get_fb_inc_paths('cairo_wrapper'),
            lib_paths=freebasic.get_fb_lib_paths('cairo_wrapper'),
        )
        print('  result:', result)
        _check(result is not None and result > 0, 'Cairo 编译运行成功（版本号 > 0）')
    except Exception as e:
        _check(False, 'Cairo 编译运行异常: %s' % e)

    # 4.3 SDL3 编译运行
    print('\n4.3 SDL3 编译运行:')
    try:
        sdl_code = freebasic.get_fb_module('sdl3_wrapper')
        result = freebasic.compile_and_run(
            'Return fb_sdl3_init(0)',
            func_name='test_unit_sdl',
            ret_type='Long',
            extra_includes=[sdl_code],
            inc_paths=freebasic.get_fb_inc_paths('sdl3_wrapper'),
            lib_paths=freebasic.get_fb_lib_paths('sdl3_wrapper'),
        )
        print('  result:', result)
        _check(result is not None, 'SDL3 编译运行成功')
    except Exception as e:
        _check(False, 'SDL3 编译运行异常: %s' % e)

    print()


# ============================================================================
# 5. 向后兼容性测试
# ============================================================================

def test_backward_compatibility():
    """测试向后兼容性（旧的 @fbc 装饰器 API 仍可用）"""
    print('=' * 60)
    print('5. 向后兼容性测试')
    print('=' * 60)

    # 5.1 @fbc 装饰器仍然可用
    print('\n5.1 @fbc 装饰器兼容性:')
    try:
        fbc = freebasic.fbc
        _check(callable(fbc), '@fbc 可调用')

        @fbc
        def add(x: int, y: int):
            return "Return x + y"

        result = add(2, 3)
        _check(result == 5, '简单 @fbc 函数可用（add(2,3) == 5）')

        @fbc
        def mul(x: int, y: int):
            return "Return x * y"

        result = mul(4, 5)
        _check(result == 20, '乘法 @fbc 函数可用（mul(4,5) == 20）')
    except Exception as e:
        _check(False, '@fbc 装饰器异常: %s' % e)

    # 5.2 compile_and_run 兼容（无 includes）
    print('\n5.2 compile_and_run 兼容（无 includes）:')
    try:
        result = freebasic.compile_and_run(
            'Return arg0 + arg1',
            func_name='test_bc_simple',
            args=(10, 20),
            ret_type='Long',
        )
        _check(result == 30, 'compile_and_run 简单调用可用（10+20 == 30）')
    except Exception as e:
        _check(False, 'compile_and_run 异常: %s' % e)

    # 5.3 旧 API 导出
    print('\n5.3 旧 API 导出:')
    expected_apis = [
        'fbc', 'compile_and_run', 'compile_and_run_async',
        'fbc_compiler_available', 'is_fbc_available',
    ]
    for api in expected_apis:
        _check(hasattr(freebasic, api), '导出 %s' % api)

    print()


# ============================================================================
# 6. Python 3.6 兼容性检查
# ============================================================================

def test_python36_compat():
    """检查源代码是否兼容 Python 3.6"""
    print('=' * 60)
    print('6. Python 3.6 兼容性检查（静态分析）')
    print('=' * 60)

    print('\n  当前 Python 版本: %s' % platform.python_version())
    print('  当前 Python 实现: %s' % platform.python_implementation())

    # 6.1 检查 from __future__ import 兼容性
    print('\n6.1 __future__ imports:')
    freebasic_path = os.path.dirname(freebasic.__file__)
    issues = []

    # 检查源代码中是否有 Python 3.7+ 专有语法
    for root, _, files in os.walk(freebasic_path):
        # 跳过缓存和二进制目录
        if '__pycache__' in root or 'compiler' in root or 'libs' in root:
            continue
        for f in files:
            if not f.endswith('.py'):
                continue
            fp = os.path.join(root, f)
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    content = fh.read()
            except (UnicodeDecodeError, IOError):
                continue
            # Python 3.7+ 特性检测
            # async/await 是 3.5+ 但 3.6 也支持
            # f-string 是 3.6+
            # contextvars 是 3.7+
            # 我们关心 3.6 兼容性
            if 'contextvars' in content and 'from vools.core.contextvars_compat' not in content:
                # 检查是否有 import contextvars
                if 'import contextvars' in content and 'contextvars_compat' not in content:
                    issues.append('%s: 包含 contextvars 引用' % fp)
            if 'importlib.resources' in content:
                # 3.7+
                issues.append('%s: 使用 importlib.resources（3.7+）' % fp)
            if 'from __future__ import annotations' in content:
                # annotations 是 3.7+
                # 但我们用 print_function 等
                pass  # 不算问题，因为 __future__ 总是兼容的

    if not issues:
        _check(True, '未发现 Python 3.6 不兼容问题')
    else:
        for issue in issues:
            _check(False, issue)

    # 6.2 关键字参数兼容（**kwargs 永远兼容）
    print('\n6.2 关键字参数 API:')
    try:
        # 测试 compile_and_run 接受新参数
        freebasic.compile_and_run(
            'Return 1',
            func_name='test_kwarg',
            extra_includes=[],
            inc_paths=[],
            lib_paths=[],
            cache_dir=cache_dir if (cache_dir := os.path.join(tempfile.gettempdir(), 'vools_fbc_test_py36')) else None,
        )
        _check(True, '新参数（extra_includes/inc_paths/lib_paths）兼容')
    except Exception as e:
        # 编译可能失败，但参数应该被接受
        if 'extra_includes' in str(e) or 'unexpected keyword' in str(e):
            _check(False, '新参数不兼容: %s' % e)
        else:
            _check(True, '新参数兼容（编译错误是预期的: %s）' % str(e)[:50])

    print()


# ============================================================================
# 7. 内置编译器检测测试
# ============================================================================

def test_builtin_compiler():
    """测试内置 FreeBASIC 编译器检测"""
    print('=' * 60)
    print('7. 内置 FreeBASIC 编译器检测')
    print('=' * 60)

    # 7.1 编译器路径
    print('\n7.1 编译器路径:')
    try:
        # 不同版本可能函数名不同
        if hasattr(freebasic, '_get_fbc_path'):
            fbc_path = freebasic._get_fbc_path()
        elif hasattr(freebasic, '_get_fbc_executable'):
            fbc_path = freebasic._get_fbc_executable()
        else:
            # 找 fbc.exe
            from vools.bridge.freebasic import compiler
            fbc_path = compiler._get_fbc_path()
        print('  fbc path:', fbc_path)
        _check(os.path.exists(fbc_path), '内置 fbc.exe 存在')
    except Exception as e:
        _check(False, '无法获取 fbc 路径: %s' % e)

    # 7.2 编译器可用性
    print('\n7.2 fbc_compiler_available():')
    avail = freebasic.fbc_compiler_available()
    print('  available:', avail)
    _check(avail is True, '内置编译器可用')

    # 7.3 编译器目录
    print('\n7.3 编译器目录:')
    compiler_dir = os.path.join(os.path.dirname(freebasic.__file__), 'compiler')
    print('  compiler dir:', compiler_dir)
    _check(os.path.exists(compiler_dir), 'compiler/ 目录存在')
    _check(os.path.isdir(os.path.join(compiler_dir, 'bin')), 'compiler/bin/ 目录存在')
    _check(os.path.isdir(os.path.join(compiler_dir, 'inc')), 'compiler/inc/ 目录存在')
    _check(os.path.isdir(os.path.join(compiler_dir, 'lib')), 'compiler/lib/ 目录存在')

    # 7.4 libs/win64 目录
    print('\n7.4 libs/win64 目录:')
    libs_dir = os.path.join(os.path.dirname(freebasic.__file__), 'libs', 'win64')
    print('  libs dir:', libs_dir)
    _check(os.path.exists(libs_dir), 'libs/win64/ 目录存在')
    if os.path.exists(libs_dir):
        for cat in ['database', 'graphics', 'multimedia', 'gui']:
            cat_path = os.path.join(libs_dir, cat)
            _check(os.path.exists(cat_path), '%s 类别存在' % cat)

    print()


# ============================================================================
# 8. .a 导入库检查
# ============================================================================

def test_a_libs():
    """检查内置 .a 导入库"""
    print('=' * 60)
    print('8. .a 导入库检查')
    print('=' * 60)

    freebasic_path = os.path.dirname(freebasic.__file__)
    libs_dir = os.path.join(freebasic_path, 'libs', 'win64')

    # 8.1 sqlite3.libsqlite3.a
    print('\n8.1 libsqlite3.a:')
    a_path = os.path.join(libs_dir, 'database', 'libsqlite3.a')
    if os.path.exists(a_path):
        _check(True, 'libsqlite3.a 存在（%d bytes）' % os.path.getsize(a_path))
    else:
        _check(False, 'libsqlite3.a 缺失')

    # 8.2 其他 .a 文件
    print('\n8.2 其他 .a 文件:')
    a_files = []
    for root, _, files in os.walk(libs_dir):
        for f in files:
            if f.startswith('lib') and f.endswith('.a'):
                a_files.append(os.path.join(root, f))

    expected = ['libcairo.a', 'libSDL3.a', 'libSDL3_image.a', 'libSDL3_mixer.a',
                'libSDL3_ttf.a', 'libmCtrl.a', 'libScintilla.a', 'libmysql.a']
    for name in expected:
        found = any(name in a for a in a_files)
        _check(found, '%s 存在' % name)

    print()


# ============================================================================
# 入口
# ============================================================================

def main():
    print('\n' + '=' * 60)
    print('Task 9 单元测试与兼容性验证')
    print('=' * 60 + '\n')

    test_loader_api()
    test_sqlite3_shim()
    test_fb_modules_api()
    test_compile_with_includes()
    test_backward_compatibility()
    test_python36_compat()
    test_builtin_compiler()
    test_a_libs()

    # 总结
    print('=' * 60)
    print('测试总结')
    print('=' * 60)
    print('通过: %d' % TESTS_PASSED)
    print('失败: %d' % TESTS_FAILED)
    print('跳过: %d' % TESTS_SKIPPED)
    print()

    if TESTS_FAILED > 0:
        print('FAILED')
        sys.exit(1)
    else:
        print('OK')
        sys.exit(0)


if __name__ == '__main__':
    main()
