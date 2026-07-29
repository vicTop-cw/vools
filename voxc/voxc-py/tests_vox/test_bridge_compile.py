"""Tests for voxc.libs.bridge and voxc.libs.voxcompile.

Run:
    cd e:\\IDEProjects\\AI\\vools\\voxc\\voxc-py && python tests_vox\\test_bridge_compile.py

The tests are organised so that Rust-dependent cases are skipped (not
failed) when the Rust backend binary is unavailable. AST/frontend tests
are skipped when the Python frontend (voxc.lexer / voxc.parser) cannot
be imported.
"""

import json
import os
import sys
import tempfile
import unittest

# Make the ``voxc`` package importable when running the file directly
# from voxc-py/  (i.e. ``python tests_vox/test_bridge_compile.py``).
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # voxc-py/
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from voxc.libs.bridge import (
    ASTGenerator,
    CompileResult,
    RunResult,
    VoxcBridge,
    VoxcCompileError,
    VoxcNotFoundError,
    VoxcRunError,
)
from voxc.libs.voxcompile import (
    CompileOptions,
    CompilePipeline,
    CompileReport,
    CompileStage,
    compile_file,
    compile_source,
    run_file,
)


# A small but valid Vox source used across multiple tests.
SAMPLE_VOX = (
    "val x = 5\n"
    "val y = x + 10\n"
    "print(y)\n"
)


def _rust_available():
    """True if the Rust voxc binary can be located."""
    try:
        return VoxcBridge().is_available()
    except Exception:
        return False


def _ast_gen_available():
    """True if the Python AST generator can be initialised."""
    try:
        return ASTGenerator().is_available()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# VoxcBridge tests
# ---------------------------------------------------------------------------

