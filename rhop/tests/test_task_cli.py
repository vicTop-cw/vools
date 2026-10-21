"""CLI 测试：subcommand 行为与退出码（直接调 main()，不走子进程）。"""

import json
import os
import sys

import pytest

from vools.rhop.task.cli import main
from vools.rhop.task.models import TaskState

PY = sys.executable.replace("\\", "/")


def _write_config(path, role, share, **overrides):
    data = {"name": "unit", "role": role, "key": "unit-key",
            "shared": {"write": str(share)},
            "queue": {"store": {"kind": "sqlite-shared"},
                      "heartbeat": {"file": "unit.heartbeat", "interval_sec": 5,
                                    "stale_after_sec": 15}},
            "exec": {"allow": ["action:*", "handler:*", "cli:python"]}}
    data.update(overrides)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    return path


@pytest.fixture
def env(tmp_path):
    share = tmp_path / "share"
    share.mkdir()
    cfg_a = _write_config(str(tmp_path / "A.json"), "A", share)
    cfg_b = _write_config(str(tmp_path / "B.json"), "B", share)
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps([
        {"task_name": "cli-1", "cli": {"cmd": '"%s" -c "print(\'one\')"' % PY}},
        {"task_name": "cli-2", "deps": ["cli-1"], "cli": {"cmd": '"%s" -c "print(\'two\')"' % PY}},
    ], ensure_ascii=False), encoding="utf-8")
    return {"dir": tmp_path, "share": share, "A": cfg_a, "B": cfg_b, "tasks": str(tasks)}


class TestConfigCommand:
    def test_config_prints_masked_and_exits_zero(self, env, capsys):
        code = main(["--config", env["A"], "--no-warn-plaintext", "config"])
        out = capsys.readouterr().out
        assert code == 0
        parsed = json.loads(out)
        assert parsed["describe"]["role"] == "A"
        assert parsed["resolved_masked"]["key"] == "***"
        assert "unit-key" not in out

    def test_config_check_store(self, env, capsys):
        code = main(["--config", env["A"], "--no-warn-plaintext", "config", "--check-store"])
        captured = capsys.readouterr()
        assert code == 0
        assert "存储校验通过" in captured.err          # 诊断走 stderr
        parsed = json.loads(captured.out)             # stdout 保持纯 JSON
        assert "path" in parsed["store"]

    def test_config_stdout_is_pure_json_with_notes_on_stderr(self, tmp_path, capsys):
        plain = tmp_path / "plain.json"
        plain.write_text(json.dumps({"name": "n", "role": "A", "key": "plain-master",
                                     "queue": {"store": {"kind": "sqlite-local"}}}),
                         encoding="utf-8")
        code = main(["--config", str(plain), "config"])
        captured = capsys.readouterr()
        assert code == 0
        assert json.loads(captured.out)["describe"]["has_key"] is True
        assert "明文" in captured.err

    def test_missing_config_file(self, tmp_path, capsys):
        code = main(["--config", str(tmp_path / "nope.json"), "config"])
        assert code == 2
        assert "配置文件不存在" in capsys.readouterr().err

    def test_invalid_role(self, tmp_path, capsys):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"name": "n", "role": "P3", "key": "k"}), encoding="utf-8")
        code = main(["--config", str(bad), "--no-warn-plaintext", "status"])
        assert code == 2
        assert "配置错误" in capsys.readouterr().err

    def test_strict_secrets_blocks_plaintext(self, tmp_path, capsys):
        bad = tmp_path / "plain.json"
        bad.write_text(json.dumps({"name": "n", "role": "A", "key": "plain-master",
                                   "queue": {"store": {"kind": "sqlite-local"}}}),
                       encoding="utf-8")
        code = main(["--config", str(bad), "--strict-secrets", "status"])
        assert code == 2
        assert "明文" in capsys.readouterr().err

    def test_no_subcommand_prints_help(self, env, capsys):
        assert main(["--config", env["A"]]) == 2

    def test_global_options_accepted_after_subcommand(self, env, capsys):
        """`--config/--json` 放在子命令之后也要生效（两级 parents + SUPPRESS 归一）。"""
        main(["--config", env["A"], "--no-warn-plaintext", "submit", "--file", env["tasks"]])
        capsys.readouterr()
        code = main(["status", "--config", env["A"], "--json", "--no-warn-plaintext"])
        out = capsys.readouterr().out
        assert code == 0
        rows = json.loads(out)
        assert len(rows) == 2
        assert rows[0]["state"] == TaskState.PENDING

    def test_missing_config_is_reported(self, capsys):
        assert main(["status"]) == 2
        assert "缺少 --config" in capsys.readouterr().err


