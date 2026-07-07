"""Table 数据结构测试"""
import os
import tempfile

import pytest

from vools.data import Table


@pytest.fixture
def sample_table():
    data = [
        ['Alice', 25, 'New York', 50000],
        ['Bob', 30, 'Los Angeles', 60000],
        ['Charlie', 35, 'Chicago', 70000],
        ['David', 28, 'New York', 55000],
    ]
    return Table(data, columns=['name', 'age', 'city', 'salary'])


def test_basic_properties(sample_table):
    assert sample_table.rows() == 4
    assert sample_table.cols() == 4
    assert sample_table.columns() == ['name', 'age', 'city', 'salary']


def test_data_access(sample_table):
    assert sample_table.at(0, 0) == 'Alice'
    assert sample_table.row(1) == {'name': 'Bob', 'age': 30, 'city': 'Los Angeles', 'salary': 60000}
    col_age = sample_table.column('age')
    assert col_age == [25, 30, 35, 28]


def test_chained_operations(sample_table):
    result = sample_table.filter(lambda r: r['age'] > 25) \
        .select('name', 'city', 'salary') \
        .sort('salary', reverse=True)
    assert result.rows() == 3
    assert result.cols() == 3
    assert result.columns() == ['name', 'city', 'salary']


def test_aggregation(sample_table):
    assert sample_table.avg('age') == pytest.approx(29.5, rel=1e-6)
    assert sample_table.max('salary') == 70000


def test_group_by(sample_table):
    groups = sample_table.group_by('city')
    assert 'New York' in groups
    assert 'Los Angeles' in groups
    assert 'Chicago' in groups
    assert groups['New York'].rows() == 2
    assert groups['Los Angeles'].rows() == 1
    assert groups['Chicago'].rows() == 1


def test_pandas_conversion(sample_table):
    pd = pytest.importorskip('pandas')
    df = sample_table.to_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 4
    assert list(df.columns) == ['name', 'age', 'city', 'salary']


def test_from_dicts():
    dicts = [
        {'x': 1, 'y': 2},
        {'x': 3, 'y': 4},
    ]
    t2 = Table.from_dicts(dicts)
    assert t2.rows() == 2
    assert t2.cols() == 2
    assert t2.columns() == ['x', 'y']
    assert t2.at(0, 0) == 1
    assert t2.at(1, 1) == 4


@pytest.mark.windows_only
def test_excel_read_write(sample_table):
    tmp = os.path.join(tempfile.gettempdir(), 'test_table.xlsx')
    try:
        sample_table.write_excel(tmp)
        assert os.path.exists(tmp)
        
        t3 = Table.read_excel(tmp)
        assert t3.rows() == 4
        assert t3.cols() == 4
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
