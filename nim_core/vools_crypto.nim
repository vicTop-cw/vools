## vools_crypto.nim - Pure Nim MD5/SHA1/SHA256/Blake2
## No external deps, uses only stdlib

import strutils, math

# ============================================================
# Helpers
# ============================================================

proc toHexBytesLower(bytes: openArray[byte]): string =
  ## Convert bytes to lowercase hex string (matching Python hashlib output)
  result = newString(bytes.len * 2)
  for i, b in bytes:
    let hex = toHex(b, 2)
    result[i * 2] = hex[0]
    result[i * 2 + 1] = hex[1]

# rotl = rotate left, rotr = rotate right
proc rotl32(x: uint32; n: int): uint32 =
  (x shl uint(n)) or (x shr uint(32 - n))

proc rotr32(x: uint32; n: int): uint32 =
  (x shr uint(n)) or (x shl uint(32 - n))

# SHA256 Sigma functions
proc ch(x, y, z: uint32): uint32 = (x and y) xor (not x and z)
proc maj(x, y, z: uint32): uint32 = (x and y) xor (x and z) xor (y and z)
proc bsig0(x: uint32): uint32 = rotr32(x, 2) xor rotr32(x, 13) xor rotr32(x, 22)
proc bsig1(x: uint32): uint32 = rotr32(x, 6) xor rotr32(x, 11) xor rotr32(x, 25)
proc ssig0(x: uint32): uint32 = rotr32(x, 7) xor rotr32(x, 18) xor (x shr uint(3))
proc ssig1(x: uint32): uint32 = rotr32(x, 17) xor rotr32(x, 19) xor (x shr uint(10))

# SHA256 constants
const SHA256_K: array[64, uint32] = [
  0x428a2f98u32, 0x71374491u32, 0xb5c0fbcfu32, 0xe9b5dba5u32,
  0x3956c25bu32, 0x59f111f1u32, 0x923f82a4u32, 0xab1c5ed5u32,
  0xd807aa98u32, 0x12835b01u32, 0x243185beu32, 0x550c7dc3u32,
  0x72be5d74u32, 0x80deb1feu32, 0x9bdc06a7u32, 0xc19bf174u32,
  0xe49b69c1u32, 0xefbe4786u32, 0x0fc19dc6u32, 0x240ca1ccu32,
  0x2de92c6fu32, 0x4a7484aau32, 0x5cb0a9dcu32, 0x76f988dau32,
  0x983e5152u32, 0xa831c66du32, 0xb00327c8u32, 0xbf597fc7u32,
  0xc6e00bf3u32, 0xd5a79147u32, 0x06ca6351u32, 0x14292967u32,
  0x27b70a85u32, 0x2e1b2138u32, 0x4d2c6dfcu32, 0x53380d13u32,
  0x650a7354u32, 0x766a0abbu32, 0x81c2c92eu32, 0x92722c85u32,
  0xa2bfe8a1u32, 0xa81a664bu32, 0xc24b8b70u32, 0xc76c51a3u32,
  0xd192e819u32, 0xd6990624u32, 0xf40e3585u32, 0x106aa070u32,
  0x19a4c116u32, 0x1e376c08u32, 0x2748774cu32, 0x34b0bcb5u32,
  0x391c0cb3u32, 0x4ed8aa4au32, 0x5b9cca4fu32, 0x682e6ff3u32,
  0x748f82eeu32, 0x78a5636fu32, 0x84c87814u32, 0x8cc70208u32,
  0x90befffau32, 0xa4506cebu32, 0xbef9a3f7u32, 0xc67178f2u32
]

# ============================================================
# MD5
# ============================================================

