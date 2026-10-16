"""probe/runtimes.py — 运行时探测。

复用 vools.actus.runtimes.RuntimeRegistry，不重复实现。
"""

from .base import Prober, ProbeItem


class RuntimesProber(Prober):
    """运行时探测器。"""

    def probe(self) -> list:
        results = []
        try:
            from ..runtimes import RuntimeRegistry
            registry = RuntimeRegistry()
            for name, runtime in registry._runtimes.items():
                available = runtime.is_available()
                version = ""
                path = None

                if available:
                    try:
                        import shutil
                        cmd_map = {
                            "python": ["python", "python3"],
                            "shell": ["bash", "sh"],
                            "node": ["node", "nodejs"],
                            "go": ["go"],
                            "rust": ["rustc", "cargo"],
                            "ruby": ["ruby"],
                            "php": ["php"],
                        }
                        cmds = cmd_map.get(runtime.name, [runtime.name])
                        for cmd in cmds:
                            path = shutil.which(cmd)
                            if path:
                                break

                        if path:
                            try:
                                import subprocess
                                if runtime.name == "go":
                                    r = subprocess.run([path, "version"], capture_output=True, text=True, errors='replace', timeout=5)
                                    version = r.stdout.strip().split("\n")[0]
                                elif runtime.name == "rust":
                                    r = subprocess.run([path, "--version"], capture_output=True, text=True, errors='replace', timeout=5)
                                    version = r.stdout.strip().split("\n")[0]
                                else:
                                    r = subprocess.run([path, "--version"], capture_output=True, text=True, errors='replace', timeout=5)
                                    version = (r.stdout or r.stderr or "").strip().split("\n")[0]
                            except Exception:
                                pass
                    except Exception:
                        pass

                results.append(ProbeItem(
                    name=runtime.name,
                    category="runtimes",
                    available=available,
                    path=path,
                    version=version,
                    extra={"aliases": runtime.aliases},
                ))
        except Exception as e:
            results.append(ProbeItem(
                name="runtimes",
                category="runtimes",
                available=False,
                error=str(e),
            ))

        return results