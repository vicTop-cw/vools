## vools_seq.nim - High-performance sequence operations in pure Nim
## 内部使用泛型实现，cstring 边界仍用显式导出函数
import std/[sequtils, algorithm, sets, strutils, strformat]

# ============================================================
# 泛型内部实现 - 消除重复代码
# ============================================================

# 泛型 map: 对序列每个元素应用 fn
proc mapImpl[T](arr: seq[T]; fn: proc(x: T): T): seq[T] =
  result = newSeqOfCap[T](arr.len)
  for x in arr:
    result.add(fn(x))

# 泛型 filter: 保留满足 pred 的元素
proc filterImpl[T](arr: seq[T]; pred: proc(x: T): bool): seq[T] =
  result = @[]
  for x in arr:
    if pred(x): result.add(x)

# 泛型 sum: 数字序列求和
proc sumImpl[T: SomeNumber](arr: seq[T]): T =
  result = T(0)
  for x in arr: result += x

# 泛型 max: 找出最大值（必须有 comparable）
proc maxImpl[T](arr: seq[T]): T =
  result = arr[0]
  for i in 1..<arr.len:
    if arr[i] > result: result = arr[i]

# 泛型 min: 找出最小值
proc minImpl[T](arr: seq[T]): T =
  result = arr[0]
  for i in 1..<arr.len:
    if arr[i] < result: result = arr[i]

# 泛型 sort: 升降序
proc sortImpl[T](arr: var seq[T]; desc: bool) =
  if desc:
    arr.sort(proc(a, b: T): int = system.cmp(b, a))
  else:
    arr.sort(system.cmp[T])

# 泛型 unique: 顺序去重
proc uniqueImpl[T](arr: seq[T]): seq[T] =
  var seen = initHashSet[T]()
  result = @[]
  for x in arr:
    if x notin seen:
      seen.incl(x)
      result.add(x)

# 泛型 count: 统计满足条件的元素个数
proc countImpl[T](arr: seq[T]; pred: proc(x: T): bool): int =
  for x in arr:
    if pred(x): inc result

# 泛型 reverse
proc reverseImpl[T](arr: seq[T]): seq[T] =
  result = newSeqOfCap[T](arr.len)
  for i in countdown(arr.len - 1, 0):
    result.add(arr[i])

# 泛型 take: 取前 n 个
proc takeImpl[T](arr: seq[T]; n: int): seq[T] =
  let k = min(n, arr.len)
  result = newSeqOfCap[T](k)
  for i in 0..<k: result.add(arr[i])

# 泛型 skip: 跳过前 n 个
proc skipImpl[T](arr: seq[T]; n: int): seq[T] =
  let start = min(n, arr.len)
  result = newSeqOfCap[T](arr.len - start)
  for i in start..<arr.len: result.add(arr[i])

# ============================================================
# CSV 解析工具
# ============================================================

proc parseInts(data: cstring): seq[int] =
  let s = $data
  if s.len == 0: return @[]
  let parts = s.split(',')
  for p in parts:
    if p.strip().len > 0:
      result.add(parseInt(p.strip()))

proc parseFloats(data: cstring): seq[float] =
  let s = $data
  if s.len == 0: return @[]
  let parts = s.split(',')
  for p in parts:
    if p.strip().len > 0:
      result.add(parseFloat(p.strip()))

# ============================================================
# C 边界 - int 系列（显式导出）
# ============================================================

