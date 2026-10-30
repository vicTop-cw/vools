"""selfdrive 模块级 load_run / list_runs 契约测试（第 32 批，直接由 Lead 编写）。

退步了会怎样：
- load_run 读取失败 → 无法恢复未完成的 run
- list_runs 列出错误 → 用户看不到历史 run
"""
import json
import os

import pytest


@pytest.fixture
def tmp_meta(tmp_path, monkeypatch):
    """隔离：meta_dir 指向 tmp。"""
    d = tmp_path / "meta"
    d.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ACTUS_META_DIR", str(d))
    return str(d)


class TestLoadRun:
    def test_load_run_not_found(self, tmp_meta):
        """退步了会怎样：不存在的 run_id 应返回 None。"""
        from vools.actus.selfdrive import load_run
        assert load_run("not.exists", meta_dir=tmp_meta) is None

    def test_load_run_found(self, tmp_meta):
        """退步了会怎样：应正确加载已保存的 run。"""
        from vools.actus.selfdrive import load_run
        # 手动创建一个 run 文件
        runs_dir = os.path.join(tmp_meta, "selfdrive")
        os.makedirs(runs_dir, exist_ok=True)
        run_data = {"run_id": "sd-001", "goal": "测试目标", "summary": {"total": 1}}
        with open(os.path.join(runs_dir, "sd-001.json"), "w", encoding="utf-8") as f:
            json.dump(run_data, f)
        result = load_run("sd-001", meta_dir=tmp_meta)
        assert result is not None
        assert result["run_id"] == "sd-001"
        assert result["goal"] == "测试目标"

    def test_load_run_invalid_json(self, tmp_meta):
        """退步了会怎样：损坏的 JSON 应抛异常（不静默吞掉）。"""
        from vools.actus.selfdrive import load_run
        runs_dir = os.path.join(tmp_meta, "selfdrive")
        os.makedirs(runs_dir, exist_ok=True)
        with open(os.path.join(runs_dir, "bad.json"), "w", encoding="utf-8") as f:
            f.write("not json {")
        with pytest.raises(json.JSONDecodeError):
            load_run("bad", meta_dir=tmp_meta)


class TestListRuns:
    def test_list_runs_empty_dir(self, tmp_meta):
        """退步了会怎样：空目录应返回空列表。"""
        from vools.actus.selfdrive import list_runs
        assert list_runs(meta_dir=tmp_meta) == []

    def test_list_runs_no_dir(self, tmp_meta):
        """退步了会怎样：目录不存在应返回空列表。"""
        from vools.actus.selfdrive import list_runs
        # 目录不存在
        assert list_runs(meta_dir="/tmp/nonexistent") == []

    def test_list_runs_with_runs(self, tmp_meta):
        """退退了会怎样：应列出所有 run。"""
        from vools.actus.selfdrive import list_runs
        runs_dir = os.path.join(tmp_meta, "selfdrive")
        os.makedirs(runs_dir, exist_ok=True)
        for i in range(2):
            run_data = {"run_id": f"sd-00{i}", "goal": f"目标{i}", "summary": {"total": 1}}
            with open(os.path.join(runs_dir, f"sd-00{i}.json"), "w", encoding="utf-8") as f:
                json.dump(run_data, f)
        runs = list_runs(meta_dir=tmp_meta)
        assert len(runs) == 2
        assert any(r["run_id"] == "sd-000" for r in runs)
        assert any(r["run_id"] == "sd-001" for r in runs)

    def test_list_runs_skips_bad_json(self, tmp_meta):
        """退步了会怎样：坏 JSON 文件应跳过，不影响其他 run。"""
        from vools.actus.selfdrive import list_runs
        runs_dir = os.path.join(tmp_meta, "selfdrive")
        os.makedirs(runs_dir, exist_ok=True)
        # 坏 JSON
        with open(os.path.join(runs_dir, "bad.json"), "w", encoding="utf-8") as f:
            f.write("not json {")
        # 好 JSON
        run_data = {"run_id": "sd-001", "goal": "目标", "summary": {"total": 1}}
        with open(os.path.join(runs_dir, "sd-001.json"), "w", encoding="utf-8") as f:
            json.dump(run_data, f)
        runs = list_runs(meta_dir=tmp_meta)
        assert len(runs) == 1
        assert runs[0]["run_id"] == "sd-001"


class TestModuleLevelRun:
    def test_module_level_run(self, tmp_meta):
        """退步了会怎样：模块级 run() 应能执行。"""
        from vools.actus.selfdrive import run
        result = run("测试目标", max_depth=1, meta_dir=tmp_meta)
        assert result is not None
        assert result["summary"]["total"] >= 1
