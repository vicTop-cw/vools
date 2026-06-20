# -*- coding: utf-8 -*-
"""
vools-recorder GUI 工具 (重构版)
- 消除 sys.path 篡改
- 消除 time.sleep 阻塞调用，使用 root.after 实现倒计时和状态更新
- 修复暂停/继续逻辑
- 改善布局与状态管理
"""
from __future__ import annotations

import os
import time
from typing import Optional, Any
from enum import Enum, auto

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .recorder import Recorder
from .player import Player
from .parser import Parser
from .actions import Recording
from .typedefs import ActionType
__all__ = ['RecorderGUI', 'main']


class _GUIState(Enum):
    """GUI 状态枚举"""
    IDLE = auto()
    RECORDING = auto()
    PAUSED = auto()
    HAS_DATA = auto()
    PLAYING = auto()
    COUNTDOWN = auto()


class RecorderGUI:
    """录制器 GUI 窗口 — 重构版"""

    INITIAL_GEOMETRY = "420x220"

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Vools 录制工具")
        self.root.geometry(self.INITIAL_GEOMETRY)
        self.root.resizable(False, False)

        # 录制组件
        self.recorder = Recorder()
        self.player: Optional[Player] = None
        self.recording: Optional[Recording] = None
        self.parser = Parser()

        # 状态管理
        self._state: _GUIState = _GUIState.IDLE

        # 倒计时相关
        self._countdown_remaining = 0

        # 暂停/继续录制暂存
        self._part_actions: list = []
        self._part_start_time = None

        self._create_ui()
        self._setup_bindings()

    # ──────────────────────────── UI 构建 ────────────────────────────

    def _create_ui(self) -> None:
        root = self.root
        _pad = 6

        # ── 第 0 行: 状态标签 ──
        self.status_label = ttk.Label(root, text="状态: 空闲",
                                      font=("微软雅黑", 9))
        self.status_label.grid(row=0, column=0, columnspan=4,
                               padx=_pad, pady=(_pad + 2, 0), sticky="w")

        # ── 第 1 行: 时间 / 动作计数 ──
        self.time_label = ttk.Label(root, text="时长: 0.0s  |  动作: 0",
                                    font=("微软雅黑", 8))
        self.time_label.grid(row=1, column=0, columnspan=4,
                             padx=_pad, pady=2, sticky="w")

        # ── 第 2 行: 分隔线 ──
        ttk.Separator(root, orient="horizontal") \
            .grid(row=2, column=0, columnspan=4, sticky="ew", padx=_pad, pady=4)

        # ── 第 3 行: 录制控制按钮 ──
        self.btn_start = ttk.Button(root, text="▶ 开始录制",
                                    command=self._on_start)
        self.btn_pause  = ttk.Button(root, text="⏸ 暂停",
                                    command=self._on_pause)
        self.btn_stop   = ttk.Button(root, text="■ 结束",
                                    command=self._on_stop)

        self.btn_start.grid(row=3, column=0, padx=_pad, pady=2, sticky="ew")
        self.btn_pause.grid(row=3, column=1, padx=_pad, pady=2, sticky="ew")
        self.btn_stop.grid(row=3, column=2, padx=_pad, pady=2, sticky="ew")

        # ── 第 4 行: 操作按钮 ──
        self.btn_save   = ttk.Button(root, text="💾 保存",
                                    command=self._on_save)
        self.btn_play   = ttk.Button(root, text="▶ 回放",
                                    command=self._on_play)
        self.btn_cancel = ttk.Button(root, text="✕ 关闭",
                                    command=self._on_cancel)

        self.btn_save.grid(row=4, column=0, padx=_pad, pady=2, sticky="ew")
        self.btn_play.grid(row=4, column=1, padx=_pad, pady=2, sticky="ew")
        self.btn_cancel.grid(row=4, column=2, padx=_pad, pady=2, sticky="ew")

        # 第 3/4 列占位对齐
        root.columnconfigure(0, weight=1, minsize=90)
        root.columnconfigure(1, weight=1, minsize=90)
        root.columnconfigure(2, weight=1, minsize=90)
        root.columnconfigure(3, weight=0)

        # ── 第 5 行: 提示 + 进度条 ──
        self.progress_bar = ttk.Progressbar(root, mode="indeterminate",
                                            length=360)
        self.progress_bar.grid(row=5, column=0, columnspan=3,
                               padx=_pad, pady=(4, 0), sticky="ew")

        self.tip_label = ttk.Label(root,
                                   text="提示: 回放中按 Esc 中断",
                                   font=("Arial", 7))
        self.tip_label.grid(row=5, column=3, padx=_pad, pady=(4, 0))

        self._update_button_states()

    def _setup_bindings(self) -> None:
        self.root.bind("<Escape>", self._on_escape)

    # ──────────────────────────── 状态与按钮 ────────────────────────────

    def _update_button_states(self) -> None:
        """根据 _state 更新所有按钮的启用/禁用状态"""
        s = self._state

        # 全部禁用
        for btn in (self.btn_start, self.btn_pause, self.btn_stop,
                    self.btn_save, self.btn_play, self.btn_cancel):
            btn.state(["disabled"])

        if s == _GUIState.IDLE:
            self.btn_start.state(["!disabled"])
            self.btn_play.state(["!disabled"])
            self.btn_cancel.state(["!disabled"])
            self.btn_pause.configure(text="⏸ 暂停")
            self._set_status("空闲")

        elif s == _GUIState.COUNTDOWN:
            self.btn_start.state(["!disabled"])

        elif s == _GUIState.RECORDING:
            self.btn_pause.state(["!disabled"])
            self.btn_stop.state(["!disabled"])
            self.btn_cancel.state(["!disabled"])
            self.btn_pause.configure(text="⏸ 暂停")

        elif s == _GUIState.PAUSED:
            self.btn_pause.state(["!disabled"])
            self.btn_stop.state(["!disabled"])
            self.btn_cancel.state(["!disabled"])
            self.btn_pause.configure(text="▶ 继续")

        elif s == _GUIState.HAS_DATA:
            self.btn_start.state(["!disabled"])
            self.btn_save.state(["!disabled"])
            self.btn_play.state(["!disabled"])
            self.btn_cancel.state(["!disabled"])
            self.btn_pause.configure(text="⏸ 暂停")

        elif s == _GUIState.PLAYING:
            self.btn_cancel.state(["!disabled"])

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=f"状态: {text}")

    def _set_time_label(self, duration_ms: float, count: int = 0) -> None:
        text = f"时长: {duration_ms / 1000:.1f}s"
        if count:
            text += f"  |  动作: {count}"
        self.time_label.configure(text=text)

    # ──────────────────────────── 录制流程 ────────────────────────────

    def _on_start(self) -> None:
        """开始录制（先倒计时）"""
        if self._state != _GUIState.IDLE:
            return
        self._state = _GUIState.COUNTDOWN
        self._update_button_states()
        self._countdown_remaining = 3
        self._do_countdown()

    def _do_countdown(self) -> None:
        """倒计时（非阻塞，通过 root.after）"""
        remaining = self._countdown_remaining
        if remaining > 0:
            self._set_status(f"⏳ {remaining}")
            self._countdown_remaining -= 1
            self.root.after(1000, self._do_countdown)
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        try:
            self.recorder = Recorder()
            self.recorder.start()
            self._state = _GUIState.RECORDING
            self._set_status("录制中...")
            self._update_button_states()
            self._schedule_status_update()
        except Exception as e:
            messagebox.showerror("错误", f"无法开始录制: {e}")
            self._state = _GUIState.IDLE
            self._update_button_states()

    def _schedule_status_update(self) -> None:
        """定时更新录制时长/动作数（100ms 间隔）"""
        if self._state not in (_GUIState.RECORDING, _GUIState.PAUSED):
            self.progress_bar.stop()
            return
        try:
            if self._state == _GUIState.RECORDING and self.recorder.is_recording:
                dur = self.recorder._relative_time()
                cnt = len(self.recorder._actions)
                self._set_time_label(dur, cnt)
                self._set_status(f"录制中 ({cnt} 动作)")
                self.progress_bar.start(50)
            elif self._state == _GUIState.PAUSED:
                self.progress_bar.stop()
        except Exception:
            pass
        self.root.after(100, self._schedule_status_update)

    def _on_stop(self) -> None:
        """结束录制 — 合并暂停片段（如有）与当前录制数据"""
        if self._state not in (_GUIState.RECORDING, _GUIState.PAUSED):
            return

        try:
            # 停止当前录制器
            current_recording = self.recorder.stop()

            # 合并暂停前保存的动作片段（如果有）
            if self._part_actions:
                all_actions = self._part_actions + current_recording.actions
                start_time = self._part_start_time or current_recording.start_time
                self.recording = Recording(
                    start_time=start_time,
                    end_time=current_recording.end_time,
                    actions=all_actions,
                    tags=current_recording.tags,
                )
            else:
                self.recording = current_recording

            self._part_actions = []
            self._state = _GUIState.HAS_DATA
            self._set_time_label(self.recording.duration, len(self.recording))
            self._set_status(f"已录制 ({len(self.recording)} 动作)")
            self._update_button_states()
            self.progress_bar.stop()
        except Exception as e:
            messagebox.showerror("错误", f"结束录制失败: {e}")

    def _on_pause(self) -> None:
        """暂停 / 继续录制"""
        if self._state == _GUIState.RECORDING:
            # 暂停：保存已录制的动作片段
            self._part_actions = self.recorder.stop().actions
            self._part_start_time = self.recorder._start_time
            self._state = _GUIState.PAUSED
            self._set_status("已暂停")

        elif self._state == _GUIState.PAUSED:
            # 继续：新建 Recorder 并在完成后合并动作
            self.recorder = Recorder()
            self.recorder.start()
            self._state = _GUIState.RECORDING
            self._set_status("继续录制...")

        else:
            return
        self._update_button_states()

    # ──────────────────────────── 保存 & 回放 ────────────────────────────

    def _on_save(self) -> None:
        """保存录制到文件"""
        if self._state != _GUIState.HAS_DATA or not self.recording:
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".yaml",
            filetypes=[("YAML 文件", "*.yaml"), ("JSON 文件", "*.json")],
            initialfile=f"recording_{time.strftime('%Y%m%d_%H%M%S')}.yaml"
        )
        if not file_path:
            return

        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".yaml":
                self.recording.to_yaml_file(file_path)
            else:
                self.recording.to_json_file(file_path)
            messagebox.showinfo("成功", f"录制已保存至:\n{file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def _on_play(self) -> None:
        """回放录制"""
        if self._state not in (_GUIState.IDLE, _GUIState.HAS_DATA):
            return
        if not self.recording or len(self.recording) == 0:
            messagebox.showwarning("警告", "没有可回放的数据")
            return

        # 倒计时 0.5s（非阻塞）
        self._set_status("准备回放...")
        self.root.after(500, self._do_play)

    def _do_play(self) -> None:
        try:
            self.player = Player()
            self.player.set_callbacks(
                on_complete=lambda: self.root.after(0, self._on_play_complete),
                on_error=lambda e: self.root.after(0, lambda: messagebox.showerror("错误", str(e)))
            )
            self.player.play(self.recording)
            self._state = _GUIState.PLAYING
            self._set_status("回放中...")
            self._update_button_states()
            self.progress_bar.start(80)
        except Exception as e:
            messagebox.showerror("错误", f"无法开始回放: {e}")

    def _on_play_complete(self) -> None:
        """回放完成回调"""
        self.progress_bar.stop()
        self._state = _GUIState.HAS_DATA
        self._set_status("回放完成")
        self._update_button_states()

    # ──────────────────────────── 取消 & Esc ────────────────────────────

    def _on_cancel(self) -> None:
        """关闭窗口 — 停止录制/回放后退出"""
        if self._state == _GUIState.RECORDING:
            self.recorder.stop()
        elif self._state == _GUIState.PLAYING and self.player:
            self.player.stop()
        elif self._state == _GUIState.COUNTDOWN:
            self._countdown_remaining = 0

        self.root.destroy()

    def _on_escape(self, event: Any) -> None:
        """Esc 快捷键中断回放"""
        if self._state == _GUIState.PLAYING and self.player:
            self.player.stop()
            self._on_play_complete()

    # ──────────────────────────── 启动入口 ────────────────────────────

    def run(self) -> None:
        """运行 GUI 主循环"""
        self.root.mainloop()


def main() -> None:
    try:
        gui = RecorderGUI()
        gui.run()
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()