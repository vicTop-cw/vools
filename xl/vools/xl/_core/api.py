"""LibXL 低层 C API 封装 (ANSI 版本)

提供 LibXL DLL 函数的 ctypes 声明。
所有函数使用 ANSI (A 后缀) 版本。
"""
import ctypes
from ctypes import c_int, c_double, c_char_p, c_void_p, c_uint, POINTER, byref

from .loader import get_libxl_dll

BookHandle = c_void_p
SheetHandle = c_void_p
FormatHandle = c_void_p
FontHandle = c_void_p
AutoFilterHandle = c_void_p
FilterColumnHandle = c_void_p

# ==================== 枚举常量 ====================

# CellType
CELLTYPE_EMPTY = 0
CELLTYPE_NUMBER = 1
CELLTYPE_STRING = 2
CELLTYPE_BOOLEAN = 3
CELLTYPE_BLANK = 4
CELLTYPE_ERROR = 5

# SheetType
SHEETTYPE_SHEET = 0
SHEETTYPE_CHART = 1
SHEETTYPE_UNKNOWN = 2

# AlignH
ALIGNH_GENERAL = 0
ALIGNH_LEFT = 1
ALIGNH_CENTER = 2
ALIGNH_RIGHT = 3
ALIGNH_FILL = 4
ALIGNH_JUSTIFY = 5
ALIGNH_MERGE = 6
ALIGNH_DISTRIBUTED = 7

# AlignV
ALIGNV_TOP = 0
ALIGNV_CENTER = 1
ALIGNV_BOTTOM = 2
ALIGNV_JUSTIFY = 3
ALIGNV_DISTRIBUTED = 4

# BorderStyle
BORDERSTYLE_NONE = 0
BORDERSTYLE_THIN = 1
BORDERSTYLE_MEDIUM = 2
BORDERSTYLE_DASHED = 3
BORDERSTYLE_DOTTED = 4
BORDERSTYLE_THICK = 5
BORDERSTYLE_DOUBLE = 6
BORDERSTYLE_HAIR = 7

# FillPattern
FILLPATTERN_NONE = 0
FILLPATTERN_SOLID = 1
FILLPATTERN_GRAY50 = 2
FILLPATTERN_GRAY75 = 3
FILLPATTERN_GRAY25 = 4

# Script
SCRIPT_NORMAL = 0
SCRIPT_SUPER = 1
SCRIPT_SUB = 2

# Underline
UNDERLINE_NONE = 0
UNDERLINE_SINGLE = 1
UNDERLINE_DOUBLE = 2

# Color
COLOR_BLACK = 8
COLOR_WHITE = 9
COLOR_RED = 10
COLOR_BRIGHTGREEN = 11
COLOR_BLUE = 12
COLOR_YELLOW = 13
COLOR_PINK = 14
COLOR_TURQUOISE = 15
COLOR_AUTO = 0x7FFF

_api_initialized = False