class TestSubmitAndRun:
    def test_submit_from_file(self, env, capsys):
        code = main(["--config", env["A"], "--no-warn-plaintext", "submit",
                     "--file", env["tasks"]])
        out = capsys.readouterr().out
        assert code == 0
        assert "已提交 2 条" in out

    def test_submit_single_task_flags(self, env, capsys):
        code = main(["--config", env["A"], "--no-warn-plaintext", "submit",
                     "--task", "one", "--cmd", '"%s" -c "print(1)"' % PY, "--priority", "7"])
        assert code == 0
        assert "已提交 1 条" in capsys.readouterr().out

    def test_submit_requires_tasks(self, env, capsys):
        code = main(["--config", env["A"], "--no-warn-plaintext", "submit"])
        assert code == 2
        assert "需要 --file 或 --task" in capsys.readouterr().err

    def test_once_executes_one_task(self, env, capsys):
        main(["--config", env["A"], "--no-warn-plaintext", "submit", "--file", env["tasks"]])
        capsys.readouterr()
        code = main(["--config", env["B"], "--no-warn-plaintext", "once"])
        out = capsys.readouterr().out
        assert code == 0
        assert "completed" in out
        assert "cli-1" in out

    def test_serve_once_flag(self, env, capsys):
        main(["--config", env["A"], "--no-warn-plaintext", "submit", "--file", env["tasks"]])
        capsys.readouterr()
        code = main(["--config", env["B"], "--no-warn-plaintext", "serve", "--once"])
        assert code == 0

    def test_status_shows_table(self, env, capsys):
        main(["--config", env["A"], "--no-warn-plaintext", "submit", "--file", env["tasks"]])
        main(["--config", env["B"], "--no-warn-plaintext", "once"])
        main(["--config", env["B"], "--no-warn-plaintext", "once"])
        capsys.readouterr()
        code = main(["--config", env["A"], "--no-warn-plaintext", "status"])
        out = capsys.readouterr().out
        assert code == 0
        assert "TASK" in out and "合计" in out
        assert "COMPLETED=2" in out

    def test_status_json(self, env, capsys):
        main(["--config", env["A"], "--no-warn-plaintext", "submit", "--file", env["tasks"]])
        capsys.readouterr()
        code = main(["--config", env["A"], "--no-warn-plaintext", "--json", "status"])
        rows = json.loads(capsys.readouterr().out)
        assert code == 0
        assert len(rows) == 2
        assert rows[0]["state"] == TaskState.PENDING

    def test_submit_wait_completes(self, env, capsys):
        code = main(["--config", env["A"], "--no-warn-plaintext", "submit",
                     "--file", env["tasks"], "--wait", "--timeout", "0.3", "--poll", "0.01"])
        out = capsys.readouterr().out
        # 没有 B 在执行 → A 会判定执行侧已死（这正是心跳判活的意义）
        assert code == 1
        assert "executor-dead" in out

    def test_watch_with_empty_queue_reports_all_done(self, env, capsys):
        code = main(["--config", env["A"], "--no-warn-plaintext", "watch"])
        assert code == 0
        assert "all-done" in capsys.readouterr().out


