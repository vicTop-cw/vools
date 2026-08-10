'' =====================================================================
'' SDL3.bi - Minimal FreeBASIC bindings for SDL3 (subset)
'' ---------------------------------------------------------------------
'' 自包含的 SDL3 FreeBASIC 头文件，覆盖 sdl3_wrapper.bas 用到的 API。
'' 完整 SDL3 头文件请到 https://github.com/freebasic/fbc 仓库获取。
'' =====================================================================

#pragma once

#inclib "SDL3"

'' --------------------------- 基础类型 ---------------------------
Type SDL_Window As SDL_Window
Type SDL_Renderer As SDL_Renderer
Type SDL_Surface As SDL_Surface
Type SDL_Texture As SDL_Texture

Type SDL_Event
    Type_ As ULong
    padding(0 To 55) As UByte
End Type

Type SDL_FPoint
    x As Single
    y As Single
End Type

Type SDL_FRect
    x As Single
    y As Single
    w As Single
    h As Single
End Type

Type SDL_Rect
    x As Long
    y As Long
    w As Long
    h As Long
End Type

Type SDL_Color
    r As UByte
    g As UByte
    b As UByte
    a As UByte
End Type

'' --------------------------- 初始化标志 ---------------------------
Const SDL_INIT_VIDEO = &h00000010
Const SDL_INIT_AUDIO = &h00000020
Const SDL_INIT_TIMER = &h00000001
Const SDL_INIT_JOYSTICK = &h00000200
Const SDL_INIT_HAPTIC = &h00001000
Const SDL_INIT_GAMECONTROLLER = &h00002000
Const SDL_INIT_EVENTS = &h00004000
Const SDL_INIT_SENSOR = &h00008000
Const SDL_INIT_EVERYTHING = SDL_INIT_TIMER Or SDL_INIT_AUDIO Or SDL_INIT_VIDEO Or _
    SDL_INIT_EVENTS Or SDL_INIT_JOYSTICK Or SDL_INIT_HAPTIC Or _
    SDL_INIT_GAMECONTROLLER Or SDL_INIT_SENSOR

'' --------------------------- 窗口标志 ---------------------------
Const SDL_WINDOW_FULLSCREEN = &h00000001
Const SDL_WINDOW_OPENGL = &h00000002
Const SDL_WINDOW_HIDDEN = &h00000008
Const SDL_WINDOW_BORDERLESS = &h00000010
Const SDL_WINDOW_RESIZABLE = &h00000020
Const SDL_WINDOW_MINIMIZED = &h00000040
Const SDL_WINDOW_MAXIMIZED = &h00000080
Const SDL_WINDOW_MOUSE_GRABBED = &h00000100
Const SDL_WINDOW_INPUT_FOCUS = &h00000200
Const SDL_WINDOW_MOUSE_FOCUS = &h00000400
Const SDL_WINDOW_FULLSCREEN_DESKTOP = SDL_WINDOW_FULLSCREEN Or &h00001000
Const SDL_WINDOW_ALLOW_HIGHDPI = &h00002000
Const SDL_WINDOW_MOUSE_CAPTURE = &h00004000
Const SDL_WINDOW_ALWAYS_ON_TOP = &h00008000
Const SDL_WINDOW_SKIP_TASKBAR = &h00010000
Const SDL_WINDOW_UTILITY = &h00020000
Const SDL_WINDOW_TOOLTIP = &h00040000
Const SDL_WINDOW_POPUP_MENU = &h00080000
Const SDL_WINDOW_KEYBOARD_GRABBED = &h00100000
Const SDL_WINDOW_VULKAN = &h10000000
Const SDL_WINDOW_METAL = &h20000000
Const SDL_WINDOW_TRANSPARENT = &h00000004
Const SDL_WINDOW_NOT_FOCUSABLE = &h00200000

