"""Pandas 集成接口

支持 engine 参数切换底层实现 (vools/openpyxl/xlrd/odf)。
"""
import os
from typing import Optional, Union, List

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from .._objects import Book
from .engines import get_engine


def read_excel_df(
    filename: str,
    sheet_name: Optional[Union[str, int]] = 0,
    header: int = 0,
    skip_rows: int = 0,
    usecols: Optional[List[int]] = None,
    dtype: Optional[dict] = None,
    skip_empty: bool = True,
    engine: str = 'vools',
    **engine_kwargs,
) -> 'pd.DataFrame':
    """读取 Excel 文件为 pandas DataFrame

    Args:
        filename: Excel 文件路径
        sheet_name: 工作表名称或索引
        header: 表头行号 (从0开始)
        skip_rows: 跳过的行数
        usecols: 要读取的列索引列表
        dtype: 列类型映射
        skip_empty: 是否跳过空行
        engine: Excel 引擎名 ('vools'/'openpyxl'/'xlrd'/'odf')
        **engine_kwargs: 透传给引擎的额外参数

    Returns:
        pandas DataFrame
    """
    if not PANDAS_AVAILABLE:
        raise ImportError('pandas is required. Install: pip install pandas')

    # 通过 engine 层读取
    eng = get_engine(engine)
    # 转换参数名以适配 pandas 接口
    engine_kwargs = dict(engine_kwargs)
    if 'skip_rows' in engine_kwargs:
        engine_kwargs['skiprows'] = engine_kwargs.pop('skip_rows')

    df = eng.read_df(
        filename,
        sheet_name=sheet_name,
        header=header,
        skip_rows=skip_rows,
        usecols=usecols,
        dtype=dtype,
        skip_empty=skip_empty,
        **engine_kwargs,
    )

    # 应用 usecols (engine 层未处理时)
    if usecols is not None and not df.empty:
        cols = list(df.columns)
        if all(isinstance(c, int) for c in usecols):
            df = df.iloc[:, [c for c in usecols if c < len(cols)]]
        else:
            df = df[[c for c in usecols if c in cols]]

    return df


def write_excel_df(
    filename: str,
    df: 'pd.DataFrame',
    sheet_name: str = 'Sheet1',
    header: bool = True,
    index: bool = False,
    fmt_header: bool = True,
    engine: str = 'vools',
    **engine_kwargs,
) -> bool:
    """将 pandas DataFrame 写入 Excel 文件

    Args:
        filename: Excel 文件路径
        df: pandas DataFrame
        sheet_name: 工作表名称
        header: 是否写入表头
        index: 是否写入索引列
        fmt_header: 是否格式化表头 (仅 vools 引擎)
        engine: Excel 引擎名 ('vools'/'openpyxl'/'xlrd'/'odf')
        **engine_kwargs: 透传给引擎的额外参数

    Returns:
        True-成功
    """
    if not PANDAS_AVAILABLE:
        raise ImportError('pandas is required. Install: pip install pandas')

    # 处理 index
    if index:
        df = df.reset_index()

    # 处理 header
    if not header:
        df = df.copy()
        df.columns = [f'col_{i}' for i in range(len(df.columns))]

    # 通过 engine 层写入
    eng = get_engine(engine)
    return eng.write_df(
        filename,
        df,
        sheet_name=sheet_name,
        index=index,
        **engine_kwargs,
    )


# 保留旧版实现以备不时之需 (标为 internal)
def _read_excel_df_v1(
    filename: str,
    sheet_name: Optional[Union[str, int]] = 0,
    header: int = 1,
    skip_rows: int = 0,
    usecols: Optional[List[int]] = None,
    dtype: Optional[dict] = None,
    skip_empty: bool = True,
) -> 'pd.DataFrame':
    """旧版接口 (header=1 默认)，保持向后兼容"""
    return read_excel_df(
        filename,
        sheet_name=sheet_name,
        header=header,
        skip_rows=skip_rows,
        usecols=usecols,
        dtype=dtype,
        skip_empty=skip_empty,
    )


__all__ = [
    'read_excel_df',
    'write_excel_df',
]
