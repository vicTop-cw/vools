"""测试对象级封装"""
import os
import tempfile

import pytest

from vools.xl import Book


pytestmark = pytest.mark.windows_only


@pytest.fixture
def tmp_dir():
    return tempfile.gettempdir()


def test_book_creation():
    book = Book()
    assert book is not None
    assert book.error_message in ('', 'ok')
    book.release()


def test_add_sheet():
    with Book() as book:
        sheet = book.add_sheet('Sheet1')
        assert sheet is not None
        assert sheet.name == 'Sheet1'
        assert book.sheet_count == 1


def test_write_and_read_str():
    with Book() as book:
        sheet = book.add_sheet('Sheet1')
        result = sheet.write_str(1, 0, 'Hello LibXL!')
        assert result is True
        value = sheet.read_str(1, 0)
        assert value == 'Hello LibXL!'


def test_write_and_read_num():
    with Book() as book:
        sheet = book.add_sheet('Sheet1')
        result = sheet.write_num(1, 1, 123.45)
        assert result is True
        value = sheet.read_num(1, 1)
        assert value == 123.45


def test_write_and_read_bool():
    with Book() as book:
        sheet = book.add_sheet('Sheet1')
        result = sheet.write_bool(1, 2, True)
        assert result is True
        value = sheet.read_bool(1, 2)
        assert value is True


def test_write_and_read_formula():
    with Book() as book:
        sheet = book.add_sheet('Sheet1')
        sheet.write_num(1, 1, 100)
        result = sheet.write_formula(1, 3, '=B2*2')
        assert result is True
        value = sheet.read_formula(1, 3)
        assert value == 'B2*2'


def test_cell_type():
    with Book() as book:
        sheet = book.add_sheet('Sheet1')
        sheet.write_str(1, 0, 'Hello')
        sheet.write_num(1, 1, 123.45)
        assert sheet.cell_type(1, 0) == 2
        assert sheet.cell_type(1, 1) == 1


def test_row_col_range():
    with Book() as book:
        sheet = book.add_sheet('Sheet1')
        sheet.write_str(1, 0, 'A2')
        sheet.write_str(3, 2, 'D4')
        assert sheet.first_row <= 1
        assert sheet.last_row >= 3
        assert sheet.first_col <= 0
        assert sheet.last_col >= 2


def test_format_and_font():
    with Book() as book:
        fmt = book.add_format()
        fmt.bold = True
        fmt.align_h = 2
        assert fmt is not None
        
        font = book.add_font()
        font.bold = True
        font.size = 14
        font.name = 'Arial'
        assert font is not None
        
        fmt2 = book.add_format()
        fmt2.font = font
        fmt2.fill_pattern = 1
        fmt2.pattern_foreground_color = 0xFFFF00
        assert fmt2 is not None
        
        sheet = book.add_sheet('Sheet1')
        sheet.write_str(2, 0, 'Bold Text', fmt)
        sheet.write_str(2, 1, 'Yellow Cell', fmt2)


def test_merge_cells():
    with Book() as book:
        sheet = book.add_sheet('Sheet1')
        result = sheet.set_merge(3, 3, 0, 2)
        assert result is True
        sheet.write_str(3, 0, 'Merged Cell')


def test_save_and_load(tmp_dir):
    test_file = os.path.join(tmp_dir, 'test_libxl_objects.xls')
    
    try:
        with Book() as book:
            sheet = book.add_sheet('Sheet1')
            sheet.write_str(1, 0, 'Hello LibXL!')
            sheet.write_num(1, 1, 123.45)
            result = book.save(test_file)
            assert result is True
            assert os.path.exists(test_file)
            assert os.path.getsize(test_file) > 0
        
        with Book() as book2:
            result = book2.load(test_file)
            assert result is True
            sheet2 = book2.get_sheet(0)
            assert sheet2.name == 'Sheet1'
            assert sheet2.read_str(1, 0) == 'Hello LibXL!'
            assert sheet2.read_num(1, 1) == 123.45
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_context_manager(tmp_dir):
    test_file = os.path.join(tmp_dir, 'test_libxl_context.xls')
    
    try:
        with Book() as book:
            sheet = book.add_sheet('Test')
            sheet.write_str(0, 0, 'Context Manager Test')
            result = book.save(test_file)
            assert result is True
            assert os.path.exists(test_file)
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
