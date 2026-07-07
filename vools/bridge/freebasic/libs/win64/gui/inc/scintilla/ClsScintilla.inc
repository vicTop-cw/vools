'控件类
#include Once "modScintilla.bi"
Type Class_Scintilla 
    
Protected : 
   hWndControl As .hWnd '控件句柄
   m_IDC As Long     '控件IDC
Public : 
   pSci As Any Ptr 'Scintilla 对象句柄，用于 SciMsg 和Scintilla控件通信。
   Declare Property Enabled() As Boolean                 '返回/设置控件是否允许操作。{=.True.False}
   Declare Property Enabled(ByVal bValue As Boolean)
   Declare Property Visible() As Boolean                 '显示或隐藏控件。{=.True.False}
   Declare Property Visible(ByVal bValue As Boolean)
   Declare Property Tag() As StringW                       '存储程序所需的附加数据。
   Declare Property Tag(sText As Wstring)
   Declare Property Left() As Long                   '返回/设置相对于父窗口的 X（像素）
   Declare Property Left(ByVal nLeft As Long)
   Declare Property Top() As Long                  '返回/设置相对于父窗口的 Y（像素）
   Declare Property Top(ByVal nTop As Long)
   Declare Property Width() As Long                '返回/设置控件宽度（像素）
   Declare Property Width(ByVal nWidth As Long)
   Declare Property Height() As Long               '返回/设置控件高度（像素）
   Declare Property Height(ByVal nHeight As Long)
   Declare Sub Move(ByVal nLeft As Long, ByVal nTop As Long, ByVal nWidth As Long = 0, ByVal nHeight As Long = 0) '设置窗口位置和大小，高度、宽度=0时不修改。
   Declare Sub Size(ByVal nWidth As Long , ByVal nHeight As Long ) '设置控件高度、宽度
   Declare Property IDC() As Long             '返回/设置控件IDC，控件标识符，1个窗口里每个控件IDC都是唯一的，包括控件数组。（不可随意修改，系统自动处理）
   Declare Property IDC(NewIDC As Long)
   Declare Sub SetFocus()  ' 使控件获取键盘焦点
   Declare Function Kill() As Boolean  '从窗体中销毁控件。成功返回 True
   Declare Property hWnd() As.hWnd                    '返回/设置控件句柄
   Declare Property hWnd(ByVal hWndNew As.hWnd)
   Declare Property hWndForm() As.hWnd         '返回/设置控件所在的父窗口句柄，主要用于多开同一个窗口后，要使用控件前，必须先指定控件所在的父窗口句柄，才能正常使用控件。如果用 SetParent 指定新父，使用时也需要用新父句柄。
   Declare Property hWndForm(ByVal hWndParent As.hWnd) '获取控件所在的父窗口句柄
   Declare Property WindowsZ(hWndlnsertAfter As.hWnd) '控件Z顺序 在某个控件之上或是{=.HWND_BOTTOM 所有控件之后.HWND_TOP 所有窗口最前.某控件句柄 将置于此控件前}
   Declare Sub Refresh()  '刷新窗口
   Declare Property UserData(idx AS LONG) As Integer      '返回/设置用户数据，idx索引号，范围为0至99。就是1个控件可以存放100个数值。
   Declare Property UserData(idx AS LONG, bValue As Integer)   
   
   Declare Property Text() As String         '返回/设置全部文本，UTF8编码，Scintilla 默认全部都是 UTF8编码文本
   Declare Property Text(Text_utf8 As String )
   Declare Property TextLine(nLine As Long) As String   '返回/设置 某行文本，行从0开始。
   Declare Property TextLine(nLine As Long,Text_utf8 As String )
   Declare Property TextSel() As String   '返回 选择中的文本 或替换它
   Declare Property TextSel(Text_utf8 As String)
   Declare Function TextAppend(Text_utf8 As String) As Long  '在尾部增加文本,返回新增的第一行， 返回-1 表示失败
   Declare Sub TextInsert(Text_utf8 As String)  '在当前位置插入文本 Text_utf8为utf8格式
   
   Declare Sub FoldAll()   '全部折叠
   Declare Sub FoldAllUn() '全部展开折叠
   Declare Sub FoldToggle(nLine As Long) '折叠开关 ，行从0开始。
   Declare Sub BookmarkToggle(nLine As Long) '切换书签 ，行从0开始。
   Declare Sub BookmarkNext() '下一个书签
   Declare Sub BookmarkPrev() '上一书签
   
   Declare Property CurrentLineNumber() As Long   '返回/设置 当前行号，行从0开始。
   Declare Property CurrentLineNumber(nLine As Long)
   Declare Property CurrentPos() As Long   '返回/设置 当前光标位置
   Declare Property CurrentPos(nPos As Long)
   Declare Property FirstVisibleLine() As Long   '返回/设置 屏幕上可见视图中第一条可见线的行号
   Declare Property FirstVisibleLine(nLine As Long)
   
   Declare Function FindText(Text_utf8 As String,startPos As Long =0,endPos As Long =-1,searchFlags As Long = SCFIND_NONE  ) As Long  '查找文本，找到返回 位置，未找到返回 -1 ，如同 InStr 的效果。 startPos 和endPos 是搜索范围 =-1 是最大值，开始大于结束为反向查找，搜索标记为组合多选，不是单选{4.SCFIND_NONE 不区分大小写.SCFIND_MATCHCASE 区分大小写.SCFIND_WHOLEWORD 后关键词字符.SCFIND_WORDSTART 前关键词字符.SCFIND_REGEXP 正则表达式.SCFIND_POSIX 解释部分带标记}   
   Declare Sub GoToPos(nPos As Long, Weizi As Long =0 , nLength As Long =0 ) '到当前位置的行，Weizi 是显示位置，nLength 是在当前位置后选择几个文字。 {1.0 位置偏上.1 位置中间.2 位置偏下} 
   Declare Sub GoToLine(nLine As Long, Weizi As Long =0 ) '到当前位置的行，Weizi 是显示位置 {1.0 位置偏上.1 位置中间.2 位置偏下} 
   Declare Function PosToLine(nPos As Long) As Long  '获取位置在第几行，失败返回 -1，行数从0开始，第一行是0
   Declare Function PosToX(nPos As Long) As Long  '获取位置在某行的第几个字符，字数从0开始，第1个字为 0
   
   Declare Function LineToPos(nLine As Long) As Long  '获取第几行的第一个字符位置，位置从0 开始。失败返回 -1
   Declare Function GetTextLength() As Long  '返回以字节为单位的文档长度。
   Declare Function GetLineCount() As Long  '返回文档中的行数。空文档包含1行。仅包含行尾的文档有2行。
   Declare Function GetLineSonscreen() As Long  '返回屏幕上可见视图的总行数

   Declare Function GetModify() As Long  '如果修改了文档，则返回非零；如果未修改，则返回0。文档的修改状态由相对于保存点的撤消位置确定
   Declare Function GetSelectionStart() As Long  '返回选择的开始位置
   Declare Function GetSelectionEnd() As Long  '返回选择的位置
   Declare Function TextWidth(Text_utf8 As String) As Long  '绘制的字符串的像素宽度
   Declare Function TextHeight(nLine As Long = 0) As Long  '行高度（以像素为单位）。当前所有行的高度都相同。
   
   Declare Function IsCanPaste() As Long  '是不是可以粘贴，返回 False 不允许，非0  True 允许{=.True.False}
   Declare Function IsSelection() As Long  '是不是有选择，返回 False 不允许，非0  True 允许{=.True.False}
   Declare Function IsCanUndo() As Long  '是不是可撤消，返回 False 不允许，非0  True 允许{=.True.False}
   Declare Function IsCanRedo() As Long  '是不是可重做，返回 False 不允许，非0  True 允许{=.True.False}
   Declare Function SendMessage( Msg  As ULong, wParam  As WPARAM, lParam  As LPARAM ) As LRESULT  '控件内部直联消息，比 SendMessage 效率高。 和控件联系都是用这个。
   
   Declare Sub SetFont(FontName_utf8 As String,FontSize As Long=9,Bold As Long =0 ,Italic As Long=0 ,Underline As Long=0 , FontCharSet As String ="") '设置默认字体，参数：字体名，字体大小，加粗，斜体，下划线， 字符集
   Declare Sub SetColors(FORE As Long ,BACK As Long ) '设置颜色，参数：文本色，底色 RGB颜色值(用 BGR(r, g, b) 获取)
   Declare Sub SetLineSpace(RAASCENT As Long ,RADESCENT As Long ) '设置行间距  字符上空位，字符下空位 
   Declare Sub SetCaretLineVisible(show As Long ) '是否高亮当前行
   
                       