def _init_api():
    """初始化 API 函数声明"""
    global _api_initialized
    if _api_initialized:
        return

    dll = get_libxl_dll()

    # ==================== Book 相关函数 ====================

    dll.xlCreateBookCA.restype = BookHandle
    dll.xlCreateBookCA.argtypes = []

    dll.xlCreateXMLBookCA.restype = BookHandle
    dll.xlCreateXMLBookCA.argtypes = []

    dll.xlBookLoadA.restype = c_int
    dll.xlBookLoadA.argtypes = [BookHandle, c_char_p]

    dll.xlBookSaveA.restype = c_int
    dll.xlBookSaveA.argtypes = [BookHandle, c_char_p]

    dll.xlBookReleaseA.restype = None
    dll.xlBookReleaseA.argtypes = [BookHandle]

    dll.xlBookAddSheetA.restype = SheetHandle
    dll.xlBookAddSheetA.argtypes = [BookHandle, c_char_p, SheetHandle]

    dll.xlBookInsertSheetA.restype = SheetHandle
    dll.xlBookInsertSheetA.argtypes = [BookHandle, c_int, c_char_p, SheetHandle]

    dll.xlBookGetSheetA.restype = SheetHandle
    dll.xlBookGetSheetA.argtypes = [BookHandle, c_int]

    dll.xlBookSheetTypeA.restype = c_int
    dll.xlBookSheetTypeA.argtypes = [BookHandle, c_int]

    dll.xlBookSheetCountA.restype = c_int
    dll.xlBookSheetCountA.argtypes = [BookHandle]

    dll.xlBookDelSheetA.restype = c_int
    dll.xlBookDelSheetA.argtypes = [BookHandle, c_int]

    dll.xlBookMoveSheetA.restype = c_int
    dll.xlBookMoveSheetA.argtypes = [BookHandle, c_int, c_int]

    dll.xlBookActiveSheetA.restype = c_int
    dll.xlBookActiveSheetA.argtypes = [BookHandle]

    dll.xlBookSetActiveSheetA.restype = None
    dll.xlBookSetActiveSheetA.argtypes = [BookHandle, c_int]

    dll.xlBookAddFormatA.restype = FormatHandle
    dll.xlBookAddFormatA.argtypes = [BookHandle, FormatHandle]

    dll.xlBookAddFontA.restype = FontHandle
    dll.xlBookAddFontA.argtypes = [BookHandle, FontHandle]

    dll.xlBookAddCustomNumFormatA.restype = c_int
    dll.xlBookAddCustomNumFormatA.argtypes = [BookHandle, c_char_p]

    dll.xlBookCustomNumFormatA.restype = c_char_p
    dll.xlBookCustomNumFormatA.argtypes = [BookHandle, c_int]

    dll.xlBookFormatA.restype = FormatHandle
    dll.xlBookFormatA.argtypes = [BookHandle, c_int]

    dll.xlBookFormatSizeA.restype = c_int
    dll.xlBookFormatSizeA.argtypes = [BookHandle]

    dll.xlBookFontA.restype = FontHandle
    dll.xlBookFontA.argtypes = [BookHandle, c_int]

    dll.xlBookFontSizeA.restype = c_int
    dll.xlBookFontSizeA.argtypes = [BookHandle]

    dll.xlBookDefaultFontA.restype = c_char_p
    dll.xlBookDefaultFontA.argtypes = [BookHandle, POINTER(c_int)]

    dll.xlBookSetDefaultFontA.restype = None
    dll.xlBookSetDefaultFontA.argtypes = [BookHandle, c_char_p, c_int]

    dll.xlBookErrorMessageA.restype = c_char_p
    dll.xlBookErrorMessageA.argtypes = [BookHandle]

    dll.xlBookSetKeyA.restype = None
    dll.xlBookSetKeyA.argtypes = [BookHandle, c_char_p, c_char_p]

    dll.xlBookVersionA.restype = c_int
    dll.xlBookVersionA.argtypes = [BookHandle]

    dll.xlBookBiffVersionA.restype = c_int
    dll.xlBookBiffVersionA.argtypes = [BookHandle]

    dll.xlBookIsDate1904A.restype = c_int
    dll.xlBookIsDate1904A.argtypes = [BookHandle]

    dll.xlBookSetDate1904A.restype = None
    dll.xlBookSetDate1904A.argtypes = [BookHandle, c_int]

    dll.xlBookIsTemplateA.restype = c_int
    dll.xlBookIsTemplateA.argtypes = [BookHandle]

    dll.xlBookSetTemplateA.restype = None
    dll.xlBookSetTemplateA.argtypes = [BookHandle, c_int]

    dll.xlBookRefR1C1A.restype = c_int
    dll.xlBookRefR1C1A.argtypes = [BookHandle]

    dll.xlBookSetRefR1C1A.restype = None
    dll.xlBookSetRefR1C1A.argtypes = [BookHandle, c_int]

    dll.xlBookRgbModeA.restype = c_int
    dll.xlBookRgbModeA.argtypes = [BookHandle]

    dll.xlBookSetRgbModeA.restype = None
    dll.xlBookSetRgbModeA.argtypes = [BookHandle, c_int]

    dll.xlBookSetLocaleA.restype = c_int
    dll.xlBookSetLocaleA.argtypes = [BookHandle, c_char_p]

    dll.xlBookDatePackA.restype = c_double
    dll.xlBookDatePackA.argtypes = [BookHandle, c_int, c_int, c_int, c_int, c_int, c_int, c_int]

    dll.xlBookDateUnpackA.restype = c_int
    dll.xlBookDateUnpackA.argtypes = [BookHandle, c_double, POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int)]

    dll.xlBookColorPackA.restype = c_int
    dll.xlBookColorPackA.argtypes = [BookHandle, c_int, c_int, c_int]

    dll.xlBookColorUnpackA.restype = None
    dll.xlBookColorUnpackA.argtypes = [BookHandle, c_int, POINTER(c_int), POINTER(c_int), POINTER(c_int)]

    dll.xlBookPictureSizeA.restype = c_int
    dll.xlBookPictureSizeA.argtypes = [BookHandle]

    dll.xlBookGetPictureA.restype = c_int
    dll.xlBookGetPictureA.argtypes = [BookHandle, c_int, POINTER(c_char_p), POINTER(c_uint)]

    dll.xlBookAddPictureA.restype = c_int
    dll.xlBookAddPictureA.argtypes = [BookHandle, c_char_p]

    dll.xlBookAddPicture2A.restype = c_int
    dll.xlBookAddPicture2A.argtypes = [BookHandle, c_char_p, c_uint]

    dll.xlBookAddPictureAsLinkA.restype = c_int
    dll.xlBookAddPictureAsLinkA.argtypes = [BookHandle, c_char_p, c_int]

    # ==================== Sheet 相关函数 ====================

    dll.xlSheetCellTypeA.restype = c_int
    dll.xlSheetCellTypeA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetIsFormulaA.restype = c_int
    dll.xlSheetIsFormulaA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetCellFormatA.restype = FormatHandle
    dll.xlSheetCellFormatA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetSetCellFormatA.restype = None
    dll.xlSheetSetCellFormatA.argtypes = [SheetHandle, c_int, c_int, FormatHandle]

    dll.xlSheetReadStrA.restype = c_char_p
    dll.xlSheetReadStrA.argtypes = [SheetHandle, c_int, c_int, POINTER(FormatHandle)]

    dll.xlSheetWriteStrA.restype = c_int
    dll.xlSheetWriteStrA.argtypes = [SheetHandle, c_int, c_int, c_char_p, FormatHandle]

    dll.xlSheetReadNumA.restype = c_double
    dll.xlSheetReadNumA.argtypes = [SheetHandle, c_int, c_int, POINTER(FormatHandle)]

    dll.xlSheetWriteNumA.restype = c_int
    dll.xlSheetWriteNumA.argtypes = [SheetHandle, c_int, c_int, c_double, FormatHandle]

    dll.xlSheetReadBoolA.restype = c_int
    dll.xlSheetReadBoolA.argtypes = [SheetHandle, c_int, c_int, POINTER(FormatHandle)]

    dll.xlSheetWriteBoolA.restype = c_int
    dll.xlSheetWriteBoolA.argtypes = [SheetHandle, c_int, c_int, c_int, FormatHandle]

    dll.xlSheetReadBlankA.restype = c_int
    dll.xlSheetReadBlankA.argtypes = [SheetHandle, c_int, c_int, POINTER(FormatHandle)]

    dll.xlSheetWriteBlankA.restype = c_int
    dll.xlSheetWriteBlankA.argtypes = [SheetHandle, c_int, c_int, FormatHandle]

    dll.xlSheetReadFormulaA.restype = c_char_p
    dll.xlSheetReadFormulaA.argtypes = [SheetHandle, c_int, c_int, POINTER(FormatHandle)]

    dll.xlSheetWriteFormulaA.restype = c_int
    dll.xlSheetWriteFormulaA.argtypes = [SheetHandle, c_int, c_int, c_char_p, FormatHandle]

    dll.xlSheetWriteFormulaNumA.restype = c_int
    dll.xlSheetWriteFormulaNumA.argtypes = [SheetHandle, c_int, c_int, c_char_p, c_double, FormatHandle]

    dll.xlSheetWriteFormulaStrA.restype = c_int
    dll.xlSheetWriteFormulaStrA.argtypes = [SheetHandle, c_int, c_int, c_char_p, c_char_p, FormatHandle]

    dll.xlSheetWriteFormulaBoolA.restype = c_int
    dll.xlSheetWriteFormulaBoolA.argtypes = [SheetHandle, c_int, c_int, c_char_p, c_int, FormatHandle]

    dll.xlSheetIsDateA.restype = c_int
    dll.xlSheetIsDateA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetReadErrorA.restype = c_int
    dll.xlSheetReadErrorA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetWriteErrorA.restype = c_int
    dll.xlSheetWriteErrorA.argtypes = [SheetHandle, c_int, c_int, c_int, FormatHandle]

    dll.xlSheetReadCommentA.restype = c_char_p
    dll.xlSheetReadCommentA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetWriteCommentA.restype = None
    dll.xlSheetWriteCommentA.argtypes = [SheetHandle, c_int, c_int, c_char_p, c_char_p, c_int, c_int]

    dll.xlSheetRemoveCommentA.restype = None
    dll.xlSheetRemoveCommentA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetColWidthA.restype = c_double
    dll.xlSheetColWidthA.argtypes = [SheetHandle, c_int]

    dll.xlSheetRowHeightA.restype = c_double
    dll.xlSheetRowHeightA.argtypes = [SheetHandle, c_int]

    dll.xlSheetSetColA.restype = c_int
    dll.xlSheetSetColA.argtypes = [SheetHandle, c_int, c_int, c_double, FormatHandle, c_int]

    dll.xlSheetSetRowA.restype = c_int
    dll.xlSheetSetRowA.argtypes = [SheetHandle, c_int, c_double, FormatHandle, c_int]

    dll.xlSheetRowHiddenA.restype = c_int
    dll.xlSheetRowHiddenA.argtypes = [SheetHandle, c_int]

    dll.xlSheetSetRowHiddenA.restype = c_int
    dll.xlSheetSetRowHiddenA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetColHiddenA.restype = c_int
    dll.xlSheetColHiddenA.argtypes = [SheetHandle, c_int]

    dll.xlSheetSetColHiddenA.restype = c_int
    dll.xlSheetSetColHiddenA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetGetMergeA.restype = c_int
    dll.xlSheetGetMergeA.argtypes = [SheetHandle, c_int, c_int, POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int)]

    dll.xlSheetSetMergeA.restype = c_int
    dll.xlSheetSetMergeA.argtypes = [SheetHandle, c_int, c_int, c_int, c_int]

    dll.xlSheetDelMergeA.restype = c_int
    dll.xlSheetDelMergeA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetMergeSizeA.restype = c_int
    dll.xlSheetMergeSizeA.argtypes = [SheetHandle]

    dll.xlSheetMergeA.restype = c_int
    dll.xlSheetMergeA.argtypes = [SheetHandle, c_int, POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int)]

    dll.xlSheetDelMergeByIndexA.restype = c_int
    dll.xlSheetDelMergeByIndexA.argtypes = [SheetHandle, c_int]

    dll.xlSheetNameA.restype = c_char_p
    dll.xlSheetNameA.argtypes = [SheetHandle]

    dll.xlSheetSetNameA.restype = c_int
    dll.xlSheetSetNameA.argtypes = [SheetHandle, c_char_p]

    dll.xlSheetFirstRowA.restype = c_int
    dll.xlSheetFirstRowA.argtypes = [SheetHandle]

    dll.xlSheetLastRowA.restype = c_int
    dll.xlSheetLastRowA.argtypes = [SheetHandle]

    dll.xlSheetFirstColA.restype = c_int
    dll.xlSheetFirstColA.argtypes = [SheetHandle]

    dll.xlSheetLastColA.restype = c_int
    dll.xlSheetLastColA.argtypes = [SheetHandle]

    dll.xlSheetHiddenA.restype = c_int
    dll.xlSheetHiddenA.argtypes = [SheetHandle]

    dll.xlSheetSetHiddenA.restype = c_int
    dll.xlSheetSetHiddenA.argtypes = [SheetHandle, c_int]

    dll.xlSheetClearA.restype = None
    dll.xlSheetClearA.argtypes = [SheetHandle, c_int, c_int, c_int, c_int]

    dll.xlSheetInsertColA.restype = c_int
    dll.xlSheetInsertColA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetInsertRowA.restype = c_int
    dll.xlSheetInsertRowA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetRemoveColA.restype = c_int
    dll.xlSheetRemoveColA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetRemoveRowA.restype = c_int
    dll.xlSheetRemoveRowA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetCopyCellA.restype = c_int
    dll.xlSheetCopyCellA.argtypes = [SheetHandle, c_int, c_int, c_int, c_int]

    dll.xlSheetDisplayGridlinesA.restype = c_int
    dll.xlSheetDisplayGridlinesA.argtypes = [SheetHandle]

    dll.xlSheetSetDisplayGridlinesA.restype = None
    dll.xlSheetSetDisplayGridlinesA.argtypes = [SheetHandle, c_int]

    dll.xlSheetPrintGridlinesA.restype = c_int
    dll.xlSheetPrintGridlinesA.argtypes = [SheetHandle]

    dll.xlSheetSetPrintGridlinesA.restype = None
    dll.xlSheetSetPrintGridlinesA.argtypes = [SheetHandle, c_int]

    dll.xlSheetZoomA.restype = c_int
    dll.xlSheetZoomA.argtypes = [SheetHandle]

    dll.xlSheetSetZoomA.restype = None
    dll.xlSheetSetZoomA.argtypes = [SheetHandle, c_int]

    dll.xlSheetPrintZoomA.restype = c_int
    dll.xlSheetPrintZoomA.argtypes = [SheetHandle]

    dll.xlSheetSetPrintZoomA.restype = None
    dll.xlSheetSetPrintZoomA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetGetPrintFitA.restype = None
    dll.xlSheetGetPrintFitA.argtypes = [SheetHandle, POINTER(c_int), POINTER(c_int)]

    dll.xlSheetSetPrintFitA.restype = None
    dll.xlSheetSetPrintFitA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetLandscapeA.restype = c_int
    dll.xlSheetLandscapeA.argtypes = [SheetHandle]

    dll.xlSheetSetLandscapeA.restype = None
    dll.xlSheetSetLandscapeA.argtypes = [SheetHandle, c_int]

    dll.xlSheetPaperA.restype = c_int
    dll.xlSheetPaperA.argtypes = [SheetHandle]

    dll.xlSheetSetPaperA.restype = None
    dll.xlSheetSetPaperA.argtypes = [SheetHandle, c_int]

    dll.xlSheetHeaderA.restype = c_char_p
    dll.xlSheetHeaderA.argtypes = [SheetHandle]

    dll.xlSheetSetHeaderA.restype = None
    dll.xlSheetSetHeaderA.argtypes = [SheetHandle, c_char_p]

    dll.xlSheetHeaderMarginA.restype = c_double
    dll.xlSheetHeaderMarginA.argtypes = [SheetHandle]

    dll.xlSheetFooterA.restype = c_char_p
    dll.xlSheetFooterA.argtypes = [SheetHandle]

    dll.xlSheetSetFooterA.restype = None
    dll.xlSheetSetFooterA.argtypes = [SheetHandle, c_char_p]

    dll.xlSheetFooterMarginA.restype = c_double
    dll.xlSheetFooterMarginA.argtypes = [SheetHandle]

    dll.xlSheetHCenterA.restype = c_int
    dll.xlSheetHCenterA.argtypes = [SheetHandle]

    dll.xlSheetSetHCenterA.restype = None
    dll.xlSheetSetHCenterA.argtypes = [SheetHandle, c_int]

    dll.xlSheetVCenterA.restype = c_int
    dll.xlSheetVCenterA.argtypes = [SheetHandle]

    dll.xlSheetSetVCenterA.restype = None
    dll.xlSheetSetVCenterA.argtypes = [SheetHandle, c_int]

    dll.xlSheetMarginLeftA.restype = c_double
    dll.xlSheetMarginLeftA.argtypes = [SheetHandle]

    dll.xlSheetSetMarginLeftA.restype = None
    dll.xlSheetSetMarginLeftA.argtypes = [SheetHandle, c_double]

    dll.xlSheetMarginRightA.restype = c_double
    dll.xlSheetMarginRightA.argtypes = [SheetHandle]

    dll.xlSheetSetMarginRightA.restype = None
    dll.xlSheetSetMarginRightA.argtypes = [SheetHandle, c_double]

    dll.xlSheetMarginTopA.restype = c_double
    dll.xlSheetMarginTopA.argtypes = [SheetHandle]

    dll.xlSheetSetMarginTopA.restype = None
    dll.xlSheetSetMarginTopA.argtypes = [SheetHandle, c_double]

    dll.xlSheetMarginBottomA.restype = c_double
    dll.xlSheetMarginBottomA.argtypes = [SheetHandle]

    dll.xlSheetSetMarginBottomA.restype = None
    dll.xlSheetSetMarginBottomA.argtypes = [SheetHandle, c_double]

    dll.xlSheetPrintRowColA.restype = c_int
    dll.xlSheetPrintRowColA.argtypes = [SheetHandle]

    dll.xlSheetSetPrintRowColA.restype = None
    dll.xlSheetSetPrintRowColA.argtypes = [SheetHandle, c_int]

    dll.xlSheetPrintRepeatRowsA.restype = None
    dll.xlSheetPrintRepeatRowsA.argtypes = [SheetHandle, POINTER(c_int), POINTER(c_int)]

    dll.xlSheetSetPrintRepeatRowsA.restype = None
    dll.xlSheetSetPrintRepeatRowsA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetPrintRepeatColsA.restype = None
    dll.xlSheetPrintRepeatColsA.argtypes = [SheetHandle, POINTER(c_int), POINTER(c_int)]

    dll.xlSheetSetPrintRepeatColsA.restype = None
    dll.xlSheetSetPrintRepeatColsA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetPrintAreaA.restype = None
    dll.xlSheetPrintAreaA.argtypes = [SheetHandle, POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int)]

    dll.xlSheetSetPrintAreaA.restype = None
    dll.xlSheetSetPrintAreaA.argtypes = [SheetHandle, c_int, c_int, c_int, c_int]

    dll.xlSheetClearPrintRepeatsA.restype = None
    dll.xlSheetClearPrintRepeatsA.argtypes = [SheetHandle]

    dll.xlSheetClearPrintAreaA.restype = None
    dll.xlSheetClearPrintAreaA.argtypes = [SheetHandle]

    dll.xlSheetAddrToRowColA.restype = c_int
    dll.xlSheetAddrToRowColA.argtypes = [SheetHandle, c_char_p, POINTER(c_int), POINTER(c_int), POINTER(c_int)]

    dll.xlSheetRowColToAddrA.restype = c_char_p
    dll.xlSheetRowColToAddrA.argtypes = [SheetHandle, c_int, c_int, c_int]

    dll.xlSheetSplitA.restype = None
    dll.xlSheetSplitA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetSplitInfoA.restype = c_int
    dll.xlSheetSplitInfoA.argtypes = [SheetHandle, POINTER(c_int), POINTER(c_int)]

    dll.xlSheetGroupRowsA.restype = c_int
    dll.xlSheetGroupRowsA.argtypes = [SheetHandle, c_int, c_int, c_int]

    dll.xlSheetGroupColsA.restype = c_int
    dll.xlSheetGroupColsA.argtypes = [SheetHandle, c_int, c_int, c_int]

    dll.xlSheetGroupSummaryBelowA.restype = c_int
    dll.xlSheetGroupSummaryBelowA.argtypes = [SheetHandle]

    dll.xlSheetSetGroupSummaryBelowA.restype = None
    dll.xlSheetSetGroupSummaryBelowA.argtypes = [SheetHandle, c_int]

    dll.xlSheetGroupSummaryRightA.restype = c_int
    dll.xlSheetGroupSummaryRightA.argtypes = [SheetHandle]

    dll.xlSheetSetGroupSummaryRightA.restype = None
    dll.xlSheetSetGroupSummaryRightA.argtypes = [SheetHandle, c_int]

    dll.xlSheetAutoFilterA.restype = AutoFilterHandle
    dll.xlSheetAutoFilterA.argtypes = [SheetHandle]

    dll.xlSheetApplyFilterA.restype = c_int
    dll.xlSheetApplyFilterA.argtypes = [SheetHandle]

    dll.xlSheetRemoveFilterA.restype = None
    dll.xlSheetRemoveFilterA.argtypes = [SheetHandle]

    dll.xlSheetRightToLeftA.restype = c_int
    dll.xlSheetRightToLeftA.argtypes = [SheetHandle]

    dll.xlSheetSetRightToLeftA.restype = c_int
    dll.xlSheetSetRightToLeftA.argtypes = [SheetHandle, c_int]

    dll.xlSheetSetTabColorA.restype = None
    dll.xlSheetSetTabColorA.argtypes = [SheetHandle, c_int]

    dll.xlSheetSetTabRgbColorA.restype = None
    dll.xlSheetSetTabRgbColorA.argtypes = [SheetHandle, c_int, c_int, c_int]

    dll.xlSheetPictureSizeA.restype = c_int
    dll.xlSheetPictureSizeA.argtypes = [SheetHandle]

    dll.xlSheetGetPictureA.restype = c_int
    dll.xlSheetGetPictureA.argtypes = [SheetHandle, c_int, POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int), POINTER(c_int)]

    dll.xlSheetSetPictureA.restype = None
    dll.xlSheetSetPictureA.argtypes = [SheetHandle, c_int, c_int, c_int, c_double, c_int, c_int, c_int]

    dll.xlSheetSetPicture2A.restype = None
    dll.xlSheetSetPicture2A.argtypes = [SheetHandle, c_int, c_int, c_int, c_int, c_int, c_int, c_int]

    dll.xlSheetGetHorPageBreakA.restype = c_int
    dll.xlSheetGetHorPageBreakA.argtypes = [SheetHandle, c_int]

    dll.xlSheetGetHorPageBreakSizeA.restype = c_int
    dll.xlSheetGetHorPageBreakSizeA.argtypes = [SheetHandle]

    dll.xlSheetGetVerPageBreakA.restype = c_int
    dll.xlSheetGetVerPageBreakA.argtypes = [SheetHandle, c_int]

    dll.xlSheetGetVerPageBreakSizeA.restype = c_int
    dll.xlSheetGetVerPageBreakSizeA.argtypes = [SheetHandle]

    dll.xlSheetSetHorPageBreakA.restype = c_int
    dll.xlSheetSetHorPageBreakA.argtypes = [SheetHandle, c_int, c_int]

    dll.xlSheetSetVerPageBreakA.restype = c_int
    dll.xlSheetSetVerPageBreakA.argtypes = [SheetHandle, c_int, c_int]

    # ==================== Format 相关函数 ====================

    dll.xlFormatFontA.restype = FontHandle
    dll.xlFormatFontA.argtypes = [FormatHandle]

    dll.xlFormatSetFontA.restype = None
    dll.xlFormatSetFontA.argtypes = [FormatHandle, FontHandle]

    dll.xlFormatNumFormatA.restype = c_int
    dll.xlFormatNumFormatA.argtypes = [FormatHandle]

    dll.xlFormatSetNumFormatA.restype = None
    dll.xlFormatSetNumFormatA.argtypes = [FormatHandle, c_int]

    dll.xlFormatAlignHA.restype = c_int
    dll.xlFormatAlignHA.argtypes = [FormatHandle]

    dll.xlFormatSetAlignHA.restype = None
    dll.xlFormatSetAlignHA.argtypes = [FormatHandle, c_int]

    dll.xlFormatAlignVA.restype = c_int
    dll.xlFormatAlignVA.argtypes = [FormatHandle]

    dll.xlFormatSetAlignVA.restype = None
    dll.xlFormatSetAlignVA.argtypes = [FormatHandle, c_int]

    dll.xlFormatWrapA.restype = c_int
    dll.xlFormatWrapA.argtypes = [FormatHandle]

    dll.xlFormatSetWrapA.restype = None
    dll.xlFormatSetWrapA.argtypes = [FormatHandle, c_int]

    dll.xlFormatRotationA.restype = c_int
    dll.xlFormatRotationA.argtypes = [FormatHandle]

    dll.xlFormatSetRotationA.restype = None
    dll.xlFormatSetRotationA.argtypes = [FormatHandle, c_int]

    dll.xlFormatIndentA.restype = c_int
    dll.xlFormatIndentA.argtypes = [FormatHandle]

    dll.xlFormatSetIndentA.restype = None
    dll.xlFormatSetIndentA.argtypes = [FormatHandle, c_int]

    dll.xlFormatShrinkToFitA.restype = c_int
    dll.xlFormatShrinkToFitA.argtypes = [FormatHandle]

    dll.xlFormatSetShrinkToFitA.restype = None
    dll.xlFormatSetShrinkToFitA.argtypes = [FormatHandle, c_int]

    dll.xlFormatSetBorderA.restype = None
    dll.xlFormatSetBorderA.argtypes = [FormatHandle, c_int]

    dll.xlFormatSetBorderColorA.restype = None
    dll.xlFormatSetBorderColorA.argtypes = [FormatHandle, c_int]

    dll.xlFormatBorderLeftA.restype = c_int
    dll.xlFormatBorderLeftA.argtypes = [FormatHandle]

    dll.xlFormatSetBorderLeftA.restype = None
    dll.xlFormatSetBorderLeftA.argtypes = [FormatHandle, c_int]

    dll.xlFormatBorderRightA.restype = c_int
    dll.xlFormatBorderRightA.argtypes = [FormatHandle]

    dll.xlFormatSetBorderRightA.restype = None
    dll.xlFormatSetBorderRightA.argtypes = [FormatHandle, c_int]

    dll.xlFormatBorderTopA.restype = c_int
    dll.xlFormatBorderTopA.argtypes = [FormatHandle]

    dll.xlFormatSetBorderTopA.restype = None
    dll.xlFormatSetBorderTopA.argtypes = [FormatHandle, c_int]

    dll.xlFormatBorderBottomA.restype = c_int
    dll.xlFormatBorderBottomA.argtypes = [FormatHandle]

    dll.xlFormatSetBorderBottomA.restype = None
    dll.xlFormatSetBorderBottomA.argtypes = [FormatHandle, c_int]

    dll.xlFormatBorderLeftColorA.restype = c_int
    dll.xlFormatBorderLeftColorA.argtypes = [FormatHandle]

    dll.xlFormatSetBorderLeftColorA.restype = None
    dll.xlFormatSetBorderLeftColorA.argtypes = [FormatHandle, c_int]

    dll.xlFormatBorderRightColorA.restype = c_int
    dll.xlFormatBorderRightColorA.argtypes = [FormatHandle]

    dll.xlFormatSetBorderRightColorA.restype = None
    dll.xlFormatSetBorderRightColorA.argtypes = [FormatHandle, c_int]

    dll.xlFormatBorderTopColorA.restype = c_int
    dll.xlFormatBorderTopColorA.argtypes = [FormatHandle]

    dll.xlFormatSetBorderTopColorA.restype = None
    dll.xlFormatSetBorderTopColorA.argtypes = [FormatHandle, c_int]

    dll.xlFormatBorderBottomColorA.restype = c_int
    dll.xlFormatBorderBottomColorA.argtypes = [FormatHandle]

    dll.xlFormatSetBorderBottomColorA.restype = None
    dll.xlFormatSetBorderBottomColorA.argtypes = [FormatHandle, c_int]

    dll.xlFormatBorderDiagonalA.restype = c_int
    dll.xlFormatBorderDiagonalA.argtypes = [FormatHandle]

    dll.xlFormatSetBorderDiagonalA.restype = None
    dll.xlFormatSetBorderDiagonalA.argtypes = [FormatHandle, c_int]

    dll.xlFormatBorderDiagonalStyleA.restype = c_int
    dll.xlFormatBorderDiagonalStyleA.argtypes = [FormatHandle]

    dll.xlFormatSetBorderDiagonalStyleA.restype = None
    dll.xlFormatSetBorderDiagonalStyleA.argtypes = [FormatHandle, c_int]

    dll.xlFormatBorderDiagonalColorA.restype = c_int
    dll.xlFormatBorderDiagonalColorA.argtypes = [FormatHandle]

    dll.xlFormatSetBorderDiagonalColorA.restype = None
    dll.xlFormatSetBorderDiagonalColorA.argtypes = [FormatHandle, c_int]

    dll.xlFormatFillPatternA.restype = c_int
    dll.xlFormatFillPatternA.argtypes = [FormatHandle]

    dll.xlFormatSetFillPatternA.restype = None
    dll.xlFormatSetFillPatternA.argtypes = [FormatHandle, c_int]

    dll.xlFormatPatternForegroundColorA.restype = c_int
    dll.xlFormatPatternForegroundColorA.argtypes = [FormatHandle]

    dll.xlFormatSetPatternForegroundColorA.restype = None
    dll.xlFormatSetPatternForegroundColorA.argtypes = [FormatHandle, c_int]

    dll.xlFormatPatternBackgroundColorA.restype = c_int
    dll.xlFormatPatternBackgroundColorA.argtypes = [FormatHandle]

    dll.xlFormatSetPatternBackgroundColorA.restype = None
    dll.xlFormatSetPatternBackgroundColorA.argtypes = [FormatHandle, c_int]

    dll.xlFormatLockedA.restype = c_int
    dll.xlFormatLockedA.argtypes = [FormatHandle]

    dll.xlFormatSetLockedA.restype = None
    dll.xlFormatSetLockedA.argtypes = [FormatHandle, c_int]

    dll.xlFormatHiddenA.restype = c_int
    dll.xlFormatHiddenA.argtypes = [FormatHandle]

    dll.xlFormatSetHiddenA.restype = None
    dll.xlFormatSetHiddenA.argtypes = [FormatHandle, c_int]

    # ==================== Font 相关函数 ====================

    dll.xlFontSizeA.restype = c_int
    dll.xlFontSizeA.argtypes = [FontHandle]

    dll.xlFontSetSizeA.restype = None
    dll.xlFontSetSizeA.argtypes = [FontHandle, c_int]

    dll.xlFontItalicA.restype = c_int
    dll.xlFontItalicA.argtypes = [FontHandle]

    dll.xlFontSetItalicA.restype = None
    dll.xlFontSetItalicA.argtypes = [FontHandle, c_int]

    dll.xlFontStrikeOutA.restype = c_int
    dll.xlFontStrikeOutA.argtypes = [FontHandle]

    dll.xlFontSetStrikeOutA.restype = None
    dll.xlFontSetStrikeOutA.argtypes = [FontHandle, c_int]

    dll.xlFontColorA.restype = c_int
    dll.xlFontColorA.argtypes = [FontHandle]

    dll.xlFontSetColorA.restype = None
    dll.xlFontSetColorA.argtypes = [FontHandle, c_int]

    dll.xlFontBoldA.restype = c_int
    dll.xlFontBoldA.argtypes = [FontHandle]

    dll.xlFontSetBoldA.restype = None
    dll.xlFontSetBoldA.argtypes = [FontHandle, c_int]

    dll.xlFontScriptA.restype = c_int
    dll.xlFontScriptA.argtypes = [FontHandle]

    dll.xlFontSetScriptA.restype = None
    dll.xlFontSetScriptA.argtypes = [FontHandle, c_int]

    dll.xlFontUnderlineA.restype = c_int
    dll.xlFontUnderlineA.argtypes = [FontHandle]

    dll.xlFontSetUnderlineA.restype = None
    dll.xlFontSetUnderlineA.argtypes = [FontHandle, c_int]

    dll.xlFontNameA.restype = c_char_p
    dll.xlFontNameA.argtypes = [FontHandle]

    dll.xlFontSetNameA.restype = None
    dll.xlFontSetNameA.argtypes = [FontHandle, c_char_p]

    _api_initialized = True


def _encode_str(s):
    """编码字符串为 bytes (UTF-8)"""
    if s is None:
        return None
    if isinstance(s, bytes):
        return s
    return s.encode('utf-8')


def _decode_str(b):
    """解码 bytes 为字符串 (UTF-8)"""
    if b is None:
        return None
    if isinstance(b, str):
        return b
    return b.decode('utf-8')


_init_api()

__all__ = [
    'BookHandle',
    'SheetHandle',
    'FormatHandle',
    'FontHandle',
    'AutoFilterHandle',
    'FilterColumnHandle',
    'get_libxl_dll',
    '_encode_str',
    '_decode_str',
]
