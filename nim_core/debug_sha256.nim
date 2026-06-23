## vools_crypto debug - SHA256 padding verification
## Run with: nim c -r --passL:-Wl,--export-all debug_sha256.nim

import strutils

# Verify padding for 'a' (1 byte)
proc test_padding() =
  let msg = @[0x61'u8]  # 'a'
  let n = msg.len
  var bits = uint(n * 8)

  var padded = msg
  padded.add(0x80)
  while (padded.len mod 64) != 56:
    padded.add(0)
  for i in 0..<8:
    padded.add(uint8((bits shr uint(i * 8)) and 0xff))

  echo "Original msg len: ", n
  echo "Bits: ", bits
  echo "Padded len: ", padded.len
  echo "Expected len: 64"
  echo "Padding starts at: ", n + 1
  echo "Length field at: ", padded.len - 8, " to ", padded.len - 1

  # Print first 16 bytes
  echo "First 16 bytes (hex):"
  for i in 0..<16:
    stdout.write(toHex(padded[i], 2), " ")
  echo ""

  # Print last 8 bytes (length)
  echo "Last 8 bytes (length in little-endian):"
  for i in padded.len-8..<padded.len:
    stdout.write(toHex(padded[i], 2), " ")
  echo ""

  # Expected: length = 0x0000000000000008 (8 bits in big-endian)
  # But code does little-endian: 0x0800000000000000
  echo "Expected big-endian length bytes:"
  echo "00 00 00 00 00 00 00 08"

test_padding()

# Now trace SHA256 step by step for 'a'
proc trace_sha256*() =
  # Message after padding
  var msg = newSeq[uint8](64)
  msg[0] = 0x61
  msg[1] = 0x80
  # rest are 0 except last 8 bytes
  msg[56] = 0x08

  echo "Initial hash values:"
  var h0 = 0x6a09e667'u32
  var h1 = 0xbb67ae85'u32
  var h2 = 0x3c6ef372'u32
  var h3 = 0xa54ff53a'u32
  var h4 = 0x510e527f'u32
  var h5 = 0x9b05688c'u32
  var h6 = 0x1f83d9ab'u32
  var h7 = 0x5be0cd19'u32

  echo "h0 = 0x", toHex(h0)
  echo "h1 = 0x", toHex(h1)
  echo "h2 = 0x", toHex(h2)
  echo "h3 = 0x", toHex(h3)
  echo "h4 = 0x", toHex(h4)
  echo "h5 = 0x", toHex(h5)
  echo "h6 = 0x", toHex(h6)
  echo "h7 = 0x", toHex(h7)

  # W[0..15] from message
  var W = newSeq[uint32](64)
  for j in 0..<16:
    W[j] = uint32(msg[j*4]) shl 24 or
           uint32(msg[j*4 + 1]) shl 16 or
           uint32(msg[j*4 + 2]) shl 8 or
           uint32(msg[j*4 + 3])
    echo "W[", j, "] = 0x", toHex(W[j])

  # Check W[0]
  echo ""
  echo "W[0] calculation:"
  echo "  msg[0] = 0x", toHex(msg[0]), " = ", msg[0]
  echo "  msg[1] = 0x", toHex(msg[1]), " = ", msg[1]
  echo "  msg[2] = 0x", toHex(msg[2]), " = ", msg[2]
  echo "  msg[3] = 0x", toHex(msg[3]), " = ", msg[3]
  echo "  W[0] = msg[0]<<24 | msg[1]<<16 | msg[2]<<8 | msg[3]"
  echo "       = 0x", toHex(msg[0]), "<<24 | 0x", toHex(msg[1]), "<<16 | 0x", toHex(msg[2]), "<<8 | 0x", toHex(msg[3])
  echo "       = 0x", toHex(W[0])

trace_sha256()
