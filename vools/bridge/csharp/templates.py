"""
vools.bridge.csharp.templates - C# 代码模板生成器

自动生成包含 DllExport 属性的 C# 类和方法。
"""

# C# 项目文件模板（csproj）
CSPROJ_TEMPLATE = '''
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net6.0</TargetFramework>
    <OutputType>Library</OutputType>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <PlatformTarget>x64</PlatformTarget>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="DllExport" Version="1.7.4" />
  </ItemGroup>
</Project>
'''

# C# 类模板（带 DllExport）
CS_CLASS_TEMPLATE = '''
using System;
using System.Runtime.InteropServices;
using RGiesecke.DllExport;

namespace VoolsBridge
{{
    public class BridgeFunctions
    {{
{methods}
    }}
}}
'''

# C# 方法模板（单个导出函数）
CS_METHOD_TEMPLATE = '''
        [DllExport(CallingConvention = CallingConvention.Cdecl)]
        public static {return_type} {func_name}({params})
        {{
{body}
        }}
'''


def generate_cs_method(func_name, params, return_type, body):
    """
    生成单个 C# 导出方法

    参数：
        func_name: 函数名称
        params: 参数列表，格式 [(name, cs_type), ...]
        return_type: C# 返回类型
        body: 方法体代码字符串

    返回：
        完整的方法代码
    """
    # 构建参数字符串
    param_str = ', '.join(f'{cs_type} {name}' for name, cs_type in params)

    # 处理返回类型
    if return_type == 'void':
        ret_keyword = 'void'
    else:
        ret_keyword = return_type

    # 缩进方法体（4空格 + 8空格 = 12空格）
    indented_body = '\n'.join('            ' + line for line in body.strip().split('\n'))

    return CS_METHOD_TEMPLATE.format(
        return_type=ret_keyword,
        func_name=func_name,
        params=param_str,
        body=indented_body
    )


def generate_cs_class(methods_code):
    """
    生成完整的 C# 类代码

    参数：
        methods_code: 方法代码列表

    返回：
        完整的类代码
    """
    methods_str = '\n'.join(methods_code)
    return CS_CLASS_TEMPLATE.format(methods=methods_str)


def generate_csproj():
    """
    生成 C# 项目文件

    返回：
        csproj 文件内容
    """
    return CSPROJ_TEMPLATE.strip()