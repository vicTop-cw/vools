'' =====================================================================
'' sdl3_wrapper.bas
'' ---------------------------------------------------------------------
'' FreeBASIC 封装模块：对 SDL3.dll 的常用 API 进行简化封装，
''               供 vools.bridge.freebasic 装饰器直接使用。
''
'' 使用方法（Python 侧）：
''   from vools.bridge.freebasic import freebasic
''
''   @freebasic(extra_includes=[...path to sdl3_wrapper.bas])
''   def init_sdl() -> int:
''       return """
''       If fb_sdl3_init(SDL_INIT_VIDEO) = 0 Then
''           Return 0
''       End If
''       Return -1
''       """
''
'' 头文件依赖（inc_path 在编译时由装饰器自动注入）：
''   - SDL3.bi
'' =====================================================================

#pragma once

'' 头文件由 inc_paths 注入路径
#include once "SDL3.bi"

'' --------------------------- 初始化与清理 ---------------------------

'' 函数：fb_sdl3_init
'' 说明：初始化 SDL 子系统
'' 参数：flags - SDL_INIT_VIDEO / SDL_INIT_AUDIO / SDL_INIT_TIMER 等
'' 返回：0 = 成功，非 0 = 失败
Function fb_sdl3_init(ByVal flags As ULong) As Long Export
    Return SDL_Init(flags)
End Function

'' 函数：fb_sdl3_init_subsystem
'' 说明：初始化指定的 SDL 子系统（不退出已初始化的子系统）
Function fb_sdl3_init_subsystem(ByVal flags As ULong) As Long Export
    Return SDL_InitSubSystem(flags)
End Function

'' 函数：fb_sdl3_quit
'' 说明：清理所有 SDL 子系统
Function fb_sdl3_quit() As Long Export
    SDL_Quit()
    Return 0
End Function

'' 函数：fb_sdl3_quit_subsystem
'' 说明：退出指定的 SDL 子系统
Function fb_sdl3_quit_subsystem(ByVal flags As ULong) As Long Export
    Return SDL_QuitSubSystem(flags)
End Function

'' 函数：fb_sdl3_was_init
'' 说明：检查哪些子系统已初始化
Function fb_sdl3_was_init(ByVal flags As ULong) As ULong Export
    Return SDL_WasInit(flags)
End Function

'' --------------------------- 错误处理 ---------------------------

'' 函数：fb_sdl3_get_error
'' 说明：获取最后一次错误信息
Function fb_sdl3_get_error() As ZString Ptr Export
    Return SDL_GetError()
End Function

'' 函数：fb_sdl3_clear_error
'' 说明：清除错误信息
Function fb_sdl3_clear_error() As Long Export
    SDL_ClearError()
    Return 0
End Function

'' --------------------------- 窗口管理 ---------------------------

'' 结构：FB_SDL3_WINDOW
'' 说明：SDL_Window* 的语义化包装
Type FB_SDL3_WINDOW
    handle As Any Ptr        '' 对应 SDL_Window*
    title  As String         '' 窗口标题
    width  As Long
    height As Long
End Type

'' 函数：fb_sdl3_create_window
'' 说明：创建窗口
Function fb_sdl3_create_window(ByVal title As ZString Ptr, _
                               ByVal w As Long, _
                               ByVal h As Long, _
                               ByVal flags As ULong) As FB_SDL3_WINDOW Export
    Dim win As FB_SDL3_WINDOW
    If title <> 0 Then win.title = *title
    win.width = w
    win.height = h
    win.handle = SDL_CreateWindow(title, w, h, flags)
    Return win
End Function

'' 函数：fb_sdl3_destroy_window
'' 说明：销毁窗口
Function fb_sdl3_destroy_window(ByVal win As FB_SDL3_WINDOW Ptr) As Long Export
    If win = 0 OrElse win->handle = 0 Then Return 0
    SDL_DestroyWindow(win->handle)
    win->handle = 0
    Return 1
End Function

'' 函数：fb_sdl3_get_window_title
'' 说明：获取窗口标题
Function fb_sdl3_get_window_title(ByVal win As FB_SDL3_WINDOW Ptr) As ZString Ptr Export
    If win = 0 OrElse win->handle = 0 Then Return @""
    Return SDL_GetWindowTitle(win->handle)
End Function

'' 函数：fb_sdl3_set_window_title
'' 说明：设置窗口标题
Function fb_sdl3_set_window_title(ByVal win As FB_SDL3_WINDOW Ptr, _
                                  ByVal title As ZString Ptr) As Long Export
    If win = 0 OrElse win->handle = 0 Then Return -1
    SDL_SetWindowTitle(win->handle, title)
    Return 0
End Function

'' 函数：fb_sdl3_get_window_size
'' 说明：获取窗口尺寸（通过 ByRef 输出）
Function fb_sdl3_get_window_size(ByVal win As FB_SDL3_WINDOW Ptr, _
                                 ByVal w As Long Ptr, _
                                 ByVal h As Long Ptr) As Long Export
    If win = 0 OrElse win->handle = 0 Then Return -1
    Return SDL_GetWindowSize(win->handle, w, h)
End Function

'' --------------------------- 渲染器 ---------------------------