End Type


Property Class_Scintilla.Enabled() As Boolean                 '使能
  Return IsWindowEnabled(hWndControl)
End Property
Property Class_Scintilla.Enabled(ByVal bValue As Boolean)
  EnableWindow(hWndControl, bValue)
End Property
Property Class_Scintilla.Visible() As Boolean                 '可见
  Return IsWindowVisible(hWndControl)
End Property
Property Class_Scintilla.Visible(ByVal bValue As Boolean)
  If bValue Then
      ShowWindow(hWndControl, SW_SHOW)
  Else
      ShowWindow(hWndControl, SW_HIDE)
  End If
End Property
Property Class_Scintilla.Tag() As StringW
   Dim fp As FormControlsPro_TYPE ptr = vfb_Get_Control_Ptr(hWndControl)
   If fp Then
      Return fp->Tag
   End If
End Property
Property Class_Scintilla.Tag(sText As WString)
   Dim fp As FormControlsPro_TYPE ptr = vfb_Get_Control_Ptr(hWndControl)
   If fp Then
      fp->Tag = sText
   End If
End Property
Property Class_Scintilla.Left() As Long                '
  Dim rc As Rect
  GetWindowRect hWndControl, @rc          '获得窗体大小
  MapWindowPoints HWND_DESKTOP, GetParent(hWndControl), Cast(LPPOINT, @rc), 2
  Return rc.Left
End Property
Property Class_Scintilla.Left(ByVal nLeft As Long)
   If IsWindow(hWndControl) Then
      Dim rc As Rect
      GetWindowRect hWndControl    ,@rc          '获得窗体大小
      MapWindowPoints HWND_DESKTOP ,GetParent(hWndControl) ,Cast(LPPOINT ,@rc) ,2
      SetWindowPos(hWndControl ,0 ,nLeft ,rc.top ,0 ,0 ,SWP_NOZORDER Or SWP_NOSIZE Or SWP_NOACTIVATE)
      Dim fp As FormControlsPro_TYPE ptr = vfb_Get_Control_Ptr(hWndControl)
      if fp then
         fp->nLeft = AfxUnscaleX(nLeft)  'VFB 内部记录的是响应DPI的数值，就是永远是 DPI=100%时的数值
      end if
   End If
End Property
Property Class_Scintilla.Top() As Long     '
  Dim rc As Rect
  GetWindowRect hWndControl, @rc     '获得窗体大小
  MapWindowPoints HWND_DESKTOP, GetParent(hWndControl), Cast(LPPOINT, @rc), 2
  Return rc.Top
End Property
Property Class_Scintilla.Top(ByVal nTop As Long)
   If IsWindow(hWndControl) Then
      Dim rc As Rect
      GetWindowRect hWndControl    ,@rc          '获得窗体大小
      MapWindowPoints HWND_DESKTOP ,GetParent(hWndControl) ,Cast(LPPOINT ,@rc) ,2
      SetWindowPos(hWndControl ,0 ,rc.Left ,nTop ,0 ,0 ,SWP_NOZORDER Or SWP_NOSIZE Or SWP_NOACTIVATE)
      Dim fp As FormControlsPro_TYPE ptr = vfb_Get_Control_Ptr(hWndControl)
      if fp then
         fp->nTop = AfxUnscaleY(nTop)  'VFB 内部记录的是响应DPI的数值，就是永远是 DPI=100%时的数值
      end if
   End If
End Property
Property Class_Scintilla.Height() As Long                  '
  Dim rc As Rect
  GetWindowRect hWndControl, @rc          '获得窗体大小
  Return  rc.Bottom - rc.Top
End Property
Property Class_Scintilla.Height(ByVal nHeight As Long)
  If IsWindow(hWndControl) Then
      Dim rc As Rect
      GetWindowRect hWndControl, @rc          '获得窗体大小
      SetWindowPos(hWndControl, 0, 0, 0, rc.Right - rc.Left, nHeight, SWP_NOZORDER Or SWP_NOMOVE Or SWP_NOACTIVATE)
      Dim fp As FormControlsPro_TYPE ptr = vfb_Get_Control_Ptr(hWndControl)
      if fp then
         fp->nHeight = AfxUnscaleY(nHeight)  'VFB 内部记录的是响应DPI的数值，就是永远是 DPI=100%时的数值
      end if      
  End If
End Property
Property Class_Scintilla.Width() As Long
  Dim rc As Rect
  GetWindowRect hWndControl, @rc          '获得窗体大小
  Return rc.Right - rc.Left
