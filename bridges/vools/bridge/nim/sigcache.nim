# vools.bridge.nim.sigcache - Nim 版签名哈希
#
# 提供高性能的函数签名哈希计算，用于缓存键生成。
# 此模块不依赖 vools，只能做纯哈希计算。
#
# 使用 FNV-1a 哈希算法，适合快速哈希计算场景。

proc hash_signature*(data: cstring, len: cint): cstring {.exportc, dynLib.} =
  ## 计算函数签名的哈希值
  ## 返回十六进制字符串（64位哈希）
  ##
  ## 算法：FNV-1a 64位
  ## 相比 DJB2 和 SDBM，FNV-1a 对短字符串分布更好

  const FNV_OFFSET = 0xcbf29ce484222325'u64
  const FNV_PRIME = 0x100000001b3'u64

  var hash_value = FNV_OFFSET
  let data_arr = toOpenArray(data, 0, len - 1)

  for i in 0..<len:
    hash_value = hash_value xor uint64(data_arr[i])
    hash_value = hash_value * FNV_PRIME

  # 转换为十六进制字符串（16个字符 = 64位）
  const HEX_CHARS = "0123456789abcdef"
  var result = newString(16)
  for j in 0..<16:
    let shift = (15 - j) * 4
    let nibble = (hash_value shr shift) and 0xFu
    result[j] = HEX_CHARS[nibble]

  return result

proc hash_signature_int*(data: cstring, len: cint): uint64 {.exportc, dynLib.} =
  ## 计算函数签名的哈希值（返回原始 64 位整数）
  ## 用于需要整数哈希值的场景

  const FNV_OFFSET = 0xcbf29ce484222325'u64
  const FNV_PRIME = 0x100000001b3'u64

  var hash_value = FNV_OFFSET
  let data_arr = toOpenArray(data, 0, len - 1)

  for i in 0..<len:
    hash_value = hash_value xor uint64(data_arr[i])
    hash_value = hash_value * FNV_PRIME

  return hash_value

proc build_signature_str*(
  func_name: cstring,
  func_name_len: cint,
  params: cstring,
  params_len: cint,
  ret_type: cstring,
  ret_type_len: cint
): cstring {.exportc, dynLib.} =
  ## 构建函数签名字符串
  ## 格式：func_name(params) -> ret_type
  ##
  ## 用于生成统一的签名字符串，然后进行哈希

  let fn = newString(func_name_len)
  for i in 0..<func_name_len:
    fn[i] = func_name[i]

  let ps = newString(params_len)
  for i in 0..<params_len:
    ps[i] = params[i]

  let rt = newString(ret_type_len)
  for i in 0..<ret_type_len:
    rt[i] = ret_type[i]

  result = fn & "(" & ps & ") -> " & rt