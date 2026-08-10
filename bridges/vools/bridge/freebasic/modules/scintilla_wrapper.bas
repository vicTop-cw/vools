'' =====================================================================
'' scintilla_wrapper.bas
'' ---------------------------------------------------------------------
'' FreeBASIC 封装模块：对 Scintilla.dll 控件的常用 API 进行简化和统一，
''               供 vools.bridge.freebasic 装饰器直接使用。
''
'' 使用方法（Python 侧）：
''   from vools.bridge import freebasic
''   from vools.bridge.freebasic import compile_and_run
''
''   result = compile_and_run(
''       '...',
''       func_name='test_scintilla',
''       extra_includes=[freebasic.get_fb_module('scintilla_wrapper')],
''       inc_paths=freebasic.get_fb_inc_paths('scintilla_wrapper'),
''       lib_paths=freebasic.get_fb_lib_paths('scintilla_wrapper'),
''   )
''
'' 头文件依赖（inc_path 在编译时由装饰器自动注入）：
''   - modScintilla.bi  （完整 SCI_* 消息常量）
''   - modSciLexer.bi   （词法分析器常量）
''
'' 注意：所有函数都需要传入 Scintilla 控件的 hWnd 句柄
'' =====================================================================

#pragma once

'' --------------------------- 头文件包含 ---------------------------
#include once "modScintilla.bi"
#include once "modSciLexer.bi"

'' --------------------------- 初始化 / DirectFunction ---------------------------

Function fb_scintilla_init_direct(ByVal hWnd As HWND) As Any Ptr Export
    SciMsg = Cast(Scintilla_DirectFunction, SendMessage(hWnd, SCI_GETDIRECTFUNCTION, 0, 0))
    Return Cast(Any Ptr, SendMessage(hWnd, SCI_GETDIRECTPOINTER, 0, 0))
End Function

'' --------------------------- 文本操作 ---------------------------

Function fb_scintilla_get_text_length(ByVal hWnd As HWND) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_GETLENGTH, 0, 0))
End Function

Function fb_scintilla_get_text(ByVal hWnd As HWND, ByVal buf As ZString Ptr, ByVal buf_size As Long) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_GETTEXT, Cast(WPARAM, buf_size), Cast(LPARAM, buf)))
End Function

Sub fb_scintilla_set_text(ByVal hWnd As HWND, ByVal text_utf8 As ZString Ptr) Export
    SendMessage hWnd, SCI_SETTEXT, 0, Cast(LPARAM, text_utf8)
End Sub

Sub fb_scintilla_add_text(ByVal hWnd As HWND, ByVal text_utf8 As ZString Ptr) Export
    SendMessage hWnd, SCI_ADDTEXT, Cast(WPARAM, Len(text_utf8)), Cast(LPARAM, text_utf8)
End Sub

Sub fb_scintilla_insert_text(ByVal hWnd As HWND, ByVal text_utf8 As ZString Ptr) Export
    SendMessage hWnd, SCI_INSERTTEXT, Cast(WPARAM, -1), Cast(LPARAM, text_utf8)
End Sub

Sub fb_scintilla_clear_all(ByVal hWnd As HWND) Export
    SendMessage hWnd, SCI_CLEARDOCUMENTSTYLE, 0, 0
    SendMessage hWnd, SCI_CLEARALL, 0, 0
End Sub

'' --------------------------- 行操作 ---------------------------

Function fb_scintilla_get_line_count(ByVal hWnd As HWND) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_GETLINECOUNT, 0, 0))
End Function

Function fb_scintilla_get_line_text(ByVal hWnd As HWND, ByVal ln As Long, ByVal buf As ZString Ptr, ByVal buf_size As Long) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_GETLINE, Cast(WPARAM, ln), Cast(LPARAM, buf)))
End Function

Function fb_scintilla_get_line_length(ByVal hWnd As HWND, ByVal ln As Long) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_LINELENGTH, Cast(WPARAM, ln), 0))
End Function

