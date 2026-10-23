---
id: actus.basics.calculator.demo
name: Calculator Demo
version: 1.0.0
trust: sandbox
kind: demo
platform: desktop
description: Calculator 的用法演示（kind=demo 的非可执行资产）
---

# Calculator 演示

> 本文件是 `actus.basics.calculator` 的演示（`demo:` 字段指向这里）。
> 演示动作 = `kind: demo` 的非可执行资产：只展示主动作的用法与预期形态，
> 不进资产池执行（docs/03 §2.1 kind 表 + §5.4 demo 字段）。

## 运行

```bash
actus run actus.basics.calculator
```

## 预期

弹出一个 400×600 的 WebView2 窗口：渐变背景、圆角卡片、计算历史栏，
支持键盘 0-9 / + - * / / Enter Esc Backspace。

## 参数

无（GUI 动作，零入参）。

## 溯源

- 主动作：`vools/actus/actions/basics/calculator.actus.schema.md`
- kind: exec · purpose: [compute, control] · trust: sandbox · license: mit
