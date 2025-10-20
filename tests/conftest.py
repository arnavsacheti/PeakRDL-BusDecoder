import textwrap
import uuid
from pathlib import Path

import pytest
from systemrdl import RDLCompiler

from peakrdl_busdecoder.udps import ALL_UDPS


def pytest_addoption(parser):
    parser.addoption(
        "--sim-tool",
        choices=["questa", "xsim", "stub", "skip", "auto"],
        default="auto",
        help="""
        Select the simulator to use.

        stub: run the testcase using a no-op simulator stub
        skip: skip all the simulation tests
        auto: choose the best simulator based on what is installed
        """,
    )

    parser.addoption(
        "--gui",
        default=False,
        action="store_true",
        help=""",
        Launch sim tool in GUI mode

        Only use this option when running a single test
        """,
    )

    parser.addoption(
        "--rerun",
        default=False,
        action="store_true",
        help=""",
        Re-run simulation in-place without re-exporting busdecoder

        Useful if hand-editing a testcase interactively.
        """,
    )

    parser.addoption(
        "--synth-tool",
        choices=["vivado", "skip", "auto"],
        default="auto",
        help="""
        Select the synthesis tool to use.

        skip: skip all the simulation tests
        auto: choose the best tool based on what is installed
        """,
    )


@pytest.fixture
def rdl_compile(tmp_path):
    """Compile SystemRDL source text and return the elaborated top addrmap."""

    udp_file = Path(__file__).resolve().parents[1] / "hdl-src" / "regblock_udps.rdl"

    def _compile(source: str, top: str, inst_name: str = "top", params: dict | None = None):
        rdl_path = tmp_path / f"{uuid.uuid4().hex}.rdl"
        rdl_path.write_text(textwrap.dedent(source))

        rdlc = RDLCompiler()
        for udp in ALL_UDPS:
            rdlc.register_udp(udp)

        rdlc.compile_file(str(udp_file))
        rdlc.compile_file(str(rdl_path))

        root = rdlc.elaborate(top, inst_name, params or {})
        return root.top

    return _compile
