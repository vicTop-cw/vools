# Nim 隐式双元操作符库 - 函数组合与管道操作
#
# 提供两组操作符：
# 1. 函|函操作符（compose01/compose11/compose21 等）- 用于函数组合
# 2. 值|函管道操作符（pipe/pipeMap/pipeFilter/pipeFlat/pipeReduce/pipeFold）- 用于值到函数的管道应用
#
# 使用方式：
#   import operators
#
#   # 函数组合
#   let composed = compose01(proc(): string = "Hello", proc(s: string): string = s & ", World!")
#   echo composed()  # 输出: Hello, World!
#
#   # 管道操作
#   let result = pipe("hello", proc(s: string): string = s.toUpper())
#   echo result  # 输出: HELLO

import sequtils

# ============ 零参数函数到单参数函数 ============

proc compose01[A, B](f: proc(): A, g: proc(x: A): B): proc(): B =
  result = proc(): B = g(f())

proc compose01Rev[A, B](g: proc(x: A): B, f: proc(): A): proc(): B =
  result = proc(): B = g(f())

proc compose02[A, B, X](f: proc(): A, g: proc(x: A, y: X): B): proc(x: X): B =
  result = proc(x: X): B = g(f(), x)

proc compose02Rev[A, B, X](g: proc(x: A, y: X): B, f: proc(): A): proc(x: X): B =
  result = proc(x: X): B = g(f(), x)

# ============ 单参数函数组合 ============

proc compose11[A, B, C](f: proc(x: A): B, g: proc(x: B): C): proc(x: A): C =
  result = proc(x: A): C = g(f(x))

proc compose11Rev[A, B, C](g: proc(x: B): C, f: proc(x: A): B): proc(x: A): C =
  result = proc(x: A): C = g(f(x))

proc compose12[A, B, C, X](f: proc(x: A): B, g: proc(x: B, y: X): C): proc(x: A, y: X): C =
  result = proc(x: A, y: X): C = g(f(x), y)

proc compose12Rev[A, B, C, X](g: proc(x: B, y: X): C, f: proc(x: A): B): proc(x: A, y: X): C =
  result = proc(x: A, y: X): C = g(f(x), y)

# ============ 双参数函数组合 ============

proc compose21[A, B, C, D](f: proc(x: A, y: B): C, g: proc(x: C): D): proc(x: A, y: B): D =
  result = proc(x: A, y: B): D = g(f(x, y))

proc compose21Rev[A, B, C, D](g: proc(x: C): D, f: proc(x: A, y: B): C): proc(x: A, y: B): D =
  result = proc(x: A, y: B): D = g(f(x, y))

proc compose22[A, B, C, D, X](f: proc(x: A, y: B): C, g: proc(x: C, y: X): D): proc(x: A, y: B, z: X): D =
  result = proc(x: A, y: B, z: X): D = g(f(x, y), z)

proc compose22Rev[A, B, C, D, X](g: proc(x: C, y: X): D, f: proc(x: A, y: B): C): proc(x: A, y: B, z: X): D =
  result = proc(x: A, y: B, z: X): D = g(f(x, y), z)

# ============ 值到函数管道操作符 ============

proc pipe[A, B](value: A, f: proc(x: A): B): B =
  result = f(value)

proc pipeLeft[A, B](f: proc(x: A): B, value: A): B =
  result = f(value)

proc pipeMap[A, B](values: seq[A], f: proc(x: A): B): seq[B] =
  result = values.map(f)

proc pipeMapLeft[A, B](f: proc(x: A): B, values: seq[A]): seq[B] =
  result = values.map(f)

proc pipeFilter[A](values: seq[A], predicate: proc(x: A): bool): seq[A] =
  result = values.filter(predicate)

proc pipeFilterLeft[A](predicate: proc(x: A): bool, values: seq[A]): seq[A] =
  result = values.filter(predicate)

proc pipeFlat[A, B](values: seq[seq[A]], f: proc(x: A): B): seq[B] =
  result = @[]
  for inner in values:
    result.add(inner.map(f))

proc pipeFlatLeft[A, B](f: proc(x: A): B, values: seq[seq[A]]): seq[B] =
  result = @[]
  for inner in values:
    result.add(inner.map(f))

proc pipeReduce[A](values: seq[A], f: proc(x, y: A): A): A =
  if values.len == 0:
    raise newException(ValueError, "Cannot reduce empty sequence")
  result = values[0]
  for i in 1..<values.len:
    result = f(result, values[i])

proc pipeReduceLeft[A](f: proc(x, y: A): A, values: seq[A]): A =
  result = pipeReduce(values, f)

proc pipeFold[A, Z](values: seq[A], folder: proc(init: Z): proc(acc: Z, x: A): Z): proc(init: Z): Z =
  result = proc(init: Z): Z =
    var acc = init
    for x in values:
      acc = folder(init)(acc, x)
    acc

proc pipeFoldLeft[A, Z](folder: proc(init: Z): proc(acc: Z, x: A): Z, values: seq[A]): proc(init: Z): Z =
  result = pipeFold(values, folder)

# ============ 导出到 DLL 的函数 ============

proc nim_pipe_str_str(value: string, f: proc(x: string): string): string {.exportc, dynlib.} =
  result = pipe(value, f)
