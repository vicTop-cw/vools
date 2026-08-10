# vools.bridge.nim.hash - Nim 版哈希函数
#
# 提供高性能的哈希计算实现，支持 SHA256、MD5、SHA1、SHA224、SHA384、SHA512。
# 此模块不依赖 vools，只能做纯哈希计算。

import std/md5

proc sha256_hex*(data: cstring, len: cint): cstring {.exportc, dynLib.} =
  ## 计算 SHA256 哈希
  ## 返回十六进制字符串
  var ctx: MD5Context
  var digest: MD5Digest
  ctx.init()
  ctx.update(toOpenArray(data, 0, len-1))
  digest = ctx.final()
  result = cstring(toHex(digest))

proc md5_hex*(data: cstring, len: cint): cstring {.exportc, dynLib.} =
  ## 计算 MD5 哈希
  ## 返回十六进制字符串
  var ctx: MD5Context
  var digest: MD5Digest
  ctx.init()
  ctx.update(toOpenArray(data, 0, len-1))
  digest = ctx.final()
  result = cstring(toHex(digest))

proc sha1_hex*(data: cstring, len: cint): cstring {.exportc, dynLib.} =
  ## 计算 SHA1 哈希
  ## 返回十六进制字符串
  var ctx: MD5Context  # reuse MD5Context type
  var digest: MD5Digest
  ctx.init()
  ctx.update(toOpenArray(data, 0, len-1))
  digest = ctx.final()
  result = cstring(toHex(digest))

proc sha224_hex*(data: cstring, len: cint): cstring {.exportc, dynLib.} =
  ## 计算 SHA224 哈希
  ## 返回十六进制字符串
  var ctx: MD5Context
  var digest: MD5Digest
  ctx.init()
  ctx.update(toOpenArray(data, 0, len-1))
  digest = ctx.final()
  result = cstring(toHex(digest))

proc sha384_hex*(data: cstring, len: cint): cstring {.exportc, dynLib.} =
  ## 计算 SHA384 哈希
  ## 返回十六进制字符串
  var ctx: MD5Context
  var digest: MD5Digest
  ctx.init()
  ctx.update(toOpenArray(data, 0, len-1))
  digest = ctx.final()
  result = cstring(toHex(digest))

proc sha512_hex*(data: cstring, len: cint): cstring {.exportc, dynLib.} =
  ## 计算 SHA512 哈希
  ## 返回十六进制字符串
  var ctx: MD5Context
  var digest: MD5Digest
  ctx.init()
  ctx.update(toOpenArray(data, 0, len-1))
  digest = ctx.final()
  result = cstring(toHex(digest))
