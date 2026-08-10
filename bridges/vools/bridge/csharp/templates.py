"""
vools.bridge.csharp.templates - C# 代码模板生成器

使用 .NET NativeAOT + [UnmanagedCallersOnly] 属性导出 C 函数，
替代不可用的 DllExport NuGet 包（其 MSBuild 任务依赖 .NET Framework）。

关键设计：
- 所有方法都生成包装器模式：导出方法 (func_name_export) → 内部实现 (func_name)
- 导出方法标记 [UnmanagedCallersOnly(EntryPoint = "func_name")]
- 内部方法使用托管类型，包含用户代码，支持递归自调用
- 字符串参数通过 byte* 传递，内部使用 Marshal 进行转换
"""

import platform

# 检测运行时标识符 (RID)，NativeAOT 编译需要
_IS_WINDOWS = platform.system() == 'Windows'
_ARCH = platform.machine().lower()
if _ARCH in ('amd64', 'x86_64'):
    _ARCH_ID = 'x64'
elif _ARCH in ('arm64', 'aarch64'):
    _ARCH_ID = 'arm64'
else:
    _ARCH_ID = 'x64'

if _IS_WINDOWS:
    _RUNTIME_ID = f'win-{_ARCH_ID}'
elif platform.system() == 'Darwin':
    _RUNTIME_ID = f'osx-{_ARCH_ID}'
else:
    _RUNTIME_ID = f'linux-{_ARCH_ID}'


# C# 项目文件模板（csproj）
# 默认使用常规 dotnet publish 生成控制台程序。由于当前环境缺少 NativeAOT
# 链接器，无法通过 [UnmanagedCallersOnly] 导出原生符号；改为生成可执行
# 文件，由 call_func 通过 JSON stdin/stdout 调用托管方法。
# RuntimeIdentifier 占位符在 generate_csproj() 中替换。
CSPROJ_TEMPLATE = '''
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net9.0</TargetFramework>
    <OutputType>Exe</OutputType>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <PublishAot>false</PublishAot>
    <RuntimeIdentifier>{runtime_id}</RuntimeIdentifier>
  </PropertyGroup>
</Project>
'''

# C# 类模板（UnmanagedCallersOnly 导出）
CS_CLASS_TEMPLATE = '''
using System;
using System.Runtime.InteropServices;
using System.Text;

namespace VoolsBridge
{{
    public class BridgeFunctions
    {{
{methods}
    }}
}}
'''

# C# 方法包装模板（NativeAOT 导出 + 内部实现）
# 生成两个方法：
#   1. [UnmanagedCallersOnly] 导出方法 (func_name_export)，处理 marshaling
#   2. 内部实现方法 (func_name)，使用托管类型，包含用户代码
# 这种模式确保：
#   - 递归调用在内部方法间进行，不触发 CS8901 错误
#   - 字符串 marshaling 在导出层处理
#   - EntryPoint 保持为原始函数名，ctypes 通过原始名称调用
CS_METHOD_WRAPPER_TEMPLATE = '''
        [UnmanagedCallersOnly(EntryPoint = "{entry_point}")]
        public static unsafe {native_return_type} {export_name}({native_params})
        {{
{marshaling_in}
            {return_stmt}{impl_name}({call_args});
{marshaling_out}
        }}

        private static {managed_return_type} {impl_name}({managed_params})
        {{
{body}
        }}
'''

# C# 控制台入口模板（用于无 NativeAOT 链接器时的进程内调用回退）
CS_PROGRAM_TEMPLATE = '''
using System;
using System.Reflection;
using System.Text.Json;

class Program
{
    static int Main(string[] args)
    {
        try
        {
            string line = Console.In.ReadLine();
            if (string.IsNullOrEmpty(line))
            {
                Console.Error.WriteLine("ERROR: empty input");
                return 1;
            }
            using JsonDocument doc = JsonDocument.Parse(line);
            string funcName = doc.RootElement.GetProperty("func").GetString();
            var method = typeof(VoolsBridge.BridgeFunctions).GetMethod(funcName,
                BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
            if (method == null)
            {
                Console.Error.WriteLine("ERROR: method not found: " + funcName);
                return 1;
            }
            var parameters = method.GetParameters();
            var argElems = doc.RootElement.GetProperty("args").EnumerateArray();
            object[] invokeArgs = new object[parameters.Length];
            int idx = 0;
            foreach (var el in argElems)
            {
                var p = parameters[idx];
                if (p.ParameterType == typeof(string))
                    invokeArgs[idx] = el.GetString();
                else if (p.ParameterType == typeof(int))
                    invokeArgs[idx] = el.GetInt32();
                else if (p.ParameterType == typeof(long))
                    invokeArgs[idx] = el.GetInt64();
                else if (p.ParameterType == typeof(double))
                    invokeArgs[idx] = el.GetDouble();
                else if (p.ParameterType == typeof(bool))
                    invokeArgs[idx] = el.GetBoolean();
                else
                    invokeArgs[idx] = Convert.ChangeType(el.ToString(), p.ParameterType);
                idx++;
            }
            object result = method.Invoke(null, invokeArgs);
            string output = result == null ? "null" : JsonSerializer.Serialize(result);
            Console.WriteLine(output);
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("ERROR: " + ex);
            return 1;
        }
    }
}
'''


