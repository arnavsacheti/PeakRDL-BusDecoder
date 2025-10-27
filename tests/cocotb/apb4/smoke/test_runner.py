"""Pytest wrapper launching the APB4 cocotb smoke test."""

from pathlib import Path

import pytest

from peakrdl_busdecoder.cpuif.apb4.apb4_cpuif_flat import APB4CpuifFlat

try:  # pragma: no cover - optional dependency shim
    from cocotb.runner import get_runner
except ImportError:  # pragma: no cover
    from cocotb_tools.runner import get_runner

from tests.cocotb_lib.utils import compile_rdl_and_export, get_verilog_sources


@pytest.mark.simulation
@pytest.mark.verilator
def test_apb4_smoke(tmp_path: Path) -> None:
    """Compile the APB4 design and execute the cocotb smoke test."""
    repo_root = Path(__file__).resolve().parents[4]

    module_path, package_path = compile_rdl_and_export(
        str(repo_root / "tests" / "cocotb_lib" / "multiple_reg.rdl"),
        "multi_reg",
        tmp_path,
        cpuif_cls=APB4CpuifFlat,
    )

    sources = get_verilog_sources(
        module_path,
        package_path,
        [repo_root / "hdl-src" / "apb4_intf.sv"],
    )

    runner = get_runner("verilator")
    build_dir = tmp_path / "sim_build"

    runner.build(
        sources=sources,
        hdl_toplevel=module_path.stem,
        build_dir=build_dir,
    )

    runner.test(
        hdl_toplevel=module_path.stem,
        test_module="tests.cocotb.apb4.smoke.test_register_access",
        build_dir=build_dir,
        log_file=str(tmp_path / "sim.log"),
    )