Sub fb_scintilla_goto_line(ByVal hWnd As HWND, ByVal ln As Long) Export
    SendMessage hWnd, SCI_GOTOLINE, Cast(WPARAM, ln), 0
End Sub

Function fb_scintilla_line_from_pos(ByVal hWnd As HWND, ByVal position As Long) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_LINEFROMPOSITION, Cast(WPARAM, position), 0))
End Function

Function fb_scintilla_pos_from_line(ByVal hWnd As HWND, ByVal ln As Long) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_POSITIONFROMLINE, Cast(WPARAM, ln), 0))
End Function

'' --------------------------- 选择操作 ---------------------------

Function fb_scintilla_get_current_position(ByVal hWnd As HWND) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_GETCURRENTPOS, 0, 0))
End Function

Function fb_scintilla_get_selection_start(ByVal hWnd As HWND) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_GETSELECTIONSTART, 0, 0))
End Function

Function fb_scintilla_get_selection_end(ByVal hWnd As HWND) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_GETSELECTIONEND, 0, 0))
End Function

Sub fb_scintilla_set_selection(ByVal hWnd As HWND, ByVal anchor As Long, ByVal caret As Long) Export
    SendMessage hWnd, SCI_SETSEL, Cast(WPARAM, anchor), Cast(LPARAM, caret)
End Sub

Sub fb_scintilla_select_all(ByVal hWnd As HWND) Export
    SendMessage hWnd, SCI_SELECTALL, 0, 0
End Sub

'' --------------------------- 撤销/重做 ---------------------------

Function fb_scintilla_can_undo(ByVal hWnd As HWND) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_CANUNDO, 0, 0))
End Function

Function fb_scintilla_can_redo(ByVal hWnd As HWND) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_CANREDO, 0, 0))
End Function

Sub fb_scintilla_undo(ByVal hWnd As HWND) Export
    SendMessage hWnd, SCI_UNDO, 0, 0
End Sub

Sub fb_scintilla_redo(ByVal hWnd As HWND) Export
    SendMessage hWnd, SCI_REDO, 0, 0
End Sub

Sub fb_scintilla_set_save_point(ByVal hWnd As HWND) Export
    SendMessage hWnd, SCI_SETSAVEPOINT, 0, 0
End Sub

Function fb_scintilla_get_modify(ByVal hWnd As HWND) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_GETMODIFY, 0, 0))
End Function

'' --------------------------- 查找 ---------------------------

Function fb_scintilla_find_text(ByVal hWnd As HWND, ByVal text As ZString Ptr, ByVal start_pos As Long, ByVal end_pos As Long, ByVal flags As Long) As Long Export
    Dim ft As Sci_TextToFind
    If end_pos = -1 Then
        ft.chrg.cpMax = Cast(Long, SendMessage(hWnd, SCI_GETLENGTH, 0, 0))
    Else
        ft.chrg.cpMax = end_pos
    End If
    ft.chrg.cpMin = start_pos
    ft.lpstrText = text
    Return Cast(Long, SendMessage(hWnd, SCI_FINDTEXT, Cast(WPARAM, flags), Cast(LPARAM, @ft)))
End Function

'' --------------------------- 折叠 ---------------------------

Sub fb_scintilla_fold_all(ByVal hWnd As HWND) Export
    SendMessage hWnd, SCI_FOLDALL, 0, 0
End Sub

Sub fb_scintilla_unfold_all(ByVal hWnd As HWND) Export
    SendMessage hWnd, SCI_FOLDALL, 1, 0
End Sub

Sub fb_scintilla_fold_toggle_line(ByVal hWnd As HWND, ByVal ln As Long) Export
    SendMessage hWnd, SCI_FOLDLINE, Cast(WPARAM, ln), 2
End Sub

'' --------------------------- 书签 ---------------------------