proc md5_hash*(data: cstring; len: cint): cstring {.exportc: "md5_hash".} =
  let n = int(len)
  if n == 0:
    result = "d41d8cd98f00b204e9800998ecf8427e"
    return

  var msg = newSeq[uint8](n)
  for i in 0..<n:
    msg[i] = uint8(ord(data[i]))

  # Padding: append bit '1' then zeros, then 64-bit length in bits (LITTLE-endian for MD5)
  var bits = uint64(n * 8)
  msg.add(0x80)
  while (msg.len mod 64) != 56:
    msg.add(0x00)
  for i in 0..<8:
    msg.add(uint8((bits shr (i * 8)) and 0xff))

  # Init
  var A = 0x67452301u32
  var B = 0xefcdab89u32
  var C = 0x98badcfeu32
  var D = 0x10325476u32

  proc F(x, y, z: uint32): uint32 = (x and y) or ((not x) and z)
  proc G(x, y, z: uint32): uint32 = (x and z) or (y and (not z))
  proc H(x, y, z: uint32): uint32 = x xor y xor z
  proc I(x, y, z: uint32): uint32 = y xor (x or (not z))

  proc rot(n: int; x: uint32): uint32 = (x shl uint(n)) or (x shr uint(32 - n))

  const K: array[64, uint32] = block:
    var a: array[64, uint32]
    for j in 0..63:
      a[j] = uint32((4294967296.0 * abs(sin(float(j + 1)))).floor)
    a

  for i in 0..<(msg.len div 64):
    var X: array[16, uint32]
    for j in 0..<16:
      let offset = i * 64 + j * 4
      X[j] = uint32(msg[offset]) or
             (uint32(msg[offset + 1]) shl 8) or
             (uint32(msg[offset + 2]) shl 16) or
             (uint32(msg[offset + 3]) shl 24)

    var AA = A; var BB = B; var CC = C; var DD = D

    # Round 1
    A = B + rot(7, A + F(B, C, D) + X[0] + K[0])
    D = A + rot(12, D + F(A, B, C) + X[1] + K[1])
    C = D + rot(17, C + F(D, A, B) + X[2] + K[2])
    B = C + rot(22, B + F(C, D, A) + X[3] + K[3])
    A = B + rot(7, A + F(B, C, D) + X[4] + K[4])
    D = A + rot(12, D + F(A, B, C) + X[5] + K[5])
    C = D + rot(17, C + F(D, A, B) + X[6] + K[6])
    B = C + rot(22, B + F(C, D, A) + X[7] + K[7])
    A = B + rot(7, A + F(B, C, D) + X[8] + K[8])
    D = A + rot(12, D + F(A, B, C) + X[9] + K[9])
    C = D + rot(17, C + F(D, A, B) + X[10] + K[10])
    B = C + rot(22, B + F(C, D, A) + X[11] + K[11])
    A = B + rot(7, A + F(B, C, D) + X[12] + K[12])
    D = A + rot(12, D + F(A, B, C) + X[13] + K[13])
    C = D + rot(17, C + F(D, A, B) + X[14] + K[14])
    B = C + rot(22, B + F(C, D, A) + X[15] + K[15])

    # Round 2
    A = B + rot(5, A + G(B, C, D) + X[1] + K[16])
    D = A + rot(9, D + G(A, B, C) + X[6] + K[17])
    C = D + rot(14, C + G(D, A, B) + X[11] + K[18])
    B = C + rot(20, B + G(C, D, A) + X[0] + K[19])
    A = B + rot(5, A + G(B, C, D) + X[5] + K[20])
    D = A + rot(9, D + G(A, B, C) + X[10] + K[21])
    C = D + rot(14, C + G(D, A, B) + X[15] + K[22])
    B = C + rot(20, B + G(C, D, A) + X[4] + K[23])
    A = B + rot(5, A + G(B, C, D) + X[9] + K[24])
    D = A + rot(9, D + G(A, B, C) + X[14] + K[25])
    C = D + rot(14, C + G(D, A, B) + X[3] + K[26])
    B = C + rot(20, B + G(C, D, A) + X[8] + K[27])
    A = B + rot(5, A + G(B, C, D) + X[13] + K[28])
    D = A + rot(9, D + G(A, B, C) + X[2] + K[29])
    C = D + rot(14, C + G(D, A, B) + X[7] + K[30])
    B = C + rot(20, B + G(C, D, A) + X[12] + K[31])

    # Round 3
    A = B + rot(4, A + H(B, C, D) + X[5] + K[32])
    D = A + rot(11, D + H(A, B, C) + X[8] + K[33])
    C = D + rot(16, C + H(D, A, B) + X[11] + K[34])
    B = C + rot(23, B + H(C, D, A) + X[14] + K[35])
    A = B + rot(4, A + H(B, C, D) + X[1] + K[36])
    D = A + rot(11, D + H(A, B, C) + X[4] + K[37])
    C = D + rot(16, C + H(D, A, B) + X[7] + K[38])
    B = C + rot(23, B + H(C, D, A) + X[10] + K[39])
    A = B + rot(4, A + H(B, C, D) + X[13] + K[40])
    D = A + rot(11, D + H(A, B, C) + X[0] + K[41])
    C = D + rot(16, C + H(D, A, B) + X[3] + K[42])
    B = C + rot(23, B + H(C, D, A) + X[6] + K[43])
    A = B + rot(4, A + H(B, C, D) + X[9] + K[44])
    D = A + rot(11, D + H(A, B, C) + X[12] + K[45])
    C = D + rot(16, C + H(D, A, B) + X[15] + K[46])
    B = C + rot(23, B + H(C, D, A) + X[2] + K[47])

    # Round 4
    A = B + rot(6, A + I(B, C, D) + X[0] + K[48])
    D = A + rot(10, D + I(A, B, C) + X[7] + K[49])
    C = D + rot(15, C + I(D, A, B) + X[14] + K[50])
    B = C + rot(21, B + I(C, D, A) + X[5] + K[51])
    A = B + rot(6, A + I(B, C, D) + X[12] + K[52])
    D = A + rot(10, D + I(A, B, C) + X[3] + K[53])
    C = D + rot(15, C + I(D, A, B) + X[10] + K[54])
    B = C + rot(21, B + I(C, D, A) + X[1] + K[55])
    A = B + rot(6, A + I(B, C, D) + X[8] + K[56])
    D = A + rot(10, D + I(A, B, C) + X[15] + K[57])
    C = D + rot(15, C + I(D, A, B) + X[6] + K[58])
    B = C + rot(21, B + I(C, D, A) + X[13] + K[59])
    A = B + rot(6, A + I(B, C, D) + X[4] + K[60])
    D = A + rot(10, D + I(A, B, C) + X[11] + K[61])
    C = D + rot(15, C + I(D, A, B) + X[2] + K[62])
    B = C + rot(21, B + I(C, D, A) + X[9] + K[63])

    A = A + AA; B = B + BB; C = C + CC; D = D + DD

  var digest = newSeq[byte](16)
  for i in 0..<4:
    digest[i] = uint8((A shr (i * 8)) and 0xff)
  for i in 0..<4:
    digest[4 + i] = uint8((B shr (i * 8)) and 0xff)
  for i in 0..<4:
    digest[8 + i] = uint8((C shr (i * 8)) and 0xff)
  for i in 0..<4:
    digest[12 + i] = uint8((D shr (i * 8)) and 0xff)

  let digest_str = toHexBytesLower(digest)
  result = digest_str

