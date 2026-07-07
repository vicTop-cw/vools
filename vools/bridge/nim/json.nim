## vools_json.nim - JSON serialization for vools
## Compiled as DLL, called from Python via ctypes

import std/json

# ============================================================
# Helper: copy cstring to Nim string
# ============================================================

proc cstrToString(data: cstring; len: cint): string =
  let n = int(len)
  if n <= 0:
    result = ""
    return
  result = newString(n)
  copyMem(result[0].addr, unsafeAddr(data[0]), n)

proc stringToCstring(s: string): cstring =
  result = cstring(s)

# ============================================================
# JSON encode/decode
# ============================================================

proc json_encode*(data: cstring; len: cint): cstring {.exportc: "json_encode", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## Encode Python object (JSON string) to JSON bytes (as string)
  let inputStr = cstrToString(data, len)
  if inputStr.len == 0:
    result = ""
    return
  
  try:
    let node = parseJson(inputStr)
    let jsonStr = $node
    result = stringToCstring(jsonStr)
  except:
    result = data

proc json_decode*(data: cstring; len: cint): cstring {.exportc: "json_decode", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## Decode JSON string to Python object (JSON string)
  let inputStr = cstrToString(data, len)
  if inputStr.len == 0:
    result = ""
    return
  
  try:
    let node = parseJson(inputStr)
    let jsonStr = $node
    result = stringToCstring(jsonStr)
  except:
    result = data

# ============================================================
# Direct passthrough for already serialized data
# ============================================================

proc json_encode_bytes*(data: cstring; len: cint): cstring {.exportc: "json_encode_bytes", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## Passthrough for already serialized bytes
  let n = int(len)
  if n == 0:
    result = ""
    return
  result = data

proc json_decode_bytes*(data: cstring; len: cint): cstring {.exportc: "json_decode_bytes", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## Passthrough for serialized bytes to decode
  let n = int(len)
  if n == 0:
    result = ""
    return
  result = data