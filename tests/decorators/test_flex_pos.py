"""
Tests for ``vools.decorators.flex_pos``.

Run with::

    cd e:\\IDEProjects\\AI\\vools
    python tests/decorators/test_flex_pos.py -v
"""

from __future__ import absolute_import
from __future__ import print_function

import importlib.util
import os
import sys
import unittest

# Load flex_pos.py directly from the file system so that this test suite does
# not depend on the surrounding ``vools`` package (which has its own
# third-party dependencies on Python 3.6). This proves the module is
# self-contained and can be copied to any Python 3.6+ project.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FLEX_POS_PATH = os.path.join(ROOT, 'vools', 'decorators', 'flex_pos.py')

_spec = importlib.util.spec_from_file_location('flex_pos', FLEX_POS_PATH)
_flex_pos_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_flex_pos_module)

flex_pos = _flex_pos_module.flex_pos
_ = _flex_pos_module._
is_placeholder = _flex_pos_module.is_placeholder


def add_plain(a, b):
    return a + b


def multiply_plain(a, b, c):
    return a * b * c


class Dummy(object):
    def __init__(self, value):
        self.value = value
        self.attr = {
            1: lambda a, b, c, d: (a, b, c, d),
        }

    def __getitem__(self, item):
        return self.value[item]


# ---------------------------------------------------------------------------
# Placeholder object tests
# ---------------------------------------------------------------------------

class TestPlaceholder(unittest.TestCase):
    def test_singleton(self):
        # The placeholder class always returns the same instance.
        self.assertIs(_, _flex_pos_module._Placeholder())

    def test_is_placeholder(self):
        self.assertTrue(is_placeholder(_))
        self.assertFalse(is_placeholder(None))
        self.assertFalse(is_placeholder('foo'))
        self.assertFalse(is_placeholder(object()))

    def test_repr(self):
        self.assertEqual(repr(_), '_')

    def test_outside_decorated_scope_is_plain_object(self):
        def outside():
            return str(_)
        result = outside()
        # Outside a decorated scope ``_`` is the singleton placeholder object.
        self.assertEqual(result, '_')


# ---------------------------------------------------------------------------
# Basic expression placeholders
# ---------------------------------------------------------------------------

class TestBasicPlaceholders(unittest.TestCase):
    def test_identity(self):
        @flex_pos
        def name():
            f = _
            return f(42)

        self.assertEqual(name(), 42)

    def test_subscript_with_constant(self):
        @flex_pos
        def name():
            f = _['a']
            return f({'a': 10})

        self.assertEqual(name(), 10)

    def test_subscript_with_variable(self):
        key = 'x'

        @flex_pos
        def name():
            f = _[key]
            return f({'x': 99})

        self.assertEqual(name(), 99)

    def test_subscript_with_placeholder(self):
        @flex_pos
        def name():
            f = _[_]
            return f([10, 20, 30], 1)

        self.assertEqual(name(), 20)

    def test_call_with_placeholder(self):
        @flex_pos
        def name():
            f = _(_, 2, 3)
            return f(lambda x, y, z: x + y + z, 4)

        self.assertEqual(name(), 9)

    def test_call_not_starting_with_placeholder(self):
        @flex_pos
        def name():
            f = add_plain(_, 3)
            return f(2)

        self.assertEqual(name(), 5)

    def test_map_like_call(self):
        data = [1, 2, 3]

        @flex_pos
        def name():
            f = map(_, data, _)
            # return list(f(lambda x, y: x + y, [10, 20, 30]))
            t = _ + _
            return list(f(t, [10, 20, 30]))

        self.assertEqual(name(), [11, 22, 33])


# ---------------------------------------------------------------------------
# Complex chained / nested placeholders
# ---------------------------------------------------------------------------