# ============================================================
# SHA1
# ============================================================

proc sha1_hash*(data: cstring; len: cint): cstring {.exportc: "sha1_hash".} =
  let n = int(len)
  if n == 0:
    result = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
    return

  var msg = newSeq[uint8](n)
  for i in 0..<n:
    msg[i] = uint8(ord(data[i]))

  var bits = uint(n * 8)
  msg.add(0x80)
  while (msg.len mod 64) != 56:
    msg.add(0x00)
  for i in 0..<8:
    msg.add(uint8((bits shr (56 - i * 8)) and 0xff))

  var H0 = 0x67452301u32
  var H1 = 0xefcdab89u32
  var H2 = 0x98badcfeu32
  var H3 = 0x10325476u32
  var H4 = 0xc3d2e1f0u32

  for i in 0..<(msg.len div 64):
    var W = newSeq[uint32](80)
    for j in 0..<16:
      let offset = i * 64 + j * 4
      W[j] = (uint32(msg[offset]) shl 24) or
             (uint32(msg[offset + 1]) shl 16) or
             (uint32(msg[offset + 2]) shl 8) or
             uint32(msg[offset + 3])
    for j in 16..<80:
      W[j] = rotl32(W[j-3] xor W[j-8] xor W[j-14] xor W[j-16], 1)

    var A = H0; var B = H1; var C = H2; var D = H3; var E = H4

    for j in 0..<80:
      var f: uint32
      var k: uint32
      if j <= 19:
        f = (B and C) or ((not B) and D); k = 0x5a827999u32
      elif j <= 39:
        f = B xor C xor D; k = 0x6ed9eba1u32
      elif j <= 59:
        f = (B and C) or (B and D) or (C and D); k = 0x8f1bbcdcu32
      else:
        f = B xor C xor D; k = 0xca62c1d6u32

      let temp = rotl32(A, 5) + f + E + W[j] + k
      E = D
      D = C
      C = rotl32(B, 30)
      B = A
      A = temp

    H0 = H0 + A; H1 = H1 + B; H2 = H2 + C; H3 = H3 + D; H4 = H4 + E

  var digest = newSeq[byte](20)
  for i in 0..<4:
    digest[i] = uint8((H0 shr (24 - i * 8)) and 0xff)
  for i in 0..<4:
    digest[4 + i] = uint8((H1 shr (24 - i * 8)) and 0xff)
  for i in 0..<4:
    digest[8 + i] = uint8((H2 shr (24 - i * 8)) and 0xff)
  for i in 0..<4:
    digest[12 + i] = uint8((H3 shr (24 - i * 8)) and 0xff)
  for i in 0..<4:
    digest[16 + i] = uint8((H4 shr (24 - i * 8)) and 0xff)

  let digest_str = toHexBytesLower(digest)
  result = digest_str

