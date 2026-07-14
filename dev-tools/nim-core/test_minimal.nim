## test_minimal.nim - Minimal test
import strutils

proc test_add*(a, b: cint): cint {.exportc: "test_add".} =
  result = a + b

proc test_str*(s: cstring; len: cint): cstring {.exportc: "test_str".} =
  result = "hello"
