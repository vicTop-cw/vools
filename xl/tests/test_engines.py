"""测试 Engine 适配层"""
import os
import tempfile

import pytest

pd = pytest.importorskip('pandas')

from vools.xl import (
    read_excel_df, write_excel_df,
    get_engine, register_engine, list_engines,
    BaseEngine, VoolsEngine, PandasEngine,
)


pytestmark = pytest.mark.windows_only


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        'name': ['Alice', 'Bob', 'Charlie'],
        'age': [25, 30, 35],
        'city': ['NYC', 'LA', 'Chicago'],
        'salary': [50000, 60000, 70000],
    })


def test_list_engines():
    engines = list_engines()
    assert 'vools' in engines
    assert 'openpyxl' in engines


def test_get_engine():
    e_vools = get_engine('vools')
    assert e_vools is not None
    assert e_vools.name == 'vools'
    
    e_openpyxl = get_engine('openpyxl')
    assert e_openpyxl is not None
    assert e_openpyxl.name == 'pandas'
    assert e_openpyxl.sub_engine == 'openpyxl'


def test_vools_engine_read_write(sample_df):
    tmp_vools = os.path.join(tempfile.gettempdir(), 'test_engine_vools.xlsx')
    
    try:
        write_excel_df(tmp_vools, sample_df, engine='vools')
        assert os.path.exists(tmp_vools)
        
        df_read = read_excel_df(tmp_vools, engine='vools')
        assert len(df_read) == 3
        assert list(df_read.columns) == ['name', 'age', 'city', 'salary']
        assert df_read.iloc[0]['name'] == 'Alice'
    finally:
        if os.path.exists(tmp_vools):
            os.remove(tmp_vools)


def test_openpyxl_engine(sample_df):
    tmp_op = os.path.join(tempfile.gettempdir(), 'test_engine_openpyxl.xlsx')
    
    try:
        write_excel_df(tmp_op, sample_df, engine='openpyxl')
        assert os.path.exists(tmp_op)
        
        df_read_op = read_excel_df(tmp_op, engine='openpyxl')
        assert len(df_read_op) == 3
        assert list(df_read_op.columns) == ['name', 'age', 'city', 'salary']
    finally:
        if os.path.exists(tmp_op):
            os.remove(tmp_op)


def test_custom_engine_registration(sample_df):
    class MyCustomEngine(BaseEngine):
        name = 'custom'
        def read_df(self, filename, **kwargs):
            return pd.DataFrame({'custom': [1, 2, 3]})
        def write_df(self, filename, df, **kwargs):
            return True
    
    register_engine('custom', MyCustomEngine())
    assert 'custom' in list_engines()
    
    e_custom = get_engine('custom')
    df_custom = e_custom.read_df('test.xlsx')
    assert df_custom.shape == (3, 1)


def test_engine_kwargs_passthrough(sample_df):
    tmp_kwargs = os.path.join(tempfile.gettempdir(), 'test_kwargs.xlsx')
    
    try:
        write_excel_df(tmp_kwargs, sample_df, engine='openpyxl', index=True)
        df_kwargs = read_excel_df(tmp_kwargs, engine='openpyxl')
        assert len(df_kwargs.columns) > 4
    finally:
        if os.path.exists(tmp_kwargs):
            os.remove(tmp_kwargs)
