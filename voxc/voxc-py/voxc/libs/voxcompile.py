"""Compile pipeline orchestrator for the Vox compiler.

Ties together the Python frontend (lexer, parser, semantic analysis)
and the Rust backend (codegen, compile, run) into a stage-based
pipeline. Each stage produces an intermediate artifact that can be
inspected or serialized via :attr:`CompilePipeline.intermediates`.

Python 3.6+ compatible. Imports from :mod:`voxc.libs.bridge` and
:mod:`voxc.libs.symtable` are deferred to method bodies so this module
can be imported even when those dependencies are partially installed.
"""

import json
import os
import sys
import tempfile
import time


# ---------------------------------------------------------------------------
# CompileStage - string constants (3.6-friendly, no Enum edge cases)
# ---------------------------------------------------------------------------

class CompileStage(object):
    """String constants identifying pipeline stages.

    Using plain string constants (instead of :class:`enum.Enum`) keeps
    the values JSON-serializable and comparable to raw strings, which
    matches the pattern used by :class:`voxc.libs.symtable.SymbolKind`.
    """

    LEX = "lex"
    PARSE = "parse"
    SEMANTIC = "semantic"
    CODEGEN = "codegen"
    COMPILE = "compile"
    RUN = "run"

    # Ordered tuple - handy for iterating all stages.
    ALL = (LEX, PARSE, SEMANTIC, CODEGEN, COMPILE, RUN)


# ---------------------------------------------------------------------------
# CompileOptions
# ---------------------------------------------------------------------------

class CompileOptions(object):
    """Options controlling the compile pipeline.

    Attributes:
        input_file: Path to the .vox source file.
        output_dir: Output directory for generated files (default: auto,
            resolved by the Rust backend as ``__vox_rust_cache__/`` next
            to the input file).
        verbose: If True, print stage progress to stderr.
        keep_intermediates: If True, do not delete temp files produced
            by the pipeline (AST JSON, etc.).
        target: Build target - ``"debug"`` or ``"release"``. Used as a
            hint for the Rust backend.
        extra_args: List of extra CLI args to forward to ``voxc``.
    """

    def __init__(self, input_file=None, output_dir=None, verbose=False,
                 keep_intermediates=False, target="release", extra_args=None):
        self.input_file = input_file
        self.output_dir = output_dir
        self.verbose = bool(verbose)
        self.keep_intermediates = bool(keep_intermediates)
        self.target = target if target in ("debug", "release") else "release"
        self.extra_args = list(extra_args or [])

    @classmethod
    def from_args(cls, args):
        """Build :class:`CompileOptions` from an :class:`argparse.Namespace`.

        Reads the following attributes if present: ``input``, ``output``,
        ``verbose``, ``keep_intermediates``, ``target``, ``extra_args``.
        Missing attributes default to ``None`` / empty.
        """
        return cls(
            input_file=getattr(args, "input", None),
            output_dir=getattr(args, "output", None),
            verbose=getattr(args, "verbose", False),
            keep_intermediates=getattr(args, "keep_intermediates", False),
            target=getattr(args, "target", "release"),
            extra_args=getattr(args, "extra_args", None),
        )

    def to_dict(self):
        return {
            "input_file": self.input_file,
            "output_dir": self.output_dir,
            "verbose": self.verbose,
            "keep_intermediates": self.keep_intermediates,
            "target": self.target,
            "extra_args": list(self.extra_args),
        }

    def __repr__(self):
        return "CompileOptions(input_file={!r}, target={!r}, verbose={!r})".format(
            self.input_file, self.target, self.verbose
        )


# ---------------------------------------------------------------------------
# CompileReport
# ---------------------------------------------------------------------------

class CompileReport(object):
    """Per-stage status / timing report for a pipeline run.

    Attributes:
        stages: ``{stage_name: {"status": ..., "duration": ...,
            "output": ...}}`` dict.
        start_time: Wall clock at :meth:`CompilePipeline.run` start.
        end_time: Wall clock at :meth:`CompilePipeline.run` end.
        error: Error message if the pipeline failed, else ``None``.
    """

    def __init__(self):
        self.stages = {}
        self.start_time = None
        self.end_time = None
        self.error = None

    def mark(self, stage, status, duration=None, output=None):
        """Record the result of a completed stage."""
        self.stages[stage] = {
            "status": status,
            "duration": duration,
            "output": output,
        }

    def fail(self, stage, error):
        """Record a stage failure and store the error message."""
        self.stages[stage] = {
            "status": "failed",
            "duration": None,
            "output": None,
            "error": str(error),
        }
        self.error = str(error)

    def to_dict(self):
        """Serialize to a JSON-friendly dict."""
        total_duration = None
        if self.start_time is not None and self.end_time is not None:
            total_duration = self.end_time - self.start_time
        return {
            "stages": {k: dict(v) for k, v in self.stages.items()},
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration": total_duration,
            "error": self.error,
        }

    def to_json(self, indent=2):
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str,
                          ensure_ascii=False)

    def __repr__(self):
        lines = ["CompileReport("]
        for stage in CompileStage.ALL:
            entry = self.stages.get(stage)
            if entry is None:
                lines.append("  {}: -".format(stage))
            else:
                dur = entry.get("duration")
                dur_str = "{:.3f}s".format(dur) if dur is not None else "-"
                status = entry.get("status", "?")
                lines.append("  {}: {} ({})".format(stage, status, dur_str))
        if self.error:
            lines.append("  error: {}".format(self.error))
        lines.append(")")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CompilePipeline
