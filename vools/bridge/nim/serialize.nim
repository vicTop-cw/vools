## vools_serialize.nim - msgpack serialization for vools
## Compiled as DLL, called from Python via ctypes

import std/[json, base64, streams]

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

proc stringToCstring(s: string): cstring =
  result = cstring(s)

# ============================================================
# Pickle-like serialization using JSON as intermediate format
# Note: This is NOT compatible with Python pickle protocol.
# For vools, we use JSON encoding as a "pickle-like" serialization.
# ============================================================

proc pickle_encode*(data: cstring; len: cint): cstring {.exportc: "pickle_encode", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## Serialize data (JSON string) to a compact representation
  let inputStr = cstrToString(data, len)
  if inputStr.len == 0:
    result = ""
    return
  
  try:
    let node = parseJson(inputStr)
    # Serialize to a compact JSON string using $ operator
    let jsonStr = $node
    result = stringToCstring(jsonStr)
  except:
    # On error, return the original string encoded
    result = data

proc pickle_decode*(data: cstring; len: cint): cstring {.exportc: "pickle_decode", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## Deserialize data back to JSON string
  let inputStr = cstrToString(data, len)
  if inputStr.len == 0:
    result = ""
    return
  
  try:
    let node = parseJson(inputStr)
    # Return formatted JSON for reconstruction using pretty
    let prettyStr = node.pretty()
    result = stringToCstring(prettyStr)
  except:
    # On error, return the original string
    result = data

# ============================================================
# msgpack-like serialization (using base64 encoded JSON)
# ============================================================

proc msgpack_encode*(data: cstring; len: cint): cstring {.exportc: "msgpack_encode", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## Encode JSON data to msgpack-like bytes (base64 encoded)
  let inputStr = cstrToString(data, len)
  if inputStr.len == 0:
    result = ""
    return
  
  try:
    let node = parseJson(inputStr)
    let jsonStr = $node
    var jsonBytes = newSeq[byte](jsonStr.len)
    for i in 0..<jsonStr.len:
      jsonBytes[i] = byte(ord(jsonStr[i]))
    result = encode(jsonBytes)
  except:
    result = data

proc msgpack_decode*(data: cstring; len: cint): cstring {.exportc: "msgpack_decode", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## Decode msgpack-like bytes back to JSON string
  let inputStr = cstrToString(data, len)
  if inputStr.len == 0:
    result = ""
    return
  
  try:
    let decoded = decode(inputStr)
    var jsonStr = newString(decoded.len)
    for i in 0..<decoded.len:
      jsonStr[i] = chr(int(decoded[i]))
    let node = parseJson(jsonStr)
    let prettyStr = node.pretty()
    result = stringToCstring(prettyStr)
  except:
    result = data

# ============================================================
# Direct bytes passthrough (for binary data)
# ============================================================

proc pickle_encode_bytes*(data: cstring; len: cint): cstring {.exportc: "pickle_encode_bytes", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## Passthrough for already serialized bytes
  let n = int(len)
  if n == 0:
    result = ""
    return
  result = data

proc pickle_decode_bytes*(data: cstring; len: cint): cstring {.exportc: "pickle_decode_bytes", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## Passthrough for serialized bytes to decode
  let n = int(len)
  if n == 0:
    result = ""
    return
  result = data
