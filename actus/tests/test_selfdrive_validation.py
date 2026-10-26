# -*- coding: utf-8 -*-
"""Decomposer / SelfDrive 的入参校验（扫 selfdrive.py 发现）。

缺陷：
  1. `Decomposer(template='abc')` → `list()` **逐字符展开**成 ['a','b','c']
     （与 BUG-490/492 的 `args='abc'` 同族）
  2. `Decomposer(max_depth='x')` → 在 `max()` 处抛裸 TypeError
  3. `children_of(None, 0)` → 把 `None` 当目标文本，生成
     「澄清「None」的验收标准与输入输出」这类**垃圾任务标题**
  4. `SelfDrive(goal=None/'')` 同样静默接受

注：`project_io.py` 的 `export_project` 等失败返回 `None` 是**文档化契约**
（CLI 按此处理），且 `validate_project` 已返回结构化错误，故不算缺陷、未改动。
"""
import pytest

from vools.actus.selfdrive import Decomposer, SelfDrive


# --------------------------------------------------------------------------
# Decomposer 构造
# --------------------------------------------------------------------------
def test_template_string_rejected():
    """字符串会被逐字符展开，必须拒绝。"""
    with pytest.raises(TypeError) as exc:
        Decomposer(template="abc")
    assert "逐字符" in str(exc.value), exc.value


@pytest.mark.parametrize("bad", [123, {"a": "b"}, [1, 2]])
def test_template_bad_types_rejected(bad):
    with pytest.raises(TypeError):
        Decomposer(template=bad)


def test_max_depth_type_checked():
    with pytest.raises(TypeError) as exc:
        Decomposer(max_depth="x")
    assert "必须是整数" in str(exc.value), exc.value


def test_max_depth_negative_rejected():
    with pytest.raises(ValueError):
        Decomposer(max_depth=-1)


def test_valid_construction():
    d = Decomposer(max_depth=3, template=["a {goal}", "b {goal}"])
    assert d.max_depth == 3 and d.template == ["a {goal}", "b {goal}"]


# --------------------------------------------------------------------------
# goal 校验（垃圾任务标题）
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [None, 123, [], "  ", ""])
def test_children_of_rejects_bad_goal(bad):
    d = Decomposer()
    with pytest.raises((TypeError, ValueError)):
        d.children_of(bad, 0)


@pytest.mark.parametrize("bad", [None, 123, "", "  "])
def test_template_children_rejects_bad_goal(bad):
    d = Decomposer()
    with pytest.raises((TypeError, ValueError)):
        d.template_children(bad, 0)


def test_children_of_uses_goal_text():
    d = Decomposer(max_depth=2)
    kids = d.children_of("做一个计算器", 0)
    assert kids, "应有子目标"
    assert all("做一个计算器" in k for k in kids)
    assert not any("None" in k for k in kids)


def test_max_depth_stops_decomposition():
    d = Decomposer(max_depth=1)
    assert d.children_of("g", 0)            # depth 0 < 1
    assert d.children_of("g", 1) == []      # depth 1 >= 1


# --------------------------------------------------------------------------
# SelfDrive 构造
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [None, 123, "", "   "])
def test_selfdrive_rejects_bad_goal(bad):
    with pytest.raises((TypeError, ValueError)):
        SelfDrive(goal=bad)


@pytest.mark.parametrize("bad", [0, -1, "x", True])
def test_selfdrive_rejects_bad_max_rounds(bad):
    with pytest.raises(ValueError):
        SelfDrive(goal="g", max_rounds=bad)


def test_selfdrive_valid(tmp_path):
    sd = SelfDrive(goal="写一个计算器", max_depth=2, meta_dir=str(tmp_path))
    assert sd.goal == "写一个计算器"
    assert sd.max_rounds >= 1
    assert sd.decomposer.max_depth == 2
