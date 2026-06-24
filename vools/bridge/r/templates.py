"""
vools.bridge.r.templates - R 代码模板生成器

生成完整的 R 脚本代码，包括函数定义、JSON 读写封装、
以及从 Python 函数签名自动生成 R 函数的能力。
"""

import inspect
from typing import List, Dict, Any, Optional

from .types import RTypeMapper, get_r_type


class RCodeGenerator:
    """
    R 代码生成器

    生成完整的 R 脚本代码，包括：
    - 函数签名生成
    - JSON 输入读取
    - 函数调用
    - JSON 结果输出
    - 错误处理
    """

    @staticmethod
    def generate_function_signature(
        func_name: str,
        params: List[tuple],
        return_type: str,
        code_body: str
    ) -> str:
        """
        生成 R 函数定义代码

        参数：
            func_name: 函数名称
            params: 参数列表，每个元素是 (param_name, r_type)
            return_type: R 返回类型字符串
            code_body: 函数体代码（不含签名）

        返回：
            完整的 R 函数代码字符串
        """
        params_str = ', '.join([name for name, _ in params])

        indented_body = ''
        for line in code_body.split('\n'):
            if line.strip():
                indented_body += '    ' + line + '\n'
            else:
                indented_body += '\n'

        func_code = f'{func_name} <- function({params_str}) {{\n{indented_body}}}'
        return func_code

    @staticmethod
    def generate_script_code(
        func_code: str,
        func_name: str,
        use_jsonlite: bool = True
    ) -> str:
        """
        生成完整的 R 脚本代码（含 JSON 读写封装）

        参数：
            func_code: 函数定义代码
            func_name: 函数名称
            use_jsonlite: 是否使用 jsonlite 包（默认 True）

        返回：
            完整的 R 脚本代码字符串
        """
        if use_jsonlite:
            script = f'''options(encoding = "UTF-8")

suppressPackageStartupMessages(library(jsonlite))

input_json <- readLines("stdin", warn = FALSE, encoding = "UTF-8")
input_data <- fromJSON(paste(input_json, collapse = "\\n"), simplifyVector = FALSE)

.args <- lapply(input_data$args, function(.x) {{
  if (is.list(.x) && length(.x) > 0 && !is.list(.x[[1]])) {{
    return(unlist(.x, recursive = FALSE))
  }}
  return(unlist(.x))
}})

{func_code}

result <- do.call({func_name}, .args)

cat(toJSON(result, auto_unbox = TRUE, pretty = FALSE))
'''
        else:
            script = f'''options(encoding = "UTF-8")

input_json <- readLines("stdin", warn = FALSE, encoding = "UTF-8")
input_data <- eval(parse(text = paste(input_json, collapse = "\\n")))

{func_code}

result <- do.call({func_name}, as.list(input_data$args))

cat(format(result))
'''
        return script

    @staticmethod
    def extract_preamble(code: str) -> tuple:
        """
        从代码中提取前置语句（library、source 等）和函数体

        参数：
            code: R 代码字符串

        返回：
            (preamble_lines, body_lines) 元组
        """
        preamble = []
        body_lines = []

        for line in code.strip().split('\n'):
            line_stripped = line.strip()

            if (line_stripped.startswith('library(') or
                line_stripped.startswith('suppressPackageStartupMessages') or
                line_stripped.startswith('source(') or
                line_stripped.startswith('#') or
                line_stripped == ''):
                preamble.append(line)
            else:
                body_lines.append(line)

        body = '\n'.join(body_lines)
        return (preamble, body)

    @staticmethod
    def generate_from_python_func(
        func_name: str,
        sig: inspect.Signature,
        return_annotation: Any,
        code_body: str,
        auto_signature: bool = True
    ) -> str:
        """
        从 Python 函数生成 R 函数代码

        参数：
            func_name: 函数名称
            sig: Python 函数签名
            return_annotation: 返回类型注解
            code_body: R 函数体代码
            auto_signature: 是否自动生成签名（默认 True）

        返回：
            R 函数代码字符串
        """
        if auto_signature:
            preamble, clean_body = RCodeGenerator.extract_preamble(code_body)

            params = []
            for param_name, param in sig.parameters.items():
                if param.annotation != param.empty:
                    py_type = param.annotation
                    r_type = get_r_type(py_type)
                else:
                    r_type = 'integer'
                params.append((param_name, r_type))

            if return_annotation is None or return_annotation is type(None):
                return_type = 'NULL'
            else:
                return_type = get_r_type(return_annotation)

            func_code = RCodeGenerator.generate_function_signature(
                func_name, params, return_type, clean_body
            )

            if preamble:
                preamble_code = '\n'.join(preamble)
                full_code = f'{preamble_code}\n\n{func_code}'
            else:
                full_code = func_code

            return full_code
        else:
            return code_body


def generate_function_signature(func_name: str, params: List[tuple],
                                return_type: str, code_body: str) -> str:
    """生成 R 函数签名"""
    return RCodeGenerator.generate_function_signature(
        func_name, params, return_type, code_body
    )


def generate_script_code(func_code: str, func_name: str,
                         use_jsonlite: bool = True) -> str:
    """生成完整 R 脚本代码"""
    return RCodeGenerator.generate_script_code(func_code, func_name, use_jsonlite)


def generate_from_python_func(func_name: str, sig: inspect.Signature,
                              return_annotation: Any, code_body: str,
                              auto_signature: bool = True) -> str:
    """从 Python 函数生成 R 代码"""
    return RCodeGenerator.generate_from_python_func(
        func_name, sig, return_annotation, code_body, auto_signature
    )
