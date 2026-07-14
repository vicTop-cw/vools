## vools_curried.nim - High-performance math/collection operations
import strutils, math, algorithm, sets, sequtils

# ============================================================
# CSV 解析辅助（前置）
# ============================================================

proc parseCsvInts(s: string): seq[int] =
  if s.len == 0: return @[]
  for p in s.split(','):
    if p.strip().len > 0:
      result.add(parseInt(p.strip()))

proc parseCsvFloats(s: string): seq[float] =
  if s.len == 0: return @[]
  for p in s.split(','):
    if p.strip().len > 0:
      result.add(parseFloat(p.strip()))

# ============================================================
# 数学统计（泛型）
# ============================================================

proc sumImpl[T: SomeNumber](arr: openArray[T]): T =
  ## 求和
  result = T(0)
  for x in arr: result += x

proc meanImpl[T: SomeNumber](arr: openArray[T]): float =
  ## 平均值
  if arr.len == 0: return 0.0
  result = float(sumImpl[T](arr)) / float(arr.len)

proc minImpl[T](arr: openArray[T]): T =
  ## 最小值
  result = arr[0]
  for i in 1..<arr.len:
    if arr[i] < result: result = arr[i]

proc maxImpl[T](arr: openArray[T]): T =
  ## 最大值
  result = arr[0]
  for i in 1..<arr.len:
    if arr[i] > result: result = arr[i]

proc minMaxImpl[T](arr: openArray[T]): tuple[mn, mx: T] =
  ## 同时取 min/max，单次遍历
  if arr.len == 0: return (T(0), T(0))
  result = (arr[0], arr[0])
  for i in 1..<arr.len:
    if arr[i] < result.mn: result.mn = arr[i]
    if arr[i] > result.mx: result.mx = arr[i]

proc varianceImpl[T: SomeNumber](arr: openArray[T]): float =
  ## 方差（总体方差）
  if arr.len == 0: return 0.0
  let m = meanImpl[T](arr)
  var s = 0.0
  for x in arr:
    let d = float(x) - m
    s += d * d
  result = s / float(arr.len)

proc stddevImpl[T: SomeNumber](arr: openArray[T]): float =
  ## 标准差
  result = sqrt(varianceImpl[T](arr))

proc medianImpl[T: SomeNumber](arr: openArray[T]): float =
  ## 中位数
  if arr.len == 0: return 0.0
  var sorted = @arr
  sorted.sort()
  let n = sorted.len
  if n mod 2 == 1:
    result = float(sorted[n div 2])
  else:
    result = (float(sorted[n div 2 - 1]) + float(sorted[n div 2])) / 2.0

# ============================================================
# 集合操作（泛型）
# ============================================================

proc distinctImpl[T](arr: openArray[T]): seq[T] =
  ## 顺序去重
  var seen = initHashSet[T]()
  result = @[]
  for x in arr:
    if x notin seen:
      seen.incl(x)
      result.add(x)

proc unionImpl[T](a, b: openArray[T]): seq[T] =
  ## 集合并集
  var seen = initHashSet[T]()
  result = @[]
  for x in a:
    if x notin seen:
      seen.incl(x)
      result.add(x)
  for x in b:
    if x notin seen:
      seen.incl(x)
      result.add(x)

proc intersectImpl[T](a, b: openArray[T]): seq[T] =
  ## 集合交集
  let setB = toHashSet(b)
  var seen = initHashSet[T]()
  result = @[]
  for x in a:
    if x in setB and x notin seen:
      seen.incl(x)
      result.add(x)

proc diffImpl[T](a, b: openArray[T]): seq[T] =
  ## 集合差集 (a - b)
  let setB = toHashSet(b)
  result = @[]
  for x in a:
    if x notin setB:
      result.add(x)

proc countImpl[T](arr: openArray[T]; v: T): int =
  ## 统计 v 出现次数
  for x in arr:
    if x == v: inc result

# ============================================================
# 数值计算
# ============================================================

proc dotImpl[T: SomeNumber](a, b: openArray[T]): T =
  ## 向量点积
  let n = min(a.len, b.len)
  result = T(0)
  for i in 0..<n:
    result += a[i] * b[i]

proc l2normImpl[T: SomeNumber](arr: openArray[T]): float =
  ## L2 范数
  var s = 0.0
  for x in arr:
    s += float(x) * float(x)
  result = sqrt(s)

# ============================================================
# C 边界 - 显式导出
# ============================================================