'' --------------------------- 像素格式 ---------------------------
Const SDL_PIXELFORMAT_UNKNOWN = 0
Const SDL_PIXELFORMAT_INDEX1LSB = &h11100100
Const SDL_PIXELFORMAT_INDEX1MSB = &h11200100
Const SDL_PIXELFORMAT_INDEX4LSB = &h12100400
Const SDL_PIXELFORMAT_INDEX4MSB = &h12200400
Const SDL_PIXELFORMAT_INDEX8 = &h13000801
Const SDL_PIXELFORMAT_RGB332 = &h14110801
Const SDL_PIXELFORMAT_XRGB4444 = &h15120c02
Const SDL_PIXELFORMAT_RGB444 = &h16120c02
Const SDL_PIXELFORMAT_XBGR4444 = &h16520c02
Const SDL_PIXELFORMAT_BGR444 = &h17520c02
Const SDL_PIXELFORMAT_XRGB1555 = &h15130f02
Const SDL_PIXELFORMAT_RGB555 = &h16130f02
Const SDL_PIXELFORMAT_XBGR1555 = &h16530f02
Const SDL_PIXELFORMAT_BGR555 = &h17530f02
Const SDL_PIXELFORMAT_ARGB4444 = &h15321002
Const SDL_PIXELFORMAT_RGBA4444 = &h15421002
Const SDL_PIXELFORMAT_ABGR4444 = &h15721002
Const SDL_PIXELFORMAT_BGRA4444 = &h15821002
Const SDL_PIXELFORMAT_ARGB1555 = &h15331002
Const SDL_PIXELFORMAT_RGBA5551 = &h15431002
Const SDL_PIXELFORMAT_ABGR1555 = &h15731002
Const SDL_PIXELFORMAT_BGRA5551 = &h15831002
Const SDL_PIXELFORMAT_RGB565 = &h15151002
Const SDL_PIXELFORMAT_BGR565 = &h15551002
Const SDL_PIXELFORMAT_RGB24 = &h17101803
Const SDL_PIXELFORMAT_BGR24 = &h17401803
Const SDL_PIXELFORMAT_XRGB8888 = &h16161804
Const SDL_PIXELFORMAT_RGB888 = &h16261804
Const SDL_PIXELFORMAT_XBGR8888 = &h16561804
Const SDL_PIXELFORMAT_BGR888 = &h16661804
Const SDL_PIXELFORMAT_ARGB8888 = &h16362004
Const SDL_PIXELFORMAT_RGBA8888 = &h16462004
Const SDL_PIXELFORMAT_ABGR8888 = &h16762004
Const SDL_PIXELFORMAT_BGRA8888 = &h16862004
Const SDL_PIXELFORMAT_ARGB2101010 = &h15372004
Const SDL_PIXELFORMAT_RGBA64 = &h12108004
Const SDL_PIXELFORMAT_ARGB64 = &h12208004
Const SDL_PIXELFORMAT_BGRA64 = &h12408004
Const SDL_PIXELFORMAT_ABGR64 = &h12308004

'' --------------------------- 事件类型 ---------------------------
Type SDL_EventType As ULong

Const SDL_EVENT_QUIT = &h100
Const SDL_EVENT_KEY_DOWN = &h300
Const SDL_EVENT_KEY_UP = &h301
Const SDL_EVENT_MOUSE_MOTION = &h400
Const SDL_EVENT_MOUSE_BUTTON_DOWN = &h401
Const SDL_EVENT_MOUSE_BUTTON_UP = &h402
Const SDL_EVENT_MOUSE_WHEEL = &h403
Const SDL_EVENT_JOYSTICK_AXIS_MOTION = &h600
Const SDL_EVENT_JOYSTICK_BUTTON_DOWN = &h604
Const SDL_EVENT_JOYSTICK_BUTTON_UP = &h605
Const SDL_EVENT_WINDOW_SHOWN = &h202
Const SDL_EVENT_WINDOW_HIDDEN = &h203
Const SDL_EVENT_WINDOW_MOVED = &h204
Const SDL_EVENT_WINDOW_RESIZED = &h205
Const SDL_EVENT_USER = &h8000