proc seq_map_int*(data: cstring; multiplier: cint): cstring {.exportc: "seq_map_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseInts(data)
  let resultSeq = mapImpl[int](arr, proc(x: int): int = x * int(multiplier))
  result = resultSeq.mapIt($it).join(",").cstring

proc seq_filter_int*(data: cstring; threshold: cint): cstring {.exportc: "seq_filter_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseInts(data)
  let filtered = filterImpl[int](arr, proc(x: int): bool = x > int(threshold))
  result = filtered.mapIt($it).join(",").cstring

proc seq_reduce_sum_int*(data: cstring): cstring {.exportc: "seq_reduce_sum_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseInts(data)
  result = $sumImpl[int](arr)

proc seq_reduce_max_int*(data: cstring): cstring {.exportc: "seq_reduce_max_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseInts(data)
  if arr.len == 0:
    result = "0".cstring
  else:
    result = $maxImpl[int](arr)

proc seq_reduce_min_int*(data: cstring): cstring {.exportc: "seq_reduce_min_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseInts(data)
  if arr.len == 0:
    result = "0".cstring
  else:
    result = $minImpl[int](arr)

proc seq_sort_int*(data: cstring; desc: cint): cstring {.exportc: "seq_sort_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  var arr = parseInts(data)
  sortImpl[int](arr, int(desc) != 0)
  result = arr.mapIt($it).join(",").cstring

proc seq_unique_int*(data: cstring): cstring {.exportc: "seq_unique_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseInts(data)
  result = uniqueImpl[int](arr).mapIt($it).join(",").cstring

proc seq_count_int*(data: cstring; threshold: cint): cstring {.exportc: "seq_count_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseInts(data)
  let c = countImpl[int](arr, proc(x: int): bool = x > int(threshold))
  result = $c

proc seq_reverse_int*(data: cstring): cstring {.exportc: "seq_reverse_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseInts(data)
  result = reverseImpl[int](arr).mapIt($it).join(",").cstring

proc seq_take_int*(data: cstring; n: cint): cstring {.exportc: "seq_take_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseInts(data)
  result = takeImpl[int](arr, int(n)).mapIt($it).join(",").cstring

proc seq_skip_int*(data: cstring; n: cint): cstring {.exportc: "seq_skip_int", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseInts(data)
  result = skipImpl[int](arr, int(n)).mapIt($it).join(",").cstring

# ============================================================
# C 边界 - float 系列
# ============================================================

proc seq_map_float*(data: cstring; multiplier: cstring): cstring {.exportc: "seq_map_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseFloats(data)
  let mult = parseFloat($multiplier)
  let resultSeq = mapImpl[float](arr, proc(x: float): float = x * mult)
  result = resultSeq.mapIt(formatFloat(it, precision = -1)).join(",").cstring

proc seq_filter_float*(data: cstring; threshold: cstring): cstring {.exportc: "seq_filter_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseFloats(data)
  let thresh = parseFloat($threshold)
  let filtered = filterImpl[float](arr, proc(x: float): bool = x > thresh)
  result = filtered.mapIt(formatFloat(it, precision = -1)).join(",").cstring

proc seq_reduce_sum_float*(data: cstring): cstring {.exportc: "seq_reduce_sum_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseFloats(data)
  result = $sumImpl[float](arr)

proc seq_reduce_max_float*(data: cstring): cstring {.exportc: "seq_reduce_max_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseFloats(data)
  if arr.len == 0:
    result = "0.0".cstring
  else:
    result = $maxImpl[float](arr)

proc seq_reduce_min_float*(data: cstring): cstring {.exportc: "seq_reduce_min_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseFloats(data)
  if arr.len == 0:
    result = "0.0".cstring
  else:
    result = $minImpl[float](arr)

proc seq_sort_float*(data: cstring; desc: cint): cstring {.exportc: "seq_sort_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  var arr = parseFloats(data)
  sortImpl[float](arr, int(desc) != 0)
  result = arr.mapIt(formatFloat(it, precision = -1)).join(",").cstring

proc seq_unique_float*(data: cstring): cstring {.exportc: "seq_unique_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseFloats(data)
  result = uniqueImpl[float](arr).mapIt(formatFloat(it, precision = -1)).join(",").cstring

proc seq_count_float*(data: cstring; threshold: cstring): cstring {.exportc: "seq_count_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseFloats(data)
  let thresh = parseFloat($threshold)
  let c = countImpl[float](arr, proc(x: float): bool = x > thresh)
  result = $c

proc seq_reverse_float*(data: cstring): cstring {.exportc: "seq_reverse_float", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let arr = parseFloats(data)
  result = reverseImpl[float](arr).mapIt(formatFloat(it, precision = -1)).join(",").cstring

# ============================================================
# C 边界 - string 系列
# ============================================================

proc seq_map_string*(data: cstring; prefix: cstring; suffix: cstring): cstring {.exportc: "seq_map_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let s = $data
  if s.len == 0: return "".cstring
  let items = s.split(',')
  let pre = $prefix
  let suf = $suffix
  let resultSeq = mapImpl[string](items, proc(x: string): string = pre & x.strip() & suf)
  result = resultSeq.join(",").cstring

proc seq_filter_string*(data: cstring; minLen: cint): cstring {.exportc: "seq_filter_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let s = $data
  if s.len == 0: return "".cstring
  let items = s.split(',')
  let ml = int(minLen)
  let filtered = filterImpl[string](items, proc(x: string): bool = x.strip().len >= ml)
  result = filtered.join(",").cstring

proc seq_sort_string*(data: cstring; desc: cint): cstring {.exportc: "seq_sort_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  var items = ($data).split(',')
  sortImpl[string](items, int(desc) != 0)
  result = items.join(",").cstring

proc seq_unique_string*(data: cstring): cstring {.exportc: "seq_unique_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let s = $data
  if s.len == 0: return "".cstring
  let items = s.split(',')
  result = uniqueImpl[string](items).join(",").cstring

proc seq_count_string*(data: cstring; minLen: cint): cstring {.exportc: "seq_count_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let s = $data
  if s.len == 0: return "0".cstring
  let items = s.split(',')
  let ml = int(minLen)
  let c = countImpl[string](items, proc(x: string): bool = x.strip().len >= ml)
  result = $c

proc seq_reverse_string*(data: cstring): cstring {.exportc: "seq_reverse_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let s = $data
  if s.len == 0: return "".cstring
  result = reverseImpl[string](s.split(',')).join(",").cstring

proc seq_take_string*(data: cstring; n: cint): cstring {.exportc: "seq_take_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let s = $data
  if s.len == 0: return "".cstring
  result = takeImpl[string](s.split(','), int(n)).join(",").cstring

proc seq_skip_string*(data: cstring; n: cint): cstring {.exportc: "seq_skip_string", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let s = $data
  if s.len == 0: return "".cstring
  result = skipImpl[string](s.split(','), int(n)).join(",").cstring