'' 结构：FB_SDL3_RENDERER
'' 说明：SDL_Renderer* 的语义化包装
Type FB_SDL3_RENDERER
    handle As Any Ptr        '' 对应 SDL_Renderer*
    window As FB_SDL3_WINDOW Ptr
End Type

'' 函数：fb_sdl3_create_renderer
'' 说明：为窗口创建渲染器
Function fb_sdl3_create_renderer(ByVal win As FB_SDL3_WINDOW Ptr, _
                                 ByVal driver_name As ZString Ptr) As FB_SDL3_RENDERER Export
    Dim ren As FB_SDL3_RENDERER
    If win <> 0 AndAlso win->handle <> 0 Then
        ren.handle = SDL_CreateRenderer(win->handle, driver_name)
        ren.window = win
    End If
    Return ren
End Function

'' 函数：fb_sdl3_destroy_renderer
'' 说明：销毁渲染器
Function fb_sdl3_destroy_renderer(ByVal ren As FB_SDL3_RENDERER Ptr) As Long Export
    If ren = 0 OrElse ren->handle = 0 Then Return 0
    SDL_DestroyRenderer(ren->handle)
    ren->handle = 0
    Return 1
End Function

'' 函数：fb_sdl3_render_clear
'' 说明：用当前绘制色清空渲染区
Function fb_sdl3_render_clear(ByVal ren As FB_SDL3_RENDERER Ptr) As Long Export
    If ren = 0 OrElse ren->handle = 0 Then Return -1
    Return SDL_RenderClear(ren->handle)
End Function

'' 函数：fb_sdl3_render_present
'' 说明：将后台缓冲区呈现到屏幕
Function fb_sdl3_render_present(ByVal ren As FB_SDL3_RENDERER Ptr) As Long Export
    If ren = 0 OrElse ren->handle = 0 Then Return -1
    SDL_RenderPresent(ren->handle)
    Return 0
End Function

'' 函数：fb_sdl3_set_render_draw_color
'' 说明：设置绘制色（RGBA，每通道 0~255）
Function fb_sdl3_set_render_draw_color(ByVal ren As FB_SDL3_RENDERER Ptr, _
                                       ByVal r As UByte, _
                                       ByVal g As UByte, _
                                       ByVal b As UByte, _
                                       ByVal a As UByte) As Long Export
    If ren = 0 OrElse ren->handle = 0 Then Return -1
    Return SDL_SetRenderDrawColor(ren->handle, r, g, b, a)
End Function

'' --------------------------- 几何绘图 ---------------------------

'' 函数：fb_sdl3_render_draw_point
'' 说明：绘制一个点
Function fb_sdl3_render_draw_point(ByVal ren As FB_SDL3_RENDERER Ptr, _
                                   ByVal x As Single, ByVal y As Single) As Long Export
    If ren = 0 OrElse ren->handle = 0 Then Return -1
    Return SDL_RenderPoint(ren->handle, x, y)
End Function

'' 函数：fb_sdl3_render_draw_line
'' 说明：绘制一条线段
Function fb_sdl3_render_draw_line(ByVal ren As FB_SDL3_RENDERER Ptr, _
                                  ByVal x1 As Single, ByVal y1 As Single, _
                                  ByVal x2 As Single, ByVal y2 As Single) As Long Export
    If ren = 0 OrElse ren->handle = 0 Then Return -1
    Return SDL_RenderLine(ren->handle, x1, y1, x2, y2)
End Function

'' 函数：fb_sdl3_render_fill_rect_xy
'' 说明：绘制一个填充矩形（通过 xywh 参数）
Function fb_sdl3_render_fill_rect_xy(ByVal ren As FB_SDL3_RENDERER Ptr, _
                                     ByVal x As Single, ByVal y As Single, _
                                     ByVal w As Single, ByVal h As Single) As Long Export
    If ren = 0 OrElse ren->handle = 0 Then Return -1
    Dim As SDL_FRect r
    r.x = x
    r.y = y
    r.w = w
    r.h = h
    Return SDL_RenderFillRect(ren->handle, @r)
End Function

'' --------------------------- 事件循环 ---------------------------

'' 结构：FB_SDL3_EVENT
'' 说明：SDL_Event 的简化包装（仅保留 type 字段）
Type FB_SDL3_EVENT
    evt_type As ULong         '' 对应 SDL_EventType
    padding(0 To 56) As UByte '' 占位空间
End Type

'' 函数：fb_sdl3_poll_event
'' 说明：轮询一个事件
'' 返回：1 = 有事件，0 = 无事件
Function fb_sdl3_poll_event(ByVal evt As FB_SDL3_EVENT Ptr) As Long Export
    If evt = 0 Then Return 0
    Dim sdl_evt As SDL_Event
    Dim rc As Long = SDL_PollEvent(@sdl_evt)
    If rc = 1 Then
        evt->evt_type = sdl_evt.Type_
    End If
    Return rc
End Function

'' --------------------------- 时间与延时 ---------------------------

'' 函数：fb_sdl3_delay
'' 说明：延时指定毫秒数
Function fb_sdl3_delay(ByVal ms As ULong) As Long Export
    SDL_Delay(ms)
    Return 0
End Function

'' 函数：fb_sdl3_get_ticks
'' 说明：获取自初始化以来经过的毫秒数
Function fb_sdl3_get_ticks() As ULongInt Export
    Return SDL_GetTicks()
End Function
