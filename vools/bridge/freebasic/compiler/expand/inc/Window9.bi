'ÐÞ¸Ä MsgBox Overload 
'ÐÞ¸Ä "Afx/AfxGdiPlus.inc"
#Ifndef __WINDOW9_BI__
#define __WINDOW9_BI__

'#define WIN_INCLUDEALL

#include Once "windows.bi"
#Include once "win/ddraw.bi"
#Include once "win/commctrl.bi"
#Include once "win/commdlg.bi"
#include once "win/shellapi.bi"
#include once "win/shlobj.bi"
#Include once "win/tlhelp32.bi"
#include once "Afx/AfxGdiPlus.inc"
#Include once "win/richedit.bi"
#Include once "win/dshow.bi"
#Include once "win/exdisp.bi"
#Include once "win/mshtmhst.bi"
#include once "GL/glu.bi"
#Include Once "win/wininet.bi"

#Include once "zlib.bi"

#define FB_IGNORE 999999

#Define Eventmove     &h3
#Define EventSize     &h5
#define EventActivate &H6
#define EventClose    &H10
#Define EventPaint    &hF

#define EventKeyDown &h100
#define EventKeyUp   &h101

#Define EventTimer &H113

#define EventLBDown   &H201
#define EventLBUp     &H202
#define EventRBDown   &H204
#define EventRBUp     &H205
#define EventMBDown   &H207
#define EventMBUp     &H208
#Define EventDblClick WM_LBUTTONDBLCLK

#define EventMouseMove  &H200
#define EventMouseWheel &H20A

#define EventGadget   &h401
#define EventMenu  &h402

#define FB_BS_PUSHLIKE (BS_PUSHLIKE Or BS_AUTOCHECKBOX)

#Ifndef Integer32
#Define Integer32 long
#EndIf
#Ifndef UInteger32
#Define UInteger32 Ulong
#EndIf

#ifndef __incany_bi__

#define __incany_bi__

#macro IncludeBinary(strFile,lpAny)

dim shared as Ubyte ptr ##lpAny

dim shared as long  ##lpAny##__len__mem__

asm

.section .text

jmp .end_##lpAny

.section .data

.align 16

.start_##lpAny:

__##lpAny##__start__ = .

.incbin ##strFile

__##lpAny##__len = . - __##lpAny##__start__

.section .text

.align 16

.end_##lpAny:

lea eax, .start_##lpAny

mov dword ptr [lpAny], eax

