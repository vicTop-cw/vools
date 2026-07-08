import locks

type
  ItorState* = enum
    PENDING, ITERRING, PAUSED, STOPPED

  ItorData = object
    data: ptr UncheckedArray[byte]
    dataLen: cint
    offsets: ptr UncheckedArray[cint]
    offsetsLen: cint
    idx: cint
    lock: Lock
    paused: bool
    cond: Cond
    stopped: bool
    jumpOffsets: ptr UncheckedArray[cint]
    jumpLengths: ptr UncheckedArray[cint]
    jumpLen: cint
    jumpCap: cint

  ItorHandle = pointer


proc newItor(data: ptr UncheckedArray[byte]; dataLen: cint; 
             offsets: ptr UncheckedArray[cint]; offsetsLen: cint): ItorHandle {.exportc, dynlib.} =
  result = cast[ItorHandle](allocShared0(sizeof(ItorData)))
  var d = cast[ptr ItorData](result)
  
  d.data = cast[ptr UncheckedArray[byte]](allocShared(dataLen))
  for i in 0..<int(dataLen):
    d.data[i] = data[i]
  d.dataLen = dataLen
  
  d.offsets = cast[ptr UncheckedArray[cint]](allocShared(offsetsLen * sizeof(cint)))
  for i in 0..<int(offsetsLen):
    d.offsets[i] = offsets[i]
  d.offsetsLen = offsetsLen
  
  d.idx = 0
  d.paused = false
  d.stopped = false
  d.jumpLen = 0
  d.jumpCap = 8
  d.jumpOffsets = cast[ptr UncheckedArray[cint]](allocShared(8 * sizeof(cint)))
  d.jumpLengths = cast[ptr UncheckedArray[cint]](allocShared(8 * sizeof(cint)))
  
  initLock(d.lock)
  initCond(d.cond)


proc nextValue(itor: ItorHandle; offset: ptr cint; length: ptr cint): bool {.exportc, dynlib.} =
  var d = cast[ptr ItorData](itor)
  acquire(d.lock)
  
  while d.paused and not d.stopped:
    wait(d.cond, d.lock)
  
  if d.stopped:
    release(d.lock)
    result = false
    return
  
  if d.jumpLen > 0:
    offset[] = d.jumpOffsets[0]
    length[] = d.jumpLengths[0]
    for i in 1..<int(d.jumpLen):
      d.jumpOffsets[i-1] = d.jumpOffsets[i]
      d.jumpLengths[i-1] = d.jumpLengths[i]
    d.jumpLen -= 1
    release(d.lock)
    result = true
    return
  
  if d.idx >= d.offsetsLen:
    release(d.lock)
    result = false
    return
  
  offset[] = d.offsets[d.idx]
  if d.idx + 1 < d.offsetsLen:
    length[] = d.offsets[d.idx + 1] - d.offsets[d.idx]
  else:
    length[] = d.dataLen - d.offsets[d.idx]
  
  d.idx += 1
  release(d.lock)
  result = true


proc setPause(itor: ItorHandle) {.exportc, dynlib.} =
  var d = cast[ptr ItorData](itor)
  acquire(d.lock)
  d.paused = true
  release(d.lock)


proc resume(itor: ItorHandle) {.exportc, dynlib.} =
  var d = cast[ptr ItorData](itor)
  acquire(d.lock)
  d.paused = false
  signal(d.cond)
  release(d.lock)


proc stop(itor: ItorHandle) {.exportc, dynlib.} =
  var d = cast[ptr ItorData](itor)
  acquire(d.lock)
  d.stopped = true
  d.paused = false
  signal(d.cond)
  release(d.lock)


proc restart(itor: ItorHandle) {.exportc, dynlib.} =
  var d = cast[ptr ItorData](itor)
  acquire(d.lock)
  d.idx = 0
  d.stopped = false
  d.paused = false
  d.jumpLen = 0
  signal(d.cond)
  release(d.lock)


proc sendJump(itor: ItorHandle; offset: cint; length: cint) {.exportc, dynlib.} =
  var d = cast[ptr ItorData](itor)
  acquire(d.lock)
  if not d.stopped:
    if d.jumpLen >= d.jumpCap:
      d.jumpCap = d.jumpCap * 2
      var newOffsets = cast[ptr UncheckedArray[cint]](allocShared(d.jumpCap * sizeof(cint)))
      var newLengths = cast[ptr UncheckedArray[cint]](allocShared(d.jumpCap * sizeof(cint)))
      for i in 0..<int(d.jumpLen):
        newOffsets[i] = d.jumpOffsets[i]
        newLengths[i] = d.jumpLengths[i]
      deallocShared(d.jumpOffsets)
      deallocShared(d.jumpLengths)
      d.jumpOffsets = newOffsets
      d.jumpLengths = newLengths
    d.jumpOffsets[d.jumpLen] = offset
    d.jumpLengths[d.jumpLen] = length
    d.jumpLen += 1
  release(d.lock)


proc state(itor: ItorHandle): cint {.exportc, dynlib.} =
  var d = cast[ptr ItorData](itor)
  acquire(d.lock)
  if d.stopped:
    result = 3
  elif d.paused:
    result = 2
  elif d.idx >= d.offsetsLen and d.jumpLen == 0:
    result = 3
  elif d.idx > 0 or d.jumpLen > 0:
    result = 1
  else:
    result = 0
  release(d.lock)


proc freeItor(itor: ItorHandle) {.exportc, dynlib.} =
  var d = cast[ptr ItorData](itor)
  deallocShared(d.data)
  deallocShared(d.offsets)
  deallocShared(d.jumpOffsets)
  deallocShared(d.jumpLengths)
  deallocShared(itor)


when not defined(dll):
  when isMainModule:
    echo "Itor library for Python"
    echo "Compile with: nim c --app:lib --out:itor.dll --define:dll itor.nim"