## vools_datetime.nim - High-performance date operations
## 提供纯 Nim 实现的日期计算：范围生成、差值计算、闰年判断等
import strutils, times, sequtils

# ============================================================
# 闰年与月份天数
# ============================================================

proc isLeapYear*(year: int): cint {.exportc: "dt_is_leap_year", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 是否闰年 - 返回 0/1（ctypes bool 兼容）
  if (year mod 4 == 0 and year mod 100 != 0) or (year mod 400 == 0): 1.cint else: 0.cint

proc daysInMonth*(year: int; month: int): int {.exportc: "dt_days_in_month", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 指定年月的天数
  case month
  of 1, 3, 5, 7, 8, 10, 12: 31
  of 4, 6, 9, 11: 30
  of 2:
    if isLeapYear(year) != 0: 29 else: 28
  else: 0

proc daysInYear*(year: int): int {.exportc: "dt_days_in_year", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 一年的天数
  if isLeapYear(year) != 0: 366 else: 365

# ============================================================
# 时间戳与日期转换
# ============================================================

proc timestampToYMD*(ts: int64): cstring {.exportc: "dt_ts_to_ymd", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 时间戳(秒) -> "YYYY-MM-DD" (UTC)
  let dt = fromUnix(ts.int).utc
  result = ($dt.year & "-" & intToStr(dt.month.ord, 2) & "-" & intToStr(dt.monthday, 2)).cstring

proc timestampToYMDHMS*(ts: int64): cstring {.exportc: "dt_ts_to_ymdhms", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 时间戳(秒) -> "YYYY-MM-DD HH:MM:SS" (UTC)
  let dt = fromUnix(ts.int).utc
  result = ($dt.year & "-" & intToStr(dt.month.ord, 2) & "-" & intToStr(dt.monthday, 2) & " " &
            intToStr(dt.hour, 2) & ":" & intToStr(dt.minute, 2) & ":" & intToStr(dt.second, 2)).cstring

proc ymdToTimestamp*(year: int; month: int; day: int): int64 {.exportc: "dt_ymd_to_ts", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## "YYYY-MM-DD" -> 时间戳(秒) (UTC)
  let dt = dateTime(year, month.Month, day.MonthdayRange, 0, 0, 0, 0, utc())
  result = dt.toTime.toUnix

# ============================================================
# 日期差值
# ============================================================

proc daysBetween*(y1: int; m1: int; d1: int; y2: int; m2: int; d2: int): int {.exportc: "dt_days_between", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 两个日期相差天数 (y2,m2,d2) - (y1,m1,d1)
  let t1 = dateTime(y1, m1.Month, d1.MonthdayRange, 0, 0, 0, 0, utc()).toTime.toUnix
  let t2 = dateTime(y2, m2.Month, d2.MonthdayRange, 0, 0, 0, 0, utc()).toTime.toUnix
  result = int((t2 - t1) div 86400)

# ============================================================
# 周计算
# ============================================================

proc dayOfWeek*(year: int; month: int; day: int): int {.exportc: "dt_day_of_week", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 返回星期几 (1=周一, 7=周日)
  let dt = dateTime(year, month.Month, day.MonthdayRange, 0, 0, 0, 0, utc())
  result = dt.weekday.ord + 1  # Nim: Monday=0, ... Sunday=6 -> we want 1..7

proc weekOfYear*(year: int; month: int; day: int): int {.exportc: "dt_week_of_year", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 返回 ISO 周数（用元旦所在周推算）
  let dt = dateTime(year, month.Month, day.MonthdayRange, 0, 0, 0, 0, utc())
  # 1月4日总是在 ISO 周数的第一周
  let jan4 = dateTime(year, 1.Month, 4.MonthdayRange, 0, 0, 0, 0, utc())
  let jan4Weekday = jan4.weekday.ord + 1  # 1=Mon..7=Sun
  let dayOfYear = getDayOfYear(dt.monthday, dt.month, dt.year)
  # 当前日期所在周的周一
  let dayWeekday = dt.weekday.ord + 1
  let weekStart = dayOfYear - (dayWeekday - 1)
  let weekNum = ((weekStart - 1) / 7).int + 1
  # 处理跨年
  if dayOfYear <= 8 - jan4Weekday:
    return 52  # 简化：上一年末
  if weekNum > 52 and dayOfYear > 365 - 3:
    return 1
  result = weekNum

# ============================================================
# 范围生成（性能热点）
# ============================================================

proc rangeDays*(startY: int; startM: int; startD: int; count: int): cstring {.exportc: "dt_range_days", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 生成从 startY-M-D 开始的 count 个日期，CSV 格式 "YYYY-MM-DD,YYYY-MM-DD,..."
  let s = dateTime(startY, startM.Month, startD.MonthdayRange, 0, 0, 0, 0, utc()).toTime
  var parts = newSeqOfCap[string](count)
  for i in 0..<count:
    let t = s + initDuration(days = i)
    let dt = t.utc
    parts.add($dt.year & "-" & intToStr(dt.month.ord, 2) & "-" & intToStr(dt.monthday, 2))
  result = parts.join(",").cstring

proc rangeDaysBetween*(y1: int; m1: int; d1: int; y2: int; m2: int; d2: int): cstring {.exportc: "dt_range_days_between", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 生成 [y1-m1-d1, y2-m2-d2] 闭区间所有日期
  let total = daysBetween(y1, m1, d1, y2, m2, d2) + 1
  if total <= 0:
    result = "".cstring
    return
  let s = dateTime(y1, m1.Month, d1.MonthdayRange, 0, 0, 0, 0, utc()).toTime
  var parts = newSeqOfCap[string](total)
  for i in 0..<total:
    let t = s + initDuration(days = i)
    let dt = t.utc
    parts.add($dt.year & "-" & intToStr(dt.month.ord, 2) & "-" & intToStr(dt.monthday, 2))
  result = parts.join(",").cstring

proc rangeMonths*(startY: int; startM: int; count: int): cstring {.exportc: "dt_range_months", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 生成从 startY-startM 开始的 count 个月，CSV 格式 "YYYY-MM,..."
  var parts = newSeqOfCap[string](count)
  var y = startY
  var m = startM
  for i in 0..<count:
    parts.add($y & "-" & intToStr(m, 2))
    inc m
    if m > 12:
      m = 1
      inc y
  result = parts.join(",").cstring

# ============================================================
# 解析与校验
# ============================================================

proc validateDate*(year: int; month: int; day: int): cint {.exportc: "dt_validate_date", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 校验日期是否合法 - 返回 0/1
  if year < 1 or year > 9999: return 0
  if month < 1 or month > 12: return 0
  if day < 1: return 0
  if day > daysInMonth(year, month): return 0
  return 1

# ============================================================
# 偏移
# ============================================================

proc addDays*(year: int; month: int; day: int; delta: int): cstring {.exportc: "dt_add_days", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 日期加 delta 天，返回 "YYYY-MM-DD"
  let s = dateTime(year, month.Month, day.MonthdayRange, 0, 0, 0, 0, utc()).toTime
  let dt = (s + initDuration(days = delta)).utc
  result = ($dt.year & "-" & intToStr(dt.month.ord, 2) & "-" & intToStr(dt.monthday, 2)).cstring

proc addMonths*(year: int; month: int; day: int; delta: int): cstring {.exportc: "dt_add_months", codegenDecl: "__attribute__((visibility(\"default\"))) $# $#$#".} =
  ## 日期加 delta 月，处理溢出
  var m = month + delta
  var y = year
  while m > 12:
    m -= 12
    inc y
  while m < 1:
    m += 12
    dec y
  let maxDay = daysInMonth(y, m)
  let d = min(day, maxDay)
  result = ($y & "-" & intToStr(m, 2) & "-" & intToStr(d, 2)).cstring