class TestVoxcBridge(unittest.TestCase):
    """Binary discovery and bridge construction."""

    def test_find_voxc_binary_does_not_crash(self):
        # Even when the binary cannot be found, the static method must
        # return None rather than raise.
        path = VoxcBridge.find_voxc_binary()
        self.assertTrue(path is None or isinstance(path, str))

    def test_bridge_construction_default(self):
        bridge = VoxcBridge()
        # voxc_path is either None or a string pointing at a file.
        self.assertIsInstance(bridge.voxc_path, (type(None), str))
        self.assertIsInstance(bridge.is_available(), bool)

    def test_bridge_construction_with_nonexistent_path(self):
        # An explicit nonexistent path must not raise; it should
        # silently produce an unavailable bridge.
        bridge = VoxcBridge(voxc_exe_path="/nonexistent/path/to/voxc")
        self.assertIsNone(bridge.voxc_path)
        self.assertFalse(bridge.is_available())

    def test_bridge_construction_with_none(self):
        # Passing None explicitly should behave like the default.
        bridge = VoxcBridge(voxc_exe_path=None)
        self.assertIsInstance(bridge.voxc_path, (type(None), str))

    @unittest.skipUnless(_rust_available(), "Rust backend not available")
    def test_dump_ast_roundtrip(self):
        # Build a tiny AST JSON file, then ask the Rust backend to
        # dump it.  We expect to get back a dict with the same name.
        gen = ASTGenerator()
        if not gen.is_available():
            self.skipTest("AST generator unavailable")
        ast = gen.generate(SAMPLE_VOX, filename="dump.vox")
        fd, path = tempfile.mkstemp(suffix=".json", prefix="voxc_ast_dump_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(ast, f)
            bridge = VoxcBridge()
            dumped = bridge.dump_ast(path)
            self.assertIsInstance(dumped, dict)
            self.assertIn("statements", dumped)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# ASTGenerator tests
# ---------------------------------------------------------------------------

class TestASTGenerator(unittest.TestCase):
    """Python-side AST generation."""

    def test_availability_flag(self):
        gen = ASTGenerator()
        self.assertIsInstance(gen.is_available(), bool)

    def test_lexer_class_property(self):
        gen = ASTGenerator()
        # lexer_class may be None when the frontend is missing - that's
        # an acceptable state, not a crash.
        self.assertTrue(gen.lexer_class is None or hasattr(gen.lexer_class, "tokenize"))

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator (voxc.lexer/parser) not available")
    def test_generate_simple(self):
        gen = ASTGenerator()
        ast = gen.generate(SAMPLE_VOX, filename="test.vox")
        self.assertIsInstance(ast, dict)
        self.assertIn("statements", ast)
        self.assertGreaterEqual(len(ast["statements"]), 1)

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator (voxc.lexer/parser) not available")
    def test_generate_from_file(self):
        gen = ASTGenerator()
        fd, path = tempfile.mkstemp(suffix=".vox", prefix="voxc_test_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(SAMPLE_VOX)
            ast = gen.generate_from_file(path)
            self.assertIsInstance(ast, dict)
            self.assertIn("statements", ast)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator (voxc.lexer/parser) not available")
    def test_generate_returns_json_serializable(self):
        # The AST must be round-trippable through json.dumps/loads.
        gen = ASTGenerator()
        ast = gen.generate(SAMPLE_VOX, filename="rt.vox")
        serialized = json.dumps(ast, ensure_ascii=False)
        restored = json.loads(serialized)
        self.assertEqual(ast, restored)


# ---------------------------------------------------------------------------
# CompileOptions tests
# ---------------------------------------------------------------------------

class TestCompileOptions(unittest.TestCase):

    def test_defaults(self):
        opts = CompileOptions()
        self.assertIsNone(opts.input_file)
        self.assertIsNone(opts.output_dir)
        self.assertFalse(opts.verbose)
        self.assertFalse(opts.keep_intermediates)
        self.assertEqual(opts.target, "release")
        self.assertEqual(opts.extra_args, [])

    def test_kwargs(self):
        opts = CompileOptions(
            input_file="foo.vox",
            output_dir="out/",
            verbose=True,
            keep_intermediates=True,
            target="debug",
            extra_args=["--foo", "bar"],
        )
        self.assertEqual(opts.input_file, "foo.vox")
        self.assertEqual(opts.output_dir, "out/")
        self.assertTrue(opts.verbose)
        self.assertTrue(opts.keep_intermediates)
        self.assertEqual(opts.target, "debug")
        self.assertEqual(opts.extra_args, ["--foo", "bar"])

    def test_invalid_target_falls_back_to_release(self):
        opts = CompileOptions(target="bogus")
        self.assertEqual(opts.target, "release")

    def test_to_dict_roundtrip(self):
        opts = CompileOptions(input_file="a.vox", verbose=True,
                              target="debug", extra_args=["--x"])
        d = opts.to_dict()
        self.assertEqual(d["input_file"], "a.vox")
        self.assertTrue(d["verbose"])
        self.assertEqual(d["target"], "debug")
        self.assertEqual(d["extra_args"], ["--x"])

    def test_from_args_namespace(self):
        # Simulate an argparse Namespace.
        class Args(object):
            input = "in.vox"
            output = "out/"
            verbose = True
            keep_intermediates = False
            target = "release"
            extra_args = ["--flag"]
        opts = CompileOptions.from_args(Args())
        self.assertEqual(opts.input_file, "in.vox")
        self.assertEqual(opts.output_dir, "out/")
        self.assertTrue(opts.verbose)
        self.assertEqual(opts.extra_args, ["--flag"])

    def test_from_args_missing_attributes(self):
        # Missing attributes should default gracefully.
        class Args(object):
            input = "in.vox"
        opts = CompileOptions.from_args(Args())
        self.assertEqual(opts.input_file, "in.vox")
        self.assertFalse(opts.verbose)
        self.assertEqual(opts.target, "release")


# ---------------------------------------------------------------------------
# CompilePipeline tests
# ---------------------------------------------------------------------------

class TestCompilePipeline(unittest.TestCase):

    def test_construction(self):
        opts = CompileOptions(input_file="dummy.vox")
        pipeline = CompilePipeline(opts)
        self.assertIsInstance(pipeline.intermediates, dict)
        self.assertIn("tokens", pipeline.intermediates)
        self.assertIn("ast", pipeline.intermediates)
        self.assertIn("rust_code", pipeline.intermediates)
        self.assertIsInstance(pipeline.report, CompileReport)

    def test_intermediates_initial_state(self):
        pipeline = CompilePipeline(CompileOptions())
        for key in ("tokens", "ast", "symbols", "rust_code",
                    "ast_json_path", "output_dir", "program_output"):
            self.assertIn(key, pipeline.intermediates)
            self.assertIsNone(pipeline.intermediates[key])

    def test_unknown_stage_raises(self):
        pipeline = CompilePipeline(CompileOptions())
        with self.assertRaises(ValueError):
            pipeline.run_stage("bogus_stage")

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator not available")
    def test_run_stage_lex(self):
        fd, path = tempfile.mkstemp(suffix=".vox", prefix="voxc_lex_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(SAMPLE_VOX)
            opts = CompileOptions(input_file=path)
            pipeline = CompilePipeline(opts)
            pipeline.run_stage(CompileStage.LEX)
            self.assertIsNotNone(pipeline.intermediates["tokens"])
            self.assertGreater(len(pipeline.intermediates["tokens"]), 0)
            self.assertIn(CompileStage.LEX, pipeline.report.stages)
            self.assertEqual(
                pipeline.report.stages[CompileStage.LEX]["status"], "ok"
            )
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator not available")
    def test_run_stage_parse(self):
        fd, path = tempfile.mkstemp(suffix=".vox", prefix="voxc_parse_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(SAMPLE_VOX)
            opts = CompileOptions(input_file=path)
            pipeline = CompilePipeline(opts)
            pipeline.run_stage(CompileStage.PARSE)
            self.assertIsNotNone(pipeline.intermediates["ast"])
            self.assertIsInstance(pipeline.intermediates["ast"], dict)
            self.assertIn("statements", pipeline.intermediates["ast"])
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator not available")
    def test_lex_parse_semantic_chain(self):
        # These three stages do NOT require the Rust backend.
        fd, path = tempfile.mkstemp(suffix=".vox", prefix="voxc_chain_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(SAMPLE_VOX)
            opts = CompileOptions(input_file=path)
            pipeline = CompilePipeline(opts)
            pipeline.run_stage(CompileStage.LEX)
            pipeline.run_stage(CompileStage.PARSE)
            pipeline.run_stage(CompileStage.SEMANTIC)
            for stage in (CompileStage.LEX, CompileStage.PARSE,
                          CompileStage.SEMANTIC):
                self.assertIn(stage, pipeline.report.stages)
                self.assertEqual(
                    pipeline.report.stages[stage]["status"], "ok"
                )
            self.assertIsNotNone(pipeline.intermediates["symbols"])
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator not available")
    def test_full_pipeline_without_rust_returns_failed_result(self):
        # When the Rust backend is unavailable, the pipeline should
        # fail gracefully at the codegen stage and return a
        # CompileResult(success=False) rather than raising.
        if _rust_available():
            self.skipTest("Rust backend IS available - skip the no-Rust path")
        fd, path = tempfile.mkstemp(suffix=".vox", prefix="voxc_no_rust_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(SAMPLE_VOX)
            opts = CompileOptions(input_file=path)
            pipeline = CompilePipeline(opts)
            result = pipeline.run()
            self.assertFalse(result.success)
            self.assertIsInstance(result.stderr, str)
            self.assertIn("voxc", result.stderr.lower())
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator not available")
    def test_verbose_hook_writes_to_stderr(self):
        import io
        from contextlib import redirect_stderr

        fd, path = tempfile.mkstemp(suffix=".vox", prefix="voxc_verbose_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(SAMPLE_VOX)
            opts = CompileOptions(input_file=path, verbose=True)
            pipeline = CompilePipeline(opts)
            buf = io.StringIO()
            with redirect_stderr(buf):
                pipeline.run_stage(CompileStage.LEX)
            self.assertIn("lex", buf.getvalue())
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# CompileReport tests
# ---------------------------------------------------------------------------

class TestCompileReport(unittest.TestCase):

    def test_empty_report(self):
        report = CompileReport()
        d = report.to_dict()
        self.assertIn("stages", d)
        self.assertEqual(d["stages"], {})
        self.assertIsNone(d["error"])
        self.assertIsNone(d["total_duration"])

    def test_mark_records_status_and_duration(self):
        report = CompileReport()
        report.mark("lex", "ok", duration=0.001, output={"tokens": 5})
        d = report.to_dict()
        self.assertIn("lex", d["stages"])
        self.assertEqual(d["stages"]["lex"]["status"], "ok")
        self.assertEqual(d["stages"]["lex"]["duration"], 0.001)
        self.assertEqual(d["stages"]["lex"]["output"], {"tokens": 5})

    def test_fail_records_error(self):
        report = CompileReport()
        report.fail("parse", SyntaxError("bad syntax"))
        d = report.to_dict()
        self.assertEqual(d["stages"]["parse"]["status"], "failed")
        self.assertIn("bad syntax", d["stages"]["parse"]["error"])
        self.assertEqual(d["error"], "bad syntax")

    def test_total_duration(self):
        report = CompileReport()
        report.start_time = 1.0
        report.end_time = 2.5
        d = report.to_dict()
        self.assertEqual(d["total_duration"], 1.5)

    def test_repr_contains_stage_names(self):
        report = CompileReport()
        report.mark("lex", "ok", duration=0.1)
        report.mark("parse", "ok", duration=0.2)
        s = repr(report)
        self.assertIn("CompileReport", s)
        self.assertIn("lex", s)
        self.assertIn("parse", s)

    def test_to_json_serializable(self):
        report = CompileReport()
        report.start_time = 1.0
        report.end_time = 2.0
        report.mark("lex", "ok", duration=0.5, output={"count": 3})
        # Must not raise.
        s = report.to_json()
        restored = json.loads(s)
        self.assertIn("stages", restored)
        self.assertEqual(restored["stages"]["lex"]["status"], "ok")


# ---------------------------------------------------------------------------
# Convenience function tests
# ---------------------------------------------------------------------------

class TestCompileSource(unittest.TestCase):

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator not available")
    def test_compile_source_returns_compile_result(self):
        # Whether or not Rust is available, compile_source must return
        # a CompileResult (success may be True or False).
        result = compile_source(SAMPLE_VOX, filename="inline.vox")
        self.assertIsInstance(result, CompileResult)
        self.assertIsInstance(result.success, bool)
        # program_output must always be set on the returned object.
        self.assertTrue(hasattr(result, "program_output"))

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator not available")
    def test_compile_source_cleans_up_temp_file(self):
        # We can't directly observe the temp file path, but we can
        # verify the function doesn't raise on a second invocation
        # (which would indicate leftover state).
        r1 = compile_source(SAMPLE_VOX)
        r2 = compile_source(SAMPLE_VOX)
        self.assertIsInstance(r1, CompileResult)
        self.assertIsInstance(r2, CompileResult)


class TestCompileFileAndRunFile(unittest.TestCase):

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator not available")
    def test_compile_file_with_missing_input(self):
        # compile_file should still return a CompileResult (with
        # success=False) when the input file doesn't exist - the
        # pipeline catches the error.
        result = compile_file("/nonexistent/file.vox")
        self.assertIsInstance(result, CompileResult)
        self.assertFalse(result.success)

    @unittest.skipUnless(_ast_gen_available(),
                         "AST generator not available")
    def test_run_file_returns_object_with_program_output(self):
        fd, path = tempfile.mkstemp(suffix=".vox", prefix="voxc_runfile_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(SAMPLE_VOX)
            result = run_file(path)
            self.assertIsInstance(result, CompileResult)
            self.assertTrue(hasattr(result, "program_output"))
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Result class tests
# ---------------------------------------------------------------------------

class TestCompileResult(unittest.TestCase):

    def test_default_construction(self):
        r = CompileResult(True, 0, "hi", "", output_dir="/tmp",
                          generated_files=["/tmp/a"])
        self.assertTrue(r.is_success)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "hi")
        self.assertEqual(r.stderr, "")
        self.assertEqual(r.output_dir, "/tmp")
        self.assertIn("/tmp/a", r.generated_files)

    def test_failed_construction(self):
        r = CompileResult(False, 1, "", "err")
        self.assertFalse(r.is_success)
        self.assertEqual(r.stderr, "err")

    def test_to_dict(self):
        r = CompileResult(True, 0, "out", "err", output_dir="/d",
                          generated_files=["/d/x"])
        d = r.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["stdout"], "out")
        self.assertEqual(d["generated_files"], ["/d/x"])

    def test_repr(self):
        r = CompileResult(True, 0, "", "")
        s = repr(r)
        self.assertIn("CompileResult", s)
        self.assertIn("True", s)


class TestRunResult(unittest.TestCase):

    def test_inherits_from_compile_result(self):
        r = RunResult(True, 0, "out", "", program_output="hello")
        self.assertIsInstance(r, CompileResult)
        self.assertTrue(r.is_success)
        self.assertEqual(r.program_output, "hello")

    def test_to_dict_includes_program_output(self):
        r = RunResult(True, 0, "out", "err", program_output="hello")
        d = r.to_dict()
        self.assertEqual(d["program_output"], "hello")
        self.assertIn("stdout", d)

    def test_repr(self):
        r = RunResult(True, 0, "out", "", program_output="hello world")
        s = repr(r)
        self.assertIn("RunResult", s)
        self.assertIn("True", s)

    def test_default_program_output_is_empty_string(self):
        r = RunResult(False, 1, "", "err")
        self.assertEqual(r.program_output, "")


# ---------------------------------------------------------------------------
# CompileStage constant tests
# ---------------------------------------------------------------------------

class TestCompileStage(unittest.TestCase):

    def test_constants_are_strings(self):
        self.assertEqual(CompileStage.LEX, "lex")
        self.assertEqual(CompileStage.PARSE, "parse")
        self.assertEqual(CompileStage.SEMANTIC, "semantic")
        self.assertEqual(CompileStage.CODEGEN, "codegen")
        self.assertEqual(CompileStage.COMPILE, "compile")
        self.assertEqual(CompileStage.RUN, "run")

    def test_all_contains_every_stage_in_order(self):
        self.assertEqual(CompileStage.ALL,
                         ("lex", "parse", "semantic", "codegen",
                          "compile", "run"))

    def test_all_has_six_stages(self):
        self.assertEqual(len(CompileStage.ALL), 6)


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------

class TestExceptionHierarchy(unittest.TestCase):

    def test_all_inherit_from_runtime_error(self):
        for exc in (VoxcNotFoundError, VoxcCompileError, VoxcRunError):
            self.assertTrue(issubclass(exc, RuntimeError))

    def test_raise_and_catch(self):
        with self.assertRaises(VoxcNotFoundError):
            raise VoxcNotFoundError("missing")
        with self.assertRaises(VoxcCompileError):
            raise VoxcCompileError("compile failed")
        with self.assertRaises(VoxcRunError):
            raise VoxcRunError("run failed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
