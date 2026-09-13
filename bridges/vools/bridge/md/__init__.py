"""vools.bridge.md — Markdown 即代码桥接子包"""

from .parser import (
    parse_md, ParsedMD, FileDirectives, CodeBlock,
)
from .directives import (
    FILE_DIRECTIVE_KEYS, BLOCK_DIRECTIVE_KEYS,
    parse_block_directives, validate_directives,
)
from .config import load_config, load_config_from_block
from .deps import parse_toml, check_deps, DepsReport
from .manifest import (
    write_manifest, read_manifest,
    minimal_yaml_parse, minimal_yaml_dump,
)
from .artifacts import (
    ensure_build_dir, compute_artifact_hash,
    is_artifact_stale, clean_build, register_artifact,
)
from .runner import (
    run_md, run_block,
    run_multiple_md, run_library,
    resolve_imports,
    scan_library, build_library_manifest, load_library_manifest,
)
from .errors import (
    MDBridgeError, MDParseError, MDDirectiveError,
    MDConfigError, MDDepsError, MDManifestError,
    MDExecutionError, MDImportError, MDArtifactError,
    MDLibraryError, MDSandboxError,
)
from .logger import get_logger, set_level, add_file_handler, remove_file_handler

__version__ = "0.5.0"

__all__ = [
    # parser
    'parse_md', 'ParsedMD', 'FileDirectives', 'CodeBlock',
    # directives
    'FILE_DIRECTIVE_KEYS', 'BLOCK_DIRECTIVE_KEYS',
    'parse_block_directives', 'validate_directives',
    # config
    'load_config', 'load_config_from_block',
    # deps
    'parse_toml', 'check_deps', 'DepsReport',
    # manifest
    'write_manifest', 'read_manifest',
    'minimal_yaml_parse', 'minimal_yaml_dump',
    # artifacts
    'ensure_build_dir', 'compute_artifact_hash',
    'is_artifact_stale', 'clean_build', 'register_artifact',
    # runner
    'run_md', 'run_block',
    'run_multiple_md', 'run_library',
    'resolve_imports',
    'scan_library', 'build_library_manifest', 'load_library_manifest',
    # errors
    'MDBridgeError', 'MDParseError', 'MDDirectiveError',
    'MDConfigError', 'MDDepsError', 'MDManifestError',
    'MDExecutionError', 'MDImportError', 'MDArtifactError',
    'MDLibraryError', 'MDSandboxError',
    # logger
    'get_logger', 'set_level', 'add_file_handler', 'remove_file_handler',
]