End Property
Property Class_Scintilla.Width(ByVal nWidth As Long)
   If IsWindow(hWndControl) Then
      Dim rc As Rect
      GetWindowRect hWndControl ,@rc          '获得窗体大小
      SetWindowPos(hWndControl ,0 ,0 ,0 ,nWidth ,rc.Bottom - rc.Top ,SWP_NOZORDER Or SWP_NOMOVE Or SWP_NOACTIVATE)
      Dim fp As FormControlsPro_TYPE ptr = vfb_Get_Control_Ptr(hWndControl)
      If fp Then
         fp->nWidth = AfxUnscaleX(nWidth)  'VFB 内部记录的是响应DPI的数值，就是永远是 DPI=100%时的数值
      end if
   End If
End Property
Sub Class_Scintilla.Move(ByVal nLeft As Long ,ByVal nTop As Long ,ByVal nWidth As Long ,ByVal nHeight As Long)
   If IsWindow(hWndControl) Then
      Dim rc As Rect
      GetWindowRect hWndControl ,@rc          '获得窗体大小
      If nWidth <= 0  Then nWidth  = rc.Right  - rc.Left
      If nHeight <= 0 Then nHeight = rc.Bottom - rc.Top
      SetWindowPos(hWndControl ,0 ,nLeft ,nTop ,nWidth ,nHeight ,SWP_NOZORDER Or SWP_NOACTIVATE)
      Dim fp As FormControlsPro_TYPE ptr = vfb_Get_Control_Ptr(hWndControl)
      if fp then
         fp->nLeft   = AfxUnscaleX(nLeft)
         fp->nTop    = AfxUnscaleY(nTop)
         fp->nWidth  = AfxUnscaleY(nWidth)  'VFB 内部记录的是响应DPI的数值，就是永远是 DPI=100%时的数值
         fp->nHeight = AfxUnscaleY(nHeight)
      end if
   end if
   
End Sub
Sub Class_Scintilla.Size( ByVal nWidth As Long, ByVal nHeight As Long)
    If IsWindow(hWndControl) Then   
      SetWindowPos(hWndControl ,0 ,0 ,0 ,nWidth ,nHeight ,SWP_NOZORDER Or SWP_NOMOVE Or SWP_NOACTIVATE)
      Dim fp As FormControlsPro_TYPE ptr = vfb_Get_Control_Ptr(hWndControl)
      if fp then
         fp->nWidth  = AfxUnscaleY(nWidth)  'VFB 内部记录的是响应DPI的数值，就是永远是 DPI=100%时的数值
         fp->nHeight = AfxUnscaleY(nHeight)
      end if      
   End if   
End Sub
Property Class_Scintilla.IDC() As Long
  Return m_IDC
End Property
Property Class_Scintilla.IDC(NewIDC As Long)  
   m_IDC = NewIDC 
End property
Sub Class_Scintilla.SetFocus()  ' 获取键盘焦点
     .SetFocus hWndControl
End Sub
Function Class_Scintilla.Kill() As Boolean  '从窗体中销毁控件。成功返回 True
   Return DestroyWindow(hWndControl)
End Function
Property Class_Scintilla.hWnd() As.hWnd                    '句柄
  Return hWndControl
End Property
Property Class_Scintilla.hWnd(ByVal hWndNew As.hWnd)        '句柄
  hWndControl = hWndNew
  m_IDC = GetDlgCtrlID(hWndNew)
  pSci = Cast(Any Ptr, .SendMessage(hWndControl, SCI_GETDIRECTPOINTER, 0, 0))
End Property
Property Class_Scintilla.hWndForm() As.hWnd         '用于多开窗口时，要使用控件前，必须先指定控件的父句柄
  Return GetParent(hWndControl)
End Property
Property Class_Scintilla.hWndForm(ByVal hWndParent As .hWnd)         '用于多开窗口时，要使用控件前，必须先指定控件的父句柄
   hWndControl = GetDlgItem(hWndParent, m_IDC)
   pSci = Cast(Any Ptr, .SendMessage(hWndControl, SCI_GETDIRECTPOINTER, 0, 0))
End Property
Property Class_Scintilla.WindowsZ(ByVal hWndlnsertAfter As .hWnd)
   'HWND_BOTTOM,HWND_TOP,HWND_NOTOPMOST,HWND_TOPMOST,设置窗口Z位置:最后，最前，普通，置顶
   SetWindowPos(hWndControl, hWndlnsertAfter, 0, 0, 0, 0, SWP_NOSIZE Or SWP_NOMOVE Or SWP_SHOWWINDOW)
End Property
Sub Class_Scintilla.Refresh() 
  InvalidateRect(hWndControl, Null, True)
  UpdateWindow(hWndControl)
End Sub
Property Class_Scintilla.UserData(idx AS LONG) As Integer      '返回/设置用户数据，就是1个控件可以存放100个数值。
   If idx < 0 Or idx > 99 Then Return 0
   Dim fp As FormControlsPro_TYPE ptr = vfb_Get_Control_Ptr(hWndControl)
   If fp  Then
      Return fp->UserData(idx)
   End If   
End Property
Property Class_Scintilla.UserData(idx AS LONG, bValue As Integer)
   If idx < 0 Or idx > 99 Then Return
   Dim fp As FormControlsPro_TYPE ptr = vfb_Get_Control_Ptr(hWndControl)
   If fp Then
      fp->UserData(idx) = bValue
   End If
End Property

Property Class_Scintilla.Text() As String
      'if pSci = 0 Then Return ""
   If IsWindow(hWndControl)=0 Then Return "" 
   Dim nLen   As Long
   Dim buffer As String
   'nLen = SciMsg(pSci, SCI_GETLENGTH, 0, 0)
   nLen =.SendMessage(hWndControl,SCI_GETLENGTH, 0, 0)
   If nLen < 1 Then Return ""
   buffer = String(nLen + 1, 0)
   'SciMsg(pSci, SCI_GETTEXT, nLen + 1, Cast(lParam, StrPtr(buffer)))
   .SendMessage(hWndControl,SCI_GETTEXT, nLen + 1, Cast(lParam, StrPtr(buffer)))
   Property = Trim(buffer, Chr(0))
End Property
Property Class_Scintilla.Text(Text_utf8 As String)
   'if pSci = 0 Then Return
   'SciMsg(pSci, SCI_SETREADONLY, 0, 0) '取消只读，避免只读时无法设置
   'SciMsg(pSci, SCI_SETTEXT, 0, Cast(lParam, StrPtr(Text_utf8)))
   'SciMsg(pSci, SCI_COLOURISE, 0, -1)  '启动语法分析
   'SciMsg(pSci, SCI_EMPTYUNDOBUFFER, 0, 0)  '设置无撤销
   If IsWindow(hWndControl) Then
      .SendMessage(hWndControl, SCI_SETREADONLY, 0, 0)
      .SendMessage(hWndControl, SCI_SETTEXT, 0, Cast(lParam, StrPtr(Text_utf8)))
      .SendMessage(hWndControl, SCI_COLOURISE, 0, -1)
      .SendMessage(hWndControl, SCI_EMPTYUNDOBUFFER, 0, 0)
   End If