class TestHeartbeatCommands:
    def test_missing_returns_2(self, env, capsys):
        code = main(["--config", env["A"], "--no-warn-plaintext", "check-heartbeat"])
        out = capsys.readouterr().out
        assert code == 2
        assert "missing" in out

    def test_close_then_check_returns_0(self, env, capsys):
        assert main(["--config", env["A"], "--no-warn-plaintext", "close"]) == 0
        capsys.readouterr()
        code = main(["--config", env["A"], "--no-warn-plaintext", "check-heartbeat"])
        assert code == 0
        assert "closed" in capsys.readouterr().out

    def test_stale_returns_1(self, env, capsys):
        share = env["share"]
        (share / "unit.heartbeat").write_text("2000-01-01T00:00:00Z", encoding="utf-8")
        code = main(["--config", env["A"], "--no-warn-plaintext", "check-heartbeat"])
        assert code == 1
        assert "stale" in capsys.readouterr().out

    def test_serve_exits_on_closed(self, env, capsys):
        main(["--config", env["A"], "--no-warn-plaintext", "close"])
        capsys.readouterr()
        code = main(["--config", env["B"], "--no-warn-plaintext", "serve",
                     "--max-iterations", "3"])
        out = capsys.readouterr().out
        assert code == 0
        assert "closed" in out or "stop" in out

    def test_close_without_shared_errors(self, tmp_path, capsys):
        bad = tmp_path / "noshared.json"
        bad.write_text(json.dumps({"name": "n", "role": "B", "key": "k",
                                   "queue": {"store": {"kind": "sqlite-local"}}}),
                       encoding="utf-8")
        assert main(["--config", str(bad), "--no-warn-plaintext", "close"]) == 2
        assert "未配置 shared path" in capsys.readouterr().err


class TestOpsCommands:
    def test_cancel(self, env, capsys):
        main(["--config", env["A"], "--no-warn-plaintext", "submit", "--file", env["tasks"]])
        capsys.readouterr()
        code = main(["--config", env["A"], "--no-warn-plaintext", "cancel", "--task", "cli-1"])
        assert code == 0
        assert "CANCELLED" in capsys.readouterr().out

    def test_requeue_missing_task_returns_1(self, env, capsys):
        code = main(["--config", env["A"], "--no-warn-plaintext", "requeue", "--task", "ghost"])
        assert code == 1

    def test_retry_failed(self, env, capsys):
        main(["--config", env["A"], "--no-warn-plaintext", "submit",
              "--task", "bad", "--cmd", '"%s" -c "import sys; sys.exit(1)"' % PY])
        for _ in range(4):
            main(["--config", env["B"], "--no-warn-plaintext", "once"])
        capsys.readouterr()
        code = main(["--config", env["A"], "--no-warn-plaintext", "retry-failed"])
        assert code == 0
        assert "重置" in capsys.readouterr().out

    def test_sync_on_shared_mode_is_rejected(self, env, capsys):
        code = main(["--config", env["A"], "--no-warn-plaintext", "sync"])
        assert code == 2
        assert "不是 sqlite-local" in capsys.readouterr().err


class TestLocalModeCli:
    def test_local_mode_full_flow(self, tmp_path, capsys):
        share = tmp_path / "share"
        share.mkdir()
        cfg_a = _write_config(str(tmp_path / "A.json"), "A", share,
                              queue={"store": {"kind": "sqlite-local"},
                                     "heartbeat": {"file": "unit.heartbeat"}})
        cfg_b = _write_config(str(tmp_path / "B.json"), "B", share,
                              queue={"store": {"kind": "sqlite-local"},
                                     "heartbeat": {"file": "unit.heartbeat"}})
        tasks = tmp_path / "t.json"
        tasks.write_text(json.dumps([
            {"task_name": "l1", "cli": {"cmd": '"%s" -c "print(\'local\')"' % PY}},
        ], ensure_ascii=False), encoding="utf-8")

        assert main(["--config", cfg_a, "--no-warn-plaintext", "submit",
                     "--file", str(tasks)]) == 0
        capsys.readouterr()
        # B 跑两轮：第一轮拉包 + 执行，第二轮把状态推回
        assert main(["--config", cfg_b, "--no-warn-plaintext", "once"]) == 0
        capsys.readouterr()
        assert main(["--config", cfg_b, "--no-warn-plaintext", "sync",
                     "--direction", "push"]) == 0
        capsys.readouterr()
        code = main(["--config", cfg_a, "--no-warn-plaintext", "status"])
        out = capsys.readouterr().out
        assert code == 0
        assert "COMPLETED=1" in out
        # A 的本地库与 B 的本地库是两份文件
        assert os.path.exists(str(tmp_path / "rhop-a.db"))
        assert os.path.exists(str(tmp_path / "rhop-b.db"))