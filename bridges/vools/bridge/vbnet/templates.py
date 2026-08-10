"""
vools.bridge.vbnet.templates - VB.NET 代码模板生成器

自动生成 VB.NET 控制台应用程序代码，通过反射调用函数并输出结果。
"""

VBPROJ_TEMPLATE = '''
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net9.0</TargetFramework>
    <OutputType>Exe</OutputType>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <PlatformTarget>x64</PlatformTarget>
    <RootNamespace></RootNamespace>
  </PropertyGroup>
</Project>
'''

VB_CLASS_TEMPLATE = '''
Imports System
Imports System.Reflection

Public Module Bridge
{methods}
    Public Sub Main(args As String())
        If args.Length = 0 Then
            Environment.Exit(1)
        End If
        Dim funcName = args(0)
        Dim t = GetType(Bridge)
        For Each m In t.GetMethods(BindingFlags.Public Or BindingFlags.Static)
            If m.Name = funcName Then
                Dim pi = m.GetParameters()
                Dim convertedArgs(pi.Length - 1) As Object
                For i = 0 To pi.Length - 1
                    Dim argIdx = i + 1
                    If argIdx < args.Length Then
                        convertedArgs(i) = Convert.ChangeType(args(argIdx), pi(i).ParameterType)
                    Else
                        convertedArgs(i) = Nothing
                    End If
                Next
                Dim result = m.Invoke(Nothing, convertedArgs)
                If result IsNot Nothing Then
                    Console.Write(result.ToString())
                End If
                Return
            End If
        Next
        Environment.Exit(1)
    End Sub
End Module
'''

VB_METHOD_TEMPLATE = '''
    Public Function {func_name}({params}) As {return_type}
{body}
    End Function
'''

VB_SUB_TEMPLATE = '''
    Public Sub {func_name}({params})
{body}
    End Sub
'''


# VB.NET 保留关键字列表（需要转义的标识符）
_VB_KEYWORDS = frozenset([
    'AddHandler', 'AddressOf', 'Alias', 'And', 'AndAlso', 'As', 'Boolean',
    'ByRef', 'Byte', 'ByVal', 'Call', 'Case', 'Catch', 'CBool', 'CByte',
    'CChar', 'CDate', 'CDbl', 'CDec', 'Char', 'CInt', 'Class', 'CLng',
    'CObj', 'Const', 'Continue', 'CSByte', 'CShort', 'CSng', 'CStr',
    'CType', 'CUInt', 'CULng', 'CUShort', 'Date', 'Decimal', 'Declare',
    'Default', 'Delegate', 'Dim', 'DirectCast', 'Do', 'Double', 'Each',
    'Else', 'ElseIf', 'End', 'EndIf', 'Enum', 'Erase', 'Error', 'Event',
    'Exit', 'False', 'Finally', 'For', 'Friend', 'Function', 'Get',
    'GetType', 'GetXMLNamespace', 'Global', 'GoSub', 'GoTo', 'Handles',
    'If', 'Implements', 'Imports', 'In', 'Inherits', 'Integer', 'Interface',
    'Is', 'IsNot', 'Let', 'Lib', 'Like', 'Long', 'Loop', 'Me', 'Mod',
    'Module', 'MustInherit', 'MustOverride', 'MyBase', 'MyClass',
    'NameOf', 'Namespace', 'Narrowing', 'New', 'Next', 'Not',
    'Nothing', 'NotInheritable', 'NotOverridable', 'Object', 'Of',
    'On', 'Operator', 'Option', 'Optional', 'Or', 'OrElse', 'Out',
    'Overloads', 'Overridable', 'Overrides', 'ParamArray', 'Partial',
    'Private', 'Property', 'Protected', 'Public', 'RaiseEvent', 'ReadOnly',
    'ReDim', 'REM', 'RemoveHandler', 'Resume', 'Return', 'SByte',
    'Select', 'Set', 'Shadows', 'Shared', 'Short', 'Single', 'Static',
    'Step', 'Stop', 'String', 'Structure', 'Sub', 'SyncLock', 'Then',
    'Throw', 'To', 'True', 'Try', 'TryCast', 'TypeOf', 'UInteger',
    'ULong', 'UShort', 'Using', 'Variant', 'Wend', 'When', 'While',
    'Widening', 'With', 'WithEvents', 'WriteOnly', 'Xor',
])
_VB_KEYWORDS_LOWER = frozenset(k.lower() for k in _VB_KEYWORDS)


def _escape_vb_identifier(name):
    """转义 VB.NET 保留关键字

    Args:
        name: 标识符名称

    Returns:
        如果名称是 VB.NET 关键字，返回 [name]；否则返回原名称
    """
    # VB.NET 关键字不区分大小写，使用小写进行比较
    if name.lower() in _VB_KEYWORDS_LOWER:
        return '[{0}]'.format(name)
    return name


def generate_vb_method(func_name, params, return_type, body):
    """生成单个 VB.NET 方法

    Args:
        func_name: 函数名称
        params: 参数列表，格式 [(name, vb_type), ...]
        return_type: VB.NET 返回类型，'Void' 表示 Sub
        body: 方法体代码字符串

    Returns:
        完整的方法代码
    """
    func_name = _escape_vb_identifier(func_name)
    param_str = ', '.join('{0} As {1}'.format(_escape_vb_identifier(name), vb_type) for name, vb_type in params)

    indented_body = '\n'.join('        ' + line for line in body.strip().split('\n'))

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
    """生成完整的 VB.NET 类代码（包含 Main 反射调度模块）

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