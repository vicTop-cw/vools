## vools/bridge/nim/compress.nim - 压缩/解压 Nim 实现
## 独立的 gzip/zlib 压缩模块，用于 vools 桥接
## 循环导入防护：不 import vools

import streams
import zip

# ============================================================
# Helper: copy cstring to Nim seq[byte]
# ============================================================
proc cstrToBytes(data: cstring; len: cint): seq[byte] =
  let n = int(len)
  result = newSeq[byte](n)
  for i in 0..<n:
    result[i] = cast[ptr UncheckedArray[byte]](data)[i]

proc cstrToString(data: cstring; len: cint): string =
  let n = int(len)
  if n <= 0:
    result = ""
    return
  result = newString(n)
  copyMem(result[0].addr, unsafeAddr(data[0]), n)

# ============================================================
# zlib 压缩和解压 (使用 zip.moddeflate)
# ============================================================

proc zlib_compress*(data: cstring; len: cint; level: cint): cstring {.
    exportc: "zlib_compress",
    codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let bytes = cstrToBytes(data, len)
  if bytes.len == 0:
    result = ""
    return
  var outBytes: seq[byte]
  var ss = newStringStream()
  var ds = zip.deflate(ss, level = level)
  ds.write(bytes)
  ds.finish()
  outBytes = ss.data
  result = cast[cstring](outBytes[0].addr)

proc zlib_decompress*(data: cstring; len: cint): cstring {.
    exportc: "zlib_decompress",
    codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let bytes = cstrToBytes(data, len)
  if bytes.len == 0:
    result = ""
    return
  var outBytes: seq[byte]
  var ss = newStringStream($bytes)
  var ds = zip.inflate(ss)
  ds.finish()
  outBytes = ss.data
  result = cast[cstring](outBytes[0].addr)

# ============================================================
# gzip 压缩和解压 (使用 zip.gzipfiles)
# ============================================================

proc gzip_compress*(data: cstring; len: cint; level: cint): cstring {.
    exportc: "gzip_compress",
    codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let bytes = cstrToBytes(data, len)
  if bytes.len == 0:
    result = ""
    return
  var outBytes: seq[byte]
  var ss = newStringStream()
  var gz = zip.open(ss, fmWrite)
  zip.gzipWrite(gz, bytes)
  zip.gzipClose(gz)
  outBytes = ss.data
  result = cast[cstring](outBytes[0].addr)

proc gzip_decompress*(data: cstring; len: cint): cstring {.
    exportc: "gzip_decompress",
    codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let bytes = cstrToBytes(data, len)
  if bytes.len == 0:
    result = ""
    return
  var outBytes: seq[byte]
  var ss = newStringStream($bytes)
  var gz = zip.open(ss, fmRead)
  outBytes = zip.gzipRead(gz)
  zip.gzipClose(gz)
  result = cast[cstring](outBytes[0].addr)