End Property

Property Class_Scintilla.TextLine(nLine As Long) As String
   'If pSci = 0 Then Return ""
   If IsWindow(hWndControl)=0 Then Return ""
   Dim nLen   As Long
   Dim buffer As String
   'nLen = SciMsg(pSci, SCI_LINELENGTH, nLine, 0)
   nLen = .SendMessage(hWndControl, SCI_LINELENGTH, nLine, 0)
   If nLen < 1 Then Return ""
   buffer = Space(nLen)
   'SciMsg(pSci, SCI_GETLINE, nLine, Cast(lParam, StrPtr(buffer)))
   .SendMessage(hWndControl,SCI_GETLINE, nLine, Cast(lParam, StrPtr(buffer)))
   Property = RTrim(buffer, Any Chr(13, 10, 0))
End Property
Property Class_Scintilla.TextLine(nLine As Long, Text_utf8 As String)
   'if pSci = 0 Then Return
   'Dim nStartPos As Long = SciMsg(pSci, SCI_POSITIONFROMLINE, nLine, 0)
   'Dim nEndPos As Long = SciMsg(pSci, SCI_GETLINEENDPOSITION, nLine, 0)
   'SciMsg(pSci, SCI_SETTARGETSTART, nStartPos, 0)
   'SciMsg(pSci, SCI_SETTARGETEND, nEndPos, 0)
   'SciMsg(pSci, SCI_REPLACETARGET, Len(Text_utf8), Cast(lParam, StrPtr(Text_utf8)))
   If IsWindow(hWndControl) Then
      Dim nStartPos As Long = .SendMessage(hWndControl, SCI_POSITIONFROMLINE, nLine, 0)
      Dim nEndPos   As Long = .SendMessage(hWndControl, SCI_GETLINEENDPOSITION, nLine, 0)
      .SendMessage(hWndControl, SCI_SETTARGETSTART, nStartPos, 0)
      .SendMessage(hWndControl, SCI_SETTARGETEND, nEndPos, 0)
      .SendMessage(hWndControl, SCI_REPLACETARGET, Len(Text_utf8), Cast(lParam, StrPtr(Text_utf8)))
   End If
End Property
Property Class_Scintilla.TextSel() As String 
      'if pSci = 0 Then Return ""
   If IsWindow(hWndControl)=0 Then Return ""    
   Dim nLen As Long
   Dim buffer As String
   'nLen = SciMsg(pSci, SCI_GETSELTEXT, 0, 0)
   nLen = .SendMessage(hWndControl,SCI_GETSELTEXT, 0, 0)
   If nLen < 1 Then Return ""
   buffer = Space(nLen)
   'SciMsg(pSci, SCI_GETSELTEXT, 0, Cast(lParam, StrPtr(buffer)))
   .SendMessage(hWndControl,SCI_GETSELTEXT, 0, Cast(lParam, StrPtr(buffer)))
   Property = Trim(buffer, Chr(0))
End Property
Property Class_Scintilla.TextSel(Text_utf8 As String)
   'if pSci = 0 Then Return
   If IsWindow(hWndControl) = 0 Then Return
   'SciMsg(pSci, SCI_REPLACESEL, NULL, Cast(lParam, StrPtr(Text_utf8)))
   .SendMessage(hWndControl, SCI_REPLACESEL, NULL, Cast(lParam, StrPtr(Text_utf8)))
End Property

Function Class_Scintilla.TextAppend(Text_utf8 As String) As Long '
   'If pSci = 0 Then Return -1
   'Function = SciMsg(pSci, SCI_APPENDTEXT, Len(Text_utf8), Cast(lParam, StrPtr(Text_utf8)))
   'SciMsg(pSci, SCI_COLOURISE, 0, -1)
   If IsWindow(hWndControl) = 0 Then Return -1
   Function = .SendMessage(hWndControl, SCI_APPENDTEXT, Len(Text_utf8), Cast(lParam, StrPtr(Text_utf8)))
   .SendMessage(hWndControl, SCI_COLOURISE, 0, -1)
End Function
Sub Class_Scintilla.TextInsert(Text_utf8 As String)
   'if pSci = 0 Then Return  
   'Dim nLen As Long = SciMsg(pSci, SCI_GETSELTEXT, 0, 0)
   'If nLen = 0 Then
   '    SciMsg(pSci, SCI_INSERTTEXT, -1, Cast(lParam, StrPtr(Text_utf8)))
   'Else
   '    SciMsg(pSci, SCI_REPLACESEL, 0, Cast(lParam, StrPtr(Text_utf8)))
   'End If
   'SciMsg(pSci, SCI_COLOURISE, 0, -1)
   If IsWindow(hWndControl)=0 Then Return    
   Dim nLen As Long = .SendMessage(hWndControl, SCI_GETSELTEXT, 0, 0)
   If nLen = 0 Then
       .SendMessage(hWndControl, SCI_INSERTTEXT, -1, Cast(lParam, StrPtr(Text_utf8)))
   Else
       .SendMessage(hWndControl, SCI_REPLACESEL, 0, Cast(lParam, StrPtr(Text_utf8)))
   End If
   .SendMessage(hWndControl, SCI_COLOURISE, 0, -1)   
   
End Sub
Sub Class_Scintilla.FoldAll()
   'if pSci = 0 Then Return  
   If IsWindow(hWndControl)=0 Then Return 
   Dim i As Long
   Dim nLines As Long
   Dim nFoldLevel As Long
   '强制词法分析器设置整个文档的样式
   'SciMsg(pSci, SCI_COLOURISE, -1, 0)
   'nLines = SciMsg(pSci, SCI_GETLINECOUNT, 0, 0)
   'For i = 0 To nLines
   '   '如果处于当前行号…
   '   nFoldLevel = SciMsg(pSci, SCI_GETFOLDLEVEL, i, 0)
   '   If (nFoldLevel And SC_FOLDLEVELNUMBERMASK) = SC_FOLDLEVELBASE Then
   '      If SciMsg(pSci, SCI_GETFOLDEXPANDED, i, 0) Then
   '         SciMsg(pSci, SCI_TOGGLEFOLD, i, 0)
   '      End If
   '   End If
   'Next
   .SendMessage(hWndControl , SCI_COLOURISE, -1, 0)
   nLines = .SendMessage(hWndControl , SCI_GETLINECOUNT, 0, 0)
   For i = 0 To nLines
      '如果处于当前行号…
      nFoldLevel = .SendMessage(hWndControl , SCI_GETFOLDLEVEL, i, 0)
      If (nFoldLevel And SC_FOLDLEVELNUMBERMASK) = SC_FOLDLEVELBASE Then
         If .SendMessage(hWndControl , SCI_GETFOLDEXPANDED, i, 0) Then
            .SendMessage(hWndControl , SCI_TOGGLEFOLD, i, 0)
         End If
      End If
   Next   
