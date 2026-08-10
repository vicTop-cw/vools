'' =====================================================================
'' cairo_wrapper.bas
'' ---------------------------------------------------------------------
'' FreeBASIC 封装模块：对 cairo.dll 的常用 2D 绘图 API 进行简化封装，
''               供 vools.bridge.freebasic 装饰器直接使用。
''
'' 使用方法（Python 侧）：
''   from vools.bridge.freebasic import freebasic
''
''   @freebasic(extra_includes=[...path to cairo_wrapper.bas])
''   def draw_something(width: int, height: int) -> int:
''       return """
''       Dim As FB_CAIRO_SURFACE Ptr surf = fb_cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 200, 200)
''       Dim As FB_CAIRO_CONTEXT Ptr cr = fb_cairo_create(surf)
''       fb_cairo_set_source_rgb(cr, 1.0, 0.0, 0.0)
''       fb_cairo_rectangle(cr, 10.0, 10.0, 100.0, 100.0)
''       fb_cairo_fill(cr)
''       fb_cairo_destroy(cr)
''       fb_cairo_surface_destroy(surf)
''       Return 0
''       """
''
'' 头文件依赖（inc_path 在编译时由装饰器自动注入）：
''   - cairo/cairo.bi
'' =====================================================================

#pragma once

'' 头文件由 inc_paths 注入路径（cairo 子目录下）
#include once "cairo/cairo.bi"

'' --------------------------- 简化别名 ---------------------------
'' cairo_t 和 cairo_surface_t 在 FB 中是 Any Ptr 别名

'' 封装：FB_CAIRO_SURFACE
'' 说明：cairo_surface_t 的语义化包装
Type FB_CAIRO_SURFACE
    handle As Any Ptr        '' 对应 cairo_surface_t*
    width  As Long
    height As Long
    stride As Long
End Type

'' 封装：FB_CAIRO_CONTEXT
'' 说明：cairo_t 的语义化包装
Type FB_CAIRO_CONTEXT
    handle  As Any Ptr       '' 对应 cairo_t*
    surface As FB_CAIRO_SURFACE Ptr
End Type

'' --------------------------- 版本信息 ---------------------------

'' 函数：fb_cairo_version_string
'' 说明：返回 Cairo 库的版本字符串
Function fb_cairo_version_string() As ZString Ptr Export
    Return cptr(ZString Ptr, cairo_version_string())
End Function

'' 函数：fb_cairo_version
'' 说明：返回 Cairo 库的版本号（编码为 MAJOR*10000 + MINOR*100 + MICRO）
Function fb_cairo_version() As Long Export
    Return cairo_version()
End Function

'' --------------------------- Surface 创建与销毁 ---------------------------

'' 函数：fb_cairo_image_surface_create
'' 说明：创建一个 ARGB32 格式的图像 surface
Function fb_cairo_image_surface_create(ByVal format As Long, _
                                       ByVal w As Long, _
                                       ByVal h As Long) As FB_CAIRO_SURFACE Export
    Dim surf As FB_CAIRO_SURFACE
    surf.handle = cairo_image_surface_create(format, w, h)
    surf.width  = w
    surf.height = h
    If surf.handle <> 0 Then
        surf.stride = cairo_image_surface_get_stride(surf.handle)
    End If
    Return surf
End Function

'' 函数：fb_cairo_image_surface_create_from_png
'' 说明：从 PNG 文件加载 surface
Function fb_cairo_image_surface_create_from_png(ByVal filename As ZString Ptr) As FB_CAIRO_SURFACE Export
    Dim surf As FB_CAIRO_SURFACE
    surf.handle = cairo_image_surface_create_from_png(filename)
    If surf.handle <> 0 Then
        surf.width  = cairo_image_surface_get_width(surf.handle)
        surf.height = cairo_image_surface_get_height(surf.handle)
        surf.stride = cairo_image_surface_get_stride(surf.handle)
    End If
    Return surf
End Function

'' 函数：fb_cairo_surface_destroy
'' 说明：销毁一个 surface
Function fb_cairo_surface_destroy(ByVal surf As FB_CAIRO_SURFACE Ptr) As Long Export
    If surf = 0 OrElse surf->handle = 0 Then Return 0
    cairo_surface_destroy(surf->handle)
    surf->handle = 0
    Return 1
End Function

'' 函数：fb_cairo_surface_write_to_png
'' 说明：将 surface 写入 PNG 文件
Function fb_cairo_surface_write_to_png(ByVal surf As FB_CAIRO_SURFACE Ptr, _
                                      ByVal filename As ZString Ptr) As Long Export
    If surf = 0 OrElse surf->handle = 0 Then Return -1
    Return cairo_surface_write_to_png(surf->handle, filename)
End Function

'' --------------------------- Context 创建与销毁 ---------------------------

'' 函数：fb_cairo_create
'' 说明：为指定 surface 创建一个绘图 context
Function fb_cairo_create(ByVal surf As FB_CAIRO_SURFACE Ptr) As FB_CAIRO_CONTEXT Export
    Dim cr As FB_CAIRO_CONTEXT
    If surf <> 0 Then
        cr.handle  = cairo_create(surf->handle)
        cr.surface = surf
    End If
    Return cr
End Function

'' 函数：fb_cairo_destroy
'' 说明：销毁一个 context
Function fb_cairo_destroy(ByVal cr As FB_CAIRO_CONTEXT Ptr) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return 0
    cairo_destroy(cr->handle)
    cr->handle = 0
    Return 1
