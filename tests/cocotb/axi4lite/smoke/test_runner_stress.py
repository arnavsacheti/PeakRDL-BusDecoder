"""Pytest wrapper launching the AXI4-Lite cocotb stress tests (exhaustive coverage)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from peakrdl_busdecoder.cpuif.axi4lite.axi4_lite_cpuif import AXI4LiteCpuifFlat

try:  # pragma: no cover - optional dependency shim
    from cocotb.runner import get_runner
except ImportError:  # pragma: no cover
    from cocotb_tools.runner import get_runner

from tests.cocotb_lib import RDL_CASES
from tests.cocotb_lib.utils import colorize_cocotb_log, get_verilog_sources, prepare_cpuif_case


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize(("rdl_file", "top_name"), RDL_CASES, ids=[case[1] for case in RDL_CASES])
def test_axi4lite_stress(tmp_path: Path, rdl_file: str, top_name: str) -> None:
    """Generate each AXI4-Lite design variant and run the randomized stress sequence."""
    repo_root = Path(__file__).resolve().parents[4]
    rdl_path = repo_root / "tests" / "cocotb_lib" / "rdl" / rdl_file
    build_root = tmp_path / top_name

    module_path, package_path, config = prepare_cpuif_case(
        str(rdl_path),
        top_name,
        build_root,
        cpuif_cls=AXI4LiteCpuifFlat,
        control_signal="AWVALID",
        max_samples_per_master=0,
    )

    sources = get_verilog_sources(
        module_path,
        package_path,
        [repo_root / "hdl-src" / "axi4lite_intf.sv"],
    )

    runner = get_runner("verilator")
    sim_build = build_root / "sim_build"

    build_log_file = build_root / "build.log"
    sim_log_file = build_root / "simulation.log"

    try:
        runner.build(
            sources=sources,
            hdl_toplevel=module_path.stem,
            build_dir=sim_build,
            log_file=str(build_log_file),
        )
    except SystemExit as e:
        if build_log_file.exists():
            logging.error(f"""
=== Build Log ===
{colorize_cocotb_log(build_log_file.read_text())}
=== End Build Log ===
""")
        if e.code != 0:
            raise

    try:
        runner.test(
            hdl_toplevel=module_path.stem,
            test_module="tests.cocotb.axi4lite.smoke.test_stress",
            build_dir=sim_build,
            log_file=str(sim_log_file),
            extra_env={
                "RDL_TEST_CONFIG": json.dumps(config),
                "RDL_TEST_SEED": "0xC0C07B",
            },
        )
    except SystemExit as e:
        if sim_log_file.exists():
            logging.error(f"""
=== Simulation Log ===
{colorize_cocotb_log(sim_log_file.read_text())}
=== End Simulation Log ===
""")
        if e.code != 0:
            raise