End Sub
Sub Class_Scintilla.FoldAllUn() ''   全部取消折叠
   'if pSci = 0 Then Return
   If IsWindow(hWndControl)=0 Then Return 
   Dim i As Long
   Dim nLines As Long
   Dim nFoldLevel As Long
   
   '强制词法分析器设置整个文档的样式
   'SciMsg(pSci, SCI_COLOURISE, -1, 0)
   'nLines = SciMsg(pSci, SCI_GETLINECOUNT, 0, 0)
   'For i = 0 To nLines
   '   '' 如果处于当前行号…
   '   nFoldLevel = SciMsg(pSci, SCI_GETFOLDLEVEL, i, 0)
   '   If (nFoldLevel And SC_FOLDLEVELNUMBERMASK) = SC_FOLDLEVELBASE Then
   '      If SciMsg(pSci, SCI_GETFOLDEXPANDED, i, 0) = 0 Then
   '         SciMsg(pSci, SCI_TOGGLEFOLD, i, 0)
   '      End If
   '   End If
   'Next
   .SendMessage(hWndControl , SCI_COLOURISE, -1, 0)
   nLines = .SendMessage(hWndControl , SCI_GETLINECOUNT, 0, 0)
   For i = 0 To nLines
      '' 如果处于当前行号…
      nFoldLevel = .SendMessage(hWndControl , SCI_GETFOLDLEVEL, i, 0)
      If (nFoldLevel And SC_FOLDLEVELNUMBERMASK) = SC_FOLDLEVELBASE Then
         If .SendMessage(hWndControl , SCI_GETFOLDEXPANDED, i, 0) = 0 Then
            .SendMessage(hWndControl , SCI_TOGGLEFOLD, i, 0)
         End If
      End If
   Next
End Sub
Sub Class_Scintilla.FoldToggle(nLine As Long)
   'if pSci = 0 Then Return
   'Dim nFoldLevel As Long = SciMsg(pSci, SCI_GETFOLDLEVEL, nLine, 0)
   'If (nFoldLevel And SC_FOLDLEVELHEADERFLAG) = 0 Then
   '   nLine = SciMsg(pSci, SCI_GETFOLDPARENT, nLine, 0)
   'End If
   'If nLine > -1 Then
   '   SciMsg(pSci, SCI_TOGGLEFOLD, nLine, 0)
   '   SciMsg(pSci, SCI_GOTOLINE, nLine, 0)
   'End If
   If IsWindow(hWndControl)=0 Then Return 
   Dim nFoldLevel As Long = .SendMessage(hWndControl, SCI_GETFOLDLEVEL, nLine, 0)
   If (nFoldLevel And SC_FOLDLEVELHEADERFLAG) = 0 Then
      nLine = .SendMessage(hWndControl, SCI_GETFOLDPARENT, nLine, 0)
   End If
   If nLine > -1 Then
      .SendMessage(hWndControl, SCI_TOGGLEFOLD, nLine, 0)
      .SendMessage(hWndControl, SCI_GOTOLINE, nLine, 0)
   End If
End Sub
Property Class_Scintilla.CurrentLineNumber() As Long
   'If pSci = 0 Then Return -1
   'Dim nPos As Long = SciMsg(pSci, SCI_GETCURRENTPOS, 0, 0)
   'Property = SciMsg(pSci, SCI_LINEFROMPOSITION, nPos, 0)
   If IsWindow(hWndControl)=0 Then Return  -1
   Dim nPos As Long = .SendMessage(hWndControl, SCI_GETCURRENTPOS, 0, 0)
   Property = .SendMessage(hWndControl, SCI_LINEFROMPOSITION, nPos, 0)      
End Property
Property Class_Scintilla.CurrentLineNumber(nLine As Long)
   'If pSci = 0 Then Return
   'Dim nPos As Long = SciMsg(pSci, SCI_POSITIONFROMLINE, nLine, 0)
   'SciMsg(pSci, SCI_SETCURRENTPOS, nPos, 0)
   'SciMsg(pSci, SCI_SETANCHOR, nPos, 0)
   If IsWindow(hWndControl)=0 Then Return 
   Dim nPos As Long = .SendMessage(hWndControl , SCI_POSITIONFROMLINE, nLine, 0)
   .SendMessage(hWndControl , SCI_SETCURRENTPOS, nPos, 0)
   .SendMessage(hWndControl , SCI_SETANCHOR, nPos, 0)   
End Property
Sub Class_Scintilla.BookmarkToggle(nLine As Long)
   'If pSci = 0 Then Return
   'Dim fMark As Long  ' 必须是32位值
   'fMark = SciMsg(pSci, SCI_MARKERGET, nLine, 0)
   'If Bit(fMark, 0) = -1 Then
   '   SciMsg(pSci, SCI_MARKERDELETE, nLine, 0)
   '   fMark = 0
   '   fMark = BitSet(fMark, 0)
   '   If SciMsg(pSci, SCI_MARKERNEXT, 0, fMark) = -1 Then '表示没书签
   '      SciMsg(pSci, SCI_SETMARGINWIDTHN, 1, 0) ' 采用动态调整，有书签 时才显示
   '   End If
   'Else
   '   SciMsg(pSci, SCI_MARKERADD, nLine, 0)
   '   SciMsg(pSci, SCI_SETMARGINWIDTHN, 1, AfxScaleX(16)) ' 采用动态调整，有书签 时才显示
   'End If
   If IsWindow(hWndControl)=0 Then Return
   Dim fMark As Long  ' 必须是32位值
   fMark = .SendMessage(hWndControl, SCI_MARKERGET, nLine, 0)
   If Bit(fMark, 0) = -1 Then
      .SendMessage(hWndControl, SCI_MARKERDELETE, nLine, 0)
      fMark = 0
      fMark = BitSet(fMark, 0)
      If .SendMessage(hWndControl, SCI_MARKERNEXT, 0, fMark) = -1 Then '表示没书签
         .SendMessage(hWndControl, SCI_SETMARGINWIDTHN, 1, 0) ' 采用动态调整，有书签 时才显示
      End If
   Else
      .SendMessage(hWndControl, SCI_MARKERADD, nLine, 0)
      .SendMessage(hWndControl, SCI_SETMARGINWIDTHN, 1, AfxScaleX(16)) ' 采用动态调整，有书签 时才显示
   End If
