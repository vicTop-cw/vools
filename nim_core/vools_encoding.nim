## vools_encoding.nim - Encoding/decoding for vools
## Compiled as DLL, called from Python via ctypes

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
# RLE Compression (simple fallback, not real zlib)
# ============================================================

proc rleCompress(data: openArray[byte]): seq[byte] =
  result = @[]
  var i = 0
  while i < data.len:
    let start = i
    var count = 1
    while i + 1 < data.len and data[i] == data[i + 1] and count < 255:
      inc i
      inc count
    if count >= 3:
      result.add(255)
      result.add(count.byte)
      result.add(data[start])
    else:
      result.add(0)
      result.add(count.byte)
      for j in start..i:
        result.add(data[j])
    inc i

proc rleDecompress(data: openArray[byte]): seq[byte] =
  result = @[]
  var i = 0
  while i < data.len:
    let marker = data[i]
    inc i
    if marker == 255:
      if i + 1 < data.len:
        let count = int(data[i])
        let value = data[i + 1]
        inc i, 2
        for j in 0..<count:
          result.add(value)
    elif marker == 0:
      if i < data.len:
        let count = int(data[i])
        inc i
        for j in 0..<count:
          if i < data.len:
            result.add(data[i])
            inc i

# ============================================================
# Base64
# ============================================================

proc base64_encode*(data: cstring; len: cint): cstring {.exportc: "base64_encode".} =
  let bytes = cstrToBytes(data, len)
  if bytes.len == 0:
    result = ""
    return
  var enc = encode(bytes)
  # Remove trailing padding '=' for Python compatibility
  while enc.len > 0 and enc[^1] == '=':
    setLen(enc, enc.len - 1)
  result = enc

proc base64_decode*(data: cstring; len: cint): cstring {.exportc: "base64_decode".} =
  let s = cstrToString(data, len)
  if s.len == 0:
    result = ""
    return
  result = decode(s)

proc base64_decode_len*(data: cstring; len: cint): cint {.exportc: "base64_decode_len".} =
  let s = cstrToString(data, len)
  if s.len == 0:
    result = 0
    return
  result = cint(decode(s).len)

# ============================================================
# Zlib (RLE + base64, for Python-side zlib use base64 output)
# ============================================================

proc zlib_compress*(data: cstring; len: cint; level: cint): cstring {.exportc: "zlib_compress".} =
  let bytes = cstrToBytes(data, len)
  if bytes.len == 0:
    result = ""
    return
  let compressed = rleCompress(bytes)
  var enc = encode(compressed)
  while enc.len > 0 and enc[^1] == '=':
    setLen(enc, enc.len - 1)
  result = enc

proc zlib_decompress*(data: cstring; len: cint): cstring {.exportc: "zlib_decompress".} =
  let s = cstrToString(data, len)
  if s.len == 0:
    result = ""
    return
  let decoded = decode(s)
  let bytes = cast[seq[byte]](decoded)
  let decompressed = rleDecompress(bytes)
  result = newString(decompressed.len)
  for i, b in decompressed:
    result[i] = chr(int(b))

proc zlib_decompress_len*(data: cstring; len: cint): cint {.exportc: "zlib_decompress_len".} =
  let s = cstrToString(data, len)
  if s.len == 0:
    result = 0
    return
  let decoded = decode(s)
  let bytes = cast[seq[byte]](decoded)
  let decompressed = rleDecompress(bytes)
  result = cint(decompressed.len)

# ============================================================
# GZip (same as zlib, RLE fallback)
# ============================================================

proc gzip_compress*(data: cstring; len: cint; level: cint): cstring {.exportc: "gzip_compress".} =
  let bytes = cstrToBytes(data, len)
  if bytes.len == 0:
    result = ""
    return
  let compressed = rleCompress(bytes)
  var enc = encode(compressed)
  while enc.len > 0 and enc[^1] == '=':
    setLen(enc, enc.len - 1)
  result = enc

proc gzip_decompress*(data: cstring; len: cint): cstring {.exportc: "gzip_decompress".} =
  let s = cstrToString(data, len)
  if s.len == 0:
    result = ""
    return
  let decoded = decode(s)
  let bytes = cast[seq[byte]](decoded)
  let decompressed = rleDecompress(bytes)
  result = newString(decompressed.len)
  for i, b in decompressed:
    result[i] = chr(int(b))

proc gzip_decompress_len*(data: cstring; len: cint): cint {.exportc: "gzip_decompress_len".} =
  let s = cstrToString(data, len)
  if s.len == 0:
    result = 0
    return
  let decoded = decode(s)
  let bytes = cast[seq[byte]](decoded)
  let decompressed = rleDecompress(bytes)
  result = cint(decompressed.len)
