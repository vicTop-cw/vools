"""Excel 引擎适配层

提供 pandas 风格的 engine 抽象，让 read_excel_df/write_excel_df 可以切换
底层实现 (vools.xl, openpyxl, xlrd, odf 等)。
"""

import os
from typing import Any, Callable, Optional, Dict, List
from abc import ABC, abstractmethod

__all__ = [
    'BaseEngine',
    'VoolsEngine',
    'PandasEngine',
    'register_engine',
    'get_engine',
    'list_engines',
]


class BaseEngine(ABC):
    """Excel 引擎抽象基类

    所有引擎必须实现 read_df / write_df 两个方法。
    """

    name: str = 'base'

    @abstractmethod
    def read_df(self, filename: str, sheet_name=None, header: int = 0,
                **kwargs) -> 'pd.DataFrame':
        """读取 Excel 为 DataFrame

        Args:
            filename: 文件路径
            sheet_name: 工作表名称/索引
            header: 表头行号
            **kwargs: 引擎特定参数

        Returns:
            DataFrame
        """
        pass

    @abstractmethod
    def write_df(self, filename: str, df: 'pd.DataFrame',
                 sheet_name: str = 'Sheet1', **kwargs) -> bool:
        """将 DataFrame 写入 Excel

        Args:
            filename: 文件路径
            df: DataFrame
            sheet_name: 工作表名称
            **kwargs: 引擎特定参数

        Returns:
            True-成功
        """
        pass


