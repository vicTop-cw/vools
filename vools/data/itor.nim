import locks

type
  ItorState* = enum
    PENDING, ITERRING, PAUSED, STOPPED

  ItorData = object
    lock: Lock
    paused: bool
    cond: Cond
    stopped: bool

  ItorHandle = pointer


proc newItor(): ItorHandle {.exportc, dynlib.} =
  result = cast[ItorHandle](allocShared0(sizeof(ItorData)))
  var d = cast[ptr ItorData](result)
  d.paused = false
  d.stopped = false
  initLock(d.lock)
  initCond(d.cond)


proc waitForData(itor: ItorHandle): bool {.exportc, dynlib.} =
  var d = cast[ptr ItorData](itor)
  acquire(d.lock)
  while d.paused and not d.stopped:
    wait(d.cond, d.lock)
  result = not d.stopped
  release(d.lock)


proc signalData(itor: ItorHandle) {.exportc, dynlib.} =
  var d = cast[ptr ItorData](itor)
  acquire(d.lock)
  signal(d.cond)
  release(d.lock)


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
  d.stopped = false
  d.paused = false
  signal(d.cond)
  release(d.lock)


proc state(itor: ItorHandle): cint {.exportc, dynlib.} =
  var d = cast[ptr ItorData](itor)
  acquire(d.lock)
  if d.stopped:
    result = 3
  elif d.paused:
    result = 2
  elif d.stopped == false:
    result = 1
  else:
    result = 0
  release(d.lock)


proc freeItor(itor: ItorHandle) {.exportc, dynlib.} =
  deallocShared(itor)


when not defined(dll):
  when isMainModule:
    echo "Itor library for Python"
    echo "Compile with: nim c --app:lib --out:itor.dll --define:dll itor.nim"