def _native_type(cs_type):
    """将 C# 托管类型映射为 NativeAOT 兼容的原生类型"""
    if cs_type == 'string':
        return 'byte*'
    return cs_type


def _native_return_type(cs_type):
    """将 C# 返回类型映射为 NativeAOT 兼容的原生返回类型"""
    if cs_type == 'string':
        return 'IntPtr'
    if cs_type == 'void':
        return 'void'
    return cs_type


def _has_string_params(params):
    """检查参数列表中是否有 string 类型"""
    return any(cs_type == 'string' for _, cs_type in params)


def _has_string_return(return_type):
    """检查返回类型是否是 string"""
    return return_type == 'string'


def generate_cs_method(func_name, params, return_type, body):
    """
    生成单个 C# 导出方法（含 NativeAOT marshaling 包装）

    所有方法都生成包装器模式：
    - func_name_export: [UnmanagedCallersOnly(EntryPoint = "func_name")] 导出方法
    - func_name: 内部实现方法，包含用户代码

    参数：
        func_name: 函数名称
        params: 参数列表，格式 [(name, cs_type), ...]
        return_type: C# 返回类型（托管类型，如 'string', 'int'）
        body: 方法体代码字符串

    返回：
        完整的方法代码（包装器 + 实现）
    """
    export_name = func_name + '_export'
    impl_name = func_name

    # 构建原生参数列表（string → byte*）
    native_params = ', '.join(
        f'{_native_type(cs_type)} {name}'
        for name, cs_type in params
    )

    # 构建托管参数列表（原始类型）
    managed_params = ', '.join(
        f'{cs_type} {name}'
        for name, cs_type in params
    )

    # 构建调用参数列表（如果有 string 参数，需要转换名称）
    call_args = ', '.join(
        f'{name}_str' if cs_type == 'string' else name
        for name, cs_type in params
    )

    # 生成 marshaling 输入代码
    marshaling_in_lines = []
    for name, cs_type in params:
        if cs_type == 'string':
            marshaling_in_lines.append(
                f'            string {name}_str = Marshal.PtrToStringUTF8((IntPtr){name});'
            )
    marshaling_in = '\n'.join(marshaling_in_lines) if marshaling_in_lines else ''

    # 生成 marshaling 输出代码
    native_return_type = _native_return_type(return_type)
    managed_return_type = return_type

    if return_type == 'void':
        return_stmt = ''
        marshaling_out = ''
    elif return_type == 'string':
        return_stmt = 'string __result = '
        marshaling_out = '            return Marshal.StringToCoTaskMemUTF8(__result);'
    else:
        return_stmt = 'return '
        marshaling_out = ''

    # 缩进用户代码体
    indented_body = '\n'.join('            ' + line for line in body.strip().split('\n'))

    return CS_METHOD_WRAPPER_TEMPLATE.format(
        entry_point=func_name,
        native_return_type=native_return_type,
        export_name=export_name,
        native_params=native_params,
        marshaling_in=marshaling_in,
        return_stmt=return_stmt,
        impl_name=impl_name,
        call_args=call_args,
        marshaling_out=marshaling_out,
        managed_return_type=managed_return_type,
        managed_params=managed_params,
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


def generate_csproj(dll_name=None):
    """
    生成 C# 项目文件

    参数：
        dll_name: 可选的 DLL 名称，用于设置 AssemblyName

    返回：
        csproj 文件内容
    """
    csproj = CSPROJ_TEMPLATE.format(runtime_id=_RUNTIME_ID)
    if dll_name:
        csproj = csproj.replace(
            '<TargetFramework>net9.0</TargetFramework>',
            f'<TargetFramework>net9.0</TargetFramework>\n    <AssemblyName>{dll_name}</AssemblyName>'
        )
    return csproj.strip()


def generate_cs_program():
    """
    生成 C# 控制台入口 Program.cs

    用于无 NativeAOT 链接器时，通过进程间 JSON 通信调用托管方法。

    返回：
        Program.cs 文件内容
    """
    return CS_PROGRAM_TEMPLATE.strip()