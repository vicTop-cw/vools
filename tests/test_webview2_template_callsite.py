"""`_create_webview2_runner_script` 的调用面回归锁。

为什么按源码文本隔离、不走 import：`vools.bridge.md` 是跨仓库 graft 出来的命名空间，
本机 site-packages 里躺着一个 0.7.6 孪生，import 到的可能不是本仓这份文件；而这段
缺陷恰恰只在**调用**时暴露（模块导入是好的，59/59 导入探针抓不到）。

缺陷本体：方法体是 `return f'''…'''` 的 f-string 模板，模板里 `{{x}}` 是刻意双写 ——
渲染成 `{x}` 交给生成的脚本自己插值。把它"修"成单花括号 `{e}` 就等于让宿主求值 `e`，
宿主作用域没有 `e` ⇒ 这个方法一调用就 NameError，WebView2 渲染整条路径全废；
反过来，模板**之外**的宿主代码里写 `{{e}}` 才是真正的 bug（异常消息被吞成字面量）。
"""
import ast
import os

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir,
                   "bridges", "vools", "bridge", "md", "webview2.py")
METHOD = "_create_webview2_runner_script"


class _Cfg:
    title = "T"
    width = 800
    height = 600
    resizable = True
    devtools = False


def _isolated_method():
    """把方法单独取出来编译执行，返回 (可调用对象, def 起始行, 结束行)。

    不能 textwrap.dedent：模板里有整块顶到第 0 列的生成脚本，dedent 找不到公共前缀
    就整块不动，def 行的缩进留着 ⇒ IndentationError。只削 def 行自己那一列。
    """
    with open(SRC, encoding="utf-8") as f:
        src = f.read()
    lines = src.splitlines()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == METHOD:
            first = lines[node.lineno - 1]
            assert first[:node.col_offset].strip() == "", "def 行前缀不是空白"
            # Python < 3.8 的 ast 节点没有 end_lineno：用子树最大行号估算
            end_ln = getattr(node, "end_lineno", None)
            if end_ln is None:
                end_ln = max((n.lineno for n in ast.walk(node)
                              if hasattr(n, "lineno")),
                             default=node.lineno)
            block = [first[node.col_offset:]] + lines[node.lineno:end_ln]
            ns = {"WebView2Config": _Cfg}
            exec(compile("\n".join(block), "<isolated webview2>", "exec"), ns)
            return ns[METHOD], node.lineno, end_ln
    raise AssertionError("找不到方法 %s" % METHOD)


def test_runner_script_builder_is_callable():
    """调用面：不许 NameError。这是本锁的存在理由。"""
    build, _, _ = _isolated_method()
    out = build(None, "C:/tmp/x.html", _Cfg(), "blk1")
    assert isinstance(out, str) and len(out) > 1000, "生成的脚本短得不像话"
    ast.parse(out)


def test_generated_script_interpolates_at_generated_scope():
    build, _, _ = _isolated_method()
    out = build(None, "C:/tmp/x.html", _Cfg(), "blk1")
    assert 'html_path = r"C:/tmp/x.html"' in out      # 宿主实参进得去
    assert 'title = "T"' in out                        # config 字段进得去
    assert 'f"[WebView2] 错误: {e}"' in out            # 异常消息留给生成的脚本插值
    assert "{{" not in out, "模板漏转义：生成的脚本里还有双花括号"


def test_host_code_does_not_swallow_exception_text():
    """模板区间外的宿主代码不许出现 `{{e}}` —— 那会被打成像 `{e}` 的字面量。"""
    build, at, end = _isolated_method()
    with open(SRC, encoding="utf-8") as f:
        lines = f.read().splitlines()
    outside = [(i + 1, l.strip()) for i, l in enumerate(lines)
               if "{{e}}" in l and not at <= i + 1 <= end]
    assert outside == [], "宿主代码把异常消息写成了字面量：%s" % outside
    inside = [i for i, l in enumerate(lines) if "{{e}}" in l and at <= i + 1 <= end]
    assert inside, "模板里一处双写都没有＝模板被拆成宿主求值，调用必炸"