'' --------------------------- API 声明 ---------------------------
extern "C"
    Declare Function SDL_Init(ByVal flags As ULong) As Long
    Declare Function SDL_InitSubSystem(ByVal flags As ULong) As Long
    Declare Sub SDL_Quit()
    Declare Function SDL_QuitSubSystem(ByVal flags As ULong) As Long
    Declare Function SDL_WasInit(ByVal flags As ULong) As ULong
    Declare Function SDL_GetNumVideoDrivers() As Long
    Declare Function SDL_GetVideoDriver(ByVal index As Long) As ZString Ptr
    Declare Function SDL_GetCurrentVideoDriver() As ZString Ptr

    Declare Function SDL_GetError() As ZString Ptr
    Declare Sub SDL_ClearError()

    Declare Function SDL_CreateWindow(ByVal title As ZString Ptr, _
                                      ByVal w As Long, _
                                      ByVal h As Long, _
                                      ByVal flags As ULong) As SDL_Window Ptr
    Declare Function SDL_CreateWindowWithProperties(ByVal props As ULong) As SDL_Window Ptr
    Declare Sub SDL_DestroyWindow(ByVal window As SDL_Window Ptr)
    Declare Function SDL_GetWindowTitle(ByVal window As SDL_Window Ptr) As ZString Ptr
    Declare Sub SDL_SetWindowTitle(ByVal window As SDL_Window Ptr, ByVal title As ZString Ptr)
    Declare Function SDL_GetWindowSize(ByVal window As SDL_Window Ptr, _
                                       ByVal w As Long Ptr, _
                                       ByVal h As Long Ptr) As Long
    Declare Sub SDL_SetWindowSize(ByVal window As SDL_Window Ptr, _
                                  ByVal w As Long, ByVal h As Long)
    Declare Function SDL_GetWindowID(ByVal window As SDL_Window Ptr) As ULong
    Declare Function SDL_GetWindowFromID(ByVal id As ULong) As SDL_Window Ptr

    Declare Function SDL_CreateRenderer(ByVal window As SDL_Window Ptr, _
                                        ByVal name As ZString Ptr) As SDL_Renderer Ptr
    Declare Sub SDL_DestroyRenderer(ByVal renderer As SDL_Renderer Ptr)
    Declare Function SDL_RenderClear(ByVal renderer As SDL_Renderer Ptr) As Long
    Declare Sub SDL_RenderPresent(ByVal renderer As SDL_Renderer Ptr)
    Declare Function SDL_SetRenderDrawColor(ByVal renderer As SDL_Renderer Ptr, _
                                            ByVal r As UByte, _
                                            ByVal g As UByte, _
                                            ByVal b As UByte, _
                                            ByVal a As UByte) As Long
    Declare Function SDL_GetRenderDrawColor(ByVal renderer As SDL_Renderer Ptr, _
                                            ByVal r As UByte Ptr, _
                                            ByVal g As UByte Ptr, _
                                            ByVal b As UByte Ptr, _
                                            ByVal a As UByte Ptr) As Long
    Declare Function SDL_RenderPoint(ByVal renderer As SDL_Renderer Ptr, _
                                     ByVal x As Single, ByVal y As Single) As Long
    Declare Function SDL_RenderPoints(ByVal renderer As SDL_Renderer Ptr, _
                                      ByVal points As SDL_FPoint Ptr, _
                                      ByVal count As Long) As Long
    Declare Function SDL_RenderLine(ByVal renderer As SDL_Renderer Ptr, _
                                    ByVal x1 As Single, ByVal y1 As Single, _
                                    ByVal x2 As Single, ByVal y2 As Single) As Long
    Declare Function SDL_RenderLines(ByVal renderer As SDL_Renderer Ptr, _
                                     ByVal points As SDL_FPoint Ptr, _
                                     ByVal count As Long) As Long
    Declare Function SDL_RenderRect(ByVal renderer As SDL_Renderer Ptr, _
                                    ByVal rect As SDL_FRect Ptr) As Long
    Declare Function SDL_RenderFillRect(ByVal renderer As SDL_Renderer Ptr, _
                                        ByVal rect As SDL_FRect Ptr) As Long
    Declare Function SDL_RenderTexture(ByVal renderer As SDL_Renderer Ptr, _
                                       ByVal texture As SDL_Texture Ptr, _
                                       ByVal srcrect As SDL_FRect Ptr, _
                                       ByVal dstrect As SDL_FRect Ptr) As Long
    Declare Function SDL_SetRenderTarget(ByVal renderer As SDL_Renderer Ptr, _
                                         ByVal texture As SDL_Texture Ptr) As Long
    Declare Function SDL_RenderTextureRotated(ByVal renderer As SDL_Renderer Ptr, _
                                              ByVal texture As SDL_Texture Ptr, _
                                              ByVal srcrect As SDL_FRect Ptr, _
                                              ByVal dstrect As SDL_FRect Ptr, _
                                              ByVal angle As Double, _
                                              ByVal center As SDL_FPoint Ptr, _
                                              ByVal flip As Long) As Long

    Declare Function SDL_PollEvent(ByVal event As SDL_Event Ptr) As Long
    Declare Function SDL_WaitEvent(ByVal event As SDL_Event Ptr) As Long
    Declare Function SDL_WaitEventTimeout(ByVal event As SDL_Event Ptr, _
                                         ByVal timeout_ms As Long) As Long
    Declare Function SDL_PushEvent(ByVal event As SDL_Event Ptr) As Long
    Declare Sub SDL_FlushEvents(ByVal minType As ULong, ByVal maxType As ULong)
    Declare Function SDL_PeepEvents(ByVal events As SDL_Event Ptr, _
                                    ByVal numevents As Long, _
                                    ByVal action As Long, _
                                    ByVal minType As ULong, _
                                    ByVal maxType As ULong) As Long

    Declare Sub SDL_Delay(ByVal ms As ULong)
    Declare Function SDL_GetTicks() As ULongInt
    Declare Function SDL_GetPerformanceCounter() As ULongInt
    Declare Function SDL_GetPerformanceFrequency() As ULongInt

    Declare Function SDL_GetNumRenderDrivers() As Long
    Declare Function SDL_GetRenderDriver(ByVal index As Long) As ZString Ptr
End Extern
