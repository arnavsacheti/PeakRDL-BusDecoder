"""Real PeakRDL configuration discovery, precedence, diagnostics, and RTL behavior.

Every export goes through this worktree's installed CLI with an explicit source
PYTHONPATH and a temporary working directory. The bounded Verilator case compiles
those exact CLI outputs; it never regenerates them through the exporter API.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

import pytest

from tests.formal.reference_model import FormalBusDecoderModel
from tests.formal.test_formal_equivalence import _compile_top, _cpp_testbench, _run_verilator

_REPO = Path(__file__).resolve().parents[2]
_PEAKRDL = _REPO / ".venv" / "bin" / "peakrdl"
_TOP = "toml_config"
_RDL = """
reg config_word_t {
    field { sw=rw; hw=r; } data[31:0];
};
reg config_read_t {
    field { sw=r; hw=w; } data[31:0];
};
reg config_write_t {
    field { sw=w; hw=r; } data[31:0];
};
addrmap config_inner_t {
    config_word_t words[3] @ 0x0 += 0x8;
    config_read_t status @ 0x18;
    config_write_t command @ 0x1c;
};
addrmap toml_config #(longint unsigned N_CHANNELS = 2) {
    config_inner_t banks[N_CHANNELS] @ 0x20 += 0x20;
    config_word_t tail @ 0x80;
};
"""
_AHB_RDL = """
addrmap config_ahb_leaf_t {
    reg { field { sw=rw; hw=r; } data[31:0]; } first @ 0x0;
    reg { field { sw=rw; hw=r; } data[31:0]; } last @ 0x3fc;
};
addrmap toml_config {
    config_ahb_leaf_t banks[2] @ 0x0 += 0x400;
    config_ahb_leaf_t tail @ 0x1000;
};
"""


@dataclass
class _CliProject:
    cwd: Path
    source: Path
    empty_config: Path
    environment: dict[str, str]

    def use_ahb_layout(self) -> None:
        """AHB routes complete, 1-KiB-aligned downstream apertures."""
        self.source.write_text(dedent(_AHB_RDL), encoding="utf-8")

    def configure(self, body: str, *, discovery: str = "cwd") -> Path:
        """Use normal discovery, not --peakrdl-cfg, for the configuration under test."""
        if discovery == "cwd":
            path = self.cwd / "peakrdl.toml"
        else:
            assert discovery == "env"
            path = self.cwd.parent / "configuration" / "project.toml"
            path.parent.mkdir()
            self.environment["PEAKRDL_CFG"] = str(path)
        path.write_text("[busdecoder]\n" + dedent(body).strip() + "\n", encoding="utf-8")
        return path

    def run(
        self,
        *arguments: str,
        output: str = "rtl",
        config_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        config_args = [] if config_path is None else ["--peakrdl-cfg", str(config_path)]
        return subprocess.run(
            [
                str(_PEAKRDL), *config_args, "busdecoder", str(self.source),
                "-t", _TOP, "-o", str(self.cwd / output), *arguments,
            ],
            cwd=self.cwd,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def rtl(self, output: str = "rtl") -> tuple[str, str]:
        directory = self.cwd / output
        return (
            (directory / f"{_TOP}.sv").read_text(encoding="utf-8"),
            (directory / f"{_TOP}_pkg.sv").read_text(encoding="utf-8"),
        )


@pytest.fixture
def cli_project(tmp_path: Path) -> _CliProject:
    assert _PEAKRDL.is_file(), f"Install PeakRDL and this plugin in {_REPO / '.venv'}"
    cwd = tmp_path / "project"
    cwd.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    xdg_config = tmp_path / "xdg-config"
    xdg_config.mkdir()
    source = cwd / "project.rdl"
    source.write_text(dedent(_RDL), encoding="utf-8")
    empty_config = tmp_path / "empty.toml"
    empty_config.write_text("", encoding="utf-8")
    environment = dict(os.environ)
    environment.pop("PEAKRDL_CFG", None)
    # Do not inherit a PYTHONPATH pointing at another worktree or plugin checkout.
    environment["PYTHONPATH"] = str(_REPO / "src")
    environment["PYTHONNOUSERSITE"] = "1"
    environment["HOME"] = str(home)
    environment["XDG_CONFIG_HOME"] = str(xdg_config)
    return _CliProject(cwd, source, empty_config, environment)


def _generate(
    project: _CliProject,
    *arguments: str,
    output: str = "rtl",
    config_path: Path | None = None,
) -> tuple[str, str]:
    result = project.run(*arguments, output=output, config_path=config_path)
    message = result.stdout + result.stderr
    assert result.returncode == 0, f"CLI export failed:\n{message}"
    assert "Traceback" not in message, message
    return project.rtl(output)


def _assert_error(
    result: subprocess.CompletedProcess[str],
    config: Path,
    keys: tuple[str, ...],
    *fragments: str,
) -> None:
    message = result.stdout + result.stderr
    assert result.returncode != 0, f"CLI unexpectedly accepted invalid configuration:\n{message}"
    assert "Traceback" not in message, message
    assert str(config) in message, message
    for key in keys:
        assert f"busdecoder.{key}" in message, message
    for fragment in fragments:
        assert fragment in message, message


def _ports(module: str) -> str:
    header = re.search(
        rf"\bmodule\s+{_TOP}\s*(?:#\(.*?\)\s*)?\((.*?)\);", module, flags=re.DOTALL
    )
    assert header is not None, "Expected the CLI-generated decoder's module ports"
    return " ".join(header.group(1).split())


def _assert_clock(module: str, expected: str, protocol: str = "apb") -> None:
    ports = _ports(module)
    if expected == "design":
        assert "input logic clk" in ports
        assert "input logic rst" in ports
        assert not re.search(r"\b(?:s_apb_PCLK|s_axil_ACLK|s_ahb_HCLK)\b", ports)
    elif expected == "off":
        assert not re.search(r"\b(?:clk|rst)\b|PCLK|PRESETn|ACLK|ARESETn|HCLK|HRESETn", module)
    else:
        assert expected == "cpuif"
        assert "input logic clk" not in ports and "input logic rst" not in ports
        clock, reset = {
            "apb": ("PCLK", "PRESETn"),
            "axil": ("ACLK", "ARESETn"),
            "ahb": ("HCLK", "HRESETn"),
        }[protocol]
        # SV-interface ingress clocks appear in the implementation rather than
        # as discrete module ports; flat ingress exposes the same named signals.
        assert clock in module and reset in module


def test_no_config_is_silent_and_preserves_old_defaults(cli_project: _CliProject) -> None:
    # PeakRDL also hard-codes /etc/peakrdl.toml after cwd/env/home discovery.
    # Never modify a machine-wide file merely to make this absence test hermetic.
    if Path("/etc/peakrdl.toml").is_file():
        pytest.skip("PeakRDL's hard-coded /etc/peakrdl.toml prevents a genuine no-config invocation")
    result = cli_project.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "" and result.stderr == "", result.stdout + result.stderr
    implicit = cli_project.rtl()
    explicit = _generate(
        cli_project,
        "--cpuif", "apb4", "--clk-src", "off", "--apb-buffer", "none",
        "--no-gate-signals", "--max-decode-depth", "1", "--no-unroll",
        "--axi4lite-max-outstanding", "4", "--no-parametrize",
        output="explicit-defaults", config_path=cli_project.empty_config,
    )
    assert implicit == explicit
    module, package = implicit
    assert "apb4_intf.slave s_apb" in _ports(module)
    assert "apb4_intf.master m_apb_banks [2]" in _ports(module)
    assert "m_apb_words" not in module  # Depth one stops at banks.
    assert "apb_state" not in module
    assert "? cpuif_wr_data : '0" not in module
    assert "parameter int N_CHANNELS" not in module
    assert "MAX_N_CHANNELS" not in package
    _assert_clock(module, "off")
    axil, _ = _generate(cli_project, "--cpuif", "axi4-lite-flat", output="axil-defaults")
    assert "localparam AXI4LITE_MAX_OUTSTANDING = 4" in axil
    _assert_clock(axil, "design", "axil")


@pytest.mark.parametrize("discovery", ["cwd", "env"], ids=["peakrdl.toml", "PEAKRDL_CFG"])
def test_project_settings_reach_generated_apb_rtl(cli_project: _CliProject, discovery: str) -> None:
    cli_project.configure(
        """
        cpuif = "apb4-flat"
        clk_src = "design"
        apb_buffer = "both"
        gate_signals = true
        max_decode_depth = 0
        unroll = true
        axi4lite_max_outstanding = 7
        parametrize = true
        """,
        discovery=discovery,
    )
    configured = _generate(cli_project)
    explicit = _generate(
        cli_project,
        "--cpuif", "apb4-flat", "--clk-src", "design", "--apb-buffer", "both",
        "--gate-signals", "--max-decode-depth", "0", "--unroll",
        "--axi4lite-max-outstanding", "7", "--parametrize",
        output="explicit", config_path=cli_project.empty_config,
    )
    assert configured == explicit
    module, package = configured
    assert "input logic s_apb_PSEL" in _ports(module)
    assert "apb4_intf.slave" not in module
    _assert_clock(module, "design")
    assert "APB_SETUP" in module and "APB_RESPONSE" in module
    assert "? cpuif_wr_data : '0" in module
    assert "m_apb_words_PSEL_0_0" in _ports(module)
    assert "m_apb_words_PSEL_1_2" in _ports(module)
    assert "m_apb_banks" not in _ports(module)
    assert "parameter int N_CHANNELS = 2" in module
    assert "TOML_CONFIG_MAX_N_CHANNELS = 2" in package


@pytest.mark.parametrize("discovery", ["cwd", "env"], ids=["peakrdl.toml", "PEAKRDL_CFG"])
@pytest.mark.parametrize("outstanding", [1, 7], ids=["minimum", "nondefault"])
def test_axi_queue_setting_reaches_generated_rtl(
    cli_project: _CliProject, discovery: str, outstanding: int
) -> None:
    cli_project.configure(
        f'cpuif = "axi4-lite-flat"\naxi4lite_max_outstanding = {outstanding}\nclk_src = "cpuif"',
        discovery=discovery,
    )
    module, _ = _generate(cli_project)
    assert f"localparam AXI4LITE_MAX_OUTSTANDING = {outstanding}" in module
    assert "axil_wr_dest_q [0:AXI4LITE_MAX_OUTSTANDING-1]" in module
    assert "axil_rd_dest_q [0:AXI4LITE_MAX_OUTSTANDING-1]" in module
    assert "input logic s_axil_AWVALID" in _ports(module)
    _assert_clock(module, "cpuif", "axil")


@pytest.mark.parametrize(
    "body,override,expected",
    [
        pytest.param(
            'cpuif = "apb3-flat"',
            ("--cpuif", "apb4"), ("--cpuif", "apb4"), id="cpuif-old-default",
        ),
        pytest.param(
            'cpuif = "apb4-flat"\nclk_src = "design"',
            ("--clk-src", "off"), ("--cpuif", "apb4-flat", "--clk-src", "off"),
            id="clock-old-apb-default",
        ),
        pytest.param(
            'cpuif = "apb4-flat"\napb_buffer = "both"',
            ("--apb-buffer", "none"), ("--cpuif", "apb4-flat", "--apb-buffer", "none"),
            id="buffer-old-default-recomputes-clock",
        ),
        pytest.param(
            'cpuif = "apb4-flat"\nmax_decode_depth = 0',
            ("--max-decode-depth", "1"), ("--cpuif", "apb4-flat", "--max-decode-depth", "1"),
            id="depth-old-default",
        ),
        pytest.param(
            'cpuif = "apb4-flat"\nmax_decode_depth = 1',
            ("--max-decode-depth", "0"), ("--cpuif", "apb4-flat", "--max-decode-depth", "0"),
            id="depth-zero-is-unlimited",
        ),
        pytest.param(
            'cpuif = "axi4-lite-flat"\naxi4lite_max_outstanding = 7',
            ("--axi4lite-max-outstanding", "4"),
            ("--cpuif", "axi4-lite-flat", "--axi4lite-max-outstanding", "4"),
            id="queue-old-default",
        ),
        pytest.param(
            'cpuif = "axi4-lite-flat"\naxi4lite_max_outstanding = 7',
            ("--axi4lite-max-outstanding", "1"),
            ("--cpuif", "axi4-lite-flat", "--axi4lite-max-outstanding", "1"),
            id="queue-minimum",
        ),
    ],
)
def test_scalar_cli_overrides_toml(
    cli_project: _CliProject, body: str, override: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    cli_project.configure(body)
    configured = _generate(cli_project, output="configured")
    overridden = _generate(cli_project, *override, output="overridden")
    explicit = _generate(cli_project, *expected, output="explicit", config_path=cli_project.empty_config)
    assert overridden == explicit
    assert overridden != configured, "The override must change observable generated RTL, not just parse"


@pytest.mark.parametrize("key", ["gate_signals", "unroll", "parametrize"])
@pytest.mark.parametrize("configured", [True, False], ids=["toml-true-cli-false", "toml-false-cli-true"])
def test_boolean_cli_overrides_toml(cli_project: _CliProject, key: str, configured: bool) -> None:
    cli_project.configure(f'cpuif = "apb4-flat"\n{key} = {str(configured).lower()}')
    flag = "--" + ("no-" if configured else "") + key.replace("_", "-")
    original = _generate(cli_project, output="configured")
    overridden = _generate(cli_project, flag, output="overridden")
    explicit = _generate(
        cli_project, "--cpuif", "apb4-flat", flag,
        output="explicit", config_path=cli_project.empty_config,
    )
    assert overridden == explicit
    assert overridden != original, f"{flag} must change the {key} RTL/port contract"


@pytest.mark.parametrize(
    "cpuif,buffer,clock,protocol",
    [
        pytest.param(cpuif, "none", "off", "apb", id=f"{cpuif}-unbuffered")
        for cpuif in ("apb3", "apb3-flat", "apb4", "apb4-flat")
    ] + [
        pytest.param(cpuif, mode, "design", "apb", id=f"{cpuif}-{mode}")
        for cpuif in ("apb3", "apb3-flat", "apb4", "apb4-flat")
        for mode in ("in", "out", "both")
    ] + [
        pytest.param(cpuif, "none", "design", "axil", id=cpuif)
        for cpuif in ("axi4-lite", "axi4-lite-flat")
    ] + [
        pytest.param(cpuif, "none", "cpuif", "ahb", id=cpuif)
        for cpuif in ("ahb-lite", "ahb-lite-flat")
    ],
)
def test_omitted_clock_uses_effective_protocol_and_buffer(
    cli_project: _CliProject, cpuif: str, buffer: str, clock: str, protocol: str
) -> None:
    if protocol == "ahb":
        cli_project.use_ahb_layout()
    cli_project.configure(f'cpuif = "{cpuif}"\napb_buffer = "{buffer}"')
    module, _ = _generate(cli_project)
    _assert_clock(module, clock, protocol)
    assert ("apb_state" in module) is (buffer != "none")


@pytest.mark.parametrize(
    "body,arguments,clock,protocol",
    [
        pytest.param(
            'cpuif = "apb4-flat"', ("--apb-buffer", "in"), "design", "apb", id="cli-adds-buffer",
        ),
        pytest.param(
            'cpuif = "apb4-flat"\napb_buffer = "both"',
            ("--apb-buffer", "none"), "off", "apb", id="cli-removes-buffer",
        ),
        pytest.param(
            'cpuif = "axi4-lite-flat"', ("--cpuif", "apb4-flat"), "off", "apb",
            id="cli-switches-axil-to-apb",
        ),
        pytest.param(
            'cpuif = "apb4-flat"', ("--cpuif", "axi4-lite-flat"), "design", "axil",
            id="cli-switches-apb-to-axil",
        ),
        pytest.param(
            'cpuif = "apb4-flat"', ("--cpuif", "ahb-lite-flat"), "cpuif", "ahb",
            id="cli-switches-apb-to-ahb",
        ),
    ],
)
def test_clock_default_is_resolved_after_cli_overrides(
    cli_project: _CliProject, body: str, arguments: tuple[str, ...], clock: str, protocol: str
) -> None:
    if protocol == "ahb":
        cli_project.use_ahb_layout()
    cli_project.configure(body)
    module, _ = _generate(cli_project, *arguments)
    _assert_clock(module, clock, protocol)


_INVALID_VALUES = {
    "cpuif": ("1", "true", "[]", '{ value = "apb4" }', '"not-a-cpuif"'),
    "clk_src": ("1", "false", "[]", '{ value = "off" }', '"invalid-clock"'),
    "apb_buffer": ("1", "true", "[]", '{ value = "none" }', '"invalid-buffer"'),
    "gate_signals": ("0", "1", '"true"', "1.0", "[]", "{}"),
    "unroll": ("0", "1", '"false"', "1.0", "[]", "{}"),
    "parametrize": ("0", "1", '"true"', "1.0", "[]", "{}"),
    "max_decode_depth": ("true", "false", '"1"', "1.5", "[]", "{}", "-1"),
    "axi4lite_max_outstanding": ("true", "false", '"4"', "1.5", "[]", "{}", "0", "-1"),
}


@pytest.mark.parametrize(
    "key,value",
    [
        pytest.param(key, value, id=f"{key}-{index}")
        for key, values in _INVALID_VALUES.items()
        for index, value in enumerate(values)
    ],
)
def test_invalid_toml_values_name_file_and_key_without_traceback(
    cli_project: _CliProject, key: str, value: str
) -> None:
    config = cli_project.configure(f"{key} = {value}")
    _assert_error(cli_project.run(), config, (key,))


@pytest.mark.parametrize(
    "key,value,override",
    [
        ("cpuif", "1", ("--cpuif", "apb4")),
        ("clk_src", '"invalid-clock"', ("--clk-src", "off")),
        ("apb_buffer", '"invalid-buffer"', ("--apb-buffer", "none")),
        ("gate_signals", "1", ("--no-gate-signals",)),
        ("unroll", "0", ("--unroll",)),
        ("parametrize", '"true"', ("--no-parametrize",)),
        ("max_decode_depth", "true", ("--max-decode-depth", "1")),
        ("axi4lite_max_outstanding", "0", ("--axi4lite-max-outstanding", "4")),
    ],
)
def test_cli_override_does_not_hide_schema_errors(
    cli_project: _CliProject, key: str, value: str, override: tuple[str, ...]
) -> None:
    config = cli_project.configure(f"{key} = {value}")
    _assert_error(cli_project.run(*override), config, (key,))


@pytest.mark.parametrize(
    "cpuif,clock,buffer,keys,fragments",
    [
        pytest.param(
            cpuif, clock, mode, ("clk_src", "apb_buffer"), ("--clk-src", "--apb-buffer"),
            id=f"{cpuif}-{clock}-{mode}",
        )
        for cpuif in ("apb3", "apb3-flat", "apb4", "apb4-flat")
        for clock in ("off", "cpuif")
        for mode in ("in", "out", "both")
    ] + [
        pytest.param(
            cpuif, "off", "none", ("cpuif", "clk_src"), ("--clk-src off", protocol), id=cpuif,
        )
        for cpuif, protocol in (
            ("axi4-lite", "AXI4-Lite"), ("axi4-lite-flat", "AXI4-Lite"),
            ("ahb-lite", "AHB-Lite"), ("ahb-lite-flat", "AHB-Lite"),
        )
    ] + [
        pytest.param(
            cpuif, "design", mode, ("cpuif", "apb_buffer"), ("only APB",),
            id=f"{cpuif}-buffer-{mode}",
        )
        for cpuif in ("axi4-lite", "axi4-lite-flat", "ahb-lite", "ahb-lite-flat")
        for mode in ("in", "out", "both")
    ],
)
def test_conflicting_toml_settings_report_contributing_sources(
    cli_project: _CliProject,
    cpuif: str,
    clock: str,
    buffer: str,
    keys: tuple[str, ...],
    fragments: tuple[str, ...],
) -> None:
    if cpuif.startswith("ahb-lite"):
        cli_project.use_ahb_layout()
    config = cli_project.configure(f'cpuif = "{cpuif}"\nclk_src = "{clock}"\napb_buffer = "{buffer}"')
    _assert_error(cli_project.run(), config, keys, *fragments)


@pytest.mark.parametrize(
    "body,arguments,keys,fragments",
    [
        pytest.param(
            'clk_src = "off"', ("--cpuif", "axi4-lite-flat"), ("clk_src",),
            ("--clk-src off", "AXI4-Lite"), id="toml-clock-cli-axil",
        ),
        pytest.param(
            'cpuif = "axi4-lite-flat"', ("--clk-src", "off"), ("cpuif",),
            ("--clk-src off", "AXI4-Lite"), id="toml-axil-cli-clock",
        ),
        pytest.param(
            'clk_src = "off"', ("--cpuif", "ahb-lite-flat"), ("clk_src",),
            ("--clk-src off", "AHB-Lite"), id="toml-clock-cli-ahb",
        ),
        pytest.param(
            'cpuif = "ahb-lite-flat"', ("--clk-src", "off"), ("cpuif",),
            ("--clk-src off", "AHB-Lite"), id="toml-ahb-cli-clock",
        ),
        pytest.param(
            'apb_buffer = "in"', ("--clk-src", "off"), ("apb_buffer",),
            ("--clk-src", "--apb-buffer"), id="toml-buffer-cli-off",
        ),
        pytest.param(
            'clk_src = "off"', ("--apb-buffer", "out"), ("clk_src",),
            ("--clk-src", "--apb-buffer"), id="toml-off-cli-buffer",
        ),
        pytest.param(
            'apb_buffer = "both"', ("--clk-src", "cpuif"), ("apb_buffer",),
            ("--clk-src", "--apb-buffer"), id="toml-buffer-cli-cpuif-clock",
        ),
        pytest.param(
            'clk_src = "cpuif"', ("--apb-buffer", "both"), ("clk_src",),
            ("--clk-src", "--apb-buffer"), id="toml-cpuif-clock-cli-buffer",
        ),
        pytest.param(
            'apb_buffer = "both"', ("--cpuif", "ahb-lite-flat"), ("apb_buffer",),
            ("only APB",), id="toml-buffer-cli-non-apb",
        ),
        pytest.param(
            'cpuif = "axi4-lite-flat"', ("--apb-buffer", "in"), ("cpuif",),
            ("only APB",), id="toml-non-apb-cli-buffer",
        ),
    ],
)
def test_mixed_cli_and_toml_conflicts_name_toml_contributors(
    cli_project: _CliProject,
    body: str,
    arguments: tuple[str, ...],
    keys: tuple[str, ...],
    fragments: tuple[str, ...],
) -> None:
    if "ahb-lite" in body or any("ahb-lite" in argument for argument in arguments):
        cli_project.use_ahb_layout()
    config = cli_project.configure(body, discovery="env")
    _assert_error(cli_project.run(*arguments), config, keys, *fragments)


@pytest.mark.parametrize(
    "body,override,expected",
    [
        pytest.param(
            'cpuif = "apb4-flat"\nclk_src = "off"\napb_buffer = "both"',
            ("--clk-src", "design"),
            ("--cpuif", "apb4-flat", "--clk-src", "design", "--apb-buffer", "both"),
            id="repair-apb-clock",
        ),
        pytest.param(
            'cpuif = "apb4-flat"\nclk_src = "off"\napb_buffer = "both"',
            ("--apb-buffer", "none"),
            ("--cpuif", "apb4-flat", "--clk-src", "off", "--apb-buffer", "none"),
            id="repair-apb-buffer",
        ),
        pytest.param(
            'cpuif = "axi4-lite-flat"\nclk_src = "off"',
            ("--clk-src", "cpuif"), ("--cpuif", "axi4-lite-flat", "--clk-src", "cpuif"),
            id="repair-axil-clock",
        ),
        pytest.param(
            'cpuif = "ahb-lite-flat"\nclk_src = "off"',
            ("--clk-src", "cpuif"), ("--cpuif", "ahb-lite-flat", "--clk-src", "cpuif"),
            id="repair-ahb-clock",
        ),
        pytest.param(
            'cpuif = "axi4-lite-flat"\nclk_src = "off"',
            ("--cpuif", "apb4-flat"), ("--cpuif", "apb4-flat", "--clk-src", "off"),
            id="repair-off-by-changing-protocol",
        ),
        pytest.param(
            'cpuif = "axi4-lite-flat"\napb_buffer = "both"',
            ("--apb-buffer", "none"), ("--cpuif", "axi4-lite-flat", "--apb-buffer", "none"),
            id="repair-non-apb-buffer",
        ),
        pytest.param(
            'cpuif = "axi4-lite-flat"\napb_buffer = "both"',
            ("--cpuif", "apb4-flat"), ("--cpuif", "apb4-flat", "--apb-buffer", "both"),
            id="repair-buffer-by-changing-protocol",
        ),
    ],
)
def test_cli_can_repair_valid_but_conflicting_toml_settings(
    cli_project: _CliProject, body: str, override: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    if "ahb-lite" in body:
        cli_project.use_ahb_layout()
    cli_project.configure(body)
    repaired = _generate(cli_project, *override)
    explicit = _generate(cli_project, *expected, output="explicit", config_path=cli_project.empty_config)
    assert repaired == explicit


@pytest.mark.parametrize("selection", ["toml", "cli"])
def test_configured_cpuif_import_alias_is_selectable(cli_project: _CliProject, selection: str) -> None:
    selected = 'cpuif = "imported-apb3"\n' if selection == "toml" else 'cpuif = "apb4"\n'
    cli_project.configure(
        selected
        + '[busdecoder.cpuifs]\n'
        + 'imported-apb3 = "peakrdl_busdecoder.cpuif.apb.apb_cpuif:APB3CpuifFlat"'
    )
    arguments = () if selection == "toml" else ("--cpuif", "imported-apb3")
    aliased = _generate(cli_project, *arguments)
    explicit = _generate(
        cli_project, "--cpuif", "apb3-flat", output="explicit", config_path=cli_project.empty_config
    )
    assert aliased == explicit
    assert "input logic s_apb_PSEL" in _ports(aliased[0])
    assert "PSTRB" not in aliased[0] and "PPROT" not in aliased[0]


@pytest.mark.parametrize("selection", ["toml", "cli"])
def test_cpuif_entry_point_is_a_dynamic_config_choice(cli_project: _CliProject, selection: str) -> None:
    # importlib.metadata discovers this real temporary distribution in the child
    # interpreter. No entry-point enumeration or CPU interface loader is mocked.
    providers = cli_project.cwd.parent / "providers"
    distribution = providers / "toml_cpuif_fixture-1.0.dist-info"
    distribution.mkdir(parents=True)
    (distribution / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: toml-cpuif-fixture\nVersion: 1.0\n", encoding="utf-8"
    )
    (distribution / "entry_points.txt").write_text(
        "[peakrdl_busdecoder.cpuif]\n"
        "entrypoint-apb3 = peakrdl_busdecoder.cpuif.apb.apb_cpuif:APB3CpuifFlat\n",
        encoding="utf-8",
    )
    cli_project.environment["PYTHONPATH"] = os.pathsep.join((str(_REPO / "src"), str(providers)))
    selected = 'cpuif = "entrypoint-apb3"' if selection == "toml" else 'cpuif = "apb4"'
    cli_project.configure(selected)
    arguments = () if selection == "toml" else ("--cpuif", "entrypoint-apb3")
    generated = _generate(cli_project, *arguments)
    explicit = _generate(
        cli_project, "--cpuif", "apb3-flat", output="explicit", config_path=cli_project.empty_config
    )
    assert generated == explicit


@pytest.mark.simulation
@pytest.mark.verilator
def test_cli_generated_rtl_executes_bounded_node_oracle(cli_project: _CliProject) -> None:
    """Sweep exact CLI outputs across addresses, permissions, APB phases and responses."""
    cli_project.configure(
        """
        cpuif = "apb4-flat"
        clk_src = "off"
        apb_buffer = "none"
        gate_signals = false
        max_decode_depth = 0
        unroll = true
        parametrize = true
        """,
        discovery="env",
    )
    module, _ = _generate(cli_project)
    assert "m_apb_words_PSEL_1_2" in _ports(module)
    assert "parameter int N_CHANNELS = 2" in module
    # Compile SystemRDL only for the independent Node oracle. Do not export again.
    model = FormalBusDecoderModel(_compile_top(cli_project.source), max_decode_depth=0, cpuif_unroll=True)
    assert model.address_space_size == 256
    assert {
        (
            target.target_name, target.indices, target.rel_start, target.size,
            target.is_readable, target.is_writable,
        )
        for target in model.targets
    } == {
        ("words", (bank, word), 0x20 + bank * 0x20 + word * 0x8, 4, True, True)
        for bank in range(2)
        for word in range(3)
    } | {
        ("status", (bank,), 0x38 + bank * 0x20, 4, True, False)
        for bank in range(2)
    } | {
        ("command", (bank,), 0x3c + bank * 0x20, 4, False, True)
        for bank in range(2)
    } | {("tail", (), 0x80, 4, True, True)}
    bindings = {("tail", ()): "m_apb_tail_{name}"}
    bindings.update({
        ("words", (bank, word)): f"m_apb_words_{{name}}_{bank}_{word}"
        for bank in range(2)
        for word in range(3)
    })
    bindings.update({
        (leaf, (bank,)): f"m_apb_{leaf}_{{name}}_{bank}"
        for leaf in ("status", "command")
        for bank in range(2)
    })
    output = _run_verilator(
        cli_project.cwd / "rtl", _TOP, _cpp_testbench(_TOP, model, bindings)
    )
    assert f"ORACLE_SWEEP_OK {model.address_space_size * 2 * 4 * 4}" in output