End Sub
Sub Class_Scintilla.BookmarkNext()
   'if pSci = 0 Then Return
   'Dim fMark As Long  ' 32 bit value
   'Dim nLine As Long = CurrentLineNumber() + 1
   'fMark = BitSet(fMark, 0)
   'nLine = SciMsg(pSci, SCI_MARKERNEXT, nLine, fMark)
   'If nLine > -1 Then
   '   SciMsg(pSci, SCI_GOTOLINE, nLine, 0)
   '   Dim pu As Long = SciMsg(pSci, SCI_LINESONSCREEN, 0, 0)
   '   SciMsg(pSci, SCI_SETFIRSTVISIBLELINE, nLine - pu / 2, 0)
   'Else
   '   nLine = SciMsg(pSci, SCI_MARKERNEXT, nLine, fMark)
   '   If nLine > -1 Then
   '      SciMsg(pSci, SCI_GOTOLINE, nLine, 0)
   '      Dim pu As Long = SciMsg(pSci, SCI_LINESONSCREEN, 0, 0)
   '      SciMsg(pSci, SCI_SETFIRSTVISIBLELINE, nLine - pu / 2, 0)
   '   End If
   'End If
   If IsWindow(hWndControl)=0 Then Return
   Dim fMark As Long  ' 32 bit value
   Dim nLine As Long = CurrentLineNumber() + 1
   fMark = BitSet(fMark, 0)
   nLine = .SendMessage(hWndControl, SCI_MARKERNEXT, nLine, fMark)
   If nLine > -1 Then
      .SendMessage(hWndControl, SCI_GOTOLINE, nLine, 0)
      Dim pu As Long = .SendMessage(hWndControl, SCI_LINESONSCREEN, 0, 0)
      .SendMessage(hWndControl, SCI_SETFIRSTVISIBLELINE, nLine - pu / 2, 0)
   Else
      nLine = .SendMessage(hWndControl, SCI_MARKERNEXT, nLine, fMark)
      If nLine > -1 Then
         .SendMessage(hWndControl, SCI_GOTOLINE, nLine, 0)
         Dim pu As Long = .SendMessage(hWndControl, SCI_LINESONSCREEN, 0, 0)
         .SendMessage(hWndControl, SCI_SETFIRSTVISIBLELINE, nLine - pu / 2, 0)
      End If
   End If
End Sub
Sub Class_Scintilla.BookmarkPrev()
   'if pSci = 0 Then Return
   'Dim fMark As Long  ' 32 bit value
   'Dim nLine As Long = CurrentLineNumber() - 1
   'Dim nLines As Long = SciMsg(pSci, SCI_GETLINECOUNT, 0, 0) - 1
   'fMark = BitSet(fMark, 0)
   'nLine = SciMsg(pSci, SCI_MARKERPREVIOUS, nLine, fMark)
   'If nLine > -1 Then
   '   SciMsg(pSci, SCI_GOTOLINE, nLine, 0)
   '   Dim pu As Long = SciMsg(pSci, SCI_LINESONSCREEN, 0, 0)
   '   SciMsg(pSci, SCI_SETFIRSTVISIBLELINE, nLine - pu / 2, 0)
   'Else
   '   nLine = SciMsg(pSci, SCI_MARKERPREVIOUS, nLines, fMark)
   '   If nLine > -1 Then
   '      SciMsg(pSci, SCI_GOTOLINE, nLine, 0)
   '      Dim pu As Long = SciMsg(pSci, SCI_LINESONSCREEN, 0, 0)
   '      SciMsg(pSci, SCI_SETFIRSTVISIBLELINE, nLine - pu / 2, 0)
   '   End If
   'End If
   If IsWindow(hWndControl)=0 Then Return
   Dim fMark As Long  ' 32 bit value
   Dim nLine As Long = CurrentLineNumber() - 1
   Dim nLines As Long = .SendMessage(hWndControl, SCI_GETLINECOUNT, 0, 0) - 1
   fMark = BitSet(fMark, 0)
   nLine = .SendMessage(hWndControl, SCI_MARKERPREVIOUS, nLine, fMark)
   If nLine > -1 Then
      .SendMessage(hWndControl, SCI_GOTOLINE, nLine, 0)
      Dim pu As Long = .SendMessage(hWndControl, SCI_LINESONSCREEN, 0, 0)
      .SendMessage(hWndControl, SCI_SETFIRSTVISIBLELINE, nLine - pu / 2, 0)
   Else
      nLine = .SendMessage(hWndControl, SCI_MARKERPREVIOUS, nLines, fMark)
      If nLine > -1 Then
         .SendMessage(hWndControl, SCI_GOTOLINE, nLine, 0)
         Dim pu As Long = .SendMessage(hWndControl, SCI_LINESONSCREEN, 0, 0)
         .SendMessage(hWndControl, SCI_SETFIRSTVISIBLELINE, nLine - pu / 2, 0)
      End If
   End If   
End Sub
Function Class_Scintilla.FindText(Text_utf8 As String, startPos As Long = 0, endPos As Long = -1, searchFlags As Long = SCFIND_NONE) As Long
   'if pSci = 0 Then Return -1
   'Dim nLen As Long = SciMsg(pSci, SCI_GETLENGTH, 0, 0)
   'if startPos = -1 Then startPos = nLen
   'if endPos = -1 Then endPos = nLen
   'Dim ccf As Sci_TextToFind
   'ccf.chrg.cpMin = startPos
   'ccf.chrg.cpMax = endPos
   'ccf.lpstrText = StrPtr(Text_utf8)
   'Function = SciMsg(pSci, SCI_FINDTEXT, searchFlags, Cast(lParam, @ccf))
   If IsWindow(hWndControl)=0 Then Return -1
   Dim nLen As Long = .SendMessage(hWndControl, SCI_GETLENGTH, 0, 0)
   if startPos = -1 Then startPos = nLen
   if endPos = -1 Then endPos = nLen
   Dim ccf As Sci_TextToFind
   ccf.chrg.cpMin = startPos
   ccf.chrg.cpMax = endPos
   ccf.lpstrText = StrPtr(Text_utf8)
   Function = .SendMessage(hWndControl, SCI_FINDTEXT, searchFlags, Cast(lParam, @ccf))   
