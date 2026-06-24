"""
vools.bridge.ruby - Ruby 语言桥接模块

提供 Ruby 动态执行与跨语言桥接能力。

设计目标：
- 通过 subprocess 调用 Ruby 解释器执行代码
- 支持 JSON 序列化进行数据交换
- 装饰器模式：@ruby 将 Python 函数转换为 Ruby 代码执行
- 继承 LangBridge 统一接口

使用示例::

    from vools.bridge.ruby import ruby, ruby_compiler_available

    if ruby_compiler_available():
        @ruby
        def fib(n: int) -> int:
            return '''
            def fib(n)
              n <= 1 ? 1 : fib(n-1) + fib(n-2)
            end
            puts fib(args[0])
            '''

        print(fib(10))  # -> 89

参数（与 go.py / fbc.py 对齐）:
    mode: 运行模式
        DEBUG: 强制重新生成并执行
        FORCE: 强制重新生成但不执行
        NORMAL: 命中缓存跳过生成；未命中则生成
        ONLY_RUN: 只在有缓存时执行；没有则报错
        ONLY_CODE: 只生成 Ruby 源码，不执行
    cache_dir: 缓存目录，None 则使用系统临时目录
    ret_type: 返回类型 ('int', 'float', 'string', 'bool', 'array', 'hash')
    auto_signature: 是否自动根据参数类型生成签名（默认 True）

前置条件:
- 安装 Ruby（>= 2.0），并将 ruby 加入 PATH
- 参考: https://www.ruby-lang.org/
"""

import os
import sys
import inspect
import functools
import json
import subprocess

from .compiler import (
    RubyBridge,
    _ruby_bridge,
    ruby_compiler_available,
    get_ruby_type,
    infer_ruby_argtypes,
    PY_TO_RUBY_TYPE,
    _generate_ruby_source,
    _execute_ruby_code,
    _parse_ruby_output,
    _get_cached_code,
    _RUBY_CACHE_DIR,
    _RUBY_PATH,
)


# ----------------------------------------------------------------------------
# 核心：@ruby 装饰器（使用基类 LangBridge 的 decorator 方法）
# ----------------------------------------------------------------------------

ruby = _ruby_bridge.decorator


# ----------------------------------------------------------------------------
# 便捷入口
# ----------------------------------------------------------------------------

def compile_and_run(
    ruby_code: str,
    func_name: str = 'main',
    args: tuple = (),
    ret_type: str = 'Integer',
    cache_dir: str = None,
):
    """
    直接执行一段 Ruby 源码（无装饰器）

    参数：
        ruby_code: 完整 Ruby 源码
        func_name: 要调用的函数名
        args: Python 位置参数
        ret_type: 返回类型（Ruby 端类型字符串）
        cache_dir: 缓存目录（可选）

    返回：
        函数调用结果
    """
    actual_cache_dir = cache_dir or _RUBY_CACHE_DIR
    os.makedirs(actual_cache_dir, exist_ok=True)

    arg_ruby_types = infer_ruby_argtypes(args)

    args_json = json.dumps(list(args))

    ruby_source = _generate_ruby_source(
        func_name=func_name,
        arg_names=['arg{}'.format(i) for i in range(len(args))],
        arg_ruby_types=arg_ruby_types,
        ret_ruby_type=ret_type,
        body=ruby_code,
        auto_signature=False,
        args_json=args_json,
    )

    output = _execute_ruby_code(ruby_source, func_name, actual_cache_dir)
    return _parse_ruby_output(output, ret_type)


def is_ruby_available() -> bool:
    """
    检查 Ruby 桥接是否可用

    返回：
        bool: True 表示 Ruby 解释器可用
    """
    return ruby_compiler_available()


# ----------------------------------------------------------------------------
# 公开 API
# ----------------------------------------------------------------------------

__all__ = [
    # 装饰器
    'ruby',
    # 类
    'RubyBridge',
    # 全局实例
    '_ruby_bridge',
    # 解释器检测
    'ruby_compiler_available',
    'is_ruby_available',
    # 便捷入口
    'compile_and_run',
    # 类型映射
    'PY_TO_RUBY_TYPE',
    'get_ruby_type',
    'infer_ruby_argtypes',
    # 内部（暴露用于测试 / 高级用法）
    '_execute_ruby_code',
    '_generate_ruby_source',
    '_parse_ruby_output',
    '_RUBY_CACHE_DIR',
]
