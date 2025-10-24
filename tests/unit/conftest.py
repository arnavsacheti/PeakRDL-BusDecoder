"""Pytest fixtures for unit tests."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable, Mapping, Optional

import pytest
from systemrdl import RDLCompileError, RDLCompiler


@pytest.fixture
def compile_rdl(tmp_path: Path):
    """Compile inline SystemRDL source and return the elaborated root node.

    Parameters
    ----------
    tmp_path:
        Temporary directory provided by pytest.
    """

    def _compile(
        source: str,
        *,
        top: Optional[str] = None,
        defines: Optional[Mapping[str, object]] = None,
        include_paths: Optional[Iterable[Path | str]] = None,
    ):
        compiler = RDLCompiler()

        for key, value in (defines or {}).items():
            compiler.define(key, value)

        for include_path in include_paths or ():
            compiler.add_include_path(str(include_path))

        with NamedTemporaryFile("w", suffix=".rdl", dir=tmp_path, delete=False) as tmp_file:
            tmp_file.write(source)
            tmp_file.flush()

            try:
                compiler.compile_file(tmp_file.name)
                if top is not None:
                    root = compiler.elaborate(top)
                    return root.top
                root = compiler.elaborate()
                return root.top
            except RDLCompileError:
                # Print error messages if available
                if hasattr(compiler, "print_messages"):
                    compiler.print_messages()
                raise

    return _compile