End Function
Sub Class_Scintilla.GoToPos(nPos As Long, Weizi As Long =0 , nLength As Long =0 )
   'if pSci = 0 Then Return
   'Dim nLine As Long = SciMsg(pSci, SCI_LINEFROMPOSITION, nPos, 0) '目标行
   'Dim aLine As Long = SciMsg(pSci, SCI_GETFIRSTVISIBLELINE, 0, 0) '第一行
   'Dim uLine As Long = SciMsg(pSci, SCI_LINESONSCREEN, 0, 0)  '可显示行数
   'Dim mPos As Long =SciMsg(pSci, SCI_POSITIONFROMLINE, nLine, 0) '返回与行首相对应的文档位置
   'Select Case Weizi
   '   Case 0
   '      aLine = nLine - (uline / 3)
   '   Case 1
   '      aLine = nLine - (uline / 3 * 2)
   '   Case 2
   '      aLine = nLine - (uLine / 2)
   'End Select
   'SciMsg(pSci, SCI_SCROLLRANGE, mPos, nPos)
   'SciMsg(pSci, SCI_SETFIRSTVISIBLELINE, aLine, 0)
   'SciMsg(pSci, SCI_SETSEL, nPos, nPos + nLength)
   If IsWindow(hWndControl)=0 Then Return
   Dim nLine As Long = .SendMessage(hWndControl, SCI_LINEFROMPOSITION, nPos, 0) '目标行
   Dim aLine As Long = .SendMessage(hWndControl, SCI_GETFIRSTVISIBLELINE, 0, 0) '第一行
   Dim uLine As Long = .SendMessage(hWndControl, SCI_LINESONSCREEN, 0, 0)  '可显示行数
   Dim mPos As Long =.SendMessage(hWndControl, SCI_POSITIONFROMLINE, nLine, 0) '返回与行首相对应的文档位置
   Select Case Weizi
      Case 0
         aLine = nLine - (uline / 3)
      Case 1
         aLine = nLine - (uline / 3 * 2)
      Case 2
         aLine = nLine - (uLine / 2)
   End Select
   .SendMessage(hWndControl, SCI_SCROLLRANGE, mPos, nPos)
   .SendMessage(hWndControl, SCI_SETFIRSTVISIBLELINE, aLine, 0)
   .SendMessage(hWndControl, SCI_SETSEL, nPos, nPos + nLength)   
End Sub
Sub Class_Scintilla.GoToLine(nLine As Long, Weizi As Long =0 )
   'if pSci = 0 Then Return
   'Dim mPos As Long = SciMsg(pSci, SCI_POSITIONFROMLINE, nLine, 0) '返回与行首相对应的文档位置
   'GoToPos mPos,Weizi,0
   If IsWindow(hWndControl)=0 Then Return
   Dim mPos As Long = .SendMessage(hWndControl, SCI_POSITIONFROMLINE, nLine, 0) '返回与行首相对应的文档位置
   GoToPos mPos,Weizi,0   
End Sub
Function Class_Scintilla.PosToLine(nPos As Long) As Long
   'if pSci = 0 Then Return  -1
   'Function = SciMsg(pSci, SCI_LINEFROMPOSITION, nPos, 0) 
   If IsWindow(hWndControl)=0 Then Return  -1
   Function = .SendMessage(hWndControl, SCI_LINEFROMPOSITION, nPos, 0)    
End Function
Function Class_Scintilla.LineToPos(nLine As Long) As Long
   'if pSci = 0 Then Return  -1
   'Function = SciMsg(pSci, SCI_POSITIONFROMLINE, nLine, 0) 
   If IsWindow(hWndControl)=0 Then Return  -1
   Function = .SendMessage(hWndControl, SCI_POSITIONFROMLINE, nLine, 0)    
End Function

Property Class_Scintilla.CurrentPos() As Long 
   'if pSci = 0 Then Return -1
   'Property = SciMsg(pSci, SCI_GETCURRENTPOS, 0, 0)
   If IsWindow(hWndControl)=0 Then Return -1
   Property = .SendMessage(hWndControl, SCI_GETCURRENTPOS, 0, 0)   
End Property
Property Class_Scintilla.CurrentPos(nPos As Long)
   'if pSci = 0 Then Return
   'SciMsg(pSci, SCI_SETCURRENTPOS, nPos, 0)
   'SciMsg(pSci, SCI_SETANCHOR, nPos, 0)
   If IsWindow(hWndControl)=0 Then Return
   .SendMessage(hWndControl, SCI_SETCURRENTPOS, nPos, 0)
   .SendMessage(hWndControl, SCI_SETANCHOR, nPos, 0)   
End Property
Function Class_Scintilla.GetTextLength() As Long
   'if pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_GETTEXTLENGTH, 0, 0) 
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_GETTEXTLENGTH, 0, 0)    
End Function
Function Class_Scintilla.GetLineCount() As Long
   'If pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_GETLINECOUNT, 0, 0) 
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_GETLINECOUNT, 0, 0)    
End Function
Function Class_Scintilla.GetLineSonscreen() As Long
   'if pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_LINESONSCREEN, 0, 0) 
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_LINESONSCREEN, 0, 0)    
End Function
Function Class_Scintilla.GetModify() As Long
   'if pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_GETMODIFY, 0, 0) 
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_GETMODIFY, 0, 0)    
End Function
Function Class_Scintilla.GetSelectionStart() As Long
   'if pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_GETSELECTIONSTART, 0, 0) 
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_GETSELECTIONSTART, 0, 0)    
End Function
Function Class_Scintilla.GetSelectionEnd() As Long
   'If pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_GETSELECTIONEND, 0, 0) 
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_GETSELECTIONEND, 0, 0) 
End Function
Function Class_Scintilla.TextWidth(Text_utf8 As String) As Long 
   'if pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_TEXTWIDTH, 0, Cast(lParam, StrPtr(Text_utf8)))
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_TEXTWIDTH, 0, Cast(lParam, StrPtr(Text_utf8)))   
End Function
Function Class_Scintilla.TextHeight(nLine As Long = 0) As Long  
   'if pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_TEXTHEIGHT, nLine, 0)
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_TEXTHEIGHT, nLine, 0)   
End Function
Function Class_Scintilla.PosToX(nPos As Long) As Long
   'if pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_GETCOLUMN, nPos, 0)
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_GETCOLUMN, nPos, 0)   
End Function
Function Class_Scintilla.IsCanPaste() As Long
   'If pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_CANPASTE, 0, 0)
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_CANPASTE, 0, 0)   
End Function
Function Class_Scintilla.IsSelection() As Long
   'if pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_GETSELECTIONEMPTY, 0, 0) = 0 
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_GETSELECTIONEMPTY, 0, 0) = 0    
End Function
Function Class_Scintilla.IsCanUndo() As Long
   'if pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_CANUNDO, 0, 0) 
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_CANUNDO, 0, 0)    
End Function
Function Class_Scintilla.IsCanRedo() As Long
   'if pSci = 0 Then Return  0
   'Function = SciMsg(pSci, SCI_CANREDO, 0, 0) 
   If IsWindow(hWndControl)=0 Then Return  0
   Function = .SendMessage(hWndControl, SCI_CANREDO, 0, 0)    