class TestComplexPlaceholders(unittest.TestCase):
    def test_attribute_subscript_call_chain(self):
        d = Dummy({'k': 100})

        @flex_pos
        def name():
            f = _.attr[_](2, 3, 4, _)[0]
            return f(d, 1, 5)

        # Dummy.attr[1] = lambda a,b,c,d: (a,b,c,d)
        # so f(d, 1, 5) -> d.attr[1](2,3,4,5)[0]
        # -> (2,3,4,5)[0] -> 2
        self.assertEqual(name(), 2)

    def test_nested_attribute_access(self):
        @flex_pos
        def name():
            f = _.upper()
            return f('hello')

        self.assertEqual(name(), 'HELLO')

    def test_binary_operator_placeholder(self):
        @flex_pos
        def name():
            f = _ + 10
            return f(5)

        self.assertEqual(name(), 15)

    def test_binary_operator_both_sides(self):
        @flex_pos
        def name():
            f = _ * _
            return f(3, 4)

        self.assertEqual(name(), 12)

    def test_comparison_placeholder(self):
        @flex_pos
        def name():
            f = _ > 5
            return f(10)

        self.assertTrue(name())

    def test_conditional_expression_placeholder(self):
        @flex_pos
        def name():
            f = 'big' if _ > 5 else 'small'
            return f(10)

        self.assertEqual(name(), 'big')

    def test_tuple_with_placeholder(self):
        @flex_pos
        def name():
            f = (_, _ + 1, _ + 2)
            return f(1, 1, 1)

        self.assertEqual(name(), (1, 2, 3))

    def test_list_with_placeholder(self):
        @flex_pos
        def name():
            f = [_, _ * 2, _ * 3]
            return f(2, 2, 2)

        self.assertEqual(name(), [2, 4, 6])

    def test_dict_with_placeholder(self):
        @flex_pos
        def name():
            f = {'value': _, 'double': _ * 2}
            return f(3, 3)

        self.assertEqual(name(), {'value': 3, 'double': 6})

    def test_repeated_placeholder_same_argument(self):
        @flex_pos
        def name():
            f = [_[0], _[0] + 1]
            return f([10, 20], [10, 20])

        self.assertEqual(name(), [10, 11])


# ---------------------------------------------------------------------------
# Control flow placeholders
# ---------------------------------------------------------------------------

class TestControlFlowPlaceholders(unittest.TestCase):
    def test_if_condition_placeholder(self):
        @flex_pos
        def name():
            f = 'yes' if _ else 'no'
            return f(True)

        self.assertEqual(name(), 'yes')

    def test_while_condition_placeholder(self):
        @flex_pos
        def name():
            n = 3
            f = _ > 0
            while f(n):
                n = n - 1
            return n

        self.assertEqual(name(), 0)

    def test_for_iter_placeholder(self):
        @flex_pos
        def name():
            f = reversed(_)
            result = []
            for x in f([1, 2, 3]):
                result.append(x)
            return result

        self.assertEqual(name(), [3, 2, 1])


# ---------------------------------------------------------------------------
# Real-world style usage
# ---------------------------------------------------------------------------

class TestRealWorldUsage(unittest.TestCase):
    def test_filter_and_map_pipeline(self):
        data = [1, 2, 3, 4, 5]

        @flex_pos
        def name():
            is_even = _ % 2 == 0
            double = _ * 2
            evens = filter(is_even, data)
            return list(map(double, evens))

        self.assertEqual(name(), [4, 8])

    def test_multi_arg_function(self):
        @flex_pos
        def name():
            f = multiply_plain(_, _, _)
            return f(2, 3, 4)

        self.assertEqual(name(), 24)

    def test_mixed_positional_and_keyword(self):
        def fn(a, b, c):
            return a + b + c

        @flex_pos
        def name():
            f = fn(_, _, _)
            return f(1, 2, 3)

        self.assertEqual(name(), 6)

    def test_keyword_only_placeholders(self):
        def fn(a, b):
            return a + b

        @flex_pos
        def name():
            f = fn(a=_, b=_)
            return f(1, 2)

        self.assertEqual(name(), 3)


# ---------------------------------------------------------------------------
# Class decoration
# ---------------------------------------------------------------------------

class TestClassDecoration(unittest.TestCase):
    def test_class_method_placeholder(self):
        @flex_pos
        class PlaceholderBuilder(object):
            def transform(self, value):
                add_one = _ + 1
                return add_one(value)

        b = PlaceholderBuilder()
        self.assertEqual(b.transform(5), 6)

    def test_class_init_placeholder(self):
        @flex_pos
        class Wrapper(object):
            def __init__(self, value):
                double = _ * 2
                self.transformed = double(value)

        w = Wrapper(7)
        self.assertEqual(w.transformed, 14)


# ---------------------------------------------------------------------------
# Nested lambdas and edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):
    def test_lambda_not_transformed(self):
        @flex_pos
        def name():
            f = lambda x: _ + x
            return f(5)

        # The placeholder is not mixed with explicit lambdas; inside the
        # lambda ``_`` refers to the global singleton and therefore fails
        # when used arithmetically.
        with self.assertRaises(TypeError):
            name()

    def test_no_placeholder_no_change(self):
        @flex_pos
        def name():
            return 42

        self.assertEqual(name(), 42)

    def test_return_placeholder(self):
        @flex_pos
        def name():
            return _ * 2

        self.assertEqual(name()(3), 6)

    def test_multiple_statements(self):
        @flex_pos
        def name():
            f = _ + 1
            g = _ * 2
            return f(g(3))

        self.assertEqual(name(), 7)


# ---------------------------------------------------------------------------
# Variadic signature markers ``_`` / ``__``
# ---------------------------------------------------------------------------

class TestVariadicSignature(unittest.TestCase):
    def test_underscore_becomes_args(self):
        @flex_pos
        def collect(prefix, _):
            return prefix, args

        self.assertEqual(collect('a', 1, 2, 3), ('a', (1, 2, 3)))

    def test_double_underscore_becomes_kwargs(self):
        @flex_pos
        def collect(prefix, __):
            return prefix, kwargs

        self.assertEqual(
            collect('a', x=1, y=2),
            ('a', {'x': 1, 'y': 2})
        )

    def test_both_markers(self):
        @flex_pos
        def collect(prefix, _, suffix, __):
            return prefix, args, suffix, kwargs

        result = collect('a', 1, 2, suffix='z', extra='e')
        self.assertEqual(result, ('a', (1, 2), 'z', {'extra': 'e'}))

    def test_underscore_enforces_keyword_only_after(self):
        @flex_pos
        def split(a, _, b):
            return a, args, b

        self.assertEqual(split(1, 2, 3, 4, b=5), (1, (2, 3, 4), 5))
        with self.assertRaises(TypeError):
            split(1, 2, 3, 4, 5)

    def test_body_still_uses_underscore_as_placeholder(self):
        key = 'k'

        @flex_pos
        def name(a, _, b, __):
            f = _
            g = _[key]
            h = _[_]
            i = _(_, 2, 3)
            j = add_plain(_, 3)
            return (
                f(1),
                g({'k': 10}),
                h([1, 2], 0),
                i(lambda x, y, z: x + y + z, 4),
                j(2),
                sum(args),
                sorted(kwargs.items())
            )

        result = name('pos', 10, 20, 30, b='kw', x=1, y=2)
        self.assertEqual(result[0], 1)
        self.assertEqual(result[1], 10)
        self.assertEqual(result[2], 1)
        self.assertEqual(result[3], 9)
        self.assertEqual(result[4], 5)
        self.assertEqual(result[5], 60)
        self.assertEqual(result[6], [('x', 1), ('y', 2)])

    def test_class_method_variadic(self):
        @flex_pos
        class CollectorVariadic(object):
            def gather(self, _, label, __):
                return args, label, kwargs

        c = CollectorVariadic()
        self.assertEqual(
            c.gather(1, 2, 3, label='x', extra='e'),
            ((1, 2, 3), 'x', {'extra': 'e'})
        )

    def test_cannot_use_underscore_as_vararg(self):
        # ``*_`` conflicts with the ``_`` marker semantics.
        with self.assertRaises(SyntaxError):
            @flex_pos
            def bad(a, *_):
                pass

    def test_cannot_use_double_underscore_as_kwarg(self):
        # ``**__`` conflicts with the ``__`` marker semantics.
        with self.assertRaises(SyntaxError):
            @flex_pos
            def bad(a, **__):
                pass

    def test_double_underscore_cannot_precede_underscore(self):
        with self.assertRaises(SyntaxError):
            @flex_pos
            def bad(a, __, _):
                pass

    def test_missing_keyword_only_argument_raises(self):
        @flex_pos
        def name(a, _, b, __):
            return a, args, b, kwargs

        with self.assertRaises(TypeError):
            name(1, 2, 3, c=2, d=3)


