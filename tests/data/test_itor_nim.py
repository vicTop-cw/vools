import pytest
import threading
import time

from vools.data import use_nim, get_itor


class TestNimItor:
    @classmethod
    def setup_class(cls):
        assert use_nim(True), "Nim DLL not available"

    @classmethod
    def teardown_class(cls):
        use_nim(False)

    def test_basic_iteration(self):
        itor = get_itor([10, 20, 30, 40, 50])
        result = list(itor)
        assert result == [10, 20, 30, 40, 50]

    def test_send_value(self):
        itor = get_itor([1, 2, 3])
        itor.send(99)
        result = list(itor)
        assert 99 in result

    def test_send_multiple_values(self):
        itor = get_itor([1, 2])
        itor.send([100, 200])
        result = list(itor)
        assert 100 in result
        assert 200 in result

    def test_pause_resume(self):
        itor = get_itor([1, 2, 3, 4, 5])
        
        values = []
        values.append(next(itor))
        assert values == [1]
        
        itor.set_pause()
        
        def resume_thread():
            time.sleep(0.1)
            itor.resume()
        
        t = threading.Thread(target=resume_thread)
        t.start()
        
        values.append(next(itor))
        t.join()
        
        values.extend(list(itor))
        assert values == [1, 2, 3, 4, 5]

    def test_stop(self):
        itor = get_itor([1, 2, 3, 4, 5])
        next(itor)
        next(itor)
        itor.stop()
        
        with pytest.raises(StopIteration):
            next(itor)

    def test_restart(self):
        itor = get_itor([1, 2, 3])
        assert next(itor) == 1
        assert next(itor) == 2
        itor.restart()
        assert next(itor) == 1
        assert next(itor) == 2
        assert next(itor) == 3

    def test_state(self):
        itor = get_itor([1, 2])
        assert itor.state.value == 0
        
        next(itor)
        assert itor.state.value == 1
        
        itor.set_pause()
        assert itor.state.value == 2
        
        itor.resume()
        next(itor)
        with pytest.raises(StopIteration):
            next(itor)
        assert itor.state.value == 3

    def test_multiple_iterators(self):
        itor1 = get_itor([1, 2, 3])
        itor2 = get_itor([4, 5, 6])
        
        assert next(itor1) == 1
        assert next(itor2) == 4
        assert next(itor1) == 2
        assert next(itor2) == 5
        
        assert list(itor1) == [3]
        assert list(itor2) == [6]

    def test_empty_iterable(self):
        itor = get_itor([])
        with pytest.raises(StopIteration):
            next(itor)

    def test_single_element(self):
        itor = get_itor([42])
        assert next(itor) == 42
        with pytest.raises(StopIteration):
            next(itor)

    def test_float_iteration(self):
        itor = get_itor([1.5, 2.5, 3.5, 4.5])
        result = list(itor)
        assert result == [1.5, 2.5, 3.5, 4.5]

    def test_string_iteration(self):
        itor = get_itor(['hello', 'world', 'nim'])
        result = list(itor)
        assert result == ['hello', 'world', 'nim']

    def test_mixed_types(self):
        itor = get_itor([1, 'abc', 3.14, True, None])
        result = list(itor)
        assert result == [1, 'abc', 3.14, True, None]

    def test_list_iteration(self):
        itor = get_itor([[1, 2], [3, 4], [5, 6]])
        result = list(itor)
        assert result == [[1, 2], [3, 4], [5, 6]]

    def test_dict_iteration(self):
        itor = get_itor([{'a': 1}, {'b': 2}])
        result = list(itor)
        assert result == [{'a': 1}, {'b': 2}]

    def test_send_string(self):
        itor = get_itor([1, 2, 3])
        itor.send('inserted')
        result = list(itor)
        assert 'inserted' in result

    def test_send_float(self):
        itor = get_itor([1, 2, 3])
        itor.send(3.14)
        result = list(itor)
        assert 3.14 in result