"""
vools.bridge.rust.templates - Rust 代码模板生成器

生成符合 C ABI 的 Rust 函数代码，用于动态编译为 DLL。
"""

import inspect
from typing import List, Dict, Any, Optional
from .types import RustTypeMapper, get_rust_type


class RustCodeGenerator:
    """
    Rust 代码生成器

    生成符合 C ABI 的 Rust 函数代码，包括：
    - 函数签名（extern "C"）
    - #[no_mangle] 属性
    - C ABI 类型声明
    - 预处理指令（use、mod 等）
    """

    @staticmethod
    def generate_function_signature(
        func_name: str,
        params: List[tuple],
        return_type: str,
        code_body: str
    ) -> str:
        """
        生成完整的 Rust 函数代码

        参数：
            func_name: 函数名称
            params: 参数列表，每个元素是 (param_name, rust_type)
            return_type: Rust 返回类型字符串
            code_body: 函数体代码（不含签名）

        返回：
            完整的 Rust 函数代码字符串
        """
        # 构建参数列表
        params_str = ', '.join([f'{name}: {rtype}' for name, rtype in params])

        # 构建函数签名
        if return_type == 'void':
            signature = f'#[no_mangle]\npub extern "C" fn {func_name}({params_str})'
        else:
            signature = f'#[no_mangle]\npub extern "C" fn {func_name}({params_str}) -> {return_type}'

        # 构建完整代码
        full_code = f'{signature} {{\n    {code_body}\n}}'
        return full_code

    @staticmethod
    def generate_lib_code(
        functions: List[str],
        imports: List[str] = None
    ) -> str:
        """
        生成完整的 lib.rs 文件内容

        参数：
            functions: 函数代码列表
            imports: 导入语句列表（可选）

        返回：
            完整的 lib.rs 文件内容
        """
        # 默认导入
        default_imports = [
            'use std::os::raw::*;',
        ]

        # 合并导入
        all_imports = default_imports + (imports or [])

        # 构建导入部分
        imports_code = '\n'.join(all_imports)

        # 构建函数部分
        functions_code = '\n\n'.join(functions)

        # 组合完整代码
        full_code = f'{imports_code}\n\n{functions_code}\n'
        return full_code

    @staticmethod
    def generate_cargo_toml(
        package_name: str,
        version: str = '0.1.0',
        dependencies: Dict[str, str] = None
    ) -> str:
        """
        生成 Cargo.toml 文件内容

        参数：
            package_name: 包名称
            version: 版本号
            dependencies: 依赖字典（可选）

        返回：
            Cargo.toml 文件内容
        """
        # 基本配置
        cargo_content = f'''[package]
name = "{package_name}"
version = "{version}"
edition = "2021"

[lib]
crate-type = ["cdylib"]
'''

        # 添加依赖
        if dependencies:
            deps_section = '\n[dependencies]\n'
            for dep_name, dep_version in dependencies.items():
                deps_section += f'{dep_name} = "{dep_version}"\n'
            cargo_content += deps_section

        return cargo_content

    @staticmethod
    def extract_imports(code: str) -> tuple:
        """
        从代码中提取导入语句和函数体

        参数：
            code: Rust 代码字符串

        返回：
            (imports, body) 元组，imports 是导入语句列表，body 是函数体代码
        """
        imports = []
        body_lines = []

        for line in code.strip().split('\n'):
            line_stripped = line.strip()

            # 识别导入语句
            if line_stripped.startswith('use ') or line_stripped.startswith('#['):
                imports.append(line_stripped)
            # 识别注释和空行，保留在导入部分
            elif line_stripped.startswith('//') or line_stripped == '':
                imports.append(line_stripped)
            else:
                body_lines.append(line)

        # 函数体代码（缩进处理）
        body = '\n    '.join(body_lines)

        return (imports, body)

    @staticmethod
    def generate_from_python_func(
        func_name: str,
        sig: inspect.Signature,
        return_annotation: Any,
        code_body: str,
        auto_signature: bool = True
    ) -> str:
        """
        从 Python 函数生成 Rust 代码

        参数：
            func_name: 函数名称
            sig: Python 函数签名
            return_annotation: 返回类型注解
            code_body: Rust 函数体代码
            auto_signature: 是否自动生成签名

        返回：
            Rust 函数代码字符串
        """
        if auto_signature:
            # 提取导入语句
            imports, clean_body = RustCodeGenerator.extract_imports(code_body)

            # 生成参数列表
            params = []
            for param_name, param in sig.parameters.items():
                if param.annotation != param.empty:
                    py_type = param.annotation
                    rust_type = get_rust_type(py_type)
                else:
                    rust_type = 'c_long'  # 默认类型
                params.append((param_name, rust_type))

            # 生成返回类型
            if return_annotation is None or return_annotation is type(None):
                return_type = 'void'
            else:
                return_type = get_rust_type(return_annotation)

            # 生成函数签名
            func_code = RustCodeGenerator.generate_function_signature(
                func_name, params, return_type, clean_body
            )

            # 组合导入和函数
            if imports:
                imports_code = '\n'.join(imports)
                full_code = f'{imports_code}\n\n{func_code}'
            else:
                full_code = func_code

            return full_code
        else:
            # 不自动生成签名，直接返回原始代码
            return code_body


# 便捷函数
def generate_function_signature(func_name: str, params: List[tuple],
                                return_type: str, code_body: str) -> str:
    """生成 Rust 函数签名"""
    return RustCodeGenerator.generate_function_signature(
        func_name, params, return_type, code_body
    )


def generate_lib_code(functions: List[str], imports: List[str] = None) -> str:
    """生成 lib.rs 文件内容"""
    return RustCodeGenerator.generate_lib_code(functions, imports)


def generate_cargo_toml(package_name: str, version: str = '0.1.0',
                        dependencies: Dict[str, str] = None) -> str:
    """生成 Cargo.toml 文件内容"""
    return RustCodeGenerator.generate_cargo_toml(
        package_name, version, dependencies
    )


def generate_from_python_func(func_name: str, sig: inspect.Signature,
                               return_annotation: Any, code_body: str,
                               auto_signature: bool = True) -> str:
    """从 Python 函数生成 Rust 代码"""
    return RustCodeGenerator.generate_from_python_func(
        func_name, sig, return_annotation, code_body, auto_signature
    )