proc cur_sum_int*(data: cstring): cstring {.exportc: "cur_sum_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvInts($data)
  result = $sumImpl[int](arr)

proc cur_mean_int*(data: cstring): cstring {.exportc: "cur_mean_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvInts($data)
  result = formatFloat(meanImpl[int](arr), precision = -1)

proc cur_min_int*(data: cstring): cstring {.exportc: "cur_min_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvInts($data)
  if arr.len == 0: result = "0" else: result = $minImpl[int](arr)

proc cur_max_int*(data: cstring): cstring {.exportc: "cur_max_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvInts($data)
  if arr.len == 0: result = "0" else: result = $maxImpl[int](arr)

proc cur_minmax_int*(data: cstring): cstring {.exportc: "cur_minmax_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvInts($data)
  if arr.len == 0:
    result = ","
  else:
    let mm = minMaxImpl[int](arr)
    result = $mm.mn & "," & $mm.mx

proc cur_stddev_int*(data: cstring): cstring {.exportc: "cur_stddev_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvInts($data)
  result = formatFloat(stddevImpl[int](arr), precision = -1)

proc cur_variance_int*(data: cstring): cstring {.exportc: "cur_variance_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvInts($data)
  result = formatFloat(varianceImpl[int](arr), precision = -1)

proc cur_median_int*(data: cstring): cstring {.exportc: "cur_median_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvInts($data)
  result = formatFloat(medianImpl[int](arr), precision = -1)

proc cur_dot_int*(a: cstring; b: cstring): cstring {.exportc: "cur_dot_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arrA = parseCsvInts($a)
  let arrB = parseCsvInts($b)
  result = $dotImpl[int](arrA, arrB)

proc cur_l2norm_int*(data: cstring): cstring {.exportc: "cur_l2norm_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvInts($data)
  result = formatFloat(l2normImpl[int](arr), precision = -1)

proc cur_distinct_int*(data: cstring): cstring {.exportc: "cur_distinct_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvInts($data)
  result = distinctImpl[int](arr).mapIt($it).join(",").cstring

proc cur_count_int*(data: cstring; v: cint): cstring {.exportc: "cur_count_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvInts($data)
  result = $countImpl[int](arr, int(v))

# float 系列
proc cur_sum_float*(data: cstring): cstring {.exportc: "cur_sum_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvFloats($data)
  result = $sumImpl[float](arr)

proc cur_mean_float*(data: cstring): cstring {.exportc: "cur_mean_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvFloats($data)
  result = formatFloat(meanImpl[float](arr), precision = -1)

proc cur_min_float*(data: cstring): cstring {.exportc: "cur_min_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvFloats($data)
  if arr.len == 0: result = "0.0" else: result = $minImpl[float](arr)

proc cur_max_float*(data: cstring): cstring {.exportc: "cur_max_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvFloats($data)
  if arr.len == 0: result = "0.0" else: result = $maxImpl[float](arr)

proc cur_minmax_float*(data: cstring): cstring {.exportc: "cur_minmax_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvFloats($data)
  if arr.len == 0:
    result = ","
  else:
    let mm = minMaxImpl[float](arr)
    result = $mm.mn & "," & $mm.mx

proc cur_stddev_float*(data: cstring): cstring {.exportc: "cur_stddev_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvFloats($data)
  result = formatFloat(stddevImpl[float](arr), precision = -1)

proc cur_variance_float*(data: cstring): cstring {.exportc: "cur_variance_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvFloats($data)
  result = formatFloat(varianceImpl[float](arr), precision = -1)

proc cur_median_float*(data: cstring): cstring {.exportc: "cur_median_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvFloats($data)
  result = formatFloat(medianImpl[float](arr), precision = -1)

proc cur_dot_float*(a: cstring; b: cstring): cstring {.exportc: "cur_dot_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arrA = parseCsvFloats($a)
  let arrB = parseCsvFloats($b)
  result = $dotImpl[float](arrA, arrB)

proc cur_l2norm_float*(data: cstring): cstring {.exportc: "cur_l2norm_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseCsvFloats($data)
  result = formatFloat(l2normImpl[float](arr), precision = -1)

# string 集合操作
proc cur_distinct_string*(data: cstring): cstring {.exportc: "cur_distinct_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let s = $data
  if s.len == 0: return "".cstring
  result = distinctImpl[string](s.split(',')).join(",").cstring

proc cur_union_string*(a: cstring; b: cstring): cstring {.exportc: "cur_union_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let sa = ($a).split(',')
  let sb = ($b).split(',')
  result = unionImpl[string](sa, sb).join(",").cstring

proc cur_intersect_string*(a: cstring; b: cstring): cstring {.exportc: "cur_intersect_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let sa = ($a).split(',')
  let sb = ($b).split(',')
  result = intersectImpl[string](sa, sb).join(",").cstring

proc cur_diff_string*(a: cstring; b: cstring): cstring {.exportc: "cur_diff_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let sa = ($a).split(',')
  let sb = ($b).split(',')
  result = diffImpl[string](sa, sb).join(",").cstring

proc cur_count_string*(data: cstring; target: cstring): cstring {.exportc: "cur_count_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let items = ($data).split(',')
  let t = $target
  result = $countImpl[string](items, t)
