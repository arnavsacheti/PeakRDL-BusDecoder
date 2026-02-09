"""Pytest wrapper launching the APB4 cocotb smoke tests with SV interface CPUIF."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from peakrdl_busdecoder.cpuif.apb4.apb4_cpuif import APB4Cpuif

try:  # pragma: no cover - optional dependency shim
    from cocotb.runner import get_runner
except ImportError:  # pragma: no cover
    from cocotb_tools.runner import get_runner

from tests.cocotb_lib import RDL_CASES
from tests.cocotb_lib.utils import colorize_cocotb_log, get_verilog_sources, prepare_cpuif_case
from tests.cocotb_lib.wrapper_gen import generate_verilator_intf_wrapper


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize(("rdl_file", "top_name"), RDL_CASES, ids=[case[1] for case in RDL_CASES])
def test_apb4_intf_smoke(tmp_path: Path, rdl_file: str, top_name: str) -> None:
    """Compile each APB4 interface design variant and execute the cocotb smoke test."""
    repo_root = Path(__file__).resolve().parents[4]
    rdl_path = repo_root / "tests" / "cocotb_lib" / "rdl" / rdl_file
    build_root = tmp_path / top_name

    module_path, package_path, config = prepare_cpuif_case(
        str(rdl_path),
        top_name,
        build_root,
        cpuif_cls=APB4Cpuif,
        control_signal="PSEL",
    )

    # Generate Verilator wrapper (Verilator can't have SV interface ports at top level)
    children = [
        {
            "inst_name": m["inst_name"],
            "child_size": m["child_size"],
            "is_array": m["is_array"],
            "dimensions": m["dimensions"],
        }
        for m in config["masters"]
    ]
    wrapper_path = generate_verilator_intf_wrapper(
        module_name=module_path.stem,
        protocol="apb4",
        children=children,
        global_addr_width=config["address_width"],
        global_data_width=config["data_width"],
        output_dir=build_root,
    )

    # Override cpuif_style since wrapper exposes flat ports
    config["cpuif_style"] = "flat"

    sources = get_verilog_sources(
        module_path,
        package_path,
        [repo_root / "hdl-src" / "apb4_intf.sv"],
    )
    sources.append(str(wrapper_path))

    runner = get_runner("verilator")
    sim_build = build_root / "sim_build"

    build_log_file = build_root / "build.log"
    sim_log_file = build_root / "simulation.log"

    try:
        runner.build(
            sources=sources,
            hdl_toplevel=wrapper_path.stem,
            build_dir=sim_build,
            log_file=str(build_log_file),
        )
    except SystemExit as e:
        # Print build log on failure for easier debugging
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
            hdl_toplevel=wrapper_path.stem,
            test_module="tests.cocotb.apb4.smoke.test_register_access",
            build_dir=sim_build,
            log_file=str(sim_log_file),
            extra_env={"RDL_TEST_CONFIG": json.dumps(config)},
        )
    except SystemExit as e:
        # Print simulation log on failure for easier debugging
        if sim_log_file.exists():
            logging.error(f"""
=== Simulation Log ===
{colorize_cocotb_log(sim_log_file.read_text())}
=== End Simulation Log ===
""")
        if e.code != 0:
            raise
