"""
vools.bridge.vbnet.templates - VB.NET 代码模板生成器

自动生成包含 DllExport 属性的 VB.NET 类和方法。
"""

VBPROJ_TEMPLATE = '''
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net6.0</TargetFramework>
    <OutputType>Library</OutputType>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <PlatformTarget>x64</PlatformTarget>
    <RootNamespace>VoolsBridge</RootNamespace>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="DllExport" Version="1.7.4" />
  </ItemGroup>
</Project>
'''

VB_CLASS_TEMPLATE = '''
Imports System
Imports System.Runtime.InteropServices
Imports RGiesecke.DllExport

Namespace VoolsBridge
    Public Class BridgeFunctions
{methods}
    End Class
End Namespace
'''

VB_METHOD_TEMPLATE = '''
        <DllExport(CallingConvention := CallingConvention.Cdecl)>
        Public Shared Function {func_name}({params}) As {return_type}
{body}
        End Function
'''

VB_SUB_TEMPLATE = '''
        <DllExport(CallingConvention := CallingConvention.Cdecl)>
        Public Shared Sub {func_name}({params})
{body}
        End Sub
'''


def generate_vb_method(func_name, params, return_type, body):
    """生成单个 VB.NET 导出方法

    Args:
        func_name: 函数名称
        params: 参数列表，格式 [(name, vb_type), ...]
        return_type: VB.NET 返回类型，'Void' 表示 Sub
        body: 方法体代码字符串

    Returns:
        完整的方法代码
    """
    param_str = ', '.join(f'[{name}] As {vb_type}' for name, vb_type in params)

    indented_body = '\n'.join('            ' + line for line in body.strip().split('\n'))

    if return_type == 'Void' or return_type == 'void':
        return VB_SUB_TEMPLATE.format(
            func_name=func_name,
            params=param_str,
            body=indented_body
        )
    else:
        return VB_METHOD_TEMPLATE.format(
            func_name=func_name,
            params=param_str,
            return_type=return_type,
            body=indented_body
        )


def generate_vb_class(methods_code):
    """生成完整的 VB.NET 类代码

    Args:
        methods_code: 方法代码列表

    Returns:
        完整的类代码
    """
    methods_str = '\n'.join(methods_code)
    return VB_CLASS_TEMPLATE.format(methods=methods_str)


def generate_vbproj():
    """生成 VB.NET 项目文件

    Returns:
        vbproj 文件内容
    """
    return VBPROJ_TEMPLATE.strip()
