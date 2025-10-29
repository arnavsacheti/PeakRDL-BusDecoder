"""Pytest fixtures for unit tests."""

from __future__ import annotations

collect_ignore_glob = ["cocotb/*/smoke/test_register_access.py", "cocotb/*/smoke/test_variable_depth.py"]

import os
from collections.abc import Callable
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
from systemrdl import RDLCompileError, RDLCompiler  # type:ignore
from systemrdl.node import AddrmapNode

_SHIM_DIR = Path(__file__).resolve().parents[1] / "tools" / "shims"
os.environ["PATH"] = f"{_SHIM_DIR}{os.pathsep}{os.environ.get('PATH', '')}"


@pytest.fixture
def compile_rdl(tmp_path: Path) -> Callable[..., AddrmapNode]:
    """Compile inline SystemRDL source and return the elaborated root node.

    Parameters
    ----------
    tmp_path:
        Temporary directory provided by pytest.
    """

    def _compile(
        source: str,
        *,
        top: str | None = None,
        defines: dict[str, str] | None = None,
        include_paths: list[Path | str] | None = None,
    ) -> AddrmapNode:
        compiler = RDLCompiler()
        # Use delete=False to keep the file around after closing
        with NamedTemporaryFile("w", suffix=".rdl", dir=tmp_path, delete=False) as tmp_file:
            tmp_file.write(source)
            tmp_file.flush()

            try:
                compiler.compile_file(
                    tmp_file.name,
                    incl_search_paths=(list(map(str, include_paths)) if include_paths else None),
                    defines=defines,
                )
                if top is not None:
                    root = compiler.elaborate(top)  # type:ignore
                    return root.top
                root = compiler.elaborate()  # type:ignore
                return root.top
            except RDLCompileError:
                # Print error messages if available
                if hasattr(compiler, "print_messages"):
                    compiler.print_messages()  # type:ignore
                raise

    return _compile
