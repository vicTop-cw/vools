"""Test Task 6: FB 封装模块 (.bas wrapper)"""
from vools.bridge import freebasic

print('=== 测试1: list_fb_modules ===')
modules = freebasic.list_fb_modules()
print('可用 .bas 模块:', modules)
assert 'sqlite3_wrapper' in modules, '缺少 sqlite3_wrapper'
assert 'cairo_wrapper' in modules, '缺少 cairo_wrapper'
assert 'sdl3_wrapper' in modules, '缺少 sdl3_wrapper'
print('  OK')

print()
print('=== 测试2: get_fb_module (sqlite3_wrapper) ===')
code = freebasic.get_fb_module('sqlite3_wrapper')
print('  文件长度:', len(code), '字符')
assert 'fb_sqlite3_libversion' in code, '缺少 fb_sqlite3_libversion 函数'
assert 'Function fb_sqlite3_open' in code, '缺少 fb_sqlite3_open 函数'
print('  OK')

print()
print('=== 测试3: get_fb_module (cairo_wrapper) ===')
code = freebasic.get_fb_module('cairo_wrapper')
print('  文件长度:', len(code), '字符')
assert 'fb_cairo_create' in code, '缺少 fb_cairo_create'
assert 'fb_cairo_rectangle' in code, '缺少 fb_cairo_rectangle'
print('  OK')

print()
print('=== 测试4: get_fb_module (sdl3_wrapper) ===')
code = freebasic.get_fb_module('sdl3_wrapper')
print('  文件长度:', len(code), '字符')
assert 'fb_sdl3_init' in code, '缺少 fb_sdl3_init'
assert 'fb_sdl3_create_window' in code, '缺少 fb_sdl3_create_window'
print('  OK')

print()
print('=== 测试5: get_fb_inc_paths ===')
sqlite_inc = freebasic.get_fb_inc_paths('sqlite3_wrapper')
print('  sqlite3 inc paths:', sqlite_inc)
cairo_inc = freebasic.get_fb_inc_paths('cairo_wrapper')
print('  cairo inc paths:', cairo_inc)
sdl_inc = freebasic.get_fb_inc_paths('sdl3_wrapper')
print('  sdl3 inc paths:', sdl_inc)
print('  OK')

print()
print('=== 测试6: SQLite3 .bas wrapper 实际编译运行 ===')
from vools.bridge.freebasic import compile_and_run

# 通过 compile_and_run + extra_includes 加载 .bas wrapper
sqlite_code = freebasic.get_fb_module('sqlite3_wrapper')
result = compile_and_run(
    'Dim As ZString Ptr v = fb_sqlite3_libversion()\nReturn v',
    func_name='test_sqlite_libversion',
    ret_type='ZString Ptr',
    extra_includes=[sqlite_code],
    inc_paths=freebasic.get_fb_inc_paths('sqlite3_wrapper'),
    lib_paths=freebasic.get_fb_lib_paths('sqlite3_wrapper'),
)
print('  sqlite3_libversion =', result)
assert result and '3.' in result, '应该返回 3.x.x 格式'
print('  OK')

print()
print('=== 测试7: SDL3 .bas wrapper 实际编译运行 ===')
sdl_code = freebasic.get_fb_module('sdl3_wrapper')
result = compile_and_run(
    'Return fb_sdl3_init(0)',
    func_name='test_sdl3_init_passive',
    ret_type='Long',
    extra_includes=[sdl_code],
    inc_paths=freebasic.get_fb_inc_paths('sdl3_wrapper'),
    lib_paths=freebasic.get_fb_lib_paths('sdl3_wrapper'),
)
print('  fb_sdl3_init(0) =', result)
# init(0) 不初始化任何子系统：返回 0 或正数（SDL3 行为）
# 关键是没有抛出异常、链接器找不到符号等问题
assert result is not None, '应返回有效值'
print('  OK')

print()
print('=== 测试8: cairo .bas wrapper 实际编译运行 ===')
cairo_code = freebasic.get_fb_module('cairo_wrapper')
result = compile_and_run(
    'Return fb_cairo_version()',
    func_name='test_cairo_version',
    ret_type='Long',
    extra_includes=[cairo_code],
    inc_paths=freebasic.get_fb_inc_paths('cairo_wrapper'),
    lib_paths=freebasic.get_fb_lib_paths('cairo_wrapper'),
)
print('  cairo_version =', result)
# cairo_version 返回 11800 系列（编码为 MAJOR*10000+MINOR*100+MICRO）
assert result is not None and result > 10000, '应返回有效版本号'
print('  OK')

print()
print('=== 全部测试完成 ===')
