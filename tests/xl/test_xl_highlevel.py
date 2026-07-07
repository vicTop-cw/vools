"""测试便捷函数"""
import os
import tempfile

import pytest

from vools.xl import (
    read_excel, write_excel,
    read_excel_rows, write_excel_rows,
    rowcol_to_addr, addr_to_rowcol,
    rgb_to_color, color_to_rgb,
)


pytestmark = pytest.mark.windows_only


def test_rowcol_to_addr():
    assert rowcol_to_addr(0, 0) == 'A1'
    assert rowcol_to_addr(0, 0, absolute=True) == '$A$1'
    assert rowcol_to_addr(10, 26) == 'AA11'


def test_addr_to_rowcol():
    assert addr_to_rowcol('A1') == (0, 0)
    assert addr_to_rowcol('$AB$12') == (11, 27)


def test_rgb_color_conversion():
    color = rgb_to_color(255, 128, 0)
    rgb = color_to_rgb(color)
    assert rgb[0] == 255
    assert rgb[1] == 128
    assert rgb[2] == 0


def test_write_and_read_excel():
    test_data = [
        {'name': 'Alice', 'age': 25, 'city': 'New York'},
        {'name': 'Bob', 'age': 30, 'city': 'Los Angeles'},
        {'name': 'Charlie', 'age': 35, 'city': 'Chicago'},
    ]
    tmp_dir = tempfile.gettempdir()
    test_file = os.path.join(tmp_dir, 'test_highlevel.xls')
    
    try:
        result = write_excel(test_file, test_data, sheet_name='Users')
        assert result is True
        assert os.path.exists(test_file)
        
        data = read_excel(test_file)
        assert len(data) == 3
        assert data[0]['name'] == 'Alice'
        assert data[1]['age'] == 30
        assert data[2]['city'] == 'Chicago'
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_write_and_read_excel_rows():
    test_rows = [
        ['Name', 'Age', 'City'],
        ['Alice', 25, 'New York'],
        ['Bob', 30, 'Los Angeles'],
    ]
    tmp_dir = tempfile.gettempdir()
    test_file = os.path.join(tmp_dir, 'test_highlevel_rows.xls')
    
    try:
        result = write_excel_rows(test_file, test_rows)
        assert result is True
        
        rows = read_excel_rows(test_file)
        assert len(rows) == 3
        assert rows[0][0] == 'Name'
        assert rows[1][1] == 25
        assert rows[2][2] == 'Los Angeles'
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_read_excel_no_header():
    test_data = [
        {'name': 'Alice', 'age': 25, 'city': 'New York'},
        {'name': 'Bob', 'age': 30, 'city': 'Los Angeles'},
    ]
    tmp_dir = tempfile.gettempdir()
    test_file = os.path.join(tmp_dir, 'test_highlevel_noheader.xls')
    
    try:
        write_excel(test_file, test_data, sheet_name='Users')
        
        data_no_header = read_excel(test_file, header=False)
        assert len(data_no_header) == 3
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
