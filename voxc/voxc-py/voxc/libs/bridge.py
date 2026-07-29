"""Python-Rust backend bridge for the Vox compiler.

Provides a high-level interface for invoking the Rust ``voxc`` backend
from Python. Handles binary discovery, AST JSON generation, and result
capture.

Python 3.6+ compatible. All external imports (voxc.lexer, voxc.parser,
voxc.ast_nodes, voxc.libs.*) are wrapped in try/except so this module
can be imported even when the rest of the frontend is partially
installed.
"""

import json
import os
import shutil
import subprocess
import tempfile


# ---------------------------------------------------------------------------
# Platform binary name(s)
# ---------------------------------------------------------------------------

# On Windows both ``voxc.exe`` and ``voxc`` (with PATHEXT resolution) may
# appear; on Unix only ``voxc``. We check both names on Windows so the
# discovery works regardless of how the binary was built.
if os.name == "nt":
    _BIN_NAMES = ("voxc.exe", "voxc")
else:
    _BIN_NAMES = ("voxc",)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class VoxcNotFoundError(RuntimeError):
    """Raised when the Rust voxc binary cannot be located."""
    pass


class VoxcCompileError(RuntimeError):
    """Raised when the Rust backend fails to compile a Vox file."""
    pass


class VoxcRunError(RuntimeError):
    """Raised when the compiled Vox program fails to run."""
    pass


# ---------------------------------------------------------------------------
# Result classes
# ---------------------------------------------------------------------------

class CompileResult(object):
    """Result of a compile invocation.

    Attributes:
        success: True if the compile succeeded.
        returncode: Exit code of the voxc process.
        stdout: Captured stdout (text).
        stderr: Captured stderr (text).
        output_dir: Directory where generated files were written.
        generated_files: List of generated file paths.
    """

    def __init__(self, success, returncode, stdout, stderr,
                 output_dir=None, generated_files=None):
        self.success = bool(success)
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.output_dir = output_dir
        self.generated_files = list(generated_files or [])

    @property
    def is_success(self):
        """Alias for ``success``."""
        return self.success

    def to_dict(self):
        return {
            "success": self.success,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "output_dir": self.output_dir,
            "generated_files": list(self.generated_files),
        }

    def __repr__(self):
        return "CompileResult(success={}, returncode={}, files={})".format(
            self.success, self.returncode, len(self.generated_files)
        )


class RunResult(CompileResult):
    """Result of a compile+run invocation.

    Additional attributes:
        program_output: The actual program output (stdout of the
            compiled Vox program). Same as ``stdout`` for ``voxc run``,
            but kept as a separate field for clarity.
    """

    def __init__(self, success, returncode, stdout, stderr,
                 output_dir=None, generated_files=None, program_output=""):
        super(RunResult, self).__init__(
            success, returncode, stdout, stderr,
            output_dir=output_dir,
            generated_files=generated_files,
        )
        self.program_output = program_output or ""

    def to_dict(self):
        d = super(RunResult, self).to_dict()
        d["program_output"] = self.program_output
        return d

    def __repr__(self):
        return "RunResult(success={}, returncode={}, output_len={})".format(
            self.success, self.returncode, len(self.program_output)
        )


# ---------------------------------------------------------------------------
# AST generation helper
# ---------------------------------------------------------------------------

class ASTGenerator(object):
    """Generates AST JSON from Vox source code.

    Tries the canonical lexer/parser first (``voxc.lexer`` +
    ``voxc.parser``), then falls back to alternative implementations in
    ``voxc.libs.tokenize`` / ``voxc.libs.lark_parser`` if available.

    All imports are wrapped in try/except so the generator degrades
    gracefully when frontend modules are missing.
    """

    def __init__(self):
        self._lexer_cls = None
        self._parser_cls = None
        self._ast_to_json = None
        self._lark_parse = None
        self._init_imports()

    def _init_imports(self):
        # Primary path: voxc.lexer + voxc.parser + voxc.ast_nodes
        try:
            from voxc.lexer import VoxLexer
            from voxc.parser import VoxParser
            from voxc.ast_nodes import ast_to_json
            self._lexer_cls = VoxLexer
            self._parser_cls = VoxParser
            self._ast_to_json = ast_to_json
            return
        except Exception:
            pass

        # Fallback 1: voxc.libs.tokenize (standalone tokenizer)
        try:
            from voxc.libs.tokenize import VoxLexer as _Lexer
            from voxc.parser import VoxParser as _Parser
            from voxc.ast_nodes import ast_to_json as _ast_to_json
            self._lexer_cls = _Lexer
            self._parser_cls = _Parser
            self._ast_to_json = _ast_to_json
            return
        except Exception:
            pass

        # Fallback 2: lark_parser.parse_source (full lark-based path)
        try:
            from voxc.libs.lark_parser import parse_source as _lark_parse
            self._lark_parse = _lark_parse
            return
        except Exception:
            self._lark_parse = None

    @property
    def lexer_class(self):
        """Expose the resolved lexer class (or None) for external use."""
        return self._lexer_cls

    def is_available(self):
        """Return True if any AST generation path is usable."""
        if self._lexer_cls is not None and self._parser_cls is not None:
            return True
        if self._lark_parse is not None:
            return True
        return False

    def generate(self, source, filename="<string>"):
        """Generate an AST dict from Vox source code.

        Args:
            source: Vox source code as a string.
            filename: Source filename (used for span info).

        Returns:
            dict - the AST JSON-serializable representation of the module.

        Raises:
            RuntimeError: if no AST generator is available.
            SyntaxError: if the source cannot be parsed.
        """
        if not self.is_available():
            raise RuntimeError(
                "No AST generator available - voxc.lexer / voxc.parser / "
                "voxc.ast_nodes could not be imported"
            )

        # Lark fast path (produces a dict directly)
        if self._lexer_cls is None and self._lark_parse is not None:
            result = self._lark_parse(source, filename)
            if isinstance(result, dict):
                return result
            if isinstance(result, str):
                return json.loads(result)
            return result

        lexer = self._lexer_cls()
        parser = self._parser_cls()
        tokens = lexer.tokenize(source)
        module = parser.parse(tokens, source_file=filename)
        return self._ast_to_json(module)

    def generate_from_file(self, filepath):
        """Generate AST dict from a .vox file on disk.

        Raises:
            FileNotFoundError: if ``filepath`` does not exist.
        """
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        return self.generate(source, filename=filepath)


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