# ---------------------------------------------------------------------------

class CompilePipeline(object):
    """Main compile pipeline orchestrator.

    Drives the compilation through six ordered stages: lex, parse,
    semantic, codegen, compile, run. Each stage can be invoked
    individually via :meth:`run_stage`, or all at once via :meth:`run`.

    Intermediate artifacts are stored in :attr:`intermediates`:
        - ``tokens``: list of Token namedtuples from the lexer.
        - ``ast``: AST dict from the parser.
        - ``symbols``: dict describing the symbol table (best-effort).
        - ``rust_code``: generated Rust source (str) if available.
        - ``ast_json_path``: path to the temp AST JSON file.
        - ``output_dir``: ``__vox_rust_cache__/`` path.
        - ``program_output``: stdout of the compiled program.
    """

    def __init__(self, options):
        self.options = options
        self.intermediates = {
            "tokens": None,
            "ast": None,
            "symbols": None,
            "rust_code": None,
            "ast_json_path": None,
            "output_dir": None,
            "program_output": None,
            "source_name": None,
        }
        self.report = CompileReport()
        self._bridge = None
        self._ast_gen = None
        self._temp_files = []
        self._stage_methods = {
            CompileStage.LEX: self._stage_lex,
            CompileStage.PARSE: self._stage_parse,
            CompileStage.SEMANTIC: self._stage_semantic,
            CompileStage.CODEGEN: self._stage_codegen,
            CompileStage.COMPILE: self._stage_compile,
            CompileStage.RUN: self._stage_run,
        }

    # ---- public API ----

    def run(self, stop_at=None):
        """Execute the pipeline.

        Args:
            stop_at: Optional stage name (see :class:`CompileStage`).
                If provided, the pipeline stops after completing this
                stage. When ``None`` (the default) all stages run.

        Returns:
            :class:`voxc.libs.bridge.CompileResult` - on success, a
            result with ``success=True``; on failure, a result with
            ``success=False`` and the error message in ``stderr``.
            The ``stdout`` field holds the program output when the
            RUN stage is reached; otherwise it is empty.
        """
        # Lazy import to avoid hard dependency at module load time.
        from voxc.libs.bridge import CompileResult

        self.report.start_time = time.time()
        try:
            for stage in CompileStage.ALL:
                self.run_stage(stage)
                if stop_at is not None and stage == stop_at:
                    break

            return CompileResult(
                success=True,
                returncode=0,
                stdout=self.intermediates.get("program_output") or "",
                stderr="",
                output_dir=self.intermediates.get("output_dir"),
                generated_files=self._collect_generated_files(),
            )
        except Exception as exc:
            self.report.error = str(exc)
            return CompileResult(
                success=False,
                returncode=1,
                stdout="",
                stderr=str(exc),
                output_dir=self.intermediates.get("output_dir"),
                generated_files=[],
            )
        finally:
            self.report.end_time = time.time()
            self._cleanup_temp_files()

    def run_stage(self, stage):
        """Execute a single stage by name.

        Raises:
            ValueError: if ``stage`` is unknown.
            Exception: whatever the stage raises (also recorded in the
                report).
        """
        method = self._stage_methods.get(stage)
        if method is None:
            raise ValueError("Unknown stage: {!r}".format(stage))
        start = time.time()
        try:
            output = method()
            duration = time.time() - start
            self.report.mark(stage, "ok", duration=duration, output=output)
            self.on_stage_complete(stage, output)
        except Exception as exc:
            duration = time.time() - start
            self.report.fail(stage, exc)
            # Re-raise so callers can react; the report already records
            # the failure.
            raise

    def on_stage_complete(self, stage, result):
        """Hook for subclasses - called after each successful stage.

        The default implementation prints progress to stderr when
        ``options.verbose`` is True.
        """
        if self.options.verbose:
            sys.stderr.write("[voxc] stage {} done\n".format(stage))

    # ---- lazy accessors ----

    def _get_ast_generator(self):
        if self._ast_gen is None:
            from voxc.libs.bridge import ASTGenerator
            self._ast_gen = ASTGenerator()
        return self._ast_gen

    def _get_bridge(self):
        if self._bridge is None:
            from voxc.libs.bridge import VoxcBridge
            self._bridge = VoxcBridge()
        return self._bridge

    def _read_source(self):
        if not self.options.input_file:
            raise ValueError("options.input_file is not set")
        with open(self.options.input_file, "r", encoding="utf-8") as f:
            return f.read()

    # ---- stage implementations ----

    def _stage_lex(self):
        """Stage 1: tokenize the source.

        Reaches into the ASTGenerator's resolved lexer class so we can
        run the lexer independently of the parser.
        """
        gen = self._get_ast_generator()
        if not gen.is_available():
            raise RuntimeError(
                "AST generator not available - cannot run lex stage"
            )
        lexer_cls = gen.lexer_class
        if lexer_cls is None:
            # Fall back to a direct import attempt.
            try:
                from voxc.lexer import VoxLexer as lexer_cls
            except Exception:
                try:
                    from voxc.libs.tokenize import VoxLexer as lexer_cls
                except Exception:
                    raise RuntimeError(
                        "No lexer class available for lex stage"
                    )

        source = self._read_source()
        lexer = lexer_cls()
        tokens = lexer.tokenize(source)
        self.intermediates["tokens"] = tokens
        return {"token_count": len(tokens)}

    def _stage_parse(self):
        """Stage 2: parse tokens into an AST dict."""
        gen = self._get_ast_generator()
        if not gen.is_available():
            raise RuntimeError(
                "AST generator not available - cannot run parse stage"
            )
        source = self._read_source()
        filename = self.options.input_file or "<string>"
        ast = gen.generate(source, filename=filename)
        self.intermediates["ast"] = ast
        statements = ast.get("statements", []) if isinstance(ast, dict) else []
        return {"statements": len(statements)}

    def _stage_semantic(self):
        """Stage 3: best-effort semantic analysis.

        Builds a :class:`voxc.libs.symtable.SymbolTable` and records
        basic stats. A full semantic pass (walking the AST, registering
        every definition) is out of scope for this orchestrator - the
        symbol table is constructed with builtins only.
        """
        ast = self.intermediates.get("ast")
        if ast is None:
            # Parse hasn't run yet - run it now.
            self._stage_parse()
            ast = self.intermediates["ast"]

        symbols = None
        try:
            from voxc.libs.symtable import SymbolTable
            st = SymbolTable()
            builtin_count = 0
            global_scope = getattr(st, "global_scope", None)
            if global_scope is not None:
                # SymbolTable stores symbols on its global scope; the
                # exact attribute name varies, so probe defensively.
                syms = (getattr(global_scope, "symbols", None)
                        or getattr(global_scope, "_symbols", None)
                        or {})
                builtin_count = len(syms)
            symbols = {
                "builtins": builtin_count,
                "ast_statements": len(ast.get("statements", []))
                                 if isinstance(ast, dict) else 0,
            }
        except Exception as exc:
            symbols = {"error": str(exc)}

        self.intermediates["symbols"] = symbols
        return symbols

    def _stage_codegen(self):
        """Stage 4: generate Rust source via ``voxc compile``.

        The Rust backend writes ``__vox_rust_cache__/src/main.rs`` next
        to the input file. We read that file back into
        :attr:`intermediates` ``["rust_code"]`` for inspection.
        """
        if not self.options.input_file:
            raise ValueError("options.input_file is not set")

        ast = self.intermediates.get("ast")
        if ast is None:
            self._stage_parse()
            ast = self.intermediates["ast"]

        # Write AST JSON to a temp file for the Rust backend to consume.
        fd, tmp_path = tempfile.mkstemp(suffix=".json",
                                        prefix="voxc_pipeline_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(ast, f, indent=2, ensure_ascii=False)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        self._temp_files.append(tmp_path)
        self.intermediates["ast_json_path"] = tmp_path

        bridge = self._get_bridge()
        if not bridge.is_available():
            raise RuntimeError(
                "Rust voxc binary not available - cannot run codegen stage"
            )

        try:
            result = bridge.compile(
                self.options.input_file, ast_json_path=tmp_path
            )
        except Exception as exc:
            raise RuntimeError(
                "voxc compile (codegen) failed: {}".format(exc)
            )

        output_dir = result.output_dir
        self.intermediates["output_dir"] = output_dir

        # Read back the generated Rust source for inspection.
        if output_dir:
            main_rs = os.path.join(output_dir, "src", "main.rs")
            if os.path.isfile(main_rs):
                try:
                    with open(main_rs, "r", encoding="utf-8") as f:
                        self.intermediates["rust_code"] = f.read()
                except OSError:
                    pass

        return {
            "output_dir": output_dir,
            "generated_files": len(result.generated_files),
        }

    def _stage_compile(self):
        """Stage 5: cargo build.

        In the current Rust backend, the cargo build step is bundled
        into ``voxc run`` (there is no standalone ``voxc build``
        subcommand yet). This stage is therefore a marker that returns
        a note; the actual build happens during :meth:`_stage_run`.
        """
        return {
            "note": "cargo build is performed by voxc run (stage: run)"
        }

    def _stage_run(self):
        """Stage 6: compile + build + execute via ``voxc run``."""
        if not self.options.input_file:
            raise ValueError("options.input_file is not set")

        ast_json_path = self.intermediates.get("ast_json_path")
        bridge = self._get_bridge()
        if not bridge.is_available():
            raise RuntimeError(
                "Rust voxc binary not available - cannot run stage"
            )

        try:
            result = bridge.run(
                self.options.input_file, ast_json_path=ast_json_path
            )
        except Exception as exc:
            raise RuntimeError("voxc run failed: {}".format(exc))

        self.intermediates["program_output"] = result.program_output
        if result.output_dir and not self.intermediates.get("output_dir"):
            self.intermediates["output_dir"] = result.output_dir
        return {"program_output": result.program_output}

    # ---- cleanup / helpers ----

    def _collect_generated_files(self):
        output_dir = self.intermediates.get("output_dir")
        if not output_dir or not os.path.isdir(output_dir):
            return []
        result = []
        for root, _dirs, files in os.walk(output_dir):
            for name in files:
                result.append(os.path.join(root, name))
        return result

    def _cleanup_temp_files(self):
        if self.options.keep_intermediates:
            return
        for path in self._temp_files:
            try:
                if os.path.isfile(path):
                    os.unlink(path)
            except OSError:
                pass
        self._temp_files = []


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def compile_file(filepath, **kwargs):
    """One-liner: compile a .vox file (without running).

    Runs the pipeline through the COMPILE stage only - the program is
    not executed. Extra keyword arguments are forwarded to
    :class:`CompileOptions`.

    Returns:
        :class:`voxc.libs.bridge.CompileResult` with ``program_output``
        set to an empty string (since RUN did not execute).
    """
    options = CompileOptions(input_file=filepath, **kwargs)
    pipeline = CompilePipeline(options)
    result = pipeline.run(stop_at=CompileStage.COMPILE)
    # CompileResult does not carry program_output by default; mirror
    # the RunResult shape so callers can read either field uniformly.
    if not hasattr(result, "program_output"):
        result.program_output = ""
    return result


def run_file(filepath, **kwargs):
    """One-liner: compile and run a .vox file.

    Runs the full pipeline (including RUN). Extra keyword arguments
    are forwarded to :class:`CompileOptions`.

    Returns:
        :class:`voxc.libs.bridge.CompileResult` with ``program_output``
        set to the program's stdout when the RUN stage succeeds.
    """
    options = CompileOptions(input_file=filepath, **kwargs)
    pipeline = CompilePipeline(options)
    result = pipeline.run()
    # The pipeline stuffs program output into ``stdout``; mirror it to
    # ``program_output`` so callers get a RunResult-shaped object.
    if not hasattr(result, "program_output"):
        result.program_output = result.stdout or ""
    return result


def compile_source(source, filename="<string>", **kwargs):
    """One-liner: compile Vox source code from a string (without running).

    Writes ``source`` to a temp .vox file, runs the pipeline through
    the COMPILE stage, and cleans up the temp file (unless
    ``keep_intermediates=True``).

    Extra keyword arguments are forwarded to :class:`CompileOptions`.

    Returns:
        :class:`voxc.libs.bridge.CompileResult` with ``program_output``
        set to an empty string (since RUN did not execute).
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".vox", prefix="voxc_src_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(source)
        options = CompileOptions(input_file=tmp_path, **kwargs)
        pipeline = CompilePipeline(options)
        # Stash the friendly name for downstream consumers.
        pipeline.intermediates["source_name"] = filename
        result = pipeline.run(stop_at=CompileStage.COMPILE)
        if not hasattr(result, "program_output"):
            result.program_output = ""
        return result
    finally:
        if not kwargs.get("keep_intermediates", False):
            try:
                if os.path.isfile(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass
