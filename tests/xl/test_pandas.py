"""测试 pandas 接口"""
import os
import tempfile

import pytest

pd = pytest.importorskip('pandas')

from vools.xl import read_excel_df, write_excel_df


pytestmark = pytest.mark.windows_only


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie', 'David'],
        'age': [25, 30, 35, 40],
        'city': ['New York', 'Los Angeles', 'Chicago', 'Boston'],
        'salary': [50000.0, 60000.0, 70000.0, 80000.0],
    })


def test_write_and_read_excel_df(sample_df):
    tmp_file = os.path.join(tempfile.gettempdir(), 'test_pandas.xlsx')
    
    try:
        result = write_excel_df(tmp_file, sample_df, sheet_name='Employees')
        assert result is True
        assert os.path.exists(tmp_file)
        assert os.path.getsize(tmp_file) > 0
        
        df_read = read_excel_df(tmp_file, sheet_name='Employees')
        assert len(df_read) == 4
        assert list(df_read.columns) == ['name', 'age', 'city', 'salary']
        assert df_read.iloc[0]['name'] == 'Alice'
        assert df_read.iloc[3]['salary'] == 80000.0
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


def test_read_excel_df_no_header(sample_df):
    tmp_file = os.path.join(tempfile.gettempdir(), 'test_pandas_noheader.xlsx')
    
    try:
        write_excel_df(tmp_file, sample_df, sheet_name='Employees')
        
        df_no_header = read_excel_df(tmp_file, sheet_name='Employees', header=-1)
        assert len(df_no_header) == 5
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


def test_read_excel_df_usecols(sample_df):
    tmp_file = os.path.join(tempfile.gettempdir(), 'test_pandas_usecols.xlsx')
    
    try:
        write_excel_df(tmp_file, sample_df, sheet_name='Employees')
        
        df_cols = read_excel_df(tmp_file, sheet_name='Employees', usecols=[0, 2])
        assert len(df_cols.columns) == 2
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)


def test_write_excel_df_with_index(sample_df):
    tmp_file = os.path.join(tempfile.gettempdir(), 'test_pandas_index.xlsx')
    
    try:
        result = write_excel_df(tmp_file, sample_df, sheet_name='Data', index=True)
        assert result is True
        
        df_index = read_excel_df(tmp_file, sheet_name='Data')
        assert len(df_index.columns) >= 4
    finally:
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