End Function

'' 函数：fb_cairo_status
'' 说明：返回 context 的当前状态码
Function fb_cairo_status(ByVal cr As FB_CAIRO_CONTEXT Ptr) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    Return cairo_status(cr->handle)
End Function

'' --------------------------- 颜色与画笔 ---------------------------

'' 函数：fb_cairo_set_source_rgb
'' 说明：设置画笔颜色（RGB 范围 0.0 ~ 1.0）
Function fb_cairo_set_source_rgb(ByVal cr As FB_CAIRO_CONTEXT Ptr, _
                                 ByVal r As Double, _
                                 ByVal g As Double, _
                                 ByVal b As Double) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_set_source_rgb(cr->handle, r, g, b)
    Return cairo_status(cr->handle)
End Function

'' 函数：fb_cairo_set_source_rgba
'' 说明：设置画笔颜色（RGBA 范围 0.0 ~ 1.0）
Function fb_cairo_set_source_rgba(ByVal cr As FB_CAIRO_CONTEXT Ptr, _
                                  ByVal r As Double, _
                                  ByVal g As Double, _
                                  ByVal b As Double, _
                                  ByVal a As Double) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_set_source_rgba(cr->handle, r, g, b, a)
    Return cairo_status(cr->handle)
End Function

'' 函数：fb_cairo_set_line_width
'' 说明：设置线宽
Function fb_cairo_set_line_width(ByVal cr As FB_CAIRO_CONTEXT Ptr, _
                                 ByVal lw As Double) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_set_line_width(cr->handle, lw)
    Return cairo_status(cr->handle)
End Function

'' --------------------------- 基本绘图 ---------------------------

'' 函数：fb_cairo_rectangle
'' 说明：定义一个矩形路径（需配合 fill/stroke 使用）
Function fb_cairo_rectangle(ByVal cr As FB_CAIRO_CONTEXT Ptr, _
                            ByVal x As Double, _
                            ByVal y As Double, _
                            ByVal w As Double, _
                            ByVal h As Double) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_rectangle(cr->handle, x, y, w, h)
    Return cairo_status(cr->handle)
End Function

'' 函数：fb_cairo_arc
'' 说明：定义一段圆弧路径
Function fb_cairo_arc(ByVal cr As FB_CAIRO_CONTEXT Ptr, _
                      ByVal xc As Double, _
                      ByVal yc As Double, _
                      ByVal radius As Double, _
                      ByVal angle1 As Double, _
                      ByVal angle2 As Double) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_arc(cr->handle, xc, yc, radius, angle1, angle2)
    Return cairo_status(cr->handle)
End Function

'' 函数：fb_cairo_line_to
'' 说明：从当前点画线到指定点
Function fb_cairo_line_to(ByVal cr As FB_CAIRO_CONTEXT Ptr, _
                          ByVal x As Double, _
                          ByVal y As Double) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_line_to(cr->handle, x, y)
    Return cairo_status(cr->handle)
End Function

'' 函数：fb_cairo_move_to
'' 说明：移动画笔到指定点（不画线）
Function fb_cairo_move_to(ByVal cr As FB_CAIRO_CONTEXT Ptr, _
                          ByVal x As Double, _
                          ByVal y As Double) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_move_to(cr->handle, x, y)
    Return cairo_status(cr->handle)
End Function

'' --------------------------- 渲染操作 ---------------------------

'' 函数：fb_cairo_fill
'' 说明：用当前画笔填充当前路径
Function fb_cairo_fill(ByVal cr As FB_CAIRO_CONTEXT Ptr) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_fill(cr->handle)
    Return cairo_status(cr->handle)
End Function

'' 函数：fb_cairo_stroke
'' 说明：描边当前路径
Function fb_cairo_stroke(ByVal cr As FB_CAIRO_CONTEXT Ptr) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_stroke(cr->handle)
    Return cairo_status(cr->handle)
End Function

'' 函数：fb_cairo_paint
'' 说明：用当前画笔覆盖整个 surface
Function fb_cairo_paint(ByVal cr As FB_CAIRO_CONTEXT Ptr) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_paint(cr->handle)
    Return cairo_status(cr->handle)
End Function

'' 函数：fb_cairo_clear
'' 说明：清空当前 surface
Function fb_cairo_clear(ByVal cr As FB_CAIRO_CONTEXT Ptr) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_save(cr->handle)
    cairo_set_operator(cr->handle, CAIRO_OPERATOR_CLEAR)
    cairo_paint(cr->handle)
    cairo_restore(cr->handle)
    Return cairo_status(cr->handle)
End Function

'' --------------------------- 路径控制 ---------------------------

'' 函数：fb_cairo_new_path
'' 说明：开始新路径
Function fb_cairo_new_path(ByVal cr As FB_CAIRO_CONTEXT Ptr) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_new_path(cr->handle)
    Return cairo_status(cr->handle)
End Function

'' 函数：fb_cairo_close_path
'' 说明：闭合当前路径
Function fb_cairo_close_path(ByVal cr As FB_CAIRO_CONTEXT Ptr) As Long Export
    If cr = 0 OrElse cr->handle = 0 Then Return -1
    cairo_close_path(cr->handle)
    Return cairo_status(cr->handle)
End Function
