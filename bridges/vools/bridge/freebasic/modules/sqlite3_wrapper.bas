'' =====================================================================
'' sqlite3_wrapper.bas
'' ---------------------------------------------------------------------
'' FreeBASIC 封装模块：对 sqlite3.dll 的常用 API 进行简化和统一，
''               供 vools.bridge.freebasic 装饰器直接使用。
''
'' 使用方法（Python 侧）：
''   from vools.bridge import freebasic
''   from vools.bridge.freebasic import compile_and_run
''
''   result = compile_and_run(
''       'Dim As ZString Ptr v = fb_sqlite3_libversion()\nReturn v',
''       func_name='test_sqlite',
''       ret_type='str',
''       extra_includes=[freebasic.get_fb_module('sqlite3_wrapper')],
''       inc_paths=freebasic.get_fb_inc_paths('sqlite3_wrapper'),
''   )
''
'' 头文件依赖（inc_path 在编译时由装饰器自动注入）：
''   - sqlite3.bi   （包含完整 C API）
''   - sqlite3ext.bi
'' =====================================================================

#pragma once

'' --------------------------- 头文件包含 ---------------------------
'' 这些 include 由 vools.bridge.freebasic.modules.get_inc_paths 提供的
'' inc_paths 自动搜索到，此处直接 #include 即可
#include once "sqlite3.bi"

'' --------------------------- 版本信息 ---------------------------

'' 函数：fb_sqlite3_libversion
'' 说明：返回 SQLite3 库的版本字符串
'' 返回：ZString Ptr（C 风格字符串指针）
Function fb_sqlite3_libversion() As ZString Ptr Export
    Return cptr(ZString Ptr, sqlite3_libversion())
End Function

'' 函数：fb_sqlite3_libversion_number
'' 说明：返回 SQLite3 库的版本号（如 3026000 = 3.26.0）
Function fb_sqlite3_libversion_number() As Long Export
    Return sqlite3_libversion_number()
End Function

'' 函数：fb_sqlite3_sourceid
'' 说明：返回 SQLite3 源码 ID 字符串
Function fb_sqlite3_sourceid() As ZString Ptr Export
    Return cptr(ZString Ptr, sqlite3_sourceid())
End Function

'' --------------------------- 数据库连接管理 ---------------------------

'' 结构：FB_SQLITE3_DB
'' 说明：与 sqlite3* 句柄对应的简单封装，用于在 FB 代码中跟踪连接
Type FB_SQLITE3_DB
    handle As Any Ptr        '' 对应 sqlite3*
    path   As String         '' 数据库文件路径
    ok     As Long           '' 0 = 成功，非 0 = 错误码
    errmsg As String         '' 最近一次错误信息
End Type

'' 函数：fb_sqlite3_open
'' 说明：打开一个数据库（path = ":memory:" 表示内存数据库）
'' 参数：path - 文件路径或 ":memory:"
'' 返回：FB_SQLITE3_DB 结构（handle = NULL 表示失败）
Function fb_sqlite3_open(ByVal path As ZString Ptr) As FB_SQLITE3_DB Export
    Dim db As FB_SQLITE3_DB
    db.handle = 0
    db.path   = *path
    db.ok     = sqlite3_open(path, @db.handle)
    If db.ok <> SQLITE_OK Then
        If db.handle <> 0 Then
            db.errmsg = *sqlite3_errmsg(db.handle)
        Else
            db.errmsg = "sqlite3_open failed (no memory)"
        End If
    End If
    Return db
End Function

'' 函数：fb_sqlite3_close
'' 说明：关闭一个由 fb_sqlite3_open 打开的数据库
Function fb_sqlite3_close(ByVal db As FB_SQLITE3_DB Ptr) As Long Export
    If db = 0 Then Return SQLITE_MISUSE
    If db->handle = 0 Then Return SQLITE_OK
    Dim rc As Long = sqlite3_close(db->handle)
    db->handle = 0
    Return rc
End Function

'' --------------------------- SQL 执行 ---------------------------

'' 函数：fb_sqlite3_exec
'' 说明：执行一条 SQL 语句（适合 CREATE/INSERT/UPDATE/DELETE 等无结果集语句）
'' 参数：
''   db     - 数据库连接
''   sql    - SQL 语句
'' 返回：SQLite3 错误码（SQLITE_OK = 0 表示成功）
Function fb_sqlite3_exec(ByVal db As FB_SQLITE3_DB Ptr, ByVal sql As ZString Ptr) As Long Export
    If db = 0 OrElse db->handle = 0 Then Return SQLITE_MISUSE
    Dim rc As Long = sqlite3_exec(db->handle, sql, 0, 0, 0)
    db->errmsg = *sqlite3_errmsg(db->handle)
    db->ok     = rc
    Return rc
End Function

'' 函数：fb_sqlite3_errmsg
'' 说明：返回最近一次错误的描述信息
Function fb_sqlite3_errmsg(ByVal db As FB_SQLITE3_DB Ptr) As ZString Ptr Export
    If db = 0 OrElse db->handle = 0 Then
        Return @"invalid db handle"
    End If
    Return cptr(ZString Ptr, sqlite3_errmsg(db->handle))
End Function

'' --------------------------- 预编译语句（Prepared Statement）---------------------------

'' 结构：FB_SQLITE3_STMT
'' 说明：与 sqlite3_stmt* 对应的简单封装
Type FB_SQLITE3_STMT
    handle As Any Ptr        '' 对应 sqlite3_stmt*
    db     As FB_SQLITE3_DB Ptr
End Type

