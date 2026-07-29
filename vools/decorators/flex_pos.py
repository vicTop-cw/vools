"""
Flexible placeholder decorator using AST rewriting.

This module is **self-contained**: it only uses the Python standard library and
can be copied directly into any Python 3.6+ project. It does not depend on the
``vools`` package or any third-party package.

``flex_pos`` decorates a function or class so that occurrences of the
placeholder ``_`` inside expressions are rewritten into lambdas at compile
time. Outside decorated scopes ``_`` is just a singleton object.

Examples
--------
Copy ``flex_pos.py`` to your project and import it directly::

    from flex_pos import flex_pos, _

    @flex_pos
    def name():
        f = _                     # lambda x: x
        g = _[key]                # lambda x: x[key]
        h = _[_]                  # lambda x1, x2: x1[x2]
        i = _(_, 2, 3)           # lambda x1, x2: x1(x2, 2, 3)
        j = _.attr[_](2, 3, 4, _)[0]()  # lambda x1, x2, x3: x1.attr[x2](2, 3, 4, x3)[0]()
        return i

Classes are supported as well::

    @flex_pos
    class Builder(object):
        def build(self, value):
            transform = _ + 1
            return transform(value)

The placeholder is bound per decorated scope::

    def outside():
        s = str(_)   # normal string, not a lambda

Nested decorators are supported: an outer ``@flex_pos`` can wrap a function or
class whose inner function/method is also decorated with ``@flex_pos``.  The
implementation registers every generated source with ``linecache`` under a
unique filename so that the inner decorator can still retrieve source code via
``inspect.getsource``.  For classes defined in local scopes (e.g. inside a test
method), the caller frame's locals are merged into the execution environment so
that locally-defined base classes and other names remain visible.

Caveat: because ``inspect.getsource`` locates definitions by name, defining
multiple classes with the same name in the same module can make the decorator
retrieve the wrong source.  Use unique class names when several decorated
classes appear in one module.
"""

from __future__ import absolute_import

import ast
import functools
import inspect
import itertools
import linecache
import sys
import textwrap
import types

__all__ = ['flex_pos', '_', 'is_placeholder', '_Placeholder']


# Strictly increasing counter for linecache keys used by exec'd sources.
_FLEX_POS_SOURCE_COUNTER = itertools.count()


