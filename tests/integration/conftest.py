"""Fixtures for cross-block integration tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from systemrdl.node import AddrmapNode
from typing_extensions import Unpack

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.exporter import ExporterKwargs


@dataclass
class ExportedDesign:
    """A compiled + exported design and everything needed to inspect it."""

    top: AddrmapNode
    exporter: BusDecoderExporter
    module_text: str
    package_text: str


@pytest.fixture
def export_design(compile_rdl: Callable[..., AddrmapNode], tmp_path: Path) -> Callable[..., ExportedDesign]:
    """Compile inline RDL and export it, returning the generated output.

    Usage::

        design = export_design(rdl_source, top="soc", cpuif_cls=APB4Cpuif)
    """
    counter = 0

    def _export(
        rdl_source: str,
        *,
        top: str,
        **exporter_kwargs: Unpack[ExporterKwargs],
    ) -> ExportedDesign:
        nonlocal counter
        counter += 1
        top_node = compile_rdl(rdl_source, top=top)

        output_dir = tmp_path / f"export_{counter}"
        module_name = exporter_kwargs.get("module_name", top_node.inst_name)
        package_name = exporter_kwargs.get("package_name", f"{module_name}_pkg")

        exporter = BusDecoderExporter()
        exporter.export(top_node, str(output_dir), **exporter_kwargs)

        module_text = (output_dir / f"{module_name}.sv").read_text()
        package_text = (output_dir / f"{package_name}.sv").read_text()

        return ExportedDesign(
            top=top_node,
            exporter=exporter,
            module_text=module_text,
            package_text=package_text,
        )

    return _export
