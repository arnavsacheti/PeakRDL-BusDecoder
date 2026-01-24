"""Pytest wrapper launching APB3 cocotb tests for parameterized designs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from peakrdl_busdecoder.cpuif.apb3.apb3_cpuif_flat import APB3CpuifFlat

try:  # pragma: no cover - optional dependency shim
    from cocotb.runner import get_runner
except ImportError:  # pragma: no cover
    from cocotb_tools.runner import get_runner

from tests.cocotb_lib.utils import (
    colorize_cocotb_log,
    get_verilog_sources,
    prepare_cpuif_case,
    write_parameterized_rdl,
)

PARAMETER_SETS = [
    (2, 3),
    (4, 2),
]


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize(("reg_count", "bank_count"), PARAMETER_SETS, ids=["regs2_banks3", "regs4_banks2"])
def test_apb3_parameterized_smoke(tmp_path: Path, reg_count: int, bank_count: int) -> None:
    """Compile APB3 parameterized variants and execute the cocotb smoke test."""
    repo_root = Path(__file__).resolve().parents[4]
    build_root = tmp_path / f"param_r{reg_count}_b{bank_count}"

    rdl_path, top_name = write_parameterized_rdl(build_root, reg_count=reg_count, bank_count=bank_count)

    logging.info("Running APB3 parameterized test: %s (regs=%d, banks=%d)", top_name, reg_count, bank_count)

    module_path, package_path, config = prepare_cpuif_case(
        str(rdl_path),
        top_name,
        build_root,
        cpuif_cls=APB3CpuifFlat,
        control_signal="PSEL",
    )

    sources = get_verilog_sources(
        module_path,
        package_path,
        [repo_root / "hdl-src" / "apb3_intf.sv"],
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
            test_module="tests.cocotb.apb3.smoke.test_register_access",
            build_dir=sim_build,
            log_file=str(sim_log_file),
            extra_env={"RDL_TEST_CONFIG": json.dumps(config)},
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
