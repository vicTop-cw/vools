---
id: actus.basics.todo_list.demo
name: Todo List Demo
version: 1.0.0
trust: sandbox
kind: demo
platform: desktop
description: Todo List 的用法演示（kind=demo 的非可执行资产）
---

# Todo List 演示

> 本文件是 `actus.basics.todo_list` 的演示（`demo:` 字段指向这里）。
> 演示动作 = `kind: demo` 的非可执行资产：只展示主动作的用法与预期形态，
> 不进资产池执行（docs/03 §2.1 kind 表 + §5.4 demo 字段）。

## 运行

```bash
actus run actus.basics.todo_list
```

## 预期

弹出一个 500×700 的 WebView2 窗口：待办事项增删改查、完成状态勾选、
本地状态持久化（declared_features: state-persist）。

## 参数

无（GUI 动作，零入参）。

## 溯源

- 主动作：`vools/actus/actions/basics/todo-list.actus.schema.md`
- kind: exec · purpose: [control, data-store] · trust: sandbox · license: mit