class VoxcBridge(object):
    """High-level bridge to the Rust ``voxc`` backend.

    Example::

        bridge = VoxcBridge()
        if bridge.is_available():
            result = bridge.compile_and_run("hello.vox")
            print(result.program_output)

    The bridge automatically locates the Rust binary (see
    :meth:`find_voxc_binary`) and can generate AST JSON on the Python
    side before invoking the Rust backend.
    """

    def __init__(self, voxc_exe_path=None):
        self._ast_gen = ASTGenerator()
        if voxc_exe_path:
            # Accept the path as-is only if it points to an existing file.
            self.voxc_path = voxc_exe_path if os.path.isfile(voxc_exe_path) else None
        else:
            self.voxc_path = self.find_voxc_binary()

    # ---- binary discovery ----

    @staticmethod
    def find_voxc_binary():
        """Locate the Rust voxc binary.

        Search order:
            1. ``VOXC_PATH`` environment variable.
            2. ``voxc-rs/target/release/voxc(.exe)`` relative to this file.
            3. ``voxc-rs/target/debug/voxc(.exe)`` relative to this file.
            4. ``voxc`` on ``PATH`` (via :func:`shutil.which`).

        Returns:
            Path string if found, else ``None``.  Never raises.
        """
        # 1. Env var
        env_path = os.environ.get("VOXC_PATH")
        if env_path and os.path.isfile(env_path):
            return env_path

        # 2 & 3. Relative to this file - climb up to 6 parents looking
        # for a sibling ``voxc-rs`` directory.
        here = os.path.dirname(os.path.abspath(__file__))
        parent = here
        for _ in range(6):
            parent = os.path.dirname(parent)
            if not parent:
                break
            rs_dir = os.path.join(parent, "voxc-rs")
            if os.path.isdir(rs_dir):
                for name in _BIN_NAMES:
                    for profile in ("release", "debug"):
                        cand = os.path.join(rs_dir, "target", profile, name)
                        if os.path.isfile(cand):
                            return cand

        # 4. PATH lookup
        for name in _BIN_NAMES:
            found = shutil.which(name)
            if found:
                return found
        return None

    def is_available(self):
        """Return True if the Rust backend binary is available."""
        return bool(self.voxc_path) and os.path.isfile(self.voxc_path)

    # ---- internals ----

    def _ensure_ast_json(self, input_file, ast_json_path):
        """Ensure an AST JSON file exists for ``input_file``.

        If ``ast_json_path`` is provided and the file already exists,
        do nothing.  Otherwise generate the AST on the Python side and
        write it out.

        Returns:
            ``(path, owned)`` tuple.  ``owned`` is True when the caller
            is responsible for unlinking the file (temp file case).
        """
        if ast_json_path and os.path.isfile(ast_json_path):
            return ast_json_path, False

        ast_dict = self._ast_gen.generate_from_file(input_file)
        ast_json_str = json.dumps(ast_dict, indent=2, ensure_ascii=False)

        if ast_json_path:
            # Caller supplied a path but the file does not exist yet -
            # write it there and let the caller own it.
            with open(ast_json_path, "w", encoding="utf-8") as f:
                f.write(ast_json_str)
            return ast_json_path, False

        # No path supplied - use a temp file we own.
        fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="voxc_ast_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(ast_json_str)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        return tmp_path, True

    def _run_voxc(self, args):
        """Invoke the Rust binary with ``args``.

        Returns a :class:`subprocess.CompletedProcess`.  Raises
        :class:`VoxcNotFoundError` if the binary is not available.
        """
        if not self.is_available():
            raise VoxcNotFoundError(
                "voxc binary not found; set VOXC_PATH or build voxc-rs"
            )
        cmd = [self.voxc_path] + list(args)
        # NOTE: ``capture_output=True`` is Python 3.7+, so use the
        # explicit PIPE form for 3.6 compatibility.
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @staticmethod
    def _decode(stream):
        """Decode a subprocess output stream to text."""
        if stream is None:
            return ""
        if isinstance(stream, (bytes, bytearray)):
            return stream.decode("utf-8", errors="replace")
        return stream

    @staticmethod
    def _scan_generated_files(output_dir):
        """Walk ``output_dir`` and return all file paths within it."""
        if not output_dir or not os.path.isdir(output_dir):
            return []
        result = []
        for root, _dirs, files in os.walk(output_dir):
            for name in files:
                result.append(os.path.join(root, name))
        return result

    @staticmethod
    def _default_output_dir(input_file):
        """Compute the default ``__vox_rust_cache__`` dir for an input."""
        vox_dir = os.path.dirname(os.path.abspath(input_file))
        return os.path.join(vox_dir, "__vox_rust_cache__")

    # ---- public API ----

    def compile(self, input_file, ast_json_path=None):
        """Invoke ``voxc compile``.

        If ``ast_json_path`` is None, the AST JSON is generated on the
        Python side and passed to the Rust binary via a temp file.

        Args:
            input_file: Path to the .vox source file.
            ast_json_path: Optional path to a pre-built AST JSON file.

        Returns:
            :class:`CompileResult`.

        Raises:
            VoxcNotFoundError: if the Rust binary is missing.
            VoxcCompileError: if compilation fails.
        """
        tmp_path = None
        try:
            json_path, owned = self._ensure_ast_json(input_file, ast_json_path)
            if owned:
                tmp_path = json_path

            input_abs = os.path.abspath(input_file)
            result = self._run_voxc([
                "compile",
                "--input", input_abs,
                "--ast-json", json_path,
            ])

            output_dir = self._default_output_dir(input_file)
            generated = self._scan_generated_files(output_dir)
            success = result.returncode == 0
            stdout_text = self._decode(result.stdout)
            stderr_text = self._decode(result.stderr)

            cr = CompileResult(
                success=success,
                returncode=result.returncode,
                stdout=stdout_text,
                stderr=stderr_text,
                output_dir=output_dir,
                generated_files=generated,
            )
            if not success:
                raise VoxcCompileError(
                    stderr_text or "voxc compile failed (rc={})".format(
                        result.returncode
                    )
                )
            return cr
        finally:
            if tmp_path and os.path.isfile(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def run(self, input_file, ast_json_path=None):
        """Invoke ``voxc run`` (compile + cargo build + execute).

        Args:
            input_file: Path to the .vox source file.
            ast_json_path: Optional path to a pre-built AST JSON file.

        Returns:
            :class:`RunResult`.

        Raises:
            VoxcNotFoundError: if the Rust binary is missing.
            VoxcRunError: if compile/run fails.
        """
        tmp_path = None
        try:
            json_path, owned = self._ensure_ast_json(input_file, ast_json_path)
            if owned:
                tmp_path = json_path

            input_abs = os.path.abspath(input_file)
            result = self._run_voxc([
                "run",
                "--input", input_abs,
                "--ast-json", json_path,
            ])

            output_dir = self._default_output_dir(input_file)
            generated = self._scan_generated_files(output_dir)
            stdout_text = self._decode(result.stdout)
            stderr_text = self._decode(result.stderr)
            success = result.returncode == 0

            rr = RunResult(
                success=success,
                returncode=result.returncode,
                stdout=stdout_text,
                stderr=stderr_text,
                output_dir=output_dir,
                generated_files=generated,
                program_output=stdout_text,
            )
            if not success:
                raise VoxcRunError(
                    stderr_text or "voxc run failed (rc={})".format(
                        result.returncode
                    )
                )
            return rr
        finally:
            if tmp_path and os.path.isfile(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def dump_ast(self, ast_json_path):
        """Invoke ``voxc ast`` - pretty-print an AST JSON file.

        Args:
            ast_json_path: Path to an AST JSON file.

        Returns:
            dict - the parsed AST.

        Raises:
            FileNotFoundError: if the AST file does not exist.
            VoxcCompileError: if the Rust binary fails.
        """
        if not ast_json_path or not os.path.isfile(ast_json_path):
            raise FileNotFoundError(
                "AST JSON file not found: {}".format(ast_json_path)
            )

        result = self._run_voxc(["ast", "--ast-json", ast_json_path])
        stdout_text = self._decode(result.stdout)
        stderr_text = self._decode(result.stderr)

        if result.returncode != 0:
            raise VoxcCompileError(
                stderr_text or "voxc ast failed (rc={})".format(
                    result.returncode
                )
            )

        try:
            return json.loads(stdout_text)
        except (ValueError, json.JSONDecodeError):
            # Fallback: read the file directly and parse it.
            with open(ast_json_path, "r", encoding="utf-8") as f:
                return json.load(f)

    def compile_and_run(self, input_file):
        """One-shot: generate AST -> compile -> run.

        Equivalent to ``self.run(input_file, ast_json_path=None)``.
        """
        return self.run(input_file, ast_json_path=None)