class _Placeholder(object):
    """Singleton placeholder object used outside decorated scopes."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(_Placeholder, cls).__new__(cls)
        return cls._instance

    def __repr__(self):
        return '_'

    def __reduce__(self):
        # Ensure pickling returns the same singleton.
        return (_get_placeholder, ())


def _get_placeholder():
    return _


_ = _Placeholder()


def is_placeholder(value):
    """Return True if *value* is the placeholder ``_``."""
    return value is _


def _contains_placeholder(node):
    """
    Return True if *node* loads the name ``_`` outside of nested lambdas.

    Lambda expressions define their own scope, so placeholders inside an
    explicit lambda are not rewritten.
    """
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.Lambda):
            continue
        if isinstance(current, ast.Name) and current.id == '_':
            return True
        stack.extend(ast.iter_child_nodes(current))
    return False


def _replace_placeholders(node, placeholders):
    """
    Return a copy of *node* where each ``_`` Name is replaced by ``_pN``.

    Lambda sub-trees are left untouched because they define their own scope.
    *placeholders* is a list that receives one entry per replacement so that
    the caller knows how many lambda parameters to create.
    """
    if isinstance(node, ast.Lambda):
        return node

    if isinstance(node, ast.Name) and node.id == '_':
        param_name = '_p{0}'.format(len(placeholders))
        placeholders.append(node)
        return ast.copy_location(
            ast.Name(id=param_name, ctx=ast.Load()),
            node
        )

    new_fields = {}
    changed = False
    for field, value in ast.iter_fields(node):
        if isinstance(value, list):
            new_list = []
            for item in value:
                if isinstance(item, ast.AST):
                    new_item = _replace_placeholders(item, placeholders)
                    if new_item is not item:
                        changed = True
                    new_list.append(new_item)
                else:
                    new_list.append(item)
            new_fields[field] = new_list
        elif isinstance(value, ast.AST):
            new_value = _replace_placeholders(value, placeholders)
            if new_value is not value:
                changed = True
            new_fields[field] = new_value
        else:
            new_fields[field] = value

    if changed:
        new_node = type(node)(**new_fields)
        return ast.copy_location(new_node, node)
    return node


def _make_lambda_node(body_expr, num_placeholders):
    """
    Build ``lambda _p0, _p1, ...: body_expr`` using a source template so that
    the resulting AST contains every field required by the running Python
    version (e.g. ``posonlyargs`` on 3.8+).
    """
    arg_names = ['_p{0}'.format(i) for i in range(num_placeholders)]
    if arg_names:
        source = 'lambda {0}: 0'.format(', '.join(arg_names))
    else:
        source = 'lambda: 0'
    template = ast.parse(source, mode='eval').body
    template.body = body_expr
    return template


def _convert_if_needed(expr):
    """
    If *expr* contains ``_``, return a ``lambda _p0, ...: expr`` node.

    Otherwise return *expr* unchanged.
    """
    if expr is None or not _contains_placeholder(expr):
        return expr

    placeholders = []
    new_expr = _replace_placeholders(expr, placeholders)
    lambda_node = _make_lambda_node(new_expr, len(placeholders))
    return ast.copy_location(lambda_node, expr)


def _arg_names(args_node):
    """Return a set of argument names defined by an ast.arguments node."""
    names = set()
    for arg in args_node.args:
        names.add(arg.arg)
    if args_node.vararg is not None:
        names.add(args_node.vararg.arg)
    for arg in args_node.kwonlyargs:
        names.add(arg.arg)
    if args_node.kwarg is not None:
        names.add(args_node.kwarg.arg)
    return names


def _transform_signature(args_node):
    """
    Transform a function signature that uses ``_`` and ``__`` as variadic
    markers.

    ``_`` becomes ``*args``; ``__`` becomes ``**kwargs``. The function body can
    then use ``args`` and ``kwargs`` directly. The original marker names ``_``
    and ``__`` disappear from the signature, so they remain available as
    expression placeholders inside the body.

    Returns the new ``ast.arguments`` node.
    """
    if args_node.vararg is not None:
        raise SyntaxError(
            "flex_pos: '_' cannot be used together with explicit *args"
        )
    if args_node.kwarg is not None:
        raise SyntaxError(
            "flex_pos: '__' cannot be used together with explicit **kwargs"
        )

    args = list(args_node.args)
    kwonly = list(args_node.kwonlyargs)

    underscore_pos = None
    double_pos = None
    double_in_kwonly = False

    for i, arg in enumerate(args):
        if arg.arg == '_':
            if underscore_pos is not None:
                raise SyntaxError("flex_pos: '_' can appear at most once")
            underscore_pos = i
        elif arg.arg == '__':
            if double_pos is not None:
                raise SyntaxError("flex_pos: '__' can appear at most once")
            double_pos = i

    for i, arg in enumerate(kwonly):
        if arg.arg == '_':
            raise SyntaxError(
                "flex_pos: '_' must appear in the positional parameter list "
                "and before '__'"
            )
        if arg.arg == '__':
            if double_pos is not None:
                raise SyntaxError("flex_pos: '__' can appear at most once")
            double_pos = i
            double_in_kwonly = True

    if underscore_pos is not None and double_pos is not None and not double_in_kwonly:
        if double_pos < underscore_pos:
            raise SyntaxError("flex_pos: '__' cannot appear before '_'")

    new_args = []
    new_kwonly = []
    new_vararg = None
    new_kwarg = None

    if underscore_pos is not None:
        # ``_`` becomes ``*args``.
        new_args = args[:underscore_pos]
        new_vararg = ast.arg(arg='args', annotation=None)

        if double_pos is not None and not double_in_kwonly:
            # ``__`` is in args after ``_`` -> ``**kwargs``.
            new_kwonly = args[underscore_pos + 1:double_pos]
            new_kwarg = ast.arg(arg='kwargs', annotation=None)
        else:
            new_kwonly = args[underscore_pos + 1:]
    elif double_pos is not None and not double_in_kwonly:
        # Only ``__`` in positional args -> ``**kwargs``; preceding args stay
        # normal positional parameters.
        new_args = args[:double_pos]
        new_kwarg = ast.arg(arg='kwargs', annotation=None)
    else:
        new_args = args

    if double_in_kwonly:
        # ``__`` is in kwonly args -> ``**kwargs``.
        new_kwarg = ast.arg(arg='kwargs', annotation=None)
        new_kwonly.extend([arg for arg in kwonly if arg.arg != '__'])
    else:
        new_kwonly.extend(kwonly)

    # Rebuild defaults. Original defaults correspond to the tail of ``args``.
    n_args = len(args)
    n_defaults = len(args_node.defaults)
    default_start = n_args - n_defaults if n_defaults <= n_args else 0

    new_defaults = []
    for i, _arg in enumerate(new_args):
        if i >= default_start:
            new_defaults.append(args_node.defaults[i - default_start])

    # kw_defaults follow kwonly order. Moved-from-args parameters have no
    # default because that would have been a Python syntax error.
    new_kw_defaults = []
    for arg in new_kwonly:
        found = False
        for i, orig_arg in enumerate(kwonly):
            if orig_arg is arg and i < len(args_node.kw_defaults):
                new_kw_defaults.append(args_node.kw_defaults[i])
                found = True
                break
        if not found:
            new_kw_defaults.append(None)

    arguments_kwargs = {
        'args': new_args,
        'vararg': new_vararg,
        'kwonlyargs': new_kwonly,
        'kw_defaults': new_kw_defaults,
        'kwarg': new_kwarg,
        'defaults': new_defaults
    }
    # Python 3.8+ adds mandatory positional-only arguments.
    if sys.version_info >= (3, 8):
        arguments_kwargs['posonlyargs'] = []

    new_arguments = ast.arguments(**arguments_kwargs)
    return new_arguments


class PlaceholderTransformer(ast.NodeTransformer):
    """
    Rewrite expressions containing ``_`` into lambdas inside a function/class.

    Lambdas themselves are not entered, so ``lambda: _ + 1`` keeps its
    original meaning. Functions that declare ``_`` as a parameter name are
    left untouched because that ``_`` is a normal local variable, not the
    placeholder.
    """

    def visit_Lambda(self, node):
        # Do not transform placeholders inside explicit lambda expressions.
        return node

    def visit_FunctionDef(self, node):
        arg_names = _arg_names(node.args)
        # ``_`` / ``__`` in the signature are variadic markers. They are
        # rewritten into ``*args`` / ``**kwargs`` and then disappear from the
        # signature, leaving the body free to use ``_`` as an expression
        # placeholder.
        if '_' in arg_names or '__' in arg_names:
            node.args = _transform_signature(node.args)
        # Recursively transform the body of every function definition.
        node.body = [self.visit(stmt) for stmt in node.body]
        return node

    def visit_AsyncFunctionDef(self, node):
        arg_names = _arg_names(node.args)
        if '_' in arg_names or '__' in arg_names:
            node.args = _transform_signature(node.args)
        node.body = [self.visit(stmt) for stmt in node.body]
        return node

    def visit_ClassDef(self, node):
        # Transform every method in the class body.
        node.body = [self.visit(stmt) for stmt in node.body]
        return node

    def visit_Assign(self, node):
        node.value = _convert_if_needed(node.value)
        return node

    def visit_AnnAssign(self, node):
        if node.value is not None:
            node.value = _convert_if_needed(node.value)
        return node

    def visit_AugAssign(self, node):
        node.value = _convert_if_needed(node.value)
        return node

    def visit_Expr(self, node):
        node.value = _convert_if_needed(node.value)
        return node

    def visit_Return(self, node):
        if node.value is not None:
            node.value = _convert_if_needed(node.value)
        return node

    # Control flow with test/iter expressions
    def visit_If(self, node):
        node.test = _convert_if_needed(node.test)
        node.body = [self.visit(stmt) for stmt in node.body]
        node.orelse = [self.visit(stmt) for stmt in node.orelse]
        return node

    def visit_While(self, node):
        node.test = _convert_if_needed(node.test)
        node.body = [self.visit(stmt) for stmt in node.body]
        node.orelse = [self.visit(stmt) for stmt in node.orelse]
        return node

    def visit_For(self, node):
        node.iter = _convert_if_needed(node.iter)
        node.body = [self.visit(stmt) for stmt in node.body]
        node.orelse = [self.visit(stmt) for stmt in node.orelse]
        return node

    def visit_Comprehension(self, node):
        # Do not rewrite ``_`` inside comprehensions automatically.
        return node


def _globals_of(target, caller_frame=None):
    """Return the globals dict of *target* (function) or its module (class).

    For classes defined in a local scope (e.g. inside a test method) the
    module globals may not contain names the class body depends on (such as a
    base class defined in the same local scope).  When *caller_frame* is
    provided, its ``f_locals`` are merged on top of the module globals so that
    those local names are visible during exec.
    """
    if hasattr(target, '__globals__'):
        return target.__globals__

    env = {}
    module = sys.modules.get(target.__module__)
    if module is not None:
        env.update(vars(module))

    if caller_frame is not None:
        # Merge the caller's locals so that classes/functions defined in the
        # same local scope (e.g. a unittest method) can see each other.
        env.update(caller_frame.f_locals)

    return env


def flex_pos(target):
    """
    Decorate a function or class so that ``_`` becomes an expression placeholder.

    Inside the decorated body, any expression that loads ``_`` is rewritten
    into a lambda whose parameters replace the ``_`` occurrences in left-to-right
    source order.

    Parameters
    ----------
    target : callable or type
        Function or class to decorate.

    Returns
    -------
    callable or type
        The rewritten function or class.
    """
    caller_frame = sys._getframe(1)
    is_class = isinstance(target, type)
    source = inspect.getsource(target)
    if source is None:
        raise TypeError(
            'flex_pos: could not retrieve source for {0!r}'.format(target)
        )

    tree = ast.parse(textwrap.dedent(source))
    top = tree.body[0]

    transformer = PlaceholderTransformer()
    if is_class:
        if not isinstance(top, ast.ClassDef):
            raise TypeError('flex_pos: expected a class definition')
        # Prevent the decorator from being re-applied when the new class is
        # executed.
        top.decorator_list = []
        transformer.visit_ClassDef(top)
    else:
        if not isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise TypeError('flex_pos: expected a function definition')
        # Prevent the decorator from being re-applied when the new function is
        # executed.
        top.decorator_list = []
        transformer.visit_FunctionDef(top)

    ast.fix_missing_locations(tree)

    # Register the source with linecache so that nested flex_pos decorators
    # can still retrieve source for functions/classes created by exec. Use a
    # strictly increasing counter as the cache key to avoid id() reuse after
    # garbage collection.
    source_id = next(_FLEX_POS_SOURCE_COUNTER)
    flex_filename = '<flex_pos:{0}>'.format(source_id)
    linecache.cache[flex_filename] = (
        len(source),
        None,
        source.splitlines(True),
        flex_filename
    )
    code = compile(tree, filename=flex_filename, mode='exec')

    env = dict(_globals_of(target, caller_frame))
    # Make sure the placeholder singleton is available in the new scope.
    env.setdefault('_', _)
    # Expose the original closure cells as globals so that internal lambdas
    # can still resolve free variables after AST rewriting.
    closure = getattr(target, '__closure__', None)
    if closure:
        for cell_name, cell in zip(target.__code__.co_freevars, closure):
            env[cell_name] = cell.cell_contents
    exec(code, env)
    new_target = env[target.__name__]

    if is_class:
        return new_target

    return functools.wraps(target)(new_target)
