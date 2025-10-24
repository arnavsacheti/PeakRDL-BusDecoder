"""Common utilities for cocotb testbenches."""

import os
import tempfile
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from systemrdl import RDLCompiler

from peakrdl_busdecoder.exporter import BusDecoderExporter


def compile_rdl_and_export(
    rdl_source: str, top_name: str, output_dir: str, cpuif_cls: Any, **kwargs: Any
) -> tuple[Path, Path]:
    """
    Compile RDL source and export to SystemVerilog.

    Args:
        rdl_source: SystemRDL source code as a string
        top_name: Name of the top-level addrmap
        output_dir: Directory to write generated files
        cpuif_cls: CPU interface class to use
        **kwargs: Additional arguments to pass to exporter

    Returns:
        Tuple of (module_path, package_path) for generated files
    """
    # Compile RDL source
    compiler = RDLCompiler()

    # Write source to temporary file
    with NamedTemporaryFile("w", suffix=".rdl", dir=output_dir, delete=False) as tmp_file:
        tmp_file.write(rdl_source)
        tmp_file.flush()
        tmp_path = tmp_file.name

    try:
        compiler.compile_file(tmp_path)
        top = compiler.elaborate(top_name)

        # Export to SystemVerilog
        exporter = BusDecoderExporter()
        exporter.export(top, output_dir, cpuif_cls=cpuif_cls, **kwargs)
    finally:
        # Clean up temporary RDL file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # Return paths to generated files
    module_name = kwargs.get("module_name", top_name)
    package_name = kwargs.get("package_name", f"{top_name}_pkg")

    module_path = Path(output_dir) / f"{module_name}.sv"
    package_path = Path(output_dir) / f"{package_name}.sv"

    return module_path, package_path


def get_verilog_sources(module_path: Path, package_path: Path, intf_files: list[Path]) -> list[str]:
    """
    Get list of Verilog source files needed for simulation.

    Args:
        module_path: Path to the generated module file
        package_path: Path to the generated package file
        intf_files: List of paths to interface definition files

    Returns:
        List of source file paths as strings
    """
    sources = []
    # Add interface files first
    sources.extend([str(f) for f in intf_files])
    # Add package file
    sources.append(str(package_path))
    # Add module file
    sources.append(str(module_path))
    return sources