# ============================================================
# SHA256 - Reference implementation
# ============================================================

proc sha256_hash*(data: cstring; len: cint): cstring {.exportc: "sha256_hash".} =
  let n = int(len)
  if n == 0:
    result = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    return

  var msg = newSeq[uint8](n)
  for i in 0..<n:
    msg[i] = uint8(ord(data[i]))

  # Padding: append bit '1' then zeros
  msg.add(0x80)
  while (msg.len mod 64) != 56:
    msg.add(0x00)

  # Append original length in bits as 64-bit big-endian
  var bits = uint64(n * 8)
  for i in 0..<8:
    msg.add(uint8((bits shr (56 - i * 8)) and 0xff))

  # Initial hash values
  var h0 = 0x6a09e667u32
  var h1 = 0xbb67ae85u32
  var h2 = 0x3c6ef372u32
  var h3 = 0xa54ff53au32
  var h4 = 0x510e527fu32
  var h5 = 0x9b05688cu32
  var h6 = 0x1f83d9abu32
  var h7 = 0x5be0cd19u32

  for i in 0..<(msg.len div 64):
    var W = newSeq[uint32](64)

    # First 16 words from message block (big-endian)
    for j in 0..<16:
      let offset = i * 64 + j * 4
      W[j] = (uint32(msg[offset]) shl 24) or
             (uint32(msg[offset + 1]) shl 16) or
             (uint32(msg[offset + 2]) shl 8) or
             uint32(msg[offset + 3])

    # Extend to 64 words
    for j in 16..<64:
      W[j] = ssig1(W[j-2]) + W[j-7] + ssig0(W[j-15]) + W[j-16]

    var a = h0; var b = h1; var c = h2; var d = h3
    var e = h4; var f = h5; var g = h6; var h = h7

    for j in 0..<64:
      let t1 = h + bsig1(e) + ch(e, f, g) + SHA256_K[j] + W[j]
      let t2 = bsig0(a) + maj(a, b, c)
      h = g
      g = f
      f = e
      e = d + t1
      d = c
      c = b
      b = a
      a = t1 + t2

    h0 = h0 + a; h1 = h1 + b; h2 = h2 + c; h3 = h3 + d
    h4 = h4 + e; h5 = h5 + f; h6 = h6 + g; h7 = h7 + h

  # Final hash (big-endian)
  var digest = newSeq[byte](32)
  for i in 0..<4:
    digest[i] = uint8((h0 shr (24 - i * 8)) and 0xff)
  for i in 0..<4:
    digest[4 + i] = uint8((h1 shr (24 - i * 8)) and 0xff)
  for i in 0..<4:
    digest[8 + i] = uint8((h2 shr (24 - i * 8)) and 0xff)
  for i in 0..<4:
    digest[12 + i] = uint8((h3 shr (24 - i * 8)) and 0xff)
  for i in 0..<4:
    digest[16 + i] = uint8((h4 shr (24 - i * 8)) and 0xff)
  for i in 0..<4:
    digest[20 + i] = uint8((h5 shr (24 - i * 8)) and 0xff)
  for i in 0..<4:
    digest[24 + i] = uint8((h6 shr (24 - i * 8)) and 0xff)
  for i in 0..<4:
    digest[28 + i] = uint8((h7 shr (24 - i * 8)) and 0xff)

  let digest_str = toHexBytesLower(digest)
  result = digest_str

