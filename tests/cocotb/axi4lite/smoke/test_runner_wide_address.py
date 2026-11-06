"""Run generated SV-interface AXI4-Lite decoders with wider upstream addresses."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from peakrdl_busdecoder.cpuif.axi4lite.axi4_lite_cpuif import AXI4LiteCpuif

try:  # pragma: no cover - optional dependency shim
    from cocotb.runner import get_runner
except ImportError:  # pragma: no cover
    from cocotb_tools.runner import get_runner

from tests.cocotb_lib.utils import colorize_cocotb_log, get_verilog_sources, prepare_cpuif_case
from tests.cocotb_lib.wrapper_gen import generate_verilator_intf_wrapper


@pytest.mark.simulation
@pytest.mark.verilator
@pytest.mark.parametrize("outstanding_depth", [1, 3], ids=["depth1", "depth3"])
def test_axi4lite_intf_wide_address(tmp_path: Path, outstanding_depth: int) -> None:
    """High upstream address bits must not alias the compact simple_test map."""
    repo_root = Path(__file__).resolve().parents[4]
    build_root = tmp_path / "simple_test"
    module_path, package_path, config = prepare_cpuif_case(
        str(repo_root / "tests" / "cocotb_lib" / "rdl" / "simple.rdl"),
        "simple_test",
        build_root,
        cpuif_cls=AXI4LiteCpuif,
        control_signal="AWVALID",
        exporter_kwargs={"axi4lite_max_outstanding": outstanding_depth},
    )

    # This generator uses global_addr_width only for the upstream flat ports
    # and interface. Downstream address widths still come from child_size, so
    # the actual generated decoder keeps its compact exporter-selected width.
    upstream_width = max(40, config["address_width"] + 3)
    children = [
        {
            "inst_name": master["inst_name"],
            "child_size": master["child_size"],
            "is_array": master["is_array"],
            "dimensions": master["dimensions"],
        }
        for master in config["masters"]
    ]
    wrapper_path = generate_verilator_intf_wrapper(
        module_name=module_path.stem,
        protocol="axi4lite",
        children=children,
        global_addr_width=upstream_width,
        global_data_width=config["data_width"],
        output_dir=build_root,
    )
    config.update(
        cpuif_style="flat",
        axi4lite_max_outstanding=outstanding_depth,
        upstream_address_width=upstream_width,
        high_address_bits=[config["address_width"], upstream_width - 1],
        wide_address_transaction=config["transactions"][0],
    )
    sources = get_verilog_sources(
        module_path,
        package_path,
        [repo_root / "hdl-src" / "axi4lite_intf.sv"],
    )
    sources.append(str(wrapper_path))
    runner = get_runner("verilator")
    sim_build = build_root / "sim_build"
    build_log = build_root / "build.log"
    sim_log = build_root / "simulation.log"

    try:
        runner.build(
            sources=sources,
            hdl_toplevel=wrapper_path.stem,
            build_dir=sim_build,
            log_file=str(build_log),
        )
    except SystemExit as error:
        if build_log.exists():
            logging.error("Build log:\n%s", colorize_cocotb_log(build_log.read_text()))
        if error.code != 0:
            raise

    try:
        runner.test(
            hdl_toplevel=wrapper_path.stem,
            test_module="tests.cocotb.axi4lite.smoke.test_wide_address",
            build_dir=sim_build,
            log_file=str(sim_log),
            extra_env={"RDL_TEST_CONFIG": json.dumps(config)},
        )
    except SystemExit as error:
        if sim_log.exists():
            logging.error("Simulation log:\n%s", colorize_cocotb_log(sim_log.read_text()))
        if error.code != 0:
            raise
