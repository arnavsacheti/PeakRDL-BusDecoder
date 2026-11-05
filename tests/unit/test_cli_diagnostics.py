"""Exercise diagnostics through the real compiler, exporter, and PeakRDL CLI."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from systemrdl import RDLCompileError
from systemrdl.node import AddrmapNode

from peakrdl_busdecoder import BusDecoderExporter
from peakrdl_busdecoder.cpuif.apb import APB4CpuifFlat

_REPO = Path(__file__).resolve().parents[2]
_SOURCE = _REPO / "src"
_INTERNAL_RDL = """
addrmap top {
    reg word_t {
        field { sw = rw; hw = r; } data[31:0];
    };
    word_t first @ 0x0;
    word_t last @ 0x40;
};
"""
_EXTERNAL_RDL = """
addrmap hidden_map {
    reg hidden_word_t {
        regwidth = 128;
        accesswidth = 128;
        field { sw = rw; hw = r; } data[127:0];
    };
    hidden_word_t hidden @ 0x0;
    hidden_word_t last @ 0x3f0;
};
mem external_memory {
    mementries = 128;
    memwidth = 64;
};
addrmap top {
    external hidden_map remote @ 0x0;
    external external_memory memory @ 0x400;
};
"""
_FLAT_CPUIFS = ("apb3-flat", "apb4-flat", "axi4-lite-flat", "ahb-lite-flat")
_RESET_ADAPTERS = (
    ("apb3", "APB3Cpuif", "s_apb.PRESETn"),
    ("apb3-flat", "APB3CpuifFlat", "s_apb_PRESETn"),
    ("apb4", "APB4Cpuif", "s_apb.PRESETn"),
    ("apb4-flat", "APB4CpuifFlat", "s_apb_PRESETn"),
    ("axi4-lite", "AXI4LiteCpuif", "s_axil.ARESETn"),
    ("axi4-lite-flat", "AXI4LiteCpuifFlat", "s_axil_ARESETn"),
    ("ahb-lite", "AHBLiteCpuif", "s_ahb.HRESETn"),
    ("ahb-lite-flat", "AHBLiteCpuifFlat", "s_ahb_HRESETn"),
)


def _run_cli(
    tmp_path: Path,
    *arguments: str,
    source: str = _INTERNAL_RDL,
    output: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    source_path = tmp_path / "diagnostic.rdl"
    source_path.write_text(source)
    env = os.environ.copy()
    # An inherited PYTHONPATH can otherwise load a sibling worktree's exporter.
    env["PYTHONPATH"] = str(_SOURCE)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "peakrdl",
            "busdecoder",
            str(source_path),
            "-o",
            str(output if output is not None else tmp_path / "out"),
            *arguments,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _assert_failure(
    result: subprocess.CompletedProcess[str],
    *phrases: str,
    status: int = 1,
    debug: bool = False,
) -> str:
    message = result.stdout + result.stderr
    assert result.returncode == status, message
    for phrase in phrases:
        assert phrase.lower() in message.lower(), message
    assert ("Traceback (most recent call last):" in message) is debug, message
    if debug:
        assert "RDLCompileError" in message, message
        assert "in do_export" in message, message
        assert "in export" in message, message
        assert re.search(r'File "[^\"]+\.py", line \d+, in ', message), message
    return message


def _assert_warning(result: subprocess.CompletedProcess[str], *phrases: str) -> str:
    message = result.stdout + result.stderr
    assert result.returncode == 0, message
    assert "warning:" in message.lower(), message
    for phrase in phrases:
        assert phrase.lower() in message.lower(), message
    assert "fatal:" not in message.lower(), message
    assert "error:" not in message.lower(), message
    assert "Traceback (most recent call last):" not in message, message
    return message


def _assert_quiet_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "", result.stdout
    assert result.stderr == "", result.stderr


def _assert_flat_data_width(output: Path, cpuif: str, targets: tuple[str, ...], width: int) -> None:
    module = (output / "top.sv").read_text()
    package = (output / "top_pkg.sv").read_text()
    assert re.search(rf"\bTOP_DATA_WIDTH\s*=\s*{width}\s*;", package), package
    if cpuif.startswith("apb"):
        protocol, payloads, strobe = "apb", ("PWDATA", "PRDATA"), "PSTRB"
    elif cpuif.startswith("axi"):
        protocol, payloads, strobe = "axil", ("WDATA", "RDATA"), "WSTRB"
    else:
        protocol, payloads, strobe = "ahb", ("HWDATA", "HRDATA"), None
    prefixes = (f"s_{protocol}_", *(f"m_{protocol}_{target}_" for target in targets))
    for prefix in prefixes:
        for payload in payloads:
            assert re.search(
                rf"\b(?:input|output)\s+logic\s+\[{width - 1}:0\]\s+{prefix}{payload}\b",
                module,
            ), module
        if strobe is not None and cpuif != "apb3-flat":
            assert re.search(
                rf"\b(?:input|output)\s+logic\s+\[{width // 8 - 1}:0\]\s+{prefix}{strobe}\b",
                module,
            ), module


def _ahb_internal_rdl(width: int = 32) -> str:
    return f"""
    regfile page {{
        reg word_t {{
            regwidth = {width};
            accesswidth = {width};
            field {{ sw = rw; hw = r; }} data[{width - 1}:0];
        }};
        word_t first @ 0x0;
        word_t last @ {1024 - width // 8};
    }};
    addrmap top {{
        page first @ 0x0;
        page last @ 0x400;
    }};
    """


def _reset_rdl(*, name: str = "rst", properties: str = "activehigh;", scope: str = "top") -> str:
    reset = f"signal {{ cpuif_reset; {properties} }} {name};"
    register = """
    regfile {
        reg word_t { field { sw = rw; hw = r; } data[31:0]; };
        word_t first @ 0x0;
        word_t last @ 0x3fc;
    } target @ 0x0;
    """
    if scope == "root":
        return f"{reset}\naddrmap top {{ {register} }};"
    if scope == "nested":
        return f"addrmap top {{ regfile {{ {reset} {register} }} block @ 0x0; }};"
    return f"addrmap top {{ {reset} {register} }};"


@pytest.mark.parametrize("debug", [False, True], ids=["normal", "debug"])
@pytest.mark.parametrize("width", [0, -1, 6], ids=["zero", "negative", "below-minimum"])
def test_numeric_address_width_reports_value_minimum_and_remedy(
    tmp_path: Path, width: int, debug: bool
) -> None:
    arguments = ["--addr-width", str(width)]
    if debug:
        arguments.append("--debug")
    result = _run_cli(tmp_path, *arguments)
    # The last word ends at 0x44, so the minimum enclosing address width is 7.
    _assert_failure(
        result,
        "fatal:",
        f"--addr-width {width}",
        "address width",
        "at least 7 bits",
        "Choose --addr-width 7",
        "omit",
        "infer",
        debug=debug,
    )


@pytest.mark.parametrize("option", ["--addr-width", "--data-width", "--axi4lite-max-outstanding"])
def test_noninteger_width_and_queue_options_remain_argparse_errors(tmp_path: Path, option: str) -> None:
    result = _run_cli(tmp_path, option, "not-an-integer")
    _assert_failure(result, option, "not-an-integer", "invalid int value", status=2)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("width", [7, 12], ids=["minimum", "larger"])
def test_valid_explicit_address_width_exports_quietly(tmp_path: Path, width: int) -> None:
    result = _run_cli(tmp_path, "--cpuif", "apb4-flat", "--addr-width", str(width))
    _assert_quiet_success(result)
    module = (tmp_path / "out" / "top.sv").read_text()
    assert re.search(rf"input\s+logic\s+\[{width - 1}:0\]\s+s_apb_PADDR\b", module), module


@pytest.mark.parametrize("debug", [False, True], ids=["normal", "debug"])
@pytest.mark.parametrize(
    "conflict",
    ["output-file", "parent-file", "package-directory", "module-directory"],
)
def test_output_path_conflicts_are_fatal_actionable_export_errors(
    tmp_path: Path, conflict: str, debug: bool
) -> None:
    output = tmp_path / "out"
    if conflict == "output-file":
        output.write_text("Do not overwrite this file.\n")
        offending_path = output
    elif conflict == "parent-file":
        parent = tmp_path / "blocked"
        parent.write_text("This is not a directory.\n")
        output = parent / "generated"
        offending_path = output
    else:
        output.mkdir()
        filename = "top_pkg.sv" if conflict == "package-directory" else "top.sv"
        offending_path = output / filename
        offending_path.mkdir()
    arguments = ["--debug"] if debug else []
    result = _run_cli(tmp_path, *arguments, output=output)
    _assert_failure(
        result,
        "fatal:",
        "Cannot write output path",
        str(offending_path),
        "-o",
        "choose",
        "directory",
        debug=debug,
    )
    if conflict == "output-file":
        assert output.read_text() == "Do not overwrite this file.\n"
    elif conflict == "parent-file":
        assert parent.read_text() == "This is not a directory.\n"


@pytest.mark.parametrize("existing_output", [False, True], ids=["mkdir-denied", "write-denied"])
def test_unwritable_output_directory_reports_path_and_permissions(
    tmp_path: Path, existing_output: bool
) -> None:
    if os.name != "posix":
        pytest.skip("This regression requires POSIX directory permission enforcement.")
    if os.geteuid() == 0:
        pytest.skip("Root bypasses chmod write restrictions; run this CLI regression as an unprivileged user.")
    readonly = tmp_path / "readonly"
    readonly.mkdir()
    output = readonly / "generated"
    if existing_output:
        output.mkdir()
        output.chmod(0o500)
    readonly.chmod(0o500)
    try:
        result = _run_cli(tmp_path, output=output)
    finally:
        readonly.chmod(0o700)
        if existing_output:
            output.chmod(0o700)
    offending_path = output / "top_pkg.sv" if existing_output else output
    _assert_failure(
        result,
        "fatal:",
        "Cannot write output path",
        str(offending_path),
        "-o",
        "writable",
        "directory",
        "permissions",
    )


def test_exporter_wraps_real_filesystem_failure_as_compile_error(
    tmp_path: Path,
    compile_rdl: Callable[..., AddrmapNode],
    capfd: pytest.CaptureFixture[str],
) -> None:
    top = compile_rdl(_INTERNAL_RDL, top="top")
    output = tmp_path / "blocked-output"
    output.write_text("Keep this file.\n")
    with pytest.raises(RDLCompileError):
        BusDecoderExporter().export(top, str(output), cpuif_cls=APB4CpuifFlat)
    captured = capfd.readouterr()
    message = captured.out + captured.err
    for phrase in ("fatal:", "Cannot write output path", str(output), "-o", "directory"):
        assert phrase.lower() in message.lower(), message
    assert output.read_text() == "Keep this file.\n"


@pytest.mark.parametrize(
    "option,choices",
    [
        ("--apb-buffer", ("none", "in", "out", "both")),
        ("--clk-src", ("cpuif", "design")),
    ],
)
def test_invalid_enum_options_use_cli_names_and_choices(
    tmp_path: Path, option: str, choices: tuple[str, ...]
) -> None:
    result = _run_cli(tmp_path, option, "unsupported")
    _assert_failure(result, option, "unsupported", "invalid choice", *choices, status=2)


@pytest.mark.parametrize(
    "option,kwargs",
    [
        ("--clk-src", {"clk_src": "unsupported"}),
        ("--apb-buffer", {"apb_buffer": "unsupported"}),
    ],
)
def test_exporter_invalid_enums_also_use_cli_option_names(
    tmp_path: Path,
    compile_rdl: Callable[..., AddrmapNode],
    capfd: pytest.CaptureFixture[str],
    option: str,
    kwargs: dict[str, str],
) -> None:
    # Argparse rejects these values first, so invoke the real public exporter
    # to cover its separate diagnostics without substituting a CLI or an OS.
    top = compile_rdl(_INTERNAL_RDL, top="top")
    with pytest.raises(RDLCompileError):
        BusDecoderExporter().export(top, str(tmp_path / "out"), cpuif_cls=APB4CpuifFlat, **kwargs)
    captured = capfd.readouterr()
    message = captured.out + captured.err
    for phrase in ("fatal:", option, "unsupported"):
        assert phrase.lower() in message.lower(), message


@pytest.mark.parametrize("mode", ["in", "out", "both"])
def test_apb_buffer_clock_conflict_names_both_cli_options(tmp_path: Path, mode: str) -> None:
    result = _run_cli(tmp_path, "--apb-buffer", mode, "--clk-src", "cpuif")
    _assert_failure(result, "fatal:", "--apb-buffer", "--clk-src", "design")


@pytest.mark.parametrize("cpuif", ["axi4-lite", "axi4-lite-flat", "ahb-lite", "ahb-lite-flat"])
def test_apb_buffer_requires_an_apb_adapter(tmp_path: Path, cpuif: str) -> None:
    result = _run_cli(tmp_path, "--cpuif", cpuif, "--apb-buffer", "both")
    _assert_failure(result, "fatal:", "--apb-buffer", "both", "choose an APB --cpuif", "--apb-buffer none")


@pytest.mark.parametrize("depth", [0, -2])
def test_invalid_axi_queue_depth_uses_cli_name_value_and_minimum(tmp_path: Path, depth: int) -> None:
    result = _run_cli(
        tmp_path, "--cpuif", "axi4-lite-flat", "--axi4lite-max-outstanding", str(depth)
    )
    _assert_failure(
        result,
        "fatal:",
        "--axi4lite-max-outstanding",
        f"got {depth}",
        "greater than or equal to 1",
        "choose a positive queue depth",
    )


@pytest.mark.parametrize("cpuif", _FLAT_CPUIFS)
def test_inferred_internal_width_exports_silently(tmp_path: Path, cpuif: str) -> None:
    source = _ahb_internal_rdl() if cpuif.startswith("ahb") else _INTERNAL_RDL
    result = _run_cli(tmp_path, "--cpuif", cpuif, source=source)
    _assert_quiet_success(result)
    _assert_flat_data_width(tmp_path / "out", cpuif, ("first", "last"), 32)


@pytest.mark.parametrize("cpuif", _FLAT_CPUIFS)
def test_external_only_fallback_explains_inference_and_all_port_widths(tmp_path: Path, cpuif: str) -> None:
    result = _run_cli(tmp_path, "--cpuif", cpuif, source=_EXTERNAL_RDL)
    _assert_warning(
        result,
        "Unable to infer",
        "32 bits",
        "no internal register accesswidth",
        "--data-width",
        "all decoder data ports",
    )
    _assert_flat_data_width(tmp_path / "out", cpuif, ("remote", "memory"), 32)


@pytest.mark.parametrize(
    "cpuif,width",
    [
        (cpuif, width)
        for cpuif in _FLAT_CPUIFS
        for width in (8, 16, 32, 64)
        if not (cpuif.startswith("ahb") and width < 32)
    ],
)
def test_explicit_external_width_is_silent_and_controls_every_data_port(
    tmp_path: Path, cpuif: str, width: int
) -> None:
    result = _run_cli(tmp_path, "--cpuif", cpuif, "--data-width", str(width), source=_EXTERNAL_RDL)
    _assert_quiet_success(result)
    _assert_flat_data_width(tmp_path / "out", cpuif, ("remote", "memory"), width)


@pytest.mark.parametrize("width", [0, -8, 4, 12, 24])
def test_invalid_data_width_reports_value_shape_minimum_and_remedy(tmp_path: Path, width: int) -> None:
    result = _run_cli(tmp_path, "--data-width", str(width), source=_EXTERNAL_RDL)
    _assert_failure(
        result, "fatal:", "--data-width", f"got {width}", "power of two", "at least 8", "choose"
    )


@pytest.mark.parametrize("width", [8, 16, 32])
def test_explicit_width_cannot_shrink_inferred_internal_accesswidth(tmp_path: Path, width: int) -> None:
    source = """
    addrmap top {
        reg {
            regwidth = 64;
            accesswidth = 64;
            field { sw = rw; hw = r; } data[63:0];
        } wide @ 0x0;
    };
    """
    result = _run_cli(tmp_path, "--data-width", str(width), source=source)
    _assert_failure(
        result,
        "fatal:",
        f"--data-width {width}",
        "inferred internal register accesswidth",
        "64 bits",
        "choose --data-width 64",
    )


@pytest.mark.parametrize("width", [32, 64])
def test_valid_internal_width_override_exports_silently(tmp_path: Path, width: int) -> None:
    result = _run_cli(tmp_path, "--cpuif", "axi4-lite-flat", "--data-width", str(width))
    _assert_quiet_success(result)
    _assert_flat_data_width(tmp_path / "out", "axi4-lite-flat", ("first", "last"), width)


def test_exporter_accepts_explicit_data_width_keyword(
    tmp_path: Path,
    compile_rdl: Callable[..., AddrmapNode],
    capfd: pytest.CaptureFixture[str],
) -> None:
    top = compile_rdl(_EXTERNAL_RDL, top="top")
    output = tmp_path / "out"
    BusDecoderExporter().export(top, str(output), cpuif_cls=APB4CpuifFlat, data_width=64)
    captured = capfd.readouterr()
    assert captured.out == "", captured.out
    assert captured.err == "", captured.err
    _assert_flat_data_width(output, "apb4-flat", ("remote", "memory"), 64)


@pytest.mark.parametrize("cpuif,adapter,bus_reset", _RESET_ADAPTERS)
@pytest.mark.parametrize("clk_src", ["design", "cpuif"])
def test_declared_reset_reports_actual_fixed_port_for_every_builtin_adapter(
    tmp_path: Path, cpuif: str, adapter: str, bus_reset: str, clk_src: str
) -> None:
    source = _reset_rdl(name="declared_reset", properties="activelow; async;")
    result = _run_cli(tmp_path, "--cpuif", cpuif, "--clk-src", clk_src, source=source)
    uses_bus_reset = clk_src == "cpuif" or cpuif.startswith("ahb")
    actual_port = bus_reset if uses_bus_reset else "rst"
    polarity = "active-low" if uses_bus_reset else "active-high"
    _assert_warning(
        result,
        "cpuif_reset",
        "top.declared_reset",
        f"built-in {adapter} adapter",
        f"reset port '{actual_port}'",
        polarity,
        "asynchronous",
        "connect that port",
        "required polarity",
    )
    module = (tmp_path / "out" / "top.sv").read_text()
    assert "declared_reset" not in module, module
    if actual_port == "rst":
        assert re.search(r"\binput\s+logic\s+rst\b", module), module
    elif cpuif.endswith("-flat"):
        assert re.search(rf"\binput\s+logic\s+{actual_port}\b", module), module
    else:
        assert re.search(rf"\b\w+_intf\.slave\s+{actual_port.split('.')[0]}\b", module), module


@pytest.mark.parametrize("cpuif", [entry[0] for entry in _RESET_ADAPTERS if not entry[0].startswith("ahb")])
def test_matching_top_level_design_reset_is_quiet(tmp_path: Path, cpuif: str) -> None:
    result = _run_cli(tmp_path, "--cpuif", cpuif, source=_reset_rdl())
    _assert_quiet_success(result)
    module = (tmp_path / "out" / "top.sv").read_text()
    assert re.search(r"\binput\s+logic\s+rst\b", module), module


@pytest.mark.parametrize(
    "properties,warns",
    [
        ("activehigh;", False),
        ("activehigh; async;", False),
        ("activehigh; sync = false;", False),
        ("activehigh; sync;", True),
        ("activehigh; async = false;", True),
        ("activelow; async;", True),
    ],
)
def test_only_explicit_reset_polarity_or_synchrony_conflicts_warn(
    tmp_path: Path, properties: str, warns: bool
) -> None:
    result = _run_cli(tmp_path, "--cpuif", "axi4-lite-flat", source=_reset_rdl(properties=properties))
    if warns:
        _assert_warning(
            result, "cpuif_reset", "top.rst", "built-in", "active-high", "asynchronous", "'rst'", "connect"
        )
    else:
        _assert_quiet_success(result)


@pytest.mark.parametrize("scope,path", [("nested", "top.block.rst"), ("root", "rst")])
def test_same_named_reset_outside_top_scope_is_not_honored(tmp_path: Path, scope: str, path: str) -> None:
    result = _run_cli(
        tmp_path,
        "--cpuif",
        "axi4-lite-flat",
        source=_reset_rdl(scope=scope, properties="activehigh; async;"),
    )
    _assert_warning(result, f"cpuif_reset signal '{path}'", "built-in", "active-high", "'rst'", "connect")


@pytest.mark.parametrize(
    "cpuif,clk_src,name",
    [
        ("apb3-flat", "cpuif", "s_apb_PRESETn"),
        ("apb4-flat", "cpuif", "s_apb_PRESETn"),
        ("axi4-lite-flat", "cpuif", "s_axil_ARESETn"),
        ("ahb-lite-flat", "design", "s_ahb_HRESETn"),
        ("ahb-lite-flat", "cpuif", "s_ahb_HRESETn"),
    ],
)
def test_matching_fixed_active_low_flat_port_is_quiet(
    tmp_path: Path, cpuif: str, clk_src: str, name: str
) -> None:
    result = _run_cli(
        tmp_path,
        "--cpuif",
        cpuif,
        "--clk-src",
        clk_src,
        source=_reset_rdl(name=name, properties="activelow; async;"),
    )
    _assert_quiet_success(result)
    module = (tmp_path / "out" / "top.sv").read_text()
    assert re.search(rf"\binput\s+logic\s+{name}\b", module), module


@pytest.mark.parametrize("name", ["rst", "reset_n"])
def test_active_low_rdl_reset_does_not_change_generated_axi_design_reset(tmp_path: Path, name: str) -> None:
    result = _run_cli(
        tmp_path,
        "--cpuif",
        "axi4-lite-flat",
        source=_reset_rdl(name=name, properties="activelow; async;"),
    )
    _assert_warning(result, "cpuif_reset", f"top.{name}", "active-high", "'rst'", "connect")
    module = (tmp_path / "out" / "top.sv").read_text()
    assert re.search(r"always_ff\s*@\(posedge\s+clk\s+or\s+posedge\s+rst\)\s*begin\s*if\s*\(rst\)", module), module
    assert re.search(r"\bwire\s+axil_in_reset\s*=\s*rst\s*;", module), module
    assert "negedge rst" not in module, module
    if name != "rst":
        assert name not in module, module


@pytest.mark.parametrize(
    "cpuif,clk_src,clock,reset",
    [
        ("axi4-lite", "cpuif", "s_axil.ACLK", "s_axil.ARESETn"),
        ("axi4-lite-flat", "cpuif", "s_axil_ACLK", "s_axil_ARESETn"),
        ("ahb-lite", "design", "s_ahb.HCLK", "s_ahb.HRESETn"),
        ("ahb-lite", "cpuif", "s_ahb.HCLK", "s_ahb.HRESETn"),
        ("ahb-lite-flat", "design", "s_ahb_HCLK", "s_ahb_HRESETn"),
        ("ahb-lite-flat", "cpuif", "s_ahb_HCLK", "s_ahb_HRESETn"),
    ],
)
def test_clocked_bus_reset_logic_remains_active_low_despite_rdl_metadata(
    tmp_path: Path, cpuif: str, clk_src: str, clock: str, reset: str
) -> None:
    result = _run_cli(tmp_path, "--cpuif", cpuif, "--clk-src", clk_src, source=_reset_rdl())
    _assert_warning(result, "cpuif_reset", "top.rst", reset, "active-low", "connect")
    module = (tmp_path / "out" / "top.sv").read_text()
    assert re.search(
        rf"always_ff\s*@\(posedge\s+{re.escape(clock)}\s+or\s+negedge\s+{re.escape(reset)}\)",
        module,
    ), module
    assert re.search(rf"if\s*\(!{re.escape(reset)}\)", module), module
    assert not re.search(r"\binput\s+logic\s+rst\b", module), module


@pytest.mark.parametrize("cpuif", ["apb3", "apb3-flat", "apb4", "apb4-flat"])
def test_buffered_apb_reset_logic_remains_fixed_active_high(tmp_path: Path, cpuif: str) -> None:
    result = _run_cli(
        tmp_path,
        "--cpuif",
        cpuif,
        "--apb-buffer",
        "both",
        source=_reset_rdl(properties="activelow; async;"),
    )
    _assert_warning(result, "cpuif_reset", "top.rst", "active-high", "'rst'", "connect")
    module = (tmp_path / "out" / "top.sv").read_text()
    assert re.search(r"always_ff\s*@\(posedge\s+clk\s+or\s+posedge\s+rst\)\s*begin\s*if\s*\(rst\)", module), module


@pytest.mark.parametrize(
    "reference,target",
    [("remote.external_control", "top.remote.external_control"),
     ("remote.status.state->anded", "top.remote.status.state->anded")],
    ids=["signal-node", "property-reference"],
)
def test_cross_boundary_property_diagnostic_identifies_owner_target_and_remedy(
    tmp_path: Path, reference: str, target: str
) -> None:
    source = f"""
    addrmap remote_map {{
        signal {{ }} external_control;
        reg {{
            field {{ sw = rw; hw = r; anded; }} state[7:0];
        }} status @ 0x0;
    }};
    addrmap top {{
        external remote_map remote @ 0x100;
        reg {{ field {{ sw = rw; hw = rw; }} data; }} control @ 0x0;
        control.data->next = {reference};
    }};
    """
    result = _run_cli(tmp_path, source=source)
    _assert_failure(
        result,
        "fatal:",
        "Property 'next' of 'top.control.data'",
        f"references '{target}'",
        "not internal to the busdecoder 'top'",
        "Make the reference target internal to the exported addrmap",
        "remove the cross-boundary property assignment",
    )


@pytest.mark.parametrize("reference", ["internal_control", "status.state->anded"])
def test_equivalent_internal_property_references_export_quietly(tmp_path: Path, reference: str) -> None:
    source = f"""
    addrmap top {{
        signal {{ }} internal_control;
        reg {{ field {{ sw = rw; hw = r; anded; }} state[7:0]; }} status @ 0x0;
        reg {{ field {{ sw = rw; hw = rw; }} data; }} control @ 0x4;
        control.data->next = {reference};
    }};
    """
    result = _run_cli(tmp_path, source=source)
    _assert_quiet_success(result)


@pytest.mark.parametrize("width,offset", [(32, 5), (32, 6), (64, 12)])
def test_unaligned_offset_reports_actual_bytes_full_path_alignment_and_remedy(
    tmp_path: Path, width: int, offset: int
) -> None:
    source = f"""
    addrmap top {{
        regfile {{
            reg word_t {{
                regwidth = {width};
                accesswidth = {width};
                field {{ sw = rw; hw = r; }} data[{width - 1}:0];
            }};
            word_t first @ 0x0;
            word_t misaligned @ {offset};
        }} bank @ 0x20;
    }};
    """
    result = _run_cli(tmp_path, source=source)
    _assert_failure(
        result,
        "fatal:",
        f"Unaligned address offset {offset} bytes",
        "top.bank.misaligned",
        f"multiple of {width // 8} bytes",
        "Move the component to an aligned address",
    )


@pytest.mark.parametrize(
    "width,dimensions,stride,invalid_dimensions",
    [
        (32, (4,), 5, ((0, 4, 5),)),
        (32, (2, 3), 5, ((0, 2, 15), (1, 3, 5))),
        (32, (2, 2), 6, ((1, 2, 6),)),
        (64, (2, 3), 12, ((0, 2, 36), (1, 3, 12))),
    ],
    ids=["one-dimensional", "both-dimensions", "only-inner-dimension", "wide-bus"],
)
def test_unaligned_array_stride_reports_zero_based_dimensions_sizes_bytes_and_full_path(
    tmp_path: Path,
    width: int,
    dimensions: tuple[int, ...],
    stride: int,
    invalid_dimensions: tuple[tuple[int, int, int], ...],
) -> None:
    array = "".join(f"[{size}]" for size in dimensions)
    source = f"""
    addrmap top {{
        regfile {{
            reg {{
                regwidth = {width};
                accesswidth = {width};
                field {{ sw = rw; hw = r; }} data[{width - 1}:0];
            }} targets{array} @ 0x0 += {stride};
        }} bank @ 0x20;
    }};
    """
    result = _run_cli(tmp_path, source=source)
    message = _assert_failure(
        result,
        "fatal:",
        "Unaligned array stride",
        "top.bank.targets" + "[]" * len(dimensions),
        f"multiple of {width // 8} bytes",
        "adjust the array's += stride",
    )
    for index, size, byte_stride in invalid_dimensions:
        assert f"dimension {index} (size {size}): {byte_stride} bytes" in message, message
    if dimensions == (2, 2):
        assert "dimension 0 (size 2):" not in message, message


@pytest.mark.parametrize("cpuif", ["ahb-lite", "ahb-lite-flat"])
@pytest.mark.parametrize("width", [8, 16, 2048])
def test_ahb_explicit_unsupported_width_reports_selected_value_and_remedy(
    tmp_path: Path, cpuif: str, width: int
) -> None:
    result = _run_cli(tmp_path, "--cpuif", cpuif, "--data-width", str(width), source=_EXTERNAL_RDL)
    message = _assert_failure(
        result,
        "fatal:",
        "AHB-Lite requires a common power-of-two data width from 32 through 1024 bits",
        f"the selected width is {width} bits",
        "Choose --data-width 32, 64, 128, 256, 512, or 1024",
        "no smaller than the internal register accesswidth",
    )
    assert "Unable to infer" not in message, message


@pytest.mark.parametrize("cpuif", ["ahb-lite", "ahb-lite-flat"])
def test_ahb_inferred_unsupported_width_reports_actual_selection(tmp_path: Path, cpuif: str) -> None:
    result = _run_cli(tmp_path, "--cpuif", cpuif, source=_ahb_internal_rdl(16))
    _assert_failure(
        result,
        "fatal:",
        "AHB-Lite requires",
        "32 through 1024 bits",
        "the selected width is 16 bits",
        "Choose --data-width 32",
        "no smaller than the internal register accesswidth",
    )


@pytest.mark.parametrize("cpuif", ["ahb-lite", "ahb-lite-flat"])
@pytest.mark.parametrize(
    "declaration,target,depth,details",
    [
        (
            "page target[2] @ 0x0 += 0x500;",
            "target[]",
            1,
            (("top.target[]", 0, 2, 1280),),
        ),
        (
            "page target[2][3] @ 0x0 += 0x500;",
            "target[][]",
            1,
            (("top.target[][]", 0, 2, 3840), ("top.target[][]", 1, 3, 1280)),
        ),
        (
            "regfile { page target @ 0x0; } bank[2][4] @ 0x0 += 0x500;",
            "bank[][].target",
            2,
            (("top.bank[][]", 1, 4, 1280),),
        ),
        (
            "regfile { page target[2] @ 0x0 += 0x500; } bank[2][3] @ 0x0 += 0xb00;",
            "bank[][].target[]",
            2,
            (
                ("top.bank[][]", 0, 2, 8448),
                ("top.bank[][]", 1, 3, 2816),
                ("top.bank[][].target[]", 0, 2, 1280),
            ),
        ),
    ],
    ids=["target-1d", "target-2d", "ancestor-inner-only", "ancestor-and-target"],
)
def test_ahb_unaligned_strides_identify_each_owning_component_and_dimension(
    tmp_path: Path,
    cpuif: str,
    declaration: str,
    target: str,
    depth: int,
    details: tuple[tuple[str, int, int, int], ...],
) -> None:
    source = f"""
    regfile page {{
        reg word_t {{ field {{ sw = rw; hw = r; }} data[31:0]; }};
        word_t first @ 0x0;
        word_t last @ 0x3fc;
    }};
    addrmap top {{
        {declaration}
    }};
    """
    result = _run_cli(
        tmp_path, "--cpuif", cpuif, "--max-decode-depth", str(depth), source=source
    )
    message = _assert_failure(
        result,
        "fatal:",
        f"AHB-Lite target '{target}' has unaligned array strides",
        "multiple of 1024 bytes (1 KiB)",
        "adjust the array's += stride",
    )
    for component, index, size, stride in details:
        assert f"'{component}' dimension {index} (size {size}): {stride} bytes" in message, message
    if target == "bank[][].target":
        assert "'top.bank[][]' dimension 0" not in message, message


_FIXED_AXI_RESET_CPP = r"""
#include "Vtop.h"
#include "verilated.h"
#include <cstdio>
#include <cstdlib>

static void require(bool condition, const char* detail) {
    if (!condition) {
        std::fprintf(stderr, "Fixed AXI reset regression: %s\n", detail);
        std::exit(1);
    }
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vtop dut;
    dut.clk = 0;
    dut.rst = 0;
    dut.s_axil_AWVALID = 0;
    dut.s_axil_AWADDR = 0;
    dut.s_axil_AWPROT = 0;
    dut.s_axil_WVALID = 0;
    dut.s_axil_WDATA = 0;
    dut.s_axil_WSTRB = 0;
    dut.s_axil_BREADY = 0;
    dut.s_axil_ARVALID = 0;
    dut.s_axil_ARADDR = 0;
    dut.s_axil_ARPROT = 0;
    dut.s_axil_RREADY = 0;
    dut.m_axil_target_AWREADY = 1;
    dut.m_axil_target_WREADY = 1;
    dut.m_axil_target_BVALID = 0;
    dut.m_axil_target_BRESP = 0;
    dut.m_axil_target_ARREADY = 1;
    dut.m_axil_target_RVALID = 0;
    dut.m_axil_target_RRESP = 0;
    dut.m_axil_target_RDATA = 0;
    dut.eval();
    auto tick = [&]() {
        dut.clk = 0;
        dut.eval();
        dut.clk = 1;
        dut.eval();
        dut.clk = 0;
        dut.eval();
    };
    auto assert_reset_outputs = [&]() {
        require(!dut.s_axil_AWREADY && !dut.s_axil_WREADY && !dut.s_axil_ARREADY,
                "active-high rst must suppress upstream READY without a clock edge");
        require(!dut.s_axil_BVALID && !dut.s_axil_RVALID,
                "asynchronous reset must discard queued responses");
        require(!dut.m_axil_target_AWVALID && !dut.m_axil_target_WVALID &&
                !dut.m_axil_target_ARVALID, "reset must discard downstream requests");
    };
    dut.rst = 1;
    dut.eval();
    assert_reset_outputs();
    dut.rst = 0;
    dut.eval();
    require(dut.s_axil_AWREADY && dut.s_axil_WREADY && dut.s_axil_ARREADY,
            "rst=0 must release the fixed active-high adapter despite activelow RDL metadata");

    // Queue a read and hold its completed response under upstream backpressure.
    dut.s_axil_ARVALID = 1;
    tick();
    dut.s_axil_ARVALID = 0;
    dut.eval();
    require(dut.m_axil_target_ARVALID, "first read was not issued to the child");
    tick();
    dut.m_axil_target_RDATA = 0x12345678;
    dut.m_axil_target_RVALID = 1;
    dut.eval();
    require(dut.s_axil_RVALID && dut.s_axil_RDATA == 0x12345678,
            "read response was not retained before reset");

    // Assert between rising clock edges: the response must disappear immediately.
    dut.rst = 1;
    dut.eval();
    assert_reset_outputs();
    dut.rst = 0;
    dut.eval();
    for (int cycle = 0; cycle < 3; ++cycle) {
        tick();
        require(!dut.s_axil_RVALID && !dut.m_axil_target_ARVALID,
                "aborted read was replayed after reset");
    }
    dut.m_axil_target_RVALID = 0;
    dut.s_axil_ARVALID = 1;
    dut.eval();
    require(dut.s_axil_ARREADY, "fresh read was not accepted after reset");
    tick();
    dut.s_axil_ARVALID = 0;
    dut.eval();
    require(dut.m_axil_target_ARVALID, "fresh read was not issued after reset");
    tick();
    dut.m_axil_target_RDATA = 0x55a5aa55;
    dut.m_axil_target_RVALID = 1;
    dut.eval();
    require(dut.s_axil_RVALID && dut.s_axil_RDATA == 0x55a5aa55,
            "fresh response did not complete after reset");
    dut.s_axil_RREADY = 1;
    tick();
    dut.m_axil_target_RVALID = 0;
    tick();
    require(!dut.s_axil_RVALID && !dut.m_axil_target_ARVALID,
            "read response or request was duplicated");
    dut.final();
    std::puts("FIXED_AXI_RESET_OK");
    return 0;
}
"""


@pytest.mark.simulation
@pytest.mark.verilator
def test_active_low_cpuif_reset_metadata_cannot_invert_axi_behavior(tmp_path: Path) -> None:
    verilator = shutil.which("verilator")
    if verilator is None:
        pytest.skip("Verilator is required for the fixed-reset behavioral regression.")
    result = _run_cli(
        tmp_path,
        "--cpuif",
        "axi4-lite-flat",
        source=_reset_rdl(properties="activelow; async;"),
    )
    _assert_warning(result, "cpuif_reset", "top.rst", "active-high", "'rst'", "connect")
    output = tmp_path / "out"
    testbench = tmp_path / "fixed_axi_reset.cpp"
    testbench.write_text(_FIXED_AXI_RESET_CPP)
    build = subprocess.run(
        [
            verilator,
            "--cc",
            "--exe",
            "--build",
            "-Wall",
            "-Wno-DECLFILENAME",
            "-Wno-UNUSEDPARAM",
            "-Wno-UNUSEDSIGNAL",
            "-Wno-GENUNNAMED",
            "--top-module",
            "top",
            "-Mdir",
            str(tmp_path / "obj_dir"),
            "-o",
            "sim",
            str(output / "top_pkg.sv"),
            str(output / "top.sv"),
            str(testbench),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert build.returncode == 0, f"Verilator compilation failed:\n{build.stdout}\n{build.stderr}"
    simulation = subprocess.run(
        [str(tmp_path / "obj_dir" / "sim")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert simulation.returncode == 0, simulation.stdout + simulation.stderr
    assert "FIXED_AXI_RESET_OK" in simulation.stdout, simulation.stdout + simulation.stderr
