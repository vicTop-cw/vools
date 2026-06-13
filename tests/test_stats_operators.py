"""
测试统计聚合扩展算子
"""

import pytest
from vools.reactive import Observable


class TestStatsOperators:
    """统计聚合算子测试"""
    
    def test_median(self):
        """测试 median 算子"""
        result = []
        Observable.from_iterable([1, 2, 3, 4, 5]).p().median().subscribe(on_next=result.append)
        assert result == [3.0]
        
        result2 = []
        Observable.from_iterable([1, 2, 3, 4]).p().median().subscribe(on_next=result2.append)
        assert result2 == [2.5]
    
    def test_variance(self):
        """测试 variance 算子"""
        result = []
        Observable.from_iterable([1, 2, 3, 4, 5]).p().variance().subscribe(on_next=result.append)
        assert abs(result[0] - 2.0) < 0.01
    
    def test_std(self):
        """测试 std 算子"""
        result = []
        Observable.from_iterable([2, 4, 4, 4, 5, 5, 7, 9]).p().std().subscribe(on_next=result.append)
        assert abs(result[0] - 2.0) < 0.01
    
    def test_quantile(self):
        """测试 quantile 算子"""
        result = []
        Observable.from_iterable([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]).p().quantile(0.5).subscribe(on_next=result.append)
        assert abs(result[0] - 5.5) < 0.01
    
    def test_arg_min(self):
        """测试 arg_min 算子"""
        result = []
        Observable.from_iterable([5, 3, 8, 1, 9]).p().arg_min().subscribe(on_next=result.append)
        assert result == [3]
    
    def test_arg_max(self):
        """测试 arg_max 算子"""
        result = []
        Observable.from_iterable([5, 3, 8, 1, 9]).p().arg_max().subscribe(on_next=result.append)
        assert result == [4]
    
    def test_n_unique(self):
        """测试 n_unique 算子"""
        result = []
        Observable.from_iterable([1, 2, 2, 3, 3, 3]).p().n_unique().subscribe(on_next=result.append)
        assert result == [3]


class TestRollingOperators:
    """滚动窗口算子测试"""
    
    def test_rolling_sum(self):
        """测试 rolling_sum 算子"""
        result = []
        Observable.from_iterable([1, 2, 3, 4, 5]).p().rolling_sum(3).subscribe(on_next=result.append)
        assert result == [1, 3, 6, 9, 12]
    
    def test_rolling_min(self):
        """测试 rolling_min 算子"""
        result = []
        Observable.from_iterable([5, 3, 8, 1, 9]).p().rolling_min(3).subscribe(on_next=result.append)
        assert result == [5, 3, 3, 1, 1]
    
    def test_rolling_max(self):
        """测试 rolling_max 算子"""
        result = []
        Observable.from_iterable([5, 3, 8, 1, 9]).p().rolling_max(3).subscribe(on_next=result.append)
        assert result == [5, 5, 8, 8, 9]
    
    def test_rolling_mean(self):
        """测试 rolling_mean 算子"""
        result = []
        Observable.from_iterable([1, 2, 3, 4, 5]).p().rolling_mean(3).subscribe(on_next=result.append)
        assert result == [1.0, 1.5, 2.0, 3.0, 4.0]


class TestCumulativeOperators:
    """累积变换算子测试"""
    
    def test_cum_sum(self):
        """测试 cum_sum 算子"""
        result = []
        Observable.from_iterable([1, 2, 3, 4]).p().cum_sum().subscribe(on_next=result.append)
        assert result == [1, 3, 6, 10]
    
    def test_cum_min(self):
        """测试 cum_min 算子"""
        result = []
        Observable.from_iterable([5, 3, 8, 1, 9]).p().cum_min().subscribe(on_next=result.append)
        assert result == [5, 3, 3, 1, 1]
    
    def test_cum_max(self):
        """测试 cum_max 算子"""
        result = []
        Observable.from_iterable([5, 3, 8, 1, 9]).p().cum_max().subscribe(on_next=result.append)
        assert result == [5, 5, 8, 8, 9]
    
    def test_cum_mean(self):
        """测试 cum_mean 算子"""
        result = []
        Observable.from_iterable([1, 2, 3, 4]).p().cum_mean().subscribe(on_next=result.append)
        assert result == [1.0, 1.5, 2.0, 2.5]
    
    def test_cum_prod(self):
        """测试 cum_prod 算子"""
        result = []
        Observable.from_iterable([1, 2, 3, 4]).p().cum_prod().subscribe(on_next=result.append)
        assert result == [1, 2, 6, 24]


class TestSortingOperators:
    """排序 Top-N 算子测试"""
    
    def test_sort(self):
        """测试 sort 算子"""
        result = []
        Observable.from_iterable([3, 1, 4, 2]).p().sort().subscribe(on_next=result.append)
        assert result == [1, 2, 3, 4]
    
    def test_sort_reverse(self):
        """测试 sort 算子（降序）"""
        result = []
        Observable.from_iterable([3, 1, 4, 2]).p().sort(reverse=True).subscribe(on_next=result.append)
        assert result == [4, 3, 2, 1]
    
    def test_top_k(self):
        """测试 top_k 算子"""
        result = []
        Observable.from_iterable([5, 3, 8, 1, 9, 2]).p().top_k(3).subscribe(on_next=result.append)
        assert result == [9, 8, 5]
    
    def test_bottom_k(self):
        """测试 bottom_k 算子"""
        result = []
        Observable.from_iterable([5, 3, 8, 1, 9, 2]).p().bottom_k(3).subscribe(on_next=result.append)
        assert result == [1, 2, 3]


class TestNoneHandlingOperators:
    """None 值处理算子测试"""
    
    def test_drop_none(self):
        """测试 drop_none 算子"""
        result = []
        Observable.from_iterable([1, None, 2, None, 3]).p().drop_none().subscribe(on_next=result.append)
        assert result == [1, 2, 3]
    
    def test_fill_none(self):
        """测试 fill_none 算子"""
        result = []
        Observable.from_iterable([1, None, 2, None, 3]).p().fill_none(0).subscribe(on_next=result.append)
        assert result == [1, 0, 2, 0, 3]
    
    def test_abs(self):
        """测试 abs 算子"""
        result = []
        Observable.from_iterable([-1, 2, -3, 4]).p().abs().subscribe(on_next=result.append)
        assert result == [1.0, 2.0, 3.0, 4.0]
    
    def test_clamp(self):
        """测试 clamp 算子"""
        result = []
        Observable.from_iterable([-1, 2, 5, 8]).p().clamp(0, 5).subscribe(on_next=result.append)
        assert result == [0.0, 2.0, 5.0, 5.0]


class TestExplodeOperators:
    """嵌套流展开算子测试"""
    
    def test_explode(self):
        """测试 explode 算子"""
        result = []
        Observable.from_iterable([[1, 2], [3, 4], [5]]).p().explode().subscribe(on_next=result.append)
        assert result == [1, 2, 3, 4, 5]
    
    def test_flatten(self):
        """测试 flatten 算子"""
        result = []
        Observable.from_iterable([[1, 2], [3, 4], [5]]).p().flatten().subscribe(on_next=result.append)
        assert result == [1, 2, 3, 4, 5]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
