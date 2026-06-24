"""
vools.bridge._examples - 依赖处理示例

展示如何使用 deps 和 module_code 参数处理跨语言依赖。

FreeBASIC 不支持函数嵌套，但支持模块级函数。
通过 deps 参数声明依赖，自动生成模块级函数。
"""

# ============================================================================
# 示例 1: 简单依赖（辅助函数）
# ============================================================================

# 定义一个辅助函数
def fb_abs(x: int) -> int:
    """FreeBASIC 辅助函数：绝对值"""
    return """
    If x < 0 Then
        Return -x
    Else
        Return x
    End If
    """


def fb_max(a: int, b: int) -> int:
    """FreeBASIC 辅助函数：最大值"""
    return """
    If a > b Then
        Return a
    Else
        Return b
    End If
    """


# 使用 @fbc 装饰器，deps 参数声明依赖
@fbc(deps=[fb_abs, fb_max])
def fb_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    """
    计算曼哈顿距离

    FreeBASIC 代码（不直接支持函数嵌套）：
    - fb_abs: 计算绝对值
    - fb_max: 计算最大值

    参数：
        deps=[fb_abs, fb_max] 声明依赖

    返回：
        曼哈顿距离 |x1-x2| + |y1-y2|
    """
    return """
    Dim dx As Long = x2 - x1
    Dim dy As Long = y2 - y1
    Return fb_abs(dx) + fb_abs(dy)
    """


# ============================================================================
# 示例 2: 模块级代码
# ============================================================================

# 有些语言需要预先定义的常量和类型
MODULE_CODE_FB = """
' 模块级常量
Const PI As Double = 3.14159265358979
Const EPS As Double = 0.0000001

' 模块级类型
Type Point
    x As Double
    y As Double
End Type

' 模块级辅助函数
Function distanceBetween(p1 As Point, p2 As Point) As Double
    Dim dx As Double = p2.x - p1.x
    Dim dy As Double = p2.y - p1.y
    Return Sqr(dx * dx + dy * dy)
End Function
"""


@fbc(module_code=MODULE_CODE_FB)
def fb_circle_area(radius: float) -> float:
    """
    计算圆面积

    使用 module_code 定义常量和辅助函数
    """
    return """
    Return PI * radius * radius
    """


# ============================================================================
# 示例 3: 复杂依赖链
# ============================================================================

# 斐波那契（递归）
def fb_fib_rec(n: int) -> int:
    """斐波那契递归版本"""
    return """
    If n <= 1 Then
        Return 1
    Else
        Return fb_fib_rec(n - 1) + fb_fib_rec(n - 2)
    End If
    """


# 记忆化缓存
MODULE_CODE_WITH_MEMO = """
' 记忆化缓存
Dim Shared memo(0 To 100) As Long
Dim Shared memo_init As Byte = 0

Sub init_memo()
    If memo_init = 0 Then
        For i As Long = 0 To 100
            memo(i) = -1
        Next i
        memo(0) = 1
        memo(1) = 1
        memo_init = 1
    End If
End Sub
"""


@fbc(deps=[fb_fib_rec], module_code=MODULE_CODE_WITH_MEMO)
def fb_fib_memo(n: int) -> int:
    """
    斐波那契记忆化版本

    依赖 fb_fib_rec（不使用缓存时）
    可以扩展为使用记忆化缓存
    """
    return """
    ' 简单版本直接用递归
    Return fb_fib_rec(n)
    """


# ============================================================================
# 示例 4: Nim 风格（Nim 支持函数嵌套）
# ============================================================================

# Nim 支持闭包和内部函数，deps 不是必须的
@nim
def nim_complex_calc(data: list) -> int:
    """
    Nim 版本：复杂的嵌套计算

    Nim 原生支持函数嵌套，不需要 deps
    """
    return """
    var result = 0
    proc helper(x: int): int =
        if x <= 0:
            return 0
        return x + helper(x - 1)

    proc filter_positive(arr: seq[int]): seq[int] =
        for x in arr:
            if x > 0:
                result.add(x)

    let positives = filter_positive(data)
    result = helper(sum(positives))
    Return result
    """


# ============================================================================
# 示例 5: C 风格（需要前置声明）
# ============================================================================

# C 需要函数原型前置声明
MODULE_CODE_C = """
// 前置声明（函数原型）
int helper_func(int n);
int filter_and_sum(int* arr, int len);

// 辅助函数
int helper_func(int n) {
    if (n <= 0) return 0;
    return n + helper_func(n - 1);
}

// 过滤正数并求和
int filter_and_sum(int* arr, int len) {
    int sum = 0;
    for (int i = 0; i < len; i++) {
        if (arr[i] > 0) {
            sum += arr[i];
        }
    }
    return sum;
}
"""


@cpp(module_code=MODULE_CODE_C)
def c_complex_calc(arr: list) -> int:
    """
    C 版本：复杂计算

    C 不支持函数嵌套，需要 module_code 声明前置函数
    """
    return """
    return helper_func(filter_and_sum(arr, len));
    """


# ============================================================================
# 设计原理总结
# ============================================================================

"""
跨语言依赖处理设计原则：

1. 统一接口，不同实现
   - @lang 装饰器提供统一参数：deps, module_code
   - 具体处理由各语言的适配器决定

2. deps 参数 - 显式依赖声明
   - 用户显式列出依赖函数
   - 装饰器自动解析并生成目标语言代码
   - 支持函数引用（不是字符串）

3. module_code 参数 - 模块级代码
   - 用于预定义常量、类型、函数
   - 在主函数之前生成
   - 支持复杂的初始化逻辑

4. 自动依赖分析（可选）
   - 分析函数体中的函数调用
   - 自动提取依赖（启发式）
   - 需要依赖注册表

5. 依赖顺序处理
   - 拓扑排序确保正确顺序
   - FreeBASIC/C: 必须在主函数前声明
   - Nim/Rust: 可以嵌套或按任意顺序

6. Fallback 机制
   - 编译器不可用时使用 Python fallback
   - Fallback 函数不需要转换
   - 确保基本功能可用
"""
