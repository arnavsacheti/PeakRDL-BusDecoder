"""Pytest wrapper launching the APB3 cocotb smoke test for variable depth."""

from pathlib import Path

import pytest

from peakrdl_busdecoder.cpuif.apb3.apb3_cpuif_flat import APB3CpuifFlat

try:  # pragma: no cover - optional dependency shim
    from cocotb.runner import get_runner
except ImportError:  # pragma: no cover
    from cocotb_tools.runner import get_runner

from tests.cocotb_lib.utils import compile_rdl_and_export, get_verilog_sources


@pytest.mark.simulation
@pytest.mark.verilator
def test_apb3_variable_depth_1(tmp_path: Path) -> None:
    """Test APB3 design with max_decode_depth=1."""
    repo_root = Path(__file__).resolve().parents[4]

    module_path, package_path = compile_rdl_and_export(
        str(repo_root / "tests" / "cocotb_lib" / "variable_depth.rdl"),
        "variable_depth",
        tmp_path,
        cpuif_cls=APB3CpuifFlat,
        max_decode_depth=1,
    )

    sources = get_verilog_sources(
        module_path,
        package_path,
        [repo_root / "hdl-src" / "apb3_intf.sv"],
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
        test_module="tests.cocotb.apb3.smoke.test_variable_depth",
        build_dir=build_dir,
        log_file=str(tmp_path / "sim_depth1.log"),
        testcase="test_depth_1",
    )


@pytest.mark.simulation
@pytest.mark.verilator
def test_apb3_variable_depth_2(tmp_path: Path) -> None:
    """Test APB3 design with max_decode_depth=2."""
    repo_root = Path(__file__).resolve().parents[4]

    module_path, package_path = compile_rdl_and_export(
        str(repo_root / "tests" / "cocotb_lib" / "variable_depth.rdl"),
        "variable_depth",
        tmp_path,
        cpuif_cls=APB3CpuifFlat,
        max_decode_depth=2,
    )

    sources = get_verilog_sources(
        module_path,
        package_path,
        [repo_root / "hdl-src" / "apb3_intf.sv"],
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
        test_module="tests.cocotb.apb3.smoke.test_variable_depth",
        build_dir=build_dir,
        log_file=str(tmp_path / "sim_depth2.log"),
        testcase="test_depth_2",
    )


@pytest.mark.simulation
@pytest.mark.verilator
def test_apb3_variable_depth_0(tmp_path: Path) -> None:
    """Test APB3 design with max_decode_depth=0 (all levels)."""
    repo_root = Path(__file__).resolve().parents[4]

    module_path, package_path = compile_rdl_and_export(
        str(repo_root / "tests" / "cocotb_lib" / "variable_depth.rdl"),
        "variable_depth",
        tmp_path,
        cpuif_cls=APB3CpuifFlat,
        max_decode_depth=0,
    )

    sources = get_verilog_sources(
        module_path,
        package_path,
        [repo_root / "hdl-src" / "apb3_intf.sv"],
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
        test_module="tests.cocotb.apb3.smoke.test_variable_depth",
        build_dir=build_dir,
        log_file=str(tmp_path / "sim_depth0.log"),
        testcase="test_depth_0",
    )
