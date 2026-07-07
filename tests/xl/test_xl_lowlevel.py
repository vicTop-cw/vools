"""测试低层 LibXL API"""
import os
import tempfile

import pytest

from vools.xl._core.api import get_libxl_dll, _encode_str, _decode_str
import ctypes
from ctypes import c_void_p, byref


pytestmark = pytest.mark.windows_only


@pytest.fixture
def dll():
    return get_libxl_dll()


def test_dll_loading(dll):
    assert dll is not None


def test_create_book(dll):
    book = dll.xlCreateBookCA()
    assert book != 0
    error = dll.xlBookErrorMessageA(book)
    error_str = _decode_str(error) if error else ''
    assert error_str in ('', 'ok')
    dll.xlBookReleaseA(book)


def test_add_sheet(dll):
    book = dll.xlCreateBookCA()
    sheet = dll.xlBookAddSheetA(book, _encode_str('Sheet1'), None)
    assert sheet != 0
    dll.xlBookReleaseA(book)


def test_write_and_read_str(dll):
    book = dll.xlCreateBookCA()
    sheet = dll.xlBookAddSheetA(book, _encode_str('Sheet1'), None)
    
    test_str = 'Hello LibXL!'
    result = dll.xlSheetWriteStrA(sheet, 1, 0, _encode_str(test_str), None)
    assert result == 1
    
    fmt = c_void_p()
    value = dll.xlSheetReadStrA(sheet, 1, 0, byref(fmt))
    assert _decode_str(value) == test_str
    
    dll.xlBookReleaseA(book)


def test_save_file(dll):
    book = dll.xlCreateBookCA()
    sheet = dll.xlBookAddSheetA(book, _encode_str('Sheet1'), None)
    dll.xlSheetWriteStrA(sheet, 0, 0, _encode_str('Test'), None)
    
    tmp_file = os.path.join(tempfile.gettempdir(), 'test_libxl_lowlevel.xls')
    try:
        result = dll.xlBookSaveA(book, _encode_str(tmp_file))
        assert result == 1
        assert os.path.exists(tmp_file)
        assert os.path.getsize(tmp_file) > 0
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
        dll.xlBookReleaseA(book)