End Function
Property Class_Scintilla.FirstVisibleLine() As Long
   'if pSci = 0 Then Return  0
   'Property = SciMsg(pSci, SCI_GETFIRSTVISIBLELINE, 0, 0) '第一行
   If IsWindow(hWndControl)=0 Then Return  0
   Property = .SendMessage(hWndControl, SCI_GETFIRSTVISIBLELINE, 0, 0) '第一行   
End Property
Property Class_Scintilla.FirstVisibleLine(nLine As Long)
   'If pSci = 0 Then Return
   'SciMsg(pSci, SCI_SETFIRSTVISIBLELINE, nLine, 0) 
   If IsWindow(hWndControl)=0 Then Return
   .SendMessage(hWndControl, SCI_SETFIRSTVISIBLELINE, nLine, 0)    
End Property


Sub Class_Scintilla.SetFont(FontName_utf8 As String, FontSize As Long = 9, Bold As Long = 0, Italic As Long = 0, Underline As Long = 0, FontCharSet As String = "")
   'If pSci = 0 Then Return
   'SciMsg(pSci, SCI_STYLESETFONT, STYLE_DEFAULT, Cast(lParam, StrPtr(FontName_utf8)))
   'SciMsg(pSci, SCI_STYLESETSIZE, STYLE_DEFAULT, FontSize)
   If IsWindow(hWndControl) = 0 Then Return
   .SendMessage(hWndControl, SCI_STYLESETFONT, STYLE_DEFAULT, Cast(lParam, StrPtr(FontName_utf8)))
   .SendMessage(hWndControl, SCI_STYLESETSIZE, STYLE_DEFAULT, FontSize)
   if Len(FontCharSet) Then
      Dim sc As Long
      Select Case FontCharSet
         Case "Default"       : sc = SC_CHARSET_DEFAULT
         Case "Ansi"          : sc = SC_CHARSET_ANSI
         Case "Arabic"        : sc = SC_CHARSET_ARABIC
         Case "Baltic"        : sc = SC_CHARSET_BALTIC
         Case "Chinese Big 5" : sc = SC_CHARSET_CHINESEBIG5
         Case "East Europe"   : sc = SC_CHARSET_EASTEUROPE
         Case "GB 2312"       : sc = SC_CHARSET_GB2312
         Case "Greek"         : sc = SC_CHARSET_GREEK
         Case "Hangul"        : sc = SC_CHARSET_HANGUL
         Case "Hebrew"        : sc = SC_CHARSET_HEBREW
         Case "Johab"         : sc = SC_CHARSET_JOHAB
         Case "Mac"           : sc = SC_CHARSET_MAC
         Case "OEM"           : sc = SC_CHARSET_OEM
         Case "Russian"       : sc = SC_CHARSET_RUSSIAN
         Case "Shiftjis"      : sc = SC_CHARSET_SHIFTJIS
         Case "Symbol"        : sc = SC_CHARSET_SYMBOL
         Case "Thai"          : sc = SC_CHARSET_THAI
         Case "Turkish"       : sc = SC_CHARSET_TURKISH
         Case "Vietnamese"    : sc = SC_CHARSET_VIETNAMESE
         Case Else
            sc = SC_CHARSET_DEFAULT
      End Select
      'SciMsg(pSci, SCI_STYLESETCHARACTERSET, STYLE_DEFAULT, sc )
      .SendMessage(hWndControl, SCI_STYLESETCHARACTERSET, STYLE_DEFAULT, sc)
   End If
   'SciMsg(pSci, SCI_STYLESETBOLD, STYLE_DEFAULT, Bold)
   'SciMsg(pSci, SCI_STYLESETITALIC, STYLE_DEFAULT, Italic)
   'SciMsg(pSci, SCI_STYLESETUNDERLINE, STYLE_DEFAULT, Underline)
   'SciMsg(pSci, SCI_STYLECLEARALL, 0, 0)  ' 将全局样式复制到所有其他样式
   .SendMessage(hWndControl, SCI_STYLESETBOLD, STYLE_DEFAULT, Bold)
   .SendMessage(hWndControl, SCI_STYLESETITALIC, STYLE_DEFAULT, Italic)
   .SendMessage(hWndControl, SCI_STYLESETUNDERLINE, STYLE_DEFAULT, Underline)
   .SendMessage(hWndControl, SCI_STYLECLEARALL, 0, 0) ' 将全局样式复制到所有其他样式
End Sub
Sub Class_Scintilla.SetColors(FORE As Long ,BACK As Long )
   'if pSci = 0 Then Return
   'SciMsg(pSci, SCI_STYLESETFORE, STYLE_DEFAULT, FORE)
   'SciMsg(pSci, SCI_STYLESETBACK, STYLE_DEFAULT, BACK)
   'SciMsg(pSci, SCI_STYLECLEARALL, 0, 0)  ' 将全局样式复制到所有其他样式
   If IsWindow(hWndControl)=0 Then Return
   .SendMessage(hWndControl, SCI_STYLESETFORE, STYLE_DEFAULT, FORE)
   .SendMessage(hWndControl, SCI_STYLESETBACK, STYLE_DEFAULT, BACK)
   .SendMessage(hWndControl, SCI_STYLECLEARALL, 0, 0)  ' 将全局样式复制到所有其他样式   
End Sub
Sub Class_Scintilla.SetLineSpace(RAASCENT As Long ,RADESCENT As Long )
   'if pSci = 0 Then Return
   'SciMsg(pSci, SCI_SETEXTRAASCENT, RAASCENT, RAASCENT) '字符上空位
   'SciMsg(pSci, SCI_SETEXTRADESCENT, RADESCENT, RADESCENT) '字符下空位 
        If IsWindow(hWndControl)=0 Then Return
   .SendMessage(hWndControl, SCI_SETEXTRAASCENT, RAASCENT, RAASCENT) '字符上空位
   .SendMessage(hWndControl, SCI_SETEXTRADESCENT, RADESCENT, RADESCENT) '字符下空位   
End Sub   
Sub Class_Scintilla.SetCaretLineVisible(show As Long )
   'if pSci = 0 Then Return
   'SciMsg(pSci, SCI_SETCARETLINEVISIBLE, show, 0) '
   If IsWindow(hWndControl)=0 Then Return
   .SendMessage(hWndControl, SCI_SETCARETLINEVISIBLE, show, 0) '   
End Sub    

Function Class_Scintilla.SendMessage( Msg As ULong, wParam  As WPARAM, lParam  As LPARAM ) As LRESULT  '控件内部直联消息，比 SendMessage 效率高。不可多线程操作。
   If pSci = 0 Then Return -1
   Function = SciMsg(pSci, Msg, wParam, lParam)
End Function



   