class VoolsEngine(BaseEngine):
    """vools.xl 内置引擎

    基于 LibXL 的 C 库实现，提供最佳的写入性能。
    trial 版本会自动从第 1 行开始写入。
    """

    name = 'vools'

    def read_df(self, filename: str, sheet_name=None, header: int = 0,
                **kwargs) -> 'pd.DataFrame':
        """读取 Excel 为 DataFrame

        vools engine 内部处理 trial 限制:
        - 读取时跳过第 0 行 (LibXL trial 版本会写入提示)
        - 写入时自动从第 1 行开始
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError('pandas is required. Install: pip install pandas')

        # trial 版本第 0 行被占用，实际表头在第 1 行
        actual_header = header + 1 if header >= 0 else 0

        from .._objects import Book

        if not os.path.exists(filename):
            raise FileNotFoundError(f'File not found: {filename}')

        with Book() as book:
            if not book.load(filename):
                raise RuntimeError(f'Failed to load: {book.error_message}')

            # 获取工作表
            if isinstance(sheet_name, int) or sheet_name is None:
                idx = sheet_name if sheet_name is not None else 0
                sheet = book.get_sheet(idx)
            else:
                found = False
                for i in range(book.sheet_count):
                    s = book.get_sheet(i)
                    if s.name == sheet_name:
                        sheet = s
                        found = True
                        break
                if not found:
                    raise ValueError(f'Sheet "{sheet_name}" not found')

            first_row = actual_header
            last_row = sheet.last_row
            first_col = sheet.first_col
            last_col = sheet.last_col

            # 自动检测有效列数 (从表头行扫描)
            last_col = first_col
            for col in range(first_col, min(first_col + 100, sheet.last_col + 1)):
                ct = sheet.cell_type(first_row, col)
                if ct == 2:  # STRING
                    val = sheet.read_str(first_row, col)
                    if val and str(val).strip() != '':
                        last_col = col
                elif ct == 1:  # NUMBER
                    last_col = col
                elif ct == 3:  # BOOLEAN
                    last_col = col

            if last_row < first_row or last_col < first_col:
                return pd.DataFrame()

            rcount = last_row - first_row + 1
            ccount = last_col - first_col + 1
            matrix = sheet.read_matrix(rcount, ccount, first_row, first_col)

            if not matrix:
                return pd.DataFrame()

            # 第一行为表头
            columns = []
            for i, c in enumerate(matrix[0]):
                if c is None or (isinstance(c, str) and c.strip() == ''):
                    columns.append(f'col_{i}')
                else:
                    columns.append(str(c))

            data = matrix[1:] if len(matrix) > 1 else []
            # 过滤空行
            data = [row for row in data if any(v is not None and v != ''
                                              for v in row)]

            df = pd.DataFrame(data, columns=columns)

            # 应用 dtype
            dtype = kwargs.get('dtype')
            if dtype:
                for col, typ in dtype.items():
                    if col in df.columns:
                        df[col] = df[col].astype(typ, errors='ignore')

            return df

    def write_df(self, filename: str, df: 'pd.DataFrame',
                 sheet_name: str = 'Sheet1', **kwargs) -> bool:
        """将 DataFrame 写入 Excel

        自动从第 1 行开始写入 (避开 trial 版本 A1)。
        """
        from .._objects import Book

        with Book() as book:
            sheet = book.add_sheet(sheet_name)
            # 写入表头 (从第 1 行开始)
            headers = [str(c) for c in df.columns]
            sheet.write_matrix([headers], start_row=1, start_col=0)
            # 写入数据
            if len(df) > 0:
                data = df.values.tolist()
                sheet.write_matrix(data, start_row=2, start_col=0)
            return book.save(filename)


class PandasEngine(BaseEngine):
    """Pandas 引擎包装

    将 pandas 自身的 read_excel/to_excel 包装为 BaseEngine 接口。
    engine 参数可以指定 openpyxl/xlrd/odf 等。
    """

    name = 'pandas'

    def __init__(self, sub_engine: str = 'openpyxl'):
        """初始化

        Args:
            sub_engine: pandas 引擎名 ('openpyxl'/'xlrd'/'odf' 等)
        """
        self.sub_engine = sub_engine

    def read_df(self, filename: str, sheet_name=None, header: int = 0,
                **kwargs) -> 'pd.DataFrame':
        try:
            import pandas as pd
        except ImportError:
            raise ImportError('pandas is required. Install: pip install pandas')

        # 转换 vools 参数名为 pandas 参数名
        pandas_kwargs = dict(kwargs)
        if 'skip_rows' in pandas_kwargs:
            pandas_kwargs['skiprows'] = pandas_kwargs.pop('skip_rows')
        if 'usecols' in pandas_kwargs:
            pandas_kwargs['usecols'] = pandas_kwargs.pop('usecols')
        if 'skip_empty' in pandas_kwargs:
            pandas_kwargs.pop('skip_empty')

        pandas_kwargs.setdefault('engine', self.sub_engine)
        pandas_kwargs['header'] = header
        return pd.read_excel(filename, sheet_name=sheet_name, **pandas_kwargs)

    def write_df(self, filename: str, df: 'pd.DataFrame',
                 sheet_name: str = 'Sheet1', **kwargs) -> bool:
        kwargs.setdefault('engine', self.sub_engine)
        kwargs['sheet_name'] = sheet_name
        kwargs['index'] = kwargs.get('index', False)
        df.to_excel(filename, **kwargs)
        return True


# ==================== 注册机制 ====================

_engines: Dict[str, BaseEngine] = {}
_engine_factories: Dict[str, Callable[[], BaseEngine]] = {}


def register_engine(name: str, engine: BaseEngine = None,
                    factory: Callable[[], BaseEngine] = None) -> None:
    """注册 Excel 引擎

    支持两种方式:
    1. 注册实例: register_engine('myengine', my_engine_instance)
    2. 注册工厂: register_engine('myengine', factory=lambda: MyEngine())

    Args:
        name: 引擎名称
        engine: 引擎实例 (可选)
        factory: 工厂函数 (可选)
    """
    if engine is not None:
        _engines[name] = engine
    elif factory is not None:
        _engine_factories[name] = factory
    else:
        raise ValueError('Must provide engine instance or factory')


def get_engine(name: str = 'vools') -> BaseEngine:
    """获取 Excel 引擎

    Args:
        name: 引擎名称，默认 'vools'

    Returns:
        引擎实例
    """
    if name in _engines:
        return _engines[name]
    if name in _engine_factories:
        engine = _engine_factories[name]()
        _engines[name] = engine
        return engine
    raise ValueError(f'Engine not found: {name}. Available: {list_engines()}')


def list_engines() -> List[str]:
    """列出已注册的引擎"""
    return sorted(set(_engines.keys()) | set(_engine_factories.keys()))


# ==================== 注册内置引擎 ====================

register_engine('vools', VoolsEngine())
register_engine('openpyxl', factory=lambda: PandasEngine('openpyxl'))
register_engine('xlrd', factory=lambda: PandasEngine('xlrd'))
register_engine('odf', factory=lambda: PandasEngine('odf'))
