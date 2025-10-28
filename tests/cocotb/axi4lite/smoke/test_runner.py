"""Pytest wrapper launching the AXI4-Lite cocotb smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from peakrdl_busdecoder.cpuif.axi4lite.axi4_lite_cpuif_flat import AXI4LiteCpuifFlat

try:  # pragma: no cover - optional dependency shim
    from cocotb.runner import get_runner
except ImportError:  # pragma: no cover
    from cocotb_tools.runner import get_runner

from tests.cocotb_lib import RDL_CASES
from tests.cocotb_lib.utils import get_verilog_sources, prepare_cpuif_case


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize(("rdl_file", "top_name"), RDL_CASES, ids=[case[1] for case in RDL_CASES])
def test_axi4lite_smoke(tmp_path: Path, rdl_file: str, top_name: str) -> None:
    """Compile each AXI4-Lite design variant and execute the cocotb smoke test."""
    repo_root = Path(__file__).resolve().parents[4]
    rdl_path = repo_root / "tests" / "cocotb_lib" / rdl_file
    build_root = tmp_path / top_name

    module_path, package_path, config = prepare_cpuif_case(
        str(rdl_path),
        top_name,
        build_root,
        cpuif_cls=AXI4LiteCpuifFlat,
        control_signal="AWVALID",
    )

    sources = get_verilog_sources(
        module_path,
        package_path,
        [repo_root / "hdl-src" / "axi4lite_intf.sv"],
    )

    runner = get_runner("verilator")
    sim_build = build_root / "sim_build"

    runner.build(
        sources=sources,
        hdl_toplevel=module_path.stem,
        build_dir=sim_build,
    )

    runner.test(
        hdl_toplevel=module_path.stem,
        test_module="tests.cocotb.axi4lite.smoke.test_register_access",
        build_dir=sim_build,
        log_file=str(build_root / "simulation.log"),
        extra_env={"RDL_TEST_CONFIG": json.dumps(config)},
    )