'' 函数：fb_sqlite3_prepare_v2
'' 说明：准备一条 SQL 语句（支持绑定参数）
'' 参数：
''   db        - 数据库连接
''   sql       - SQL 语句
''   sql_len   - SQL 长度（-1 表示自动计算）
'' 返回：FB_SQLITE3_STMT 结构
Function fb_sqlite3_prepare_v2(ByVal db As FB_SQLITE3_DB Ptr, _
                              ByVal sql As ZString Ptr, _
                              ByVal sql_len As Long) As FB_SQLITE3_STMT Export
    Dim stmt As FB_SQLITE3_STMT
    stmt.db = db
    If db = 0 OrElse db->handle = 0 Then
        stmt.handle = 0
        Return stmt
    End If
    Dim tail As ZString Ptr = 0
    Dim rc As Long = sqlite3_prepare_v2(db->handle, sql, sql_len, @stmt.handle, @tail)
    If rc <> SQLITE_OK Then
        db->errmsg = *sqlite3_errmsg(db->handle)
    End If
    Return stmt
End Function

'' 函数：fb_sqlite3_step
'' 说明：执行预编译语句（返回 SQLITE_ROW 表示有一行结果，SQLITE_DONE 表示完成）
Function fb_sqlite3_step(ByVal stmt As FB_SQLITE3_STMT Ptr) As Long Export
    If stmt = 0 OrElse stmt->handle = 0 Then Return SQLITE_MISUSE
    Return sqlite3_step(stmt->handle)
End Function

'' 函数：fb_sqlite3_finalize
'' 说明：释放预编译语句
Function fb_sqlite3_finalize(ByVal stmt As FB_SQLITE3_STMT Ptr) As Long Export
    If stmt = 0 OrElse stmt->handle = 0 Then Return SQLITE_OK
    Dim rc As Long = sqlite3_finalize(stmt->handle)
    stmt->handle = 0
    Return rc
End Function

'' 函数：fb_sqlite3_column_int
'' 说明：获取当前行的整数字段值
Function fb_sqlite3_column_int(ByVal stmt As FB_SQLITE3_STMT Ptr, ByVal col As Long) As Long Export
    If stmt = 0 OrElse stmt->handle = 0 Then Return 0
    Return sqlite3_column_int(stmt->handle, col)
End Function

'' 函数：fb_sqlite3_column_int64
'' 说明：获取当前行的 64 位整数字段值
Function fb_sqlite3_column_int64(ByVal stmt As FB_SQLITE3_STMT Ptr, ByVal col As Long) As LongInt Export
    If stmt = 0 OrElse stmt->handle = 0 Then Return 0
    Return sqlite3_column_int64(stmt->handle, col)
End Function

'' 函数：fb_sqlite3_column_double
'' 说明：获取当前行的双精度浮点字段值
Function fb_sqlite3_column_double(ByVal stmt As FB_SQLITE3_STMT Ptr, ByVal col As Long) As Double Export
    If stmt = 0 OrElse stmt->handle = 0 Then Return 0.0
    Return sqlite3_column_double(stmt->handle, col)
End Function

'' 函数：fb_sqlite3_column_text
'' 说明：获取当前行的文本字段值
Function fb_sqlite3_column_text(ByVal stmt As FB_SQLITE3_STMT Ptr, ByVal col As Long) As ZString Ptr Export
    If stmt = 0 OrElse stmt->handle = 0 Then Return @""
    Return cptr(ZString Ptr, sqlite3_column_text(stmt->handle, col))
End Function

'' 函数：fb_sqlite3_column_type
'' 说明：返回字段类型（SQLITE_INTEGER/TEXT/FLOAT/NULL/BLOB）
Function fb_sqlite3_column_type(ByVal stmt As FB_SQLITE3_STMT Ptr, ByVal col As Long) As Long Export
    If stmt = 0 OrElse stmt->handle = 0 Then Return SQLITE_NULL
    Return sqlite3_column_type(stmt->handle, col)
End Function

'' 函数：fb_sqlite3_column_count
'' 说明：返回结果集的列数
Function fb_sqlite3_column_count(ByVal stmt As FB_SQLITE3_STMT Ptr) As Long Export
    If stmt = 0 OrElse stmt->handle = 0 Then Return 0
    Return sqlite3_column_count(stmt->handle)
End Function

'' --------------------------- 参数绑定 ---------------------------

'' 函数：fb_sqlite3_bind_int
'' 说明：绑定一个整型参数
Function fb_sqlite3_bind_int(ByVal stmt As FB_SQLITE3_STMT Ptr, _
                             ByVal idx As Long, _
                             ByVal value As Long) As Long Export
    If stmt = 0 OrElse stmt->handle = 0 Then Return SQLITE_MISUSE
    Return sqlite3_bind_int(stmt->handle, idx, value)
End Function

'' 函数：fb_sqlite3_bind_text
'' 说明：绑定一个文本参数
Function fb_sqlite3_bind_text(ByVal stmt As FB_SQLITE3_STMT Ptr, _
                             ByVal idx As Long, _
                             ByVal text As ZString Ptr) As Long Export
    If stmt = 0 OrElse stmt->handle = 0 Then Return SQLITE_MISUSE
    Return sqlite3_bind_text(stmt->handle, idx, text, -1, SQLITE_TRANSIENT)
End Function

'' --------------------------- 工具函数 ---------------------------

'' 函数：fb_sqlite3_is_ok
'' 说明：检查最近一次操作是否成功
Function fb_sqlite3_is_ok(ByVal rc As Long) As Long Export
    If rc = SQLITE_OK Then Return 1 Else Return 0
End Function