# ---------------------------------------------------------------------------
# Nested decorators and class-method coverage
# ---------------------------------------------------------------------------

class TestNestedAndClassMethods(unittest.TestCase):
    def test_class_with_multiple_placeholder_methods(self):
        @flex_pos
        class Calc(object):
            def add(self, x):
                return add_plain(_, x)

            def scale(self, factor):
                return _ * factor

        c = Calc()
        self.assertEqual(c.add(2)(3), 5)
        self.assertEqual(c.scale(3)(4), 12)

    def test_class_with_multiple_variadic_methods(self):
        @flex_pos
        class Collector(object):
            def pos(self, _):
                return args

            def kw(self, __):
                return kwargs

            def both(self, prefix, _, label, __):
                return prefix, args, label, kwargs

        c = Collector()
        self.assertEqual(c.pos(1, 2, 3), (1, 2, 3))
        self.assertEqual(c.kw(a=1, b=2), {'a': 1, 'b': 2})
        self.assertEqual(
            c.both('p', 1, 2, label='L', extra='E'),
            ('p', (1, 2), 'L', {'extra': 'E'})
        )

    def test_class_and_methods_double_decorated(self):
        @flex_pos
        class OuterDoubleDecorated(object):
            @flex_pos
            def method(self, _, x):
                f = _
                return f(x)

        o = OuterDoubleDecorated()
        # ``_`` in the body is a placeholder; it receives the argument that
        # fills the placeholder position (``x`` here), not the variadic args.
        self.assertEqual(o.method(5, x=10), 10)
        self.assertEqual(OuterDoubleDecorated().method(7, x=20), 20)

    def test_nested_functions_double_decorated(self):
        @flex_pos
        def outer(x):
            f = _

            @flex_pos
            def inner(y, _):
                return y, args

            return f(x), inner(1, 2, 3)

        self.assertEqual(outer(10), (10, (1, (2, 3))))

    def test_triple_nesting(self):
        @flex_pos
        def level1(a):
            @flex_pos
            def level2(b, _):
                @flex_pos
                def level3(c, _, __):
                    return c, args, kwargs
                return b, args, level3
            return level2(a, 2, 3)

        result = level1(1)
        self.assertEqual(result[0], 1)
        self.assertEqual(result[1], (2, 3))
        self.assertEqual(result[2](4, k='v'), (4, (), {'k': 'v'}))

    def test_classmethod_staticmethod(self):
        @flex_pos
        class Mixed(object):
            @classmethod
            @flex_pos
            def from_values(cls, _):
                return args

            @staticmethod
            @flex_pos
            def compute(x, _):
                return args[0] * x

        self.assertEqual(Mixed.from_values(1, 2, 3), (1, 2, 3))
        self.assertEqual(Mixed.compute(2, 4), 8)

    def test_many_methods(self):
        @flex_pos
        class Big(object):
            pass

        # Dynamically attach many methods to stress class-body traversal.
        for i in range(20):
            def make_method(idx):
                @flex_pos
                def method(self, _):
                    return args[0] + idx
                return method
            setattr(Big, 'm{}'.format(i), make_method(i))

        b = Big()
        for i in range(20):
            self.assertEqual(getattr(b, 'm{}'.format(i))(10), 10 + i)


# ---------------------------------------------------------------------------
# Stress / high-load tests
# ---------------------------------------------------------------------------