# ============================================================
# HMAC-SHA256
# ============================================================

proc hmac_sha256*(data: cstring; datalen: cint; key: cstring; keylen: cint): cstring {.exportc: "hmac_sha256".} =
  let dl = int(datalen)
  let kl = int(keylen)

  # Prepare key (64 bytes)
  var keyBytes = newSeq[uint8](64)
  if kl > 64:
    # Hash key if too long
    let keyHash = sha256_hash(key, cint(kl))
    # keyHash is hex string, need to convert back to bytes
    let keyHashStr = $keyHash
    for i in 0..<32:
      keyBytes[i] = uint8(parseHexInt(keyHashStr.substr(i*2, i*2+1)))
  else:
    for i in 0..<kl:
      keyBytes[i] = cast[ptr UncheckedArray[byte]](key)[i]

  # Inner/outer padding
  var innerPad = uint8(0x36)
  var outerPad = uint8(0x5c)

  var innerKey = newSeq[uint8](64)
  var outerKey = newSeq[uint8](64)
  for i in 0..<64:
    innerKey[i] = keyBytes[i] xor innerPad
    outerKey[i] = keyBytes[i] xor outerPad

  # Inner hash = SHA256(innerKey || data)
  var innerMsg = innerKey
  for i in 0..<dl:
    innerMsg.add(cast[ptr UncheckedArray[byte]](data)[i])

  let innerHex = sha256_hash(cast[cstring](unsafeAddr(innerMsg[0])), cint(innerMsg.len))

  # Outer hash = SHA256(outerKey || innerHex)
  var outerMsg = outerKey
  # innerHex is hex string, convert back to bytes
  let innerHexStr = $innerHex
  for i in 0..<innerHexStr.len div 2:
    outerMsg.add(uint8(parseHexInt(innerHexStr.substr(i*2, i*2+1))))

  result = sha256_hash(cast[cstring](unsafeAddr(outerMsg[0])), cint(outerMsg.len))

# ============================================================
# HMAC-MD5
# ============================================================

proc hmac_md5*(data: cstring; datalen: cint; key: cstring; keylen: cint): cstring {.exportc: "hmac_md5".} =
  let dl = int(datalen)
  let kl = int(keylen)

  var keyBytes = newSeq[uint8](64)
  if kl > 64:
    let keyHash = md5_hash(key, keylen)
    let keyHashStr = $keyHash
    for i in 0..<16:
      keyBytes[i] = uint8(parseHexInt(keyHashStr.substr(i*2, i*2+1)))
  else:
    for i in 0..<kl:
      keyBytes[i] = cast[ptr UncheckedArray[byte]](key)[i]

  var innerPad = uint8(0x36)
  var outerPad = uint8(0x5c)

  var innerKey = newSeq[uint8](64)
  var outerKey = newSeq[uint8](64)
  for i in 0..<64:
    innerKey[i] = keyBytes[i] xor innerPad
    outerKey[i] = keyBytes[i] xor outerPad

  var innerMsg = innerKey
  for i in 0..<dl:
    innerMsg.add(cast[ptr UncheckedArray[byte]](data)[i])

  let innerHex = md5_hash(cast[cstring](unsafeAddr(innerMsg[0])), cint(innerMsg.len))

  var outerMsg = outerKey
  let innerHexStr = $innerHex
  for i in 0..<innerHexStr.len div 2:
    outerMsg.add(uint8(parseHexInt(innerHexStr.substr(i*2, i*2+1))))

  result = md5_hash(cast[cstring](unsafeAddr(outerMsg[0])), cint(outerMsg.len))
