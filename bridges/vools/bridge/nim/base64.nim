## vools/bridge/nim/base64.nim - Base64 Nim 实现
## 独立的 Base64 编解码模块，用于 vools 桥接

import std/base64

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
# Base64 编码和解码
# ============================================================

proc base64_encode*(data: cstring; len: cint): cstring {.exportc: "base64_encode", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let bytes = cstrToBytes(data, len)
  if bytes.len == 0:
    result = ""
    return
  var enc = encode(bytes)
  # Remove trailing padding '=' for Python compatibility
  while enc.len > 0 and enc[^1] == '=':
    setLen(enc, enc.len - 1)
  result = enc

proc base64_decode*(data: cstring; len: cint): cstring {.exportc: "base64_decode", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let s = cstrToString(data, len)
  if s.len == 0:
    result = ""
    return
  result = decode(s)

proc base64_decode_len*(data: cstring; len: cint): cint {.exportc: "base64_decode_len", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  let s = cstrToString(data, len)
  if s.len == 0:
    result = 0
    return
  result = cint(decode(s).len)