mov dword ptr [##lpAny##__len__mem__] , offset __##lpAny##__len

end asm

addInclude_binary_info((##lpAny) , ##lpAny##__len__mem__)

#endmacro

#endif ' __incany_bi__


' is it a exe build ?
#if __FB_OUT_EXE__ or __FB_OUT_DLL__

 #inclib "window9"

  InitCommonControls()
  Dim As INITCOMMONCONTROLSEX InitCtrlEx
  InitCtrlEx.dwSize = sizeof(INITCOMMONCONTROLSEX)
  InitCtrlEx.dwICC  = ICC_STANDARD_CLASSES
  InitCommonControlsEx(@InitCtrlEx)

#else

' no must be a lib build declare things for internal use only

#undef export
#define export

Type ACCELERATOR
  As HACCEL hAccel
  As HWND   hwnd
End Type

#define ACCELERATORSTRUCT ACCELERATOR

Declare Function win9GetGadgetClass(ByVal hWin As HWND) As Long
Declare Sub      win9GetAcceleratorInfo(ByVal a As ACCELERATOR ptr)
Declare Function win9GetCurrent() As HWND
Declare Function win9AddNewGadget(ByVal gadget As Integer, ByVal hWin As HWND) As Integer
Declare Function win9GetGadgetFont() As Integer
Declare Function win9AddColor(byval hWin as HWND, ByVal colorBKD_ as Integer, ByVal colorText_ as Integer) As Integer
Declare Function win9GetGuiWinProc() As Integer
Declare Function win9GetGuiMSG() As Integer
Declare Sub      win9SetDCPrint(byval pHdc As HDC)
Declare Function win9SetGadgetColor(ByVal hWin As HWND,ByVal colorBKD_ As integer,ByVal colorText_ As Integer, ByVal flag As byte) As byte
Declare Function win9SetErrorColor(ByVal colorBKD_ As Integer) As Integer
Declare Function win9SetCurrentColors(ByVal colorBKD_ As Integer, ByVal colorText_ As integer) As Integer
declare Sub      win9SetMDIClient(ByVal hWin As HWND)
Declare Sub      win9removeMenu(ByVal menu As Integer)

#EndIf

Namespace window9
  Type FontPrint
    as string Name_
    as integer size
    as integer Bold
    as integer Italic
    as integer Underline
    as integer StrikeOut
  End Type
  Type SinglePoint
    as single x,y
  End Type
  Declare function StartPrinter(ByRef Scale As SinglePoint Ptr=0, ByVal Flagstart As Integer=1) As HDC
  Declare Sub StopPrinter()
  Declare Sub FramePage(ByRef Left_ As Integer, ByRef Right_ As Integer, ByRef Top As Integer, ByRef Bottom As Integer)
  Declare Sub PrintText(ByRef text As String, byval L As Integer=0, byval T As Integer=0, byval R As Integer=0, byval B As Integer=0, byval flag As Integer=0)
  Declare Sub PrintImage(ByVal bitmap_ As HBITMAP,ByVal x As Integer, ByVal y As Integer)
  Declare Sub ColorPrinter(byval ColorText As Integer=0, byval colorBK As Integer=-1, byval Flag As Integer=1)
  Declare Sub FontPrinter(byval Font As FontPrint Ptr=0)
  Declare Sub GetRealSize(ByRef X As Integer, ByRef Y As Integer)
  Declare Function GetCountLine() As Integer
  Declare Sub GetFullSize(ByRef X As Integer, ByRef Y As Integer)
  Declare Sub GetLenString(ByRef Str_ As String, ByRef X As Integer, ByRef Y As Integer)
  Declare function GetCountDoc() As Integer
  Declare Sub DocumentStart()
  Declare Sub DocumentEnd()
  Declare Sub PageStart()
  Declare Sub PageEnd()
End Namespace

Declare Sub SleepW9(byval n as integer)

' events
Declare Function WindowEvent() As Long
Declare Function WaitEvent() As Long
Declare Function EventNumber() As Integer
Declare Function MouseX() As Integer
Declare Function MouseY() As Integer
Declare Function EventHwnd() As HWND
Declare Function EventKEY() As Integer
Declare Function EventNumberToolBar() As Integer
Declare Function EventNumberListView() As Integer
Declare Function EventNumberTreeView() As Integer
Declare Function EventWParam() As WPARAM
Declare Function EventLParam() As LPARAM

' window
Declare Function OpenWindow(ByRef sName As String, _
                            ByVal x As Integer, ByVal y As Integer, _
                            ByVal w As Integer, ByVal h As Integer, _
                            ByVal Style As Integer=WS_OVERLAPPEDWINDOW or WS_VISIBLE, _
                            ByVal ExStyle As Integer=0, _
                            ByVal User_data_Sub as any ptr = 0) As HWND

Declare Sub Close_Window(ByVal hWin As HWND)
Declare sub DisableWindow(ByVal hWin As HWND, ByVal state As Long) 
Declare Sub HideWindow(ByVal hWin As HWND, ByVal state As Long)
Declare Sub CenterWindow(ByVal hWin As HWND)
Declare Sub WindowColor(ByVal hWin As HWND, ByVal iColor As ulong) 
Declare sub UseGadgetList(byval hWin As HWND) 
Declare Function SizeX() As Integer
Declare Function SizeY() As Integer
Declare Sub ResizeWindow(ByVal hWin As HWND, _
                              ByVal x As Long=FB_ignore, ByVal y As Long=FB_ignore, _
                              ByVal w As Long=FB_ignore, ByVal h As Long=FB_ignore)
Declare Function WindowX(ByVal hWin As HWND) As Integer
Declare Function WindowY(ByVal hWin As HWND) As Integer
Declare Function WindowWidth(ByVal hWin As hWnd) As Integer
Declare Function WindowHeight(ByVal hWin As HWND) As Integer
Declare Function WindowClientWidth(ByVal hWin As HWND) As Integer
Declare Function WindowClientHeight(ByVal hWin As HWND) As Integer
Declare sub WindowBounds(ByVal hWin As HWND, byval MinimalWidth As Long ,ByVal  MinimalHeight As Long, byval MaximalWidth As Long, ByVal MaximalHeight As long)
Declare Function SetWindowStyle(byval hWin As HWND, byval Style As Integer, byval ExStyle As Bool=0, byval added As BOOL = 0) As Integer
Declare Function GetClassName_(byval hWin As HWND) As String

#Ifndef UNICODE

#Undef GetWindowText
Declare Function GetWindowText overload(byval hWin As HWND) As String
Declare Function GetWindowText overload(byval hWin as HWND, byval buf as LPSTR, byval lenBuf as integer) as Integer
#EndIf

Declare sub SetWindowTop(ByVal hWin As HWND, ByVal state As Integer)
Declare Function SetTransparentWindow(ByVal hWin As HWND, ByVal AlphaState As Integer) As Integer
Declare Function WindowBackgroundImage(ByVal hWin As HWND, ByVal bitmap_ As HBITMAP, ByVal param As Integer=0) As Integer
Declare Function AddKeyboardShortcut(ByVal hWin As HWND, ByVal Syskey As Integer, ByVal Shortcut As integer, ByVal ID_Event As Integer)As HACCEL
Declare sub DeleteAllKeyboardShortcut(ByVal hWin As HWND)
Declare function IsMouseOver(ByVal hWin As HWND) As Integer

' gadget
Declare Function ID_In_Number(ByVal hWin As HWND) As Integer
Declare Function GadgetID(ByVal gadget As Integer) As HWND
Declare Sub FreeGadget(ByVal gadget As Long) 
Declare Function GadgetX(ByVal gadget As long) As Long
Declare Function GadgetY(ByVal gadget As Long) As Long
Declare Function GadgetWidth(ByVal gadget As long) As long
Declare Function GadgetHeight(ByVal gadget As long) As Long
Declare sub ResizeGadget(ByVal gadget As long, ByVal x As long=FB_ignore, ByVal y As long=FB_ignore, ByVal w As long=FB_ignore,ByVal h As Long=FB_ignore) 
Declare Sub DisableGadget(ByVal gadget As long, ByVal state As long)
Declare sub HideGadget(ByVal gadget As Long, ByVal state As Long)

Declare Function GetGadgetText(ByVal gadget As Long) As String
Declare Sub SetGadgetText(ByVal gadget As long, ByRef Text As string)

Declare Function GetGadgetState(ByVal gadget As long) As Integer
Declare Sub SetGadgetState(ByVal gadget As long, ByVal state As Long)

Declare Function GetGadgetAttribute(ByVal gadget As Integer, ByVal Attribut As Integer) As Integer
Declare Function SetGadgetAttribute(ByVal gadget As Integer ,ByVal Attribut As Integer, ByVal ValueMax As Integer, ByVal ValueMin As Integer=0) As Integer

Declare Sub SetGadgetColor(byval gadget As Long, ByVal colorBKD_ as Long, ByVal colorText_ as Long, ByVal flag as Long)
Declare Function GetGadgetColor(byval gadget as Long ,ByVal flag as Long ) As Integer

Declare Sub UpdateItem(ByVal gadget As long,ByVal item As long)
Declare Function SetGadgetStyle(byval gadget As Long, byval style As Integer, byval ExStyle As Bool=0, byval added As BOOL = 0) As Integer

' statusbar
Declare Function StatusBarGadget(ByVal gadget As long, ByRef SingleText As String="", ByVal style As integer=0, ByVal style2 As integer=0) As HWND
Declare Sub      RemoveStatusbar(byval gadget As Integer)
Declare sub SetStatusBarField(ByVal gadget As Long ,ByVal NField As long, ByVal Width_ As Long, ByRef Text As String) 
Declare Sub ToolTipStatusBar(ByVal gadget As Integer, ByVal NumberField As Integer, ByRef text As String)

' combobox
Declare Function ComboBoxGadget(ByVal gadget As Long, _
                                ByVal x As Long, ByVal y As Long, _
                                ByVal w As Long, ByVal h As Long, _
                                ByVal Style As Long=CBS_DROPDOWNLIST Or WS_VSCROLL) As HWND
Declare sub ShowListComboBox(ByVal gadget As long, ByVal state As long=0)
Declare Function LenItemTextComboBox(ByVal gadget As long, ByVal item As long=0) As Integer
Declare sub AddComboBoxItem(ByVal gadget As long, ByRef sItem As String, ByVal iPos As Long)
Declare sub DeleteComboBoxItem(ByVal gadget As long, ByVal iPos As long)
Declare Function GetComboBoxText(ByVal gadget As long, ByVal iPos As long) As String
Declare Function CountItemComboBox(ByVal gadget As long) As Integer
Declare Sub ResetAllComboBox(ByVal gadget As long)
Declare Function FindItemComboBox(ByVal gadget As Long, ByRef sItem As String, ByVal Startpos As Long = -1) As Integer
Declare Sub SetItemComboBox(ByVal gadget As long, ByVal number As long)
Declare Function GetItemComboBox(ByVal gadget As Long) As Integer
Declare sub FileComboBoxItem(ByVal gadget As long, ByRef File_AND_MASK As String, ByVal ATTRIBUT As long=DDL_READWRITE or DDL_READONLY Or DDL_HIDDEN or DDL_SYSTEM or DDL_DIRECTORY) 
Declare Function ComboBoxImageGadget(ByVal gadget As Long, _
                                     ByVal x As Long, ByVal y As Long, _
                                     ByVal w As Long, ByVal h As Long, _
                                     ByVal SizeIcon As Long=16, _
                                     ByVal Style As Long=CBS_DROPDOWNLIST Or WS_VSCROLL) As HWND
Declare Function GetHimageCombo_(ByVal gadget As Integer) As Integer
Declare Sub AddComboBoxImageItem(ByVal gadget As long, ByRef string_ As String, ByVal IDImage_ As HBITMAP, ByVal pos_ As Long) 
Declare Sub SetComboBoxItemText(ByVal gadget As Long, ByRef string_ As String, ByVal Item As Long)

' listbox
Declare Function ListBoxGadget(ByVal gadget As long, ByVal x As Long, ByVal y As Long, ByVal w As Long, ByVal h As Long, ByVal parametr As Long=LBS_SORT Or WS_VSCROLL Or WS_HSCROLL Or LBS_WANTKEYBOARDINPUT Or LBS_NOTIFY,ByVal parametr2 As Long=0) As HWND
Declare sub AddListBoxItem(ByVal gadget As Long, ByRef string_ As String, ByVal item As Long=-1)
Declare sub DeleteListBoxItem(ByVal gadget As long, ByVal pos_ As Long) 
Declare Sub FileListBoxItem(ByVal gadget As Long, ByRef File_AND_MASK As String, ByVal ATTRIBUT As Long=DDL_READWRITE or DDL_READONLY Or DDL_HIDDEN or DDL_SYSTEM or DDL_DIRECTORY) 
Declare Function FindItemListBox(ByVal gadget As Long, ByRef stri As String, ByVal Startpos As Long = -1) As Integer
Declare Function CountItemListBox(ByVal gadget As long) As Integer
Declare Sub SetSelectManyItem(ByVal gadget As long, ByVal Start As long, ByVal Finish As long, ByVal flag As long=1)
Declare Sub SetColumnWidthListBox(ByVal gadget As long, ByVal width_ As Long) 
Declare Sub SetItemListBox(ByVal gadget As long, ByVal item As Long)
Declare Function GetItemListBox(ByVal gadget As Long) As Integer
Declare Function GetSelCountListBox(ByVal gadget As long, ByVal ARRAY_ As Integer Ptr=0) As Integer
Declare Function GetListBoxText(ByVal gadget As Long, ByVal item As Long) As String
Declare Function LenItemTextListBox(ByVal gadget As Long, ByVal item As Long) As Integer
Declare Function GetTopIndexListBox(ByVal gadget As Long) As Integer
Declare sub SetTopIndexListBox(ByVal gadget As long, ByVal item As long) 
Declare sub ResetAllListBox(ByVal gadget As long)
Declare sub SetListBoxItemText(ByVal gadget As long, ByRef text As String, ByVal Item As long)

' listview
Declare Function ListViewGadget(ByVal gadget As Long, ByVal x As Long, ByVal y As Long, ByVal w As Long, ByVal h As Long, ByVal ExStyle As Long = 0, ByVal Style As Long = LVS_ICON  Or LVS_REPORT,ByVal Style2 As Long = 0,ByVal SizeIcon As Long = 16, ByVal StyleIcon As Long = LVSIL_SMALL) As HWND
Declare Function AddListViewColumn(ByVal gadget As Long, ByRef string_ As String, ByVal pos_ As Long, ByVal SubItem_ As Long, ByVal width_Column As Long, ByVal Style_Column_TEXT As Long=LVCFMT_CENTER, ByVal Style_Mask As Long=LVCF_FMT Or LVCF_SUBITEM Or LVCF_TEXT Or LVCF_WIDTH) As Long
Declare Function AddListViewItem(ByVal  iGadget As Long, ByRef sText As String, ByVal IDImage As HBITMAP, ByVal iPos As Long, ByVal iSubItem As Long, ByVal iMaskItem As Long =LVIF_TEXT Or LVIF_IMAGE) As integer
Declare Function GetSubItemListView() As Integer
Declare Function GetItemListView() As Integer
Declare Function FlagKeyListView(iState as Long = -1) As integer
Declare Function GetColumnListView() As Long
Declare Sub DeleteListViewItemsAll(ByVal gadget As Long)
Declare Sub DeleteItemListView(ByVal gadget As Long, ByVal Item As Long) 
Declare Sub DeleteIndexImageListView(ByVal gadget As long, ByVal indexImage As long)
Declare Sub DeleteListViewColumn(ByVal gadget As Long, ByVal columnIndex As Long)
Declare Function GetColumnWidthListView(ByVal gadget As Long, ByVal IndexColumn As long) As Integer
Declare Function GetItemCountListView(ByVal gadget As long) As Integer
Declare Function GetTextItemListView(ByVal gadget As long, ByVal Item As long, ByVal SubItem_ As Long) As String
Declare Sub SetColumnWidthListView(ByVal gadget As Long, ByVal IndexColumn As Long,ByVal Width_ As Long, ByVal flag As Long =-1)
Declare Function GetSelectedCountListView(ByVal gadget As Long,ByVal  iArray as long ptr = 0) As Integer
Declare Sub ReplaceTextItemListView(ByVal gadget As long, ByVal item As Long, ByVal subItem As Long, ByRef text As String)
Declare sub ReplaceTextColumnListView(ByVal gadget As Long,ByVal Column As Long, ByRef Text As String)
Declare Function ReplaceImageListView(ByVal gadget As long, ByVal indexImage As Integer, ByVal Image As HBITMAP) As Integer
Declare Sub SetSelectListViewItem(ByVal gadget As long, ByVal Item As long) 
Declare Function GetSelectedListViewItem(byval gadget As Long, byval Item as long, byval Mask As Long = LVIS_SELECTED  Or LVIS_FOCUSED) As Integer

'ExplorerListGadget
Type OptionsExplorerGadget
  szName As String*30 = "Name"
  szSize As String*15 = "Size"
  szType As String*15 = "Type"
  szModified As String*15 = "Modified"
  szCaptionError As String*15 = "Error"
  szTextError As String*50 = "Access Denied"
  iStyle As Integer  = 0
  iOneWidth As Integer = FB_IGNORE
  iTwoWidth As Integer = FB_IGNORE
  iThreeWidth As Integer = FB_IGNORE
  iFourWidth As Integer = FB_IGNORE
End Type
Declare Function ExplorerListGadget(byval gadget As long, byval x As long, byval y As long, byval w As long=400, byval h As long=300, byref szPath As String = "C:\", byval LGELocal As OptionsExplorerGadget ptr= 0) As HWND
Declare Function GetExplorerListGadgetHwnd(byval gadget As long) As HWND
Declare Function GetExplorerListGadgetPath(byval gadget As long) As String
Declare Function SetExplorerListGadgetPath(byval gadget As Integer, byref sPath As String) As BOOL
Declare Function SetExplorerListGadgetSort(byval gadget As Integer, byval Column As Integer) As Integer
Declare Function GetExplorerListGadgetCurentItem(byval gadget As long) As Integer
Declare Function SetExplorerListGadgetStyle(byval gadget As Integer, byval Style As Integer) As Integer
Declare Sub FlagExplorerListGadget(byval gadget As Integer, byval iFlag As Integer = 3)

' trackbar
Declare Function TrackBarGadget(ByVal gadget As long, ByVal x As Long , ByVal y As Long , ByVal w As Long, ByVal h As Long, ByVal min_ As Integer, ByVal max_ As Integer, ByVal style As Integer=1) As HWND
Declare Sub SetTrackBarPos(ByVal gadget As long, ByVal NewPos As long)
Declare Function GetTrackBarPos(ByVal gadget As long) As Integer
Declare Sub SetTrackBarMaxPos(ByVal gadget As Long, ByVal MaxPos As Long,ByVal flag As Long=0)
Declare Sub SetTrackBarMinPos(ByVal gadget As Long, ByVal MinPos As Long,ByVal flag As Long=0)

' calender
Declare Function CalendarGadget(ByVal gadget As long, ByVal x As long, ByVal y As long, ByVal w As long, ByVal h As long,ByVal Style As long=0) As HWND
Declare Function DateCalendarGadget(ByVal gadget As long,ByVal x As long, ByVal y As long, ByVal w As long, ByVal h As long) As HWND
Declare Function GetStateCalendar(ByVal gadget As long,ByVal flag As long=5) As Integer
Declare sub SetStateCalendar(ByVal gadget As Long,ByVal YEAR_ As Long, ByVal MONTH_ As Long, ByVal DAY_ As Long)

' treeview
#Undef TVI_ROOT
#Undef TVI_FIRST
#Undef TVI_LAST
#Undef TVI_SORT
#define TVI_ROOT  &hFFFF0000
#define TVI_FIRST  &hFFFF0001
#define TVI_LAST  &hFFFF0002
#define TVI_SORT  &hFFFF0003
Declare Function TreeViewGadget(ByVal gadget As Long, ByVal x As Long, ByVal y As Long, ByVal w As Long, ByVal h As Long, ByVal Style As Long= 0, ByVal ExStyle As Long=0, ByVal SizeIcon As Long=16)As HWND
Declare Function AddTreeViewItem OverLoad(ByVal gadget As long, ByRef string_ As String, ByVal IDImage_0 As HBITMAP, ByVal IDImage_Selected As HBITMAP, ByVal pos_ As integer, ByVal parent As Integer=0) As Integer
Declare Function AddTreeViewItem(ByVal gadget As Long, ByRef string_ As String,ByVal IDImage_0 As HICON,ByVal IDImage_Selected As HICON,ByVal pos_ As Long,ByVal parent As Integer=0) As Integer
Declare Function GetItemTreeView(ByVal iGadget as Long) As Integer
Declare sub DeleteTreeViewItem(ByVal gadget As Long, ByVal Item As integer)
Declare Function GetCountItemTreeView(ByVal gadget As long) As Integer
Declare Sub ReplaceImageItemTreeView OverLoad(ByVal gadget As Integer, ByVal item As Integer, ByVal image As Hbitmap=0,ByVal Selectimage As Hbitmap=0)
Declare Sub ReplaceImageItemTreeView (ByVal gadget As Integer, ByVal item As Integer, ByVal image As HICON=0  ,ByVal Selectimage As HICON=0)
Declare Sub RenameItemTreeView(ByVal gadget As Integer,ByVal item As Integer, ByVal String_ As String)
Declare Function GetIndexImageTreeView(ByVal gadget As Long, ByVal item As Integer,ByVal flag As Long=0) As Integer
Declare Function GetTextTreeView(ByVal gadget As long, ByVal item As Integer) As String
Declare Function MoveItemTreeView(ByVal gadget As long,ByVal itembegin As Integer, ByVal itemend As Integer, ByVal Parent As Integer) As Integer

' ipstringfield
Declare Function IpAddressGadget(ByVal gadget As Integer, ByVal x As Integer, ByVal y As Integer, ByVal w As Integer, ByVal h As Integer) As HWND
Declare Sub SetIpAddress(ByVal gadget As Long, byref IP_ADDRESS As string)
Declare Function GetIpAddress(ByVal gadget As long) As String

' toolbar
Declare Function CreateToolBar(ByVal nID As Integer=0, ByVal Style As Integer=CCS_ADJUSTABLE or CCS_NODIVIDER, ByVal ExStyle As Integer=0) As Integer
Declare Function ToolBarStandardButton(ByVal hwndToolBar As Integer, ByVal ButtonID As Integer, ByVal IndexImage As Integer, ByRef String_ As String="", ByVal PositionButton As Integer=-1, ByVal State As Integer=4, ByVal Style As Integer=0) As Integer
Declare Function ToolBarImageButton(ByVal hwndToolBar As Integer, ByVal buttonID As Integer, ByVal ImageID_ As Integer, ByRef String_ As String="", ByVal PositionButton As Integer=-1, ByVal State As Integer=4, ByVal Style As Integer=0, ByVal SizeIcon As Integer=16) As Integer
Declare Sub DeleteButtonToolBar(ByVal hwndToolBar As Integer, ByVal IndexButton As long) 
Declare Sub SetButtonToolBarState(ByVal hwndToolBar As Integer, ByVal IdButton As Integer, ByVal flag As Long, ByVal State As Long) 
Declare Function GetButtonToolBarState(ByVal hwndToolBar As Integer, ByVal IdButton As Integer, ByVal flag As long) As integer
Declare Function CountButtonToolBar(ByVal hwndToolBar As Integer) As Integer
Declare sub ToolBarToolTip(ByVal Hwnd As hwnd, ByVal buttonID As Integer, ByRef toolTipS As String) 
Declare sub SetToolBarToolTipFont(ByVal HwndToolBar As integer, ByVal Font_ As integer) 
Declare sub SetToolBarToolTipColor(ByVal HwndToolBar As Integer, ByVal colorBk_ As Integer=0, ByVal colorText_ As Integer=0, ByVal flag As Integer=0) 
Declare Function GetToolBarTextButton(byval HwndToolBar As Integer, ByVal ButtonID As Integer) As String
Declare sub SetToolBarButtonSize(byval HwndToolBar As Integer, ByVal w As Integer, ByVal h As Integer)
Declare Function ToolBarSeparator(ByVal hwndToolBar As Integer, ByVal IndexButton As Integer=-1 , ByVal  iFlagDrawSeparator as Long = 1) As Integer
Declare sub DeleteToolBar(ByVal hwndToolBar As Integer)

' image
Declare Function ImageGadget(ByVal gadget As Long, ByVal x As Long, ByVal y As Long, ByVal w As Long, ByVal h As Long, ByVal imageId As Any Ptr = 0, byval ExSyle As Long =0, byval Style As Long = SS_BITMAP) As HWND
Declare sub SetImageGadget(ByVal gadget As long, ByVal imageID As HBITMAP) 
Declare Sub SetIconGadget(ByVal gadget As Long, ByVal icon As HICON) 

declare Function Load_ImageA(byref sFileName as String) as Any Ptr
declare function Load_Image(byref sFileName as String,ByVal ColorBack As Integer=0) as HBITMAP
declare Function Catch_Image(byval array  As UByte Ptr, byval color_ As COLORREF=&hf0f0f0) As HBITMAP
declare Function Catch_ImageA(byval array As Ubyte ptr) As Any ptr
Declare Function LoadImageFromResource(byval lpResName As LPCTSTR, byval color_ As Integer=&hf0f0f0) As HBITMAP
Declare Function LoadImageFromResourceA(byval lpResName As LPCTSTR) As Any ptr

Declare sub Free_Image(ByVal hBmp As HBITMAP)
Declare Sub      FreeGpBitmap(ByVal GpBitmap As Any Ptr)

declare function Image_Height(ByVal hBmp As HBITMAP) as Long
declare function Image_Width(ByVal hBmp As HBITMAP) as Long
declare Function Image_WidthA(byval GpImage as Any Ptr) as Integer
declare Function Image_HeightA(byval GpImage as Any Ptr) as Integer
declare function Resize_Image(ByVal hBmp As HBITMAP, ByVal w As Integer, ByVal h As Integer) as HBITMAP
declare Sub Resize_ImageA(ByRef GpImage as Any Ptr,ByRef w As Single=0, ByRef h As Single=0)
declare Function Copy_ImageA(byval GpImage as Any Ptr) as Any Ptr
declare function Copy_Image(ByVal hBmp As HBITMAP) as HBITMAP
declare Sub Save_Image(ByVal hBmp As HBITMAP,ByRef sFileName As String)
Declare Function Save_ImageA(ByVal GpBitmap As Any Ptr, ByRef sFileName As string) as Integer
Declare Function Grab_Image(ByVal soursehBmp As HBITMAP, ByVal x As Integer,ByVal y As Integer, ByVal w As Integer, ByVal h As Integer) As HBITMAP
Declare Function Grab_ImageA(byval GpImage as Any Ptr,ByVal x As Single=0, ByVal y As Single=0, Byref w As Single=0, ByRef h As Single=0) as Any Ptr
Declare Function CreateCopyImageWindow(ByVal hWin As HWND, ByVal iFlag as Long = 0) As HBITMAP
Declare Function CreateCopyImageWindowClient(ByVal hWin As HWND, ByVal iFlag as Long = 0) As HBITMAP
Declare Function CreateCopyImageDesktop() As HBITMAP
Declare Function CreateCopyImageRect(ByVal hWin As HWND,ByVal x As long,ByVal y As Long,ByVal w As Long,ByVal h As Long ,ByVal  iFlag as Long = 0) As HBITMAP
Declare Function Create_Image(ByVal w As long, ByVal h As long) As HBITMAP
Declare Function Create_ImageA(ByVal w As Single, ByVal h As Single) As Any Ptr
Declare Function CreateHBitmapFromGpBitmap(ByVal GpBitmap As Any Ptr,ByVal BackColor As Integer=&hf0f0f0) As HBITMAP
Declare Function CreateGPBitmapFromHBitmap(ByVal hBmp As HBITMAP) As Any Ptr

Declare Function Rotate4_Image(ByVal soursehBmp As HBITMAP, ByVal angle As Integer) As HBITMAP
Declare Sub RotateAndScaleImage(ByVal sourcehBmp As HBITMAP, ByRef hbmpDest As HBITMAP, ByVal X As Integer, ByVal Y As Integer,ByVal Xr As Integer,ByVal Yr As Integer,ByVal angle As Single,ByVal Xscale As Single=0,ByVal Yscale As Single=0,ByVal Color_ As integer=0,ByVal BGbitmap As HBITMAP=0)
Declare Sub RotateAndScaleImageA(Byval GpbitmapSource As Any Ptr, ByRef hbmpDest As HBITMAP, ByVal X As Integer, ByVal Y As Integer,ByVal Xr As Integer,ByVal Yr As Integer,ByVal angle As Single,ByVal Xscale As Single=0,ByVal Yscale As Single=0,ByVal Color_ As Integer=0,ByVal BGbitmap As Any ptr=0)

' icon
Declare Function CreateIconOrCursorFromFile(ByRef sFileName As String) As HICON
Declare Function CreateIconOrCursorFromBitmap(ByVal hBmp As HBITMAP) As HICON
Declare Function CreateIconOrCursorFromGpBitmap(ByVal GpBitmap As Any Ptr) As HICON
Declare Function SaveIconOrCursor(byval hIco As HICON, byref sFileName As String) As Integer
Declare Function Load_Icon(ByRef sFileName As String) As HICON
Declare Function Extract_Icon(byref sFileName as String, ByVal number As Integer,ByVal colorBk As Integer=&hf0f0f0) as HBITMAP

' button
Declare Function ButtonImageGadget(ByVal gadget As Long, _
                                   ByVal x As Long, ByVal y As Long, _
                                   ByVal w As Long, ByVal h As Long, _
                                   ByVal imageId As Any ptr = 0, _
                                   ByVal Style As Long=BS_BITMAP) As HWND
Declare Function ButtonGadget(ByVal gadget As Long, _
                              ByVal x As Long, ByVal y As Long, _
                              ByVal w As Long, ByVal h As Long, _
                              ByRef s As String="", ByVal Style As Long=0) As HWND
Declare Function CheckBoxGadget(ByVal gadget As Long, _
                                ByVal x As Long, ByVal y As long, _
                                ByVal w As Long, ByVal h As Long, _
                                ByRef s As String="", ByVal Style As Long=3) As HWND
Declare Function TextGadget(ByVal gadget As Integer, _
                            ByVal x As Integer, ByVal y As Integer, _
                            ByVal w As Integer, ByVal h As Integer, _
                            ByRef s As String="", ByVal Style As Integer=SS_NOTIFY) As HWND
Declare Function OptionGadget(ByVal gadget As Long, _
                              ByVal x As Long, ByVal y As Long, _
                              ByVal w As Long, ByVal h As Long, _
                              ByRef s As String="", ByVal Style As Long = 9) As HWND
Declare Function StringGadget(ByVal gadget As long, _
                              ByVal x As Long, ByVal y As Long, _
                              ByVal w As Long, ByVal h As Long, _
                              ByRef s As String="", _
                              ByVal Style As Long=0, _
                              ByVal ExStyle As Long=0) As HWND
Declare Function HyperLinkGadget(ByVal gadget As Long, _
                                 ByVal x As Long, ByVal y As Long, _
                                 ByVal w As Long, ByVal h As Long, _
                                 ByRef s As String="") As HWND
Declare Function SpinGadget(ByVal gadget As Long, _
                            ByVal x As Long, ByVal y As Long, _
                            ByVal w As long, ByVal h As Long, _
                            ByVal maxvalue As integer, ByVal minvalue As Integer, _
                            ByVal curvalue As Integer, ByVal style As Integer=2 Or 4, ByVal style2 As Integer=0) As HWND
Declare Function GroupGadget(ByVal gadget As Long, _
                             ByVal x As Long, ByVal y As Long, _
                             ByVal w As Long, ByVal h As Long, _
                             ByRef s As String="") As HWND

Declare Function ProgressBarGadget(ByVal gadget As Long, _
                                   ByVal x As Long, ByVal y As Long, _
                                   ByVal w As Long, ByVal h As Long, _
                                   ByVal BeginPos As Long=0, ByVal EndPos As Long=0, _
                                   ByVal style As Long=0) As HWND
Declare Sub SetRangeProgressBar(ByVal gadget As Long, ByVal BeginPos As Integer, ByVal EndPos As Integer)
Declare Sub SetXProgressBarColor(ByVal gadget As long, ByVal iColor As Long)

' browser
Declare Function WebGadget(ByVal Gadget As Long, _
                           ByVal x As Long, ByVal y As Long, _
                           byval w As Long, byval h As Long, _
                           byref URL As String=" ", _
                           ByVal Style As Integer=0, ByVal ExStyle As Integer=0) As Integer Ptr
Declare Sub WebGadgetNavigate(ByVal pIWebBrowser As Integer Ptr, ByVal URL As wString ptr) 
Declare Sub WebGadgetGoForward(ByVal pIWebBrowser As Integer Ptr)
Declare Sub WebGadgetGoBack(ByVal pIWebBrowser As Integer Ptr)
Declare sub WebGadgetRefresh(ByVal pIWebBrowser As Integer Ptr)
Declare Function WebGadgetGetURL(ByVal pIWebBrowser As Integer Ptr) As String
Declare function WebGadgetState(ByVal pIWebBrowser As Integer Ptr) As Integer
Declare Sub WebGadgetStop(ByVal pIWebBrowser As Integer Ptr) 
Declare Function WebGadgetGetBody(ByVal pIWebBrowser As Integer Ptr,ByVal flag As long=0) As String
Declare Sub      WebGadgetSetBody(ByVal pIWebBrowser As Integer Ptr,ByVal text As String)

' tooltip
Declare Function GadgetToolTip(ByVal parentGadget as long, ByRef text As String, ByVal gadget As long=0) As Integer
Declare Sub DelToolTip(ByVal parentGadget as long, ByVal gadget As long)
Declare Sub DisableToolTip(ByVal gadget As Long, ByVal state As long)
Declare Function GetToolTipText(ByVal parentGadget as Long, ByVal gadget As Long) As string
Declare Sub SetToolTipText(ByVal parentGadget as long, ByVal gadget As Long, ByRef text As String)

' menu
Declare Function Create_Menu() As HMENU
Declare Function CreatePopMenu() As HMENU
Declare sub CreateIconItemMenu(ByVal menu As HMENU, ByVal Number As Long, ByVal ImageId As Hbitmap)
Declare Function MenuTitle(ByVal menu As HMENU, ByRef name_ As String ) As HMENU
Declare Function MenuItem  OverLoad(ByVal number As Integer,ByVal menu As HMENU,Byref sName As String, ByVal flag As Integer=0 ) As Integer
Declare Function MenuItem  OverLoad(ByVal number As Integer,ByVal menu As HMENU,ByVal iName As integer, ByVal flag As Integer=MF_BITMAP ) As Integer
Declare Function Insert_Menu  OverLoad(ByVal number As Integer,ByVal menu As HMENU,Byref sName As string, ByVal NumberSpace As Integer,ByVal flag As Integer=0) As Integer
Declare Function Insert_Menu  OverLoad(ByVal number As Integer,ByVal menu As HMENU,ByVal iName As integer, ByVal NumberSpace As Integer,ByVal flag As Integer=MF_BITMAP) As Integer
Declare Function MenuBar(ByVal menu As HMENU) As Integer
Declare Function OpenSubMenu(ByVal menu As HMENU, ByRef sName As String) As HMENU
Declare sub Delete_Menu(ByVal menu As HMENU)
Declare Sub HideMenu(ByVal menu As HMENU, ByVal State As Long) 
Declare Function FreeMenu(ByVal menu As HMENU) As Integer
Declare Function Modify_Menu OverLoad(ByVal Soursenumber As Integer,ByVal menu As HMENU,ByRef sName As string, ByVal Newnumber As Integer=FB_IGNORE,ByVal flag As Integer=0) As Integer
Declare Function Modify_Menu  OverLoad(ByVal Soursenumber As Integer,ByVal menu As HMENU,ByVal iName As integer, ByVal Newnumber As Integer=FB_IGNORE,ByVal flag As Integer=MF_BITMAP) As Integer
Declare sub DeleteItemMenu(ByVal menu As HMENU, ByVal Npos As long,ByVal flag As Long=0)
Declare sub SetStateMenu(ByVal menu As HMENU, ByVal Npos As Integer,ByVal State As Integer) 
Declare Function GetStateMenu(ByVal menu As HMENU, ByVal Npos As Long) As Integer
Declare Function GetMenuItemText(ByVal menu As HMENU, ByVal Npos As Long) As string
Declare sub DisplayPopupMenu(ByVal menu As HMENU, ByVal Xpos As long=FB_IGNORE, ByVal Ypos As long=FB_IGNORE, ByVal hwnd As hwnd = Cast(hwnd,1),ByVal flag As long=TPM_VERTICAL) 
Declare Function MenuBackColor(byval menu as HMENU, byval colour as integer, byval submenues as integer) as byte

' requester
Declare Function OpenFileRequester(ByRef Title As String, ByRef curentdir As String, ByRef Pattern As String = "All files(*.*)"+Chr(0)+"*.*"+Chr(0), ByVal flag As Integer=0, ByRef templateName As String = "", ByVal  hParentWin as HWND = 0) As String
Declare Function NextSelectedFilename() As String
Declare Function SaveFileRequester(ByRef Title As String, ByRef curentdir As String, ByRef Pattern As String = "All files(*.*)"+Chr(0)+"*.*"+Chr(0), ByVal defaultsetpattern As bool=0, ByRef templateName As String = "",  ByVal hParentWin as HWND = 0) As String
Declare Function ShellFolder(byRef NameDialog as string, ByRef DefaultFolder as String, ByVal FlagOption As Integer=81) as String 'BIF_RETURNONLYFSDIRS Or BIF_USENEWUI=81
Declare Function ColorRequester(ByVal rgbCurrentUSER As Integer=0, ByVal flagg As Integer=2, ByVal hwnd As HWND=0) As COLORREF

' simple dialog
#define MessBox MsgBox
'Declare Function MsgBox Overload (ByRef Caption As String, ByRef Message As String, ByVal flag As Integer=0,ByVal  ParentWin as Hwnd = 0) As Integer

Declare Function InputBox(ByRef Caption As String="", ByRef Message As String="Enter text:", ByRef DefaultString As String="", ByVal flag As Integer=0, ByVal flag2 As Integer=0, hParentWin as Hwnd = 0) As String

' font
Declare Function LoadFont(ByRef sFileName As String , _
                          ByVal Size      As Long, _
                          ByVal Corner    As Long=0, _
                          ByVal Bold      As Long=0, _
                          ByVal Italic    As Long=0, _
                          ByVal Underline As Long=0, _
                          ByVal StrikeOut As long=0) As integer
Declare Function SetGadgetFont(ByVal gadget As Long = -1 ,ByVal Font As integer=-1) As Integer
Declare Function FontRequester(byval hWin As HWND = 0, byval nColor As Integer = 0) As integer
Declare Function SelectedFontColor() As Integer
Declare Function SelectedFontName() As String
Declare Function SelectedFontSize() As Integer
Declare Function SelectedFontStyle(ByVal style As Byte) As Byte
declare sub FreeFont(iFont as integer)

' clipboard
Declare Function GetClipBoardText() As String
Declare Sub SetClipBoardText(ByRef Text As String)
Declare Function GetClipBoardImage() As HBITMAP
Declare Sub SetClipBoardImage(ByVal hbmp As HBITMAP) 
Declare Function GetClipBoardFile() As String
Declare Function SetClipboardFile(byRef sFile As String) As Integer
Declare Function ClearClipBoard() As Integer

' file
declare Function Create_File(ByRef FileName As String,ByVal PAR As Integer=FILE_ATTRIBUTE_NORMAL) As HANDLE
declare Function Open_File(ByRef FileName As String,ByVal PAR As Integer=FILE_ATTRIBUTE_NORMAL) As HANDLE
declare Function Read_File(ByRef FileName As String,ByVal PAR As Integer=FILE_ATTRIBUTE_NORMAL) As HANDLE
declare Sub Close_File(Byref H As HANDLE)
declare Function Size_File(ByVal fileHandle As HANDLE) As Integer
declare Function E_O_F(ByVal fileHandle As HANDLE) As Long
declare Function Get_File_Pointer(ByVal fileHandle As HANDLE) As Integer
declare sub Set_File_Pointer(ByVal fileHandle As HANDLE,ByVal Number As Integer, ByVal Method As Integer=1) 

declare Function Read_Character(ByVal fileHandle As HANDLE) As String
declare Function Read_Byte(ByVal fileHandle As HANDLE) As Byte
declare Function Read_Word(ByVal fileHandle As HANDLE) As Short
declare Function Read_Long(ByVal fileHandle As HANDLE) As Long
#define Read_Integer Read_Long
declare Function Read_Single(ByVal fileHandle As HANDLE) As Single
declare Function Read_Double(ByVal fileHandle As HANDLE) As Double
declare Function Read_LongInt(ByVal fileHandle As HANDLE) As LongInt
Declare sub Read_Data(ByVal fileHandle As HANDLE,ByRef pMemory As Byte ptr ,ByVal Lenght As Integer) 
Declare Function Read_DataA(ByVal fileHandle As HANDLE, ByVal Lenght As Integer) As Byte Ptr
Declare Function Read_DataS(ByVal fileHandle As HANDLE, ByVal Lenght As Integer) As Byte Ptr
Declare Function Read_String(ByVal fileHandle As HANDLE) As String

declare sub Write_Character(ByVal fileHandle As HANDLE, ByRef CHAR As String)
declare sub Write_Byte(ByVal fileHandle As HANDLE, ByVal Byte_ As Byte) 
declare Sub Write_Word(ByVal fileHandle As HANDLE, ByVal Word_ As Short) 
declare Sub Write_Long(ByVal fileHandle As HANDLE, ByVal i32 As long)
#define Write_Integer Write_Long
declare sub Write_Single(ByVal fileHandle As HANDLE, ByVal Single_ As Single) 
declare Sub Write_Double(ByVal fileHandle As HANDLE, ByVal Double_ As Double) 
declare Sub Write_String(ByVal fileHandle As HANDLE, ByRef String_ As String) 
declare Sub Write_StringN(ByVal fileHandle As HANDLE, ByRef String_ As String) 
Declare Sub Write_LongInt(ByVal fileHandle As HANDLE, ByVal Longint_ As longint) 
Declare Sub Write_Data(ByVal H As handle, ByVal Address As Any Ptr, ByVal Lenght As Long)

' folder
Declare Sub Delete_File (ByRef sFile As String)
Declare Sub CreateDir(ByRef sDir As String) 
Declare Function RemoveDir(ByRef sDir As String) As Integer
Declare Function GetCurentDir() As String
Declare Sub SetCurentDir(ByRef sDir As String)
Declare Function GetWindowsDir() As String
Declare Function GetSystemDir() As String
Declare Function GetTempDir() As String
Declare function GetSpecialFolder(ByVal folderFlag As integer) As String
Declare Sub CopyDir(ByRef SourseDir As String, ByRef NewDir As String, ByVal flag As long=0) 
Declare Sub MoveDir(ByRef SourseDir As String, ByRef NewDir As String, ByVal flag As Long=0) 
Declare sub RenameDir(ByRef SourseDirName As String,ByRef NewDirName As String, ByVal flag As Integer=0)
Declare Sub DeleteDir(ByRef DeleteDirName As String,ByVal flag As Integer=0)
Declare Function GetExtensionPart(ByRef sPath As String) As String
Declare Function GetPathPart(ByRef sPath As String) As String
Declare Function GetFilePart(ByRef sPath As String) As String
Declare Function ExamineDirectory(ByRef DirectoryName As string, ByRef Pattern As string) As Integer
Declare Function NextDirectoryEntry(ByVal HandleDirectory As integer) As Integer
Declare Sub FinishDirectory(ByVal HandleDirectory As integer) 
Declare Function DirectoryEntrySize(ByVal HandleDirectory As integer) As ULongInt
Declare Function DirectoryEntryDate(ByVal HandleDirectory As Integer, ByVal flag As Long) As String
Declare Function DirectoryEntryName(ByVal HandleDirectory As integer) As string
Declare Function DirectoryEntryAttributes(ByVal HandleDirectory As integer) As UInteger

' dshow movie
Declare Function LoadMovie(ByVal hWin As HWND, ByRef sFileName As String, ByVal x As Integer, ByVal y As Integer,ByVal w As Integer, ByVal h As integer) as integer
Declare Function FreeMovie(ByVal Movie_ As Integer) As Integer
Declare Function PlayMovie(ByVal Movie_ As integer) As Integer
Declare Function StopMovie(ByVal Movie_ As Integer) As Integer
Declare Function PauseMovie(ByVal Movie_ As Integer) As Integer
Declare Function ResizeMovie(ByVal Movie_ As Integer,ByVal x As Integer, ByVal y As Integer, ByVal Width_ As Integer, ByVal Height_ As integer) As Integer
Declare Function SetRateMovie(ByVal Movie_ As Integer,ByVal Rate As Double) As bool
Declare Function GetRateMovie(ByVal Movie_ As Integer) As Double
Declare Function GetEndPosMovie(ByVal Movie_ As Integer) As longint
Declare Function MovieSetPositions(ByVal Movie_ As Integer,ByVal Rnew As LongInt,ByVal Rend As LongInt,ByVal flagNew As Integer=1,ByVal flagEnd As Integer=1) As Integer 'AM_SEEKING_AbsolutePositioning=1
Declare Function MovieGetCurrentPosition(ByVal Movie_ As Integer) As LongInt
Declare Function MovieSourseWidth(ByVal Movie_ As Integer) As LongInt
Declare Function MovieSourseHeight(ByVal Movie_ As Integer) As LongInt
Declare Function MovieFullScreen(ByVal Movie_ As Integer,ByVal Mode As Integer) As Integer
Declare Function MovieAudioSetVolume(ByVal Movie_ As Integer,ByVal Volume As Integer) As Integer
Declare Function MovieAudioGetVolume(ByVal Movie_ As Integer) As Integer
Declare Function MovieScreenShot(ByVal Movie_ As Integer) As HBITMAP
Declare Function MovieGetState(ByVal Movie_ As Integer,ByVal msTimeout As Integer=-1) As Integer

' 2D drawing
Declare Function ImageStartDraw(ByVal hBmp As HBITMAP) As HDC
Declare Function WindowStartDraw(ByVal hWin As HWND,ByVal x As Long=0,ByVal y As Long=0,ByVal w As Long=0, ByVal h As Long=0,ByVal Alpha_FLAG As Long=0, ByVal Alpha_VALUE As ULong=0) As HDC
Declare Function StopDraw() As Integer
Declare Function LineDraw(ByVal x As Long,ByVal y As Long,ByVal x1 As Long,ByVal y1 As Long,ByVal width_ As Long=0,ByVal color_ As Long=0,ByVal style As Long=PS_SOLID) As Integer
Declare Sub PixDraw(ByVal x As Long,ByVal y As Long,ByVal Color_ As Long)
Declare Function GetPix(ByVal x As Long,ByVal y As Long) As Long
Declare Function BoxDraw(ByVal x As Long,ByVal y As Long,ByVal w As Long,ByVal h As Long,ByVal ColorPen As Long=0,ByVal ColorBk As Long=0,ByVal widthPen As Long=0,ByVal StylePen As Long=PS_SOLID, ByVal AlPHAPARAM As Long=255) As Integer
Declare Function RoundBoxDraw(ByVal x As Long,ByVal y As Long,ByVal w As Long,ByVal h As Long,ByVal ColorPen As Long=0,ByVal ColorBk As Long=0,ByVal widthPen As Long=0,ByVal StylePen As Long=PS_SOLID,ByVal ellipsewidth As Long=0,ByVal ellipseheight As Long=0, ByVal AlPHAPARAM As Long=255) As Integer
Declare Function RoundDraw(ByVal x As Long,ByVal y As Long,ByVal w As Long,ByVal h As Long,ByVal ColorPen As Long=0,ByVal ColorBk As Long=0,ByVal widthPen As Long=0,ByVal StylePen As Long=PS_SOLID, ByVal AlPHAPARAM As Long=255) As Integer
Declare Function CircleDraw(ByVal x As Long,ByVal y As Long,ByVal radius As Long,ByVal ColorPen As Long=0,ByVal ColorBk As Long=0,ByVal widthPen As Long=0,ByVal StylePen As Long=PS_SOLID, ByVal AlPHAPARAM As Long=255) As Integer
Declare Sub FontDraw(ByVal FontID As integer)
Declare Function TextDraw(ByVal x As Long, ByVal y As Long, ByRef txt As string, ByVal ColorBK As Long=0, ByVal ColorText As Long=0, ByVal AlPHAPARAM As Long=255) As Integer
Declare Function PolylineDraw(ByVal pPoint As POINT Ptr,ByVal nCount As Long, ByVal ColorPen As Long=0, ByVal widthPen As Long=0, ByVal StylePen As Long=PS_SOLID) As Integer
Declare Function PolygonDraw(ByVal pPoint As POINT ptr,ByVal nCount As Long, byval FillColor as Long, ByVal BorderColor As Long=0,ByVal BorderWidth As Long=0,ByVal BorderStyle As Long=PS_SOLID) As Integer
Declare Sub ImageDraw(ByVal hBmp As HBITMAP,ByVal x As Long, ByVal y As Long, ByVal AlPHAPARAM As Long=255) 
Declare sub FillRectDraw(ByVal x As Long, ByVal y As Long, ByVal Color_ As Long)
Declare sub FocusDraw(ByVal x As Long, ByVal y As Long, ByVal w As Long, ByVal h As Long ,ByVal  iColor as Long = 0)
Declare Sub IconDraw(ByVal x As Long, ByVal y As Long, ByVal Hicon As HICON)
Declare Function GradientFillDraw(ByVal x As Long, ByVal y As Long,ByVal w As Long, ByVal h As Long,ByVal Rbegin As Long,ByVal Gbegin As Long,ByVal Bbegin As Long,ByVal REnd As Long,ByVal GEnd As Long,ByVal BEnd As Long, ByVal GOR_VERT As bool=0)As Integer
Declare Function PieDraw(ByVal x As Long,ByVal y As Long,ByVal w As Long,ByVal h As Long,ByVal x1 As Long,ByVal y1 As Long,ByVal x2 As Long,ByVal y2 As Long,ByVal ColorPen As Long=0,ByVal ColorBk As Long=0,ByVal widthPen As Long=0,ByVal StylePen As Long=PS_SOLID) As Integer

' 2D drawing GDI+
Declare Function ImageStartDrawA(ByRef bitmapGP As Any Ptr,ByVal ColorFlag As Integer=0,ByVal Color_ As Integer=&hFFFFFFFF) As Any Ptr
Declare Function WindowStartDrawA(ByVal hWin As HWND,ByVal x As Integer=0,ByVal y As Integer=0,ByVal width_ As Integer=0, ByVal height_ As Integer=0,ByVal ColorFlag As Integer=0,ByVal Color_ As Integer=&hFFFFFFFF) As Any Ptr
Declare Sub StopDrawA()
Declare Sub LineDrawA(ByVal x As single,ByVal y As single,ByVal x1 As single,ByVal y1 As single,ByVal width_ As Single=1,ByVal color_ As Integer=&hff000000,byval brushPen as Any Ptr=0)
Declare Sub BoxDrawA(ByVal x As single,ByVal y As single,ByVal width_ As single,ByVal height_ As single,ByVal ColorPen As integer=&hff000000,ByVal flagcolorBK As Integer=1,ByVal ColorBk As integer=&hff000000,byval brushPen as Any Ptr=0,byval brushBk as Any Ptr=0,ByVal widthPen As Single=1)
Declare Sub BezierDrawA(ByVal x0 As single,ByVal y0 As single,ByVal x1 As single,ByVal y1 As single,ByVal x2 As single,ByVal y2 As single,ByVal x3 As single,ByVal y3 As single,ByVal ColorPen As integer=&hff000000,ByVal brushPen as Any Ptr=0,ByVal widthPen As Single=1)
Declare Sub RoundDrawA(ByVal x As single,ByVal y As single,ByVal width_ As single,ByVal height_ As single,ByVal ColorPen As integer=&hff000000,ByVal flagcolorBK As Integer=1,ByVal ColorBk As integer=&hff000000,ByVal brushPen as Any Ptr=0,byval brushBk as Any Ptr=0,ByVal widthPen As Single=1)
Declare Sub CircleDrawA(ByVal x As single,ByVal y As single,ByVal Radius As single,ByVal ColorPen As integer=&hff000000,ByVal flagcolorBK As Integer=1,ByVal ColorBk As integer=&hff000000,ByVal brushPen as Any Ptr=0,byval brushBk as Any Ptr=0,ByVal widthPen As Single=1)
Declare Sub ArcDrawA(ByVal x As single,ByVal y As single,ByVal width_ As single,ByVal height_ As single,ByVal startAngle As Single,ByVal sweepAngle As Single,ByVal ColorPen As integer=&hff000000,ByVal brushPen as Any Ptr=0,ByVal widthPen As Single=1)
Declare Sub PieDrawA(ByVal x As single,ByVal y As single,ByVal width_ As single,ByVal height_ As single,ByVal startAngle As Single,ByVal sweepAngle As Single,ByVal ColorPen As integer=&hff000000,ByVal flagcolorBK As Integer=1,ByVal ColorBk As integer=&hff000000,ByVal brushPen as Any Ptr=0,byval brushBk as Any Ptr=0,ByVal widthPen As Single=1)
Declare Sub PolygonDrawA(ByVal Points As Any ptr,ByVal countPoints As Integer,ByVal ColorPen As integer=&hff000000,ByVal flagcolorBK As Integer=1,ByVal ColorBk As integer=&hff000000,ByVal brushPen as Any Ptr=0,byval brushBk as Any Ptr=0,ByVal widthPen As Single=1,ByVal fillmode As Integer=0)
Declare Sub SetPixA(ByVal X As single,ByVal Y As Single,ByVal Color_ As integer=&hff000000)
Declare Function GetPixA(ByVal X As single,ByVal Y As Single) As Integer
Declare Sub CurveDrawA(ByVal Points As Any ptr,ByVal countPoints As Integer,ByVal RoundPoints As Single=0.5,ByVal ColorPen As integer=&hff000000,ByVal flagcolorBK As Integer=1,ByVal ColorBk As integer=&hff000000,ByVal brushPen as Any Ptr=0,byval brushBk as Any Ptr=0,ByVal widthPen As Single=1,ByVal Closed As Integer=0,ByVal fillmode As Integer=0)
Declare Function CreateBrushA(ByVal x0 As Single=0,ByVal y0 As Single=0,ByVal x1 As Single=0,ByVal y1 As Single=0, ByVal color1 As Integer=&hFF00FF00, ByVal color2 As Integer=&hFF0000FF,ByVal GpImage As Any ptr=0,ByVal WrapMode As Integer=3 ) As Any Ptr
Declare Function CreateFontDrawA(ByVal name_ As String="Arial",ByVal size As Integer=10,ByVal style As Integer=0,ByVal Unit As Integer=6) As Any Ptr
Declare Sub FreeFontDrawA(ByVal GpFont As Any Ptr)
Declare Sub FreeBrushA(ByVal Brush As Any Ptr)
Declare Sub TextDrawA(ByRef text As String,ByVal x As Integer, ByVal y As Integer, ByVal GpFont As Any Ptr=0, ByVal color_ As Integer=&hFFFFFFFF,ByVal brush As Any Ptr=0,ByVal mode As Integer=0)
Declare Sub ImageDrawA(ByVal GpImage As Any Ptr,ByVal x As single, ByVal y As single,ByVal Width_ As Single=0, ByVal Height_ As Single=0)
Declare Sub ModeDrawA(ByVal mode As Integer)
Declare Sub FillRectDrawA(byval x As Integer, byval y As Integer, byval newcol As integer)

' 3D / 2D OpenGL
declare sub Perspective(byval fov as double,byval ratio as double,byval zNear as double,byval zFar as double)
declare sub LookAt(byval ex as double, byval ey as double, byval ez as double, _
                   byval lx as double, byval ly as double, byval lz as double, _
                   byval ux as double, byval uy as double, byval uz as double )

declare function OpenGLGadget(ByVal gadget As Long, _
                              ByVal x As Long, ByVal y As Long, _
                              ByVal w As Long, ByVal h As Long, _
                              ByVal cBits As Long = 32, _
                              byval dBits as Long = 24, _
                              byval sBits as Long =  0, _
                              byval aBits as Long =  0) As HWND
declare Sub OpenGLGadgetMakeCurrent(ByVal gadget As Long) 
declare Sub OpenGLGadgetSwapBuffers(ByVal gadget As Long)

' desktop
Declare Function EnumSettingsDisplay() As String
Declare Function ResetEnum() As Integer
Declare Function SetCurrentSettingsDisplay(ByVal w As Integer, ByVal h As Integer,ByVal Bits As Integer,ByVal Frequency As Integer) As Integer
Declare Function GetCurrentSettingsDisplay() As string
Declare Function GetWidthDesktop(Byref setting As String) As Integer
Declare Function GetHeightDesktop(Byref setting As String) As Integer
Declare Function GetBitsDesktop(Byref setting As String) As Integer
Declare Function GetFrequencyDesktop(Byref setting As String) As Integer
Declare Function GlobalMouseX() As Integer
Declare Function GlobalMouseY() As Integer

' scrollbar
Declare Function ScrollBarGadget(ByVal gadget As Long,ByVal x As Long, ByVal y As Long, ByVal w As Long, ByVal h As Long, ByVal MINRange As Long, ByVal MAXRange As Long, ByVal Style As Long = SB_HORZ, ByVal PageLength As Long = 10) As HWND
Declare Function GetScrollGadgetRange OverLoad(ByVal hWin As HWND,ByVal flag As Integer, ByVal style As Integer) As Integer
Declare Function GetScrollGadgetRange OverLoad(ByVal gadget As long, ByVal flag As Integer) As Integer
Declare Sub SetScrollGadgetRange OverLoad(ByVal hWin As HWND,ByVal MINRange As Integer,ByVal MAXRange As Integer, ByVal style As Integer) 
Declare Sub SetScrollGadgetRange OverLoad(ByVal gadget As Long,ByVal MINRange As Integer,ByVal MAXRange As Integer) 
Declare Function GetScrollGadgetPos OverLoad(ByVal hWin As HWND, ByVal style As Integer) As Integer
Declare Function GetScrollGadgetPos OverLoad(ByVal gadget As Long) As Integer
Declare Sub SetScrollGadgetPos OverLoad(ByVal hWin As HWND,ByVal POSITION As Integer, ByVal style As integer) 
Declare Sub SetScrollGadgetPos OverLoad(ByVal gadget As Long,ByVal POSITION As Integer) 
Declare Sub SetScrollGadgetPage OVERLOAD(ByVal gadget As Long, ByVal page As Integer)
Declare Sub SetScrollGadgetPage OVERLOAD(ByVal hWin As HWND, ByVal page As Integer,ByVal style As Integer) 
Declare Sub SetPageStepScrollBar OverLoad(ByVal iGadget As Long , ByVal parscroll As Integer)
Declare Sub SetPageStepScrollBar (ByVal hw As HWND, ByVal parscroll As Integer)

' systray
#Ifndef NIIF_USER
#Define NIIF_USER 4
#EndIf
Declare Function AddSysTrayIcon(ByVal NumberSysTray As Integer,ByVal hwnd As HWND,ByVal icon As HICON,ByRef ToolTipSysTray As String) As Integer
Declare sub ReplaceSysTrayIcon(ByVal NumberSysTray As Integer,ByVal icon As HICON,ByRef ToolTipSysTray As String) 
Declare sub DeleteSysTrayIcon(ByVal NumberSysTray As Integer)
Declare Function MessageSysTrayIcon(ByVal NumberSysTray As Integer, ByVal hwnd As HWND, byRef Title As String, byRef Text As String, byval Timeout As Integer = 5000, ByVal icon As HICON = 0, ByVal TypeIcon As Integer = NIIF_INFO) As Integer

' MDI
Declare Function ClientMDIGadget(ByVal menu As HMENU,ByVal IDmenuMDI As Integer, ByVal Style As Integer=WS_CLIPCHILDREN Or WS_CLIPSIBLINGS  Or WS_VSCROLL Or WS_HSCROLL) As HWND
Declare Function MDIGadget(ByRef sName As String, ByVal x As Integer, ByVal y As Integer,ByVal w As Integer, ByVal h As Integer, ByVal Style As Integer=WS_OVERLAPPEDWINDOW) As HWND

' printer
Declare Function HWNDPrinter(byval hWin As HWND, byval Xpr As Integer=0, byval Ypr As Integer=0, byval X As Integer=0, byval Y As Integer=0, byval X1 As Integer=0, byval Y1 As Integer=0) As integer
Declare Sub      TextPrinter(byref SourseText As String, byval Font As window9.FontPrint Ptr=0, byval color_BK As COLORREF=0, byval color_T As COLORREF=0)


Declare Function ContainerGadget(ByVal gadget As Long, ByVal x As Long,ByVal y As Long,ByVal w As Long, ByVal h As Long, ByVal par As Long=0) As HWND
Declare Function GroupContainerGadget(byval id as integer, byval x as integer, byval y as integer, byval w as integer, byval h as integer, byref caption as string) as HWND

' panel
Declare Function PanelGadget(ByVal gadget As Long, ByVal x As Long, ByVal y As Long, ByVal w As Long=0, ByVal h As Long=0, ByVal SizeIcon As Long=16, ByVal par As Long=0) As HWND
Declare Function AddPanelGadgetItem(ByVal gadget As Long, ByVal Item As Long, ByRef text As String, ByVal ImageID As HBITMAP=0, ByVal flag As Long=0) As HWND
Declare sub DeleteItemPanelGadget(ByVal gadget As Long, ByVal item As Long) 
Declare Function PanelGadgetGetCursel(ByVal gadget As Long) As Long
Declare sub PanelGadgetSetCursel(ByVal gadget As Long, ByVal item As Long)

' richedit
Declare Function EditorGadget(ByVal gadget As Long, ByVal x As Long, ByVal y As Long, ByVal w As Long,ByVal h As Long, ByRef stri As String="", ByVal style As Long=0 ,ByVal tag as long = 0) As HWND
Declare Function UndoEditor(ByVal gadget As Long) As Integer
Declare Function RedoEditor(ByVal gadget As Long) As Integer
Declare sub PasteEditor(ByVal gadget As Long, ByRef text As String, ByVal param As Integer=1) 
Declare Function CanUndoEditor(ByVal gadget As Long) As Integer
Declare Function CanRedoEditor(ByVal gadget As Long) As Integer
Declare sub EmptyUndoBufferEditor(ByVal gadget As Long)
Declare Function GetLineTextEditor(ByVal gadget As Long, ByVal Number As integer, ByVal Buffer As Integer=512) As String
Declare Function GetLineCountEditor(ByVal gadget As Long) As Integer
Declare Function GetModifyEditor(ByVal gadget As Long) As Integer
Declare Function GetRectEditor(ByVal gadget As Long, ByVal rect As RECT Ptr) As integer
Declare Function SetLimitTextEditor(ByVal gadget As Long, ByVal Limit As Integer=0) As Integer
Declare sub SetModifyEditor(ByVal gadget As Long, ByVal Flag As long=0) 
Declare Sub SetPasswordChar(ByVal gadget As Long, ByVal CharCode As UBYTE=0)
Declare Function GetPasswordChar(ByVal gadget As Long) As UByte
Declare Function LineFromCharEditor(ByVal gadget As Long, ByVal index As Integer=-1) As Integer
Declare Function LineIndexEditor(ByVal gadget As Long, ByVal NumberLine As Integer=-1) As Integer
Declare Function LineLengthEditor(ByVal gadget As Long, ByVal index As Integer=-1) As Integer
Declare Function LineScrollEditor(ByVal gadget As Long, ByVal VertPos As Integer) As Integer
Declare Sub SetTabStopsEditor(ByVal gadget As Long, ByVal TabWidth As Integer=0) 
Declare Function ReadOnlyEditor(ByVal gadget As Long, ByVal ReadOnly As Integer=0) As Integer
Declare Function GetFirstVisibleLineEditor(ByVal gadget As Long) As Integer
Declare Function SetRectEditor(ByVal gadget As Long, ByVal rec As RECT Ptr) As integer
Declare Function GetCurrentIndexCharEditor(ByVal gadget As Long) As integer
Declare Sub SetTransferTextLineEditorGadget(ByVal gadget As Long, ByVal state As long) 
Declare Function GetSelectTextEditorGadget(ByVal gadget As Long) As String
Declare Sub SetSelectTextEditorGadget(ByVal gadget As Long, ByVal selBegin As long, ByVal selEnd As long) 

' rebar
Declare Function RebarGadget(ByVal gadget  As Long, _
                             ByVal Style   As Integer = WS_CLIPCHILDREN Or WS_CLIPSIBLINGS Or RBS_VARHEIGHT Or RBS_AUTOSIZE Or RBS_BANDBORDERS Or CCS_ADJUSTABLE Or CCS_TOP Or CCS_NODIVIDER, _
                             ByVal ExStyle As Integer = 0) As HWND
Declare Function AddRebarTab(ByVal gadget As Long, _
                             ByVal GadgetChild As long, _
                             ByVal IDinNumber As Integer = 0, _
                             ByRef string_ As String = "", _
                             ByVal pos_ As Integer = -1, _
                             ByVal x    As Integer = 100, _
                             ByVal MinX As Integer = 0, _
                             ByVal MinY As Integer = 20, _
                             ByVal Mask As Integer = RBBIM_STYLE Or RBBIM_CHILD Or RBBIM_CHILDSIZE Or RBBIM_SIZE Or RBBIM_TEXT Or RBBIM_ID, _
                             ByVal Style As Integer = RBBS_CHILDEDGE Or RBBS_GRIPPERALWAYS) As Integer
Declare Function GetCountTabRebarGadget(ByVal gadget As Long) As Integer
Declare Function GetHeightRebarGadget(ByVal gadget As Long) As Integer
Declare Function GetTextRebarGadget(ByVal gadget As Long, ByVal index As Long) As String
Declare sub SetTextRebarGadget(ByVal gadget As Long, ByVal index As Integer, ByVal text As String) 
Declare Function MoveTabRebarGadget(ByVal gadget As Long, ByVal IndexMove As Integer, byval IndexNew as Integer) As integer
Declare sub DeleteTabRebarGadget(ByVal gadget As long, ByVal Index As long) 
Declare Function IDinIndexRebarGadget(ByVal gadget As Long, ByVal ID As Integer) As integer

' ini
Declare Function CreateFBini(ByRef sFileName As String) As handle
Declare Function OpenFBini(ByRef sFileName As String, ByVal flag As bool = 0) As handle
Declare Function CloseFBini() As bool
Declare Sub      WriteGroupFBini(Byref group As String)
Declare Sub      WriteValueFBini OverLoad(ByRef sGroup As String, ByRef sKey As String, ByVal value As byte)
Declare Sub      WriteValueFBini (ByRef sGroup As String, ByRef sKey As String, ByVal value As Short)
Declare Sub      WriteValueFBini (ByRef sGroup As String, ByRef sKey As String, ByVal value As Integer32)
Declare Sub      WriteValueFBini (ByRef sGroup As String, ByRef sKey As String, ByVal value As Double)
Declare Sub      WriteValueFBini (ByRef sGroup As String, ByRef sKey As String, ByVal value As LongInt)
Declare Sub      WriteValueFBini (ByRef sGroup As String, ByRef sKey As String, ByRef value As string)
Declare Function ReadByteValueFBini(ByRef sGroup As String, ByRef sKey As String) As byte
Declare Function ReadShortValueFBini(ByRef sGroup As String, ByRef sKey As String) As Short
Declare Function ReadIntegerValueFBini(ByRef sGroup As String, ByRef sKey As String) As Integer32
Declare Function ReadLongintValueFBini(ByRef sGroup As String, ByRef sKey As String) As LongInt
Declare Function ReadDoubleValueFBini(ByRef sGroup As String, ByRef sKey As String) As Double
Declare Function ReadStringValueFBini(ByRef sGroup As String, ByRef sKey As String) As String
Declare Function GetCurrentFileName() As String
Declare Function GetCurrentFileNameA() As String

Declare Sub SetRunOnlyExe()

' process / thread
Declare Function InitProcess() As HANDLE
Declare Function FirstProcess(byval hProc As HANDLE) As Long
Declare Function NextProcess(byval hProc As HANDLE) As Long
Declare Function GetNameProcess() As String
Declare Function GetIDProcess() As Integer
Declare Function Create_Process(ByRef FileName As String, ByRef DirDefault As String="", ByVal flag As Integer=0, ByVal STARTUPINFO_ As STARTUPINFO Ptr=0, ByVal PROCESS_INFORMATION_ As PROCESS_INFORMATION Ptr=0) As Integer
Declare Function Open_Process(ByVal pid As Integer, ByVal Access_ As Integer=PROCESS_ALL_ACCESS, ByVal flag As BOOL=0) As HANDLE
Declare sub KillProcess(ByVal hProc As HANDLE, ByVal ExitCode As Integer=0)
Declare Function WaitExitProcess(ByVal hProc as HANDLE, ByVal WaitTime As Integer=INFINITE)As bool
Declare Function WaitLoadProcess(ByVal hProc As HANDLE, ByVal WaitTime As Integer=INFINITE)As bool
Declare Function GetExitCode(ByVal hProc As HANDLE) As Integer

' zip packer
Declare Function CompressMem(Byref BUF_DEST As Byte Ptr,byval SOURSEDATA As Byte ptr,Byval SIZEDATA As ULong, ByVal level As long=5) As Long
Declare Function DeCompressMem(Byref BUF_COMPRESSED As Byte Ptr,byval SIZECOMPRESSED As Long,ByRef BUFDESTDATA As Byte Ptr) As Long
Declare Function CompressFile(ByRef filename As String, ByRef filenameDest As String,ByVal level As Long=5) As Long
Declare Function DeCompressFile(ByRef filename As String, ByRef filenameDest As String) As Long

' HELP
Declare Function OpenHelp(ByRef sPathHelp As String, ByRef sTopic As String, byval iParam As Integer = FB_IGNORE) As HWND
Declare Sub CloseHelp()

' tools and misc.
Declare Function ASCIITOUTF(ByRef text As String) As WString Ptr
Declare Function UTFTOASCII(ByVal text As WString Ptr) As String

Declare sub FastCopy(Byval pTarget as any ptr, Byval pSource as any ptr, Byval nBytes as uinteger)

declare function FastCRC16(byval pBuffer as any ptr, byval BufferSize as uinteger) as ushort
Declare Function FastCRC32(Byval pBuffer As any Ptr, Byval BufferSize As uInteger) As ulong

declare function AESEncoder(ByRef Text as string, ByRef Key as string) as String
declare function AESDecoder(ByRef Text as string, ByRef Key as string) as String

Declare Function Encode64(ByRef text As String) As String
Declare Function Decode64(ByRef strb64 as const String) As String

Declare Function MD5createFileHash(ByRef file As String) As String
Declare Function MD5createHash(ByRef text As String) As String

Declare Function SHA512create(ByRef text As String) As String
Declare Function SHA512createFile(ByRef file As String) As String

Declare Function SHA1createFile(ByRef file As String) As String
Declare Function SHA1create(ByRef file As String) As String

declare Function PeekS(ByVal Memory As Any Ptr, byval iLen As Integer = 0) As String
declare Function RunProgram(ByRef Filename As String, ByRef Parameter As String="", ByRef WorkingDirectory As String="", ByRef Flags As String = "open", ByVal ShowCmd As Integer=1) As Integer
Declare Function ReplaceString(ByRef String_ As string, ByRef SearchString As String, ByRef ReplaceString_ As String, ByVal Position As Long=1,ByVal searchParam As Long=0, ByVal RegisterParam As Long=0) As String
Declare Function InsertString(ByRef DestS As String, ByRef InsertS As String, ByVal Position As Integer) As Integer
Declare Function LtrimA(ByRef dest As String, ByRef trimString As String=" ") As String
Declare Function RtrimA(ByRef dest As String, ByRef trimString As String=" ") As String
Declare Function TrimA(ByRef dest As String, ByRef trimString As String=" ") As String
Declare Function ClearString(ByRef dest As String, ByRef trimString As String=" ") As String

Declare Function SetWindowCallback(ByVal Address_Function As Integer,ByVal flag As Integer=0) As Integer
Declare Function FreeCallback(byval flag as integer) As Integer

Declare Sub UpdateInfoXServer(iCountCicles As Long = 10000)

Declare function UBoundIncBin(byval pBuf as any ptr) as Long
Declare Sub      addInclude_binary_info(ByVal pAny As Any Ptr ,ByVal iLen As Long)

' Internet
Type FTPINFO
  As WIN32_FIND_DATA FileInformation
  Declare Function FtpExamineDirectory(ByVal hConnect As HINTERNET, ByRef DirectoryName As String, ByRef Pattern As String, byval dwFlags As Integer = 0) As HINTERNET
  Declare Function FtpNextDirectoryEntry(ByVal hFind As HINTERNET) As Integer
  Declare Function FtpFinishDirectory(ByVal hFind As HINTERNET) As Integer
  Declare Function FtpDirectoryEntryAttributes() As Integer
  Declare Function FtpDirectoryEntrySize() As ULongInt
  Declare Function FtpDirectoryEntryDate() As String
  Declare Function FtpDirectoryEntryName() As String
End Type

Declare Function UrlDecoder(ByRef sUrl As String) As String
Declare Function UrlEncoder(ByRef sUrl As String) As String

Declare Function InetOpen(ByRef szUserAgent As String = "FB", byval iType As Integer = INTERNET_OPEN_TYPE_DIRECT, ByRef szProxyName As String = "", ByRef szProxyBypass As String="", byval iFlags As Integer = 0) As HINTERNET
Declare Function OpenUrl(byval hInet As HINTERNET, byref szURL As String, ByRef szHeaders As String = "", byval iSizeHeaders As Integer = 0, byval iFlags As Integer = INTERNET_FLAG_RELOAD) As HINTERNET
Declare Function InetReadFile(byval hUrl As HINTERNET, byval psData As Any Ptr, byval iLenData As Integer) As Integer
Declare Sub      InetFreeHandle(byval handle As HINTERNET)
Declare Function GetHTTPHeader(byval hUrl As HINTERNET) As String
Declare Function ReceiveHTTPFile(ByRef sUrl As String, ByRef sFile As String) As Integer
Declare Function GetContentSize(byval hUrl As HINTERNET) As ULongInt
Declare Function FtpFinishDirectory(ByVal hFind As HINTERNET) As Integer
Declare Function FtpConnect(byval hInet As HINTERNET, ByRef ServerName As String, ByRef UserName As String, ByRef UserPassword As String, byval ServerPort As Integer = 21, byval Flags As Integer = 0) As HINTERNET
Declare Function FtpFileGet(byval hConnect As HINTERNET, ByRef RemoteFile As String, ByRef LocalFile As String, byval fFailExists As Integer = 0, byval dwFlagAttributes As Integer = 0, byval dwFlags As Integer = FTP_TRANSFER_TYPE_BINARY ) As Integer
Declare Function FtpFilePut(byval hInet As HINTERNET, ByRef LocalFile As String, ByRef RemoteFile As String, byval dwFlags As Integer = FTP_TRANSFER_TYPE_BINARY) As Integer
Declare Function FtpSetDirectory(byval hConnect As HINTERNET, ByRef Directory As String) As Integer
Declare Function FtpGetDirectory(byval hConnect As HINTERNET) As String
Declare Function FtpFileOpen(byval hConnect As HINTERNET, ByRef File As String, byval dwFlags As Integer = FTP_TRANSFER_TYPE_BINARY, byval dwAccess As Integer = GENERIC_WRITE) As HINTERNET
Declare Function FtpFileClose(byval hFile As HINTERNET) As Integer
Declare Function FtpWriteFile(byval hFile As HINTERNET, byval Buffer As Any ptr, byval nBuffer As Integer) As Integer
Declare Function FtpGetSizeFile(byval hFile As HINTERNET) As ULongint

#EndIf ' __WINDOW9_BI__