Sub fb_scintilla_bookmark_toggle(ByVal hWnd As HWND, ByVal ln As Long) Export
    Dim mask As Long
    mask = 1 SHL 1
    If SendMessage(hWnd, SCI_MARKERGET, Cast(WPARAM, ln), 0) And mask Then
        SendMessage hWnd, SCI_MARKERDELETE, Cast(WPARAM, ln), 1
    Else
        SendMessage hWnd, SCI_MARKERADD, Cast(WPARAM, ln), 1
    End If
End Sub

Function fb_scintilla_bookmark_next(ByVal hWnd As HWND, ByVal from_line As Long) As Long Export
    Dim mask As Long = 1 SHL 1
    Return Cast(Long, SendMessage(hWnd, SCI_MARKERNEXT, Cast(WPARAM, from_line + 1), Cast(LPARAM, mask)))
End Function

Function fb_scintilla_bookmark_prev(ByVal hWnd As HWND, ByVal from_line As Long) As Long Export
    Dim mask As Long = 1 SHL 1
    Return Cast(Long, SendMessage(hWnd, SCI_MARKERPREVIOUS, Cast(WPARAM, from_line - 1), Cast(LPARAM, mask)))
End Function

'' --------------------------- 词法分析器 ---------------------------

Sub fb_scintilla_set_lexer(ByVal hWnd As HWND, ByVal lexer As Long) Export
    SendMessage hWnd, SCI_SETLEXER, Cast(WPARAM, lexer), 0
End Sub

Sub fb_scintilla_set_lexer_language(ByVal hWnd As HWND, ByVal lang_name As ZString Ptr) Export
    SendMessage hWnd, SCI_SETLEXERLANGUAGE, 0, Cast(LPARAM, lang_name)
End Sub

'' --------------------------- 样式设置 ---------------------------

Sub fb_scintilla_style_set_fore(ByVal hWnd As HWND, ByVal style As Long, ByVal clr As Long) Export
    SendMessage hWnd, SCI_STYLESETFORE, Cast(WPARAM, style), Cast(LPARAM, clr)
End Sub

Sub fb_scintilla_style_set_back(ByVal hWnd As HWND, ByVal style As Long, ByVal clr As Long) Export
    SendMessage hWnd, SCI_STYLESETBACK, Cast(WPARAM, style), Cast(LPARAM, clr)
End Sub

Sub fb_scintilla_style_set_size(ByVal hWnd As HWND, ByVal style As Long, ByVal fsize As Long) Export
    SendMessage hWnd, SCI_STYLESETSIZE, Cast(WPARAM, style), Cast(LPARAM, fsize)
End Sub

Sub fb_scintilla_style_set_font(ByVal hWnd As HWND, ByVal style As Long, ByVal font_name As ZString Ptr) Export
    SendMessage hWnd, SCI_STYLESETFONT, Cast(WPARAM, style), Cast(LPARAM, font_name)
End Sub

'' --------------------------- 显示设置 ---------------------------

Sub fb_scintilla_set_caret_line_visible(ByVal hWnd As HWND, ByVal show As Long) Export
    SendMessage hWnd, SCI_SETCARETLINEVISIBLE, Cast(WPARAM, show), 0
End Sub

Sub fb_scintilla_set_tab_width(ByVal hWnd As HWND, ByVal w As Long) Export
    SendMessage hWnd, SCI_SETTABWIDTH, Cast(WPARAM, w), 0
End Sub

Sub fb_scintilla_set_codepage(ByVal hWnd As HWND, ByVal codepage As Long) Export
    SendMessage hWnd, SCI_SETCODEPAGE, Cast(WPARAM, codepage), 0
End Sub

'' --------------------------- 视图 ---------------------------

Function fb_scintilla_get_first_visible_line(ByVal hWnd As HWND) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_GETFIRSTVISIBLELINE, 0, 0))
End Function

Function fb_scintilla_lines_on_screen(ByVal hWnd As HWND) As Long Export
    Return Cast(Long, SendMessage(hWnd, SCI_LINESONSCREEN, 0, 0))
End Function