class TestStress(unittest.TestCase):
    def test_many_placeholders(self):
        @flex_pos
        def name():
            f = _ + _ + _ + _ + _ + _ + _ + _ + _ + _
            return f(1, 2, 3, 4, 5, 6, 7, 8, 9, 10)

        self.assertEqual(name(), 55)

    def test_deeply_nested_expression(self):
        @flex_pos
        def name():
            f = (((((_ + 1) * 2 - 3) / 4 + _) ** 2) // _) % 7
            return f(5, 3, 11)

        # ((5+1)*2-3)/4 + 3 = (12-3)/4 + 3 = 2.25 + 3 = 5.25
        # 5.25 ** 2 = 27.5625
        # 27.5625 // 11 = 2
        # 2 % 7 = 2
        self.assertEqual(name(), 2)

    def test_complex_call_chain_with_many_args(self):
        def compute(a, b, c, d, e, f, g, h):
            return a * b + c * d - e * f + g * h

        @flex_pos
        def name():
            f = compute(_, _, _, _, _, _, _, _)
            return f(1, 2, 3, 4, 5, 6, 7, 8)

        self.assertEqual(name(), 1 * 2 + 3 * 4 - 5 * 6 + 7 * 8)

    def test_nested_functions_and_closures(self):
        outer = 100

        @flex_pos
        def name():
            def inner(x):
                return x + outer

            f = inner(_) * 2
            return f(5)

        self.assertEqual(name(), 210)

    def test_many_statements(self):
        @flex_pos
        def name():
            a = _ + 1
            b = _ * 2
            c = _ - 3
            d = _ / 2
            e = _ % 5
            f = _ ** 2
            return a(1) + b(2) + c(5) + d(8) + e(12) + f(3)

        self.assertEqual(name(), 2 + 4 + 2 + 4.0 + 2 + 9)

    def test_nested_classes_and_methods(self):
        @flex_pos
        class OuterNested(object):
            def __init__(self, x):
                self.x = x

            def make_inner(self):
                class Inner(object):
                    def __init__(self, value):
                        self.value = value * 2

                f = Inner(_)
                return f(self.x)

        o = OuterNested(7)
        self.assertEqual(o.make_inner().value, 14)

    def test_repeated_invocation(self):
        @flex_pos
        def name():
            return _ * 2

        results = [name()(i) for i in range(100)]
        self.assertEqual(results, [i * 2 for i in range(100)])

    def test_heterogeneous_data_structure(self):
        data = {'base': 10}

        @flex_pos
        def name():
            f = {
                'a': _ + data['base'],
                'b': [_ * 2, _ * 3],
                'c': {'nested': _ - 1},
            }
            return f(5, 4, 6, 2)

        result = name()
        self.assertEqual(result['a'], 15)
        self.assertEqual(result['b'], [8, 18])
        self.assertEqual(result['c'], {'nested': 1})

    def test_control_flow_with_placeholders(self):
        threshold = 5

        @flex_pos
        def name():
            check = _ > threshold
            transform = _ * 2
            result = []
            for x in [1, 6, 3, 8, 2]:
                if check(x):
                    result.append(transform(x))
                else:
                    result.append(x)
            return result

        self.assertEqual(name(), [1, 12, 3, 16, 2])


# ---------------------------------------------------------------------------
# High-pressure tests: every method in a class, nested decorators, inheritance
# ---------------------------------------------------------------------------

class TestHighPressure(unittest.TestCase):
    def test_every_method_kind_transformed(self):
        """All methods (instance, class, static, __init__) get flex_pos."""
        @flex_pos
        class AllMethodsTransformed(object):
            def __init__(self, base):
                self.base = base
                self.doubled = _ * 2

            def instance_add(self, value):
                return self.base + value

            @classmethod
            @flex_pos
            def class_collect(cls, _):
                return args

            @staticmethod
            @flex_pos
            def static_scale(factor, _):
                return args[0] * factor

            def pipeline(self, value):
                add_one = _ + 1
                scaled = self.static_scale(2, add_one(value))
                return scaled

        obj = AllMethodsTransformed(5)
        self.assertEqual(obj.doubled(3), 6)
        self.assertEqual(obj.base, 5)
        self.assertEqual(obj.instance_add(4), 9)
        self.assertEqual(AllMethodsTransformed.class_collect(1, 2, 3), (1, 2, 3))
        self.assertEqual(AllMethodsTransformed.static_scale(3, 7), 21)
        self.assertEqual(obj.pipeline(10), 22)

    def test_methods_call_each_other(self):
        """Methods inside a flex_pos class call other flex_pos methods."""
        @flex_pos
        class MethodGraph(object):
            def a(self, x):
                return x + 1

            def b(self, x):
                return self.a(x) * 2

            def c(self, x):
                return self.b(x) - 1

            def chain(self, x):
                inc = _ + 1
                return self.c(inc(x))

        m = MethodGraph()
        # chain(2) -> inc(2)=3 -> c(3)=b(3)-1=(a(3)*2)-1=(3+1)*2-1=7
        self.assertEqual(m.chain(2), 7)

    def test_outer_class_inner_method_double_decorated(self):
        """Outer class decorated, inner method also decorated."""
        @flex_pos
        class OuterClassDecorated(object):
            def __init__(self, factor):
                self.factor = factor

            @flex_pos
            def compute(self, offset, _):
                scale = _ * self.factor
                return scale(args[0]) + offset

        o = OuterClassDecorated(3)
        self.assertEqual(o.compute(10, 4), 22)

    def test_triple_nested_functions(self):
        """Function -> function -> function, all with flex_pos."""
        @flex_pos
        def level_one(x):
            double = _ * 2

            @flex_pos
            def level_two(y, _):
                add = _ + y

                @flex_pos
                def level_three(z, _, __):
                    return z, args, kwargs

                return add(args[0]), level_three

            return double(x), level_two

        d, l2 = level_one(5)
        self.assertEqual(d, 10)
        a3, l3 = l2(1, 2, 3)
        self.assertEqual(a3, 3)
        self.assertEqual(l3(4, k='v'), (4, (), {'k': 'v'}))

    def test_inheritance_with_flex_pos(self):
        """Base and derived classes both decorated."""
        @flex_pos
        class FlexBase(object):
            def transform(self, x):
                return _ + 1

        @flex_pos
        class FlexDerived(FlexBase):
            def transform(self, x):
                parent = super(FlexDerived, self).transform
                return parent(x)(x) * 2

        d = FlexDerived()
        self.assertEqual(d.transform(5), 12)

    def test_class_with_many_methods_all_variadic(self):
        """A class with many variadic methods, verify each is transformed."""
        @flex_pos
        class BigVariadic(object):
            pass

        for i in range(30):
            def make_method(idx):
                @flex_pos
                def method(self, _, __):
                    return idx, args, kwargs
                return method
            setattr(BigVariadic, 'm{0}'.format(i), make_method(i))

        b = BigVariadic()
        for i in range(30):
            result = getattr(b, 'm{0}'.format(i))(1, 2, k='v')
            self.assertEqual(result, (i, (1, 2), {'k': 'v'}))

    def test_class_decorated_then_manual_method_added(self):
        """Decorate a class, then attach a flex_pos-decorated method."""
        @flex_pos
        class Extendable(object):
            def base(self, x):
                return _ + x

        @flex_pos
        def extra(self, _, y):
            return args[0] * y

        Extendable.extra = extra
        e = Extendable()
        self.assertEqual(e.base(2)(3), 5)
        self.assertEqual(e.extra(4, y=3), 12)

    def test_by_user_request(self):
        """A user on Gitter asked for this, so here it is."""

        @flex_pos
        def foo(pre,_,__):
            print(pre, args, kwargs)
            f = _ * 3
            print([f(i) for i in range(5)])
            for k,v in kwargs.items():
                print(k,v,f(v))
            return list(map(f,args))
        lst = foo('hello', 1, 2, 3, k1=4, k2=5)
        print(lst)
        self.assertEqual(lst, [3, 6, 9])

if __name__ == '__main__':
    unittest.main()
