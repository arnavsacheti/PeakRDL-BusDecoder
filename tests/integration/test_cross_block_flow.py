"""End-to-end flow tests over a heterogeneous multi-block design.

Rather than exercising each generator class in isolation, these tests export
one realistic SoC-style address map (arrayed external block, scalar external
block, a bare register, an external memory) and verify that the *whole*
generated decoder is coherent:

* every register address routes to the select of its enclosing block,
* addresses outside any block never select a block,
* the read and write decoders implement the same map,
* module ports, select struct, fanout, fanin, and decoder all agree on the
  set of downstream blocks,
* package parameters match the compiled address map,
* every CPU interface flavor implements the same decode.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif
from peakrdl_busdecoder.cpuif.apb3.apb3_cpuif import APB3CpuifFlat
from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif
from peakrdl_busdecoder.cpuif.apb4.apb4_cpuif import APB4CpuifFlat
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif
from peakrdl_busdecoder.cpuif.axi4lite.axi4_lite_cpuif import AXI4LiteCpuifFlat
from peakrdl_busdecoder.utils import clog2

from .conftest import ExportedDesign
from .helpers import (
    iter_reg_expectations,
    occupied_extent,
    parse_decode_assigns,
    parse_fanin_sel_paths,
    parse_fanout_masters,
    parse_flat_master_ports,
    parse_interface_master_ports,
    parse_package_localparams,
    parse_sel_struct_leaves,
    route,
    top_level_blocks,
)

# A heterogeneous SoC-style map: an arrayed external block, a scalar external
# block, a plain register, and an external memory — with gaps between them.
SOC_RDL = """
addrmap uart {
    reg { field { sw=rw; hw=r; } data[7:0]; } tx @ 0x0;
    reg { field { sw=r;  hw=w; } data[7:0]; } rx @ 0x4;
    reg { field { sw=rw; hw=r; } div[15:0]; } baud @ 0x8;
};

addrmap dma {
    reg { field { sw=rw; hw=r; } addr[31:0]; } src @ 0x0;
    reg { field { sw=rw; hw=r; } addr[31:0]; } dst @ 0x4;
    reg { field { sw=rw; hw=r; } len[15:0]; } xfer @ 0x8;
};

mem buf_t {
    mementries = 64;
    memwidth = 32;
};

addrmap soc {
    external uart  uarts[2] @ 0x0000 += 0x100;
    external dma   dma0     @ 0x1000;
    reg { field { sw=rw; hw=r; } v[31:0]; } ctrl @ 0x2000;
    external buf_t buffer   @ 0x3000;
};
"""

INTERFACE_CPUIFS = [
    pytest.param(APB3Cpuif, id="apb3"),
    pytest.param(APB4Cpuif, id="apb4"),
    pytest.param(AXI4LiteCpuif, id="axi4lite"),
]

FLAT_CPUIFS = [
    pytest.param(APB3CpuifFlat, "PSEL", id="apb3-flat"),
    pytest.param(APB4CpuifFlat, "PSEL", id="apb4-flat"),
    pytest.param(AXI4LiteCpuifFlat, "AWVALID", id="axi4lite-flat"),
]


@pytest.fixture(params=INTERFACE_CPUIFS)
def soc(request: pytest.FixtureRequest, export_design: Callable[..., ExportedDesign]) -> ExportedDesign:
    return export_design(SOC_RDL, top="soc", cpuif_cls=request.param)


class TestAddressRouting:
    """Feed concrete addresses through the parsed decoder and check the target."""

    @pytest.mark.parametrize("flavor", ["wr", "rd"])
    def test_every_register_address_routes_to_its_block(self, soc: ExportedDesign, flavor: str) -> None:
        assigns = parse_decode_assigns(soc.module_text, flavor)
        expectations = iter_reg_expectations(soc.top)
        assert expectations, "oracle found no registers — bad test design"

        for addr, expected_target in expectations:
            assert route(assigns, addr) == [expected_target], (
                f"address {addr:#x} should select {expected_target}"
            )

    @pytest.mark.parametrize("flavor", ["wr", "rd"])
    def test_memory_block_is_selected_across_its_full_size(self, soc: ExportedDesign, flavor: str) -> None:
        assigns = parse_decode_assigns(soc.module_text, flavor)
        # buffer: 64 entries x 32 bits at 0x3000
        assert route(assigns, 0x3000) == ["buffer"]
        assert route(assigns, 0x30FC) == ["buffer"]  # last word
        assert route(assigns, 0x3100) == ["cpuif_err"]  # one past the end

    @pytest.mark.parametrize("flavor", ["wr", "rd"])
    def test_addresses_outside_any_block_never_select_a_block(self, soc: ExportedDesign, flavor: str) -> None:
        assigns = parse_decode_assigns(soc.module_text, flavor)
        gap_addresses = [
            0x000C,  # tail of uarts[0], before uarts[1]
            0x010C,  # tail of uarts[1], within the array span
            0x0200,  # between the uarts array span and dma0
            0x0FFC,  # just before dma0
            0x100C,  # just past dma0's last register
            0x2004,  # just past ctrl
            0x2FFC,  # just before buffer
            0x3FFC,  # top of the address space
        ]
        for addr in gap_addresses:
            targets = route(assigns, addr)
            blocks = [t for t in targets if t != "cpuif_err"]
            assert not blocks, f"gap address {addr:#x} unexpectedly selected {blocks}"

    def test_read_and_write_decoders_implement_the_same_map(self, soc: ExportedDesign) -> None:
        wr = parse_decode_assigns(soc.module_text, "wr")
        rd = parse_decode_assigns(soc.module_text, "rd")

        def normalize(assigns: list) -> list:
            return [(a.target, [c.replace("_rd_", "_wr_") for c in a.conditions], a.loops) for a in assigns]

        assert normalize(wr) == normalize(rd)


class TestCrossGeneratorConsistency:
    """The independently generated module sections must agree on the block set."""

    def test_ports_struct_decode_fanout_fanin_agree(self, soc: ExportedDesign) -> None:
        expected = {
            block.inst_name: tuple(block.array_dimensions or ()) for block in top_level_blocks(soc.top)
        }

        ports = parse_interface_master_ports(soc.module_text)
        sel_leaves = parse_sel_struct_leaves(soc.module_text)
        fanout = parse_fanout_masters(soc.module_text)
        fanin = parse_fanin_sel_paths(soc.module_text)
        decode_targets = {
            re.sub(r"\[\w+\]", "", a.target)
            for a in parse_decode_assigns(soc.module_text, "wr")
            if a.target != "cpuif_err"
        }

        assert ports == expected
        assert sel_leaves == expected
        assert fanout == set(expected)
        assert fanin == set(expected)
        assert decode_targets == set(expected)

    @pytest.mark.parametrize(("cpuif_cls", "select_signal"), FLAT_CPUIFS)
    def test_flat_ports_agree_with_decode(
        self,
        export_design: Callable[..., ExportedDesign],
        cpuif_cls: type,
        select_signal: str,
    ) -> None:
        design = export_design(SOC_RDL, top="soc", cpuif_cls=cpuif_cls)
        expected = {
            block.inst_name: tuple(block.array_dimensions or ()) for block in top_level_blocks(design.top)
        }

        ports = parse_flat_master_ports(design.module_text, select_signal)
        decode_targets = {
            re.sub(r"\[\w+\]", "", a.target)
            for a in parse_decode_assigns(design.module_text, "wr")
            if a.target != "cpuif_err"
        }

        assert ports == expected
        assert decode_targets == set(expected)

    def test_decode_logic_is_identical_across_all_cpuifs(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        all_cpuifs = [
            APB3Cpuif,
            APB3CpuifFlat,
            APB4Cpuif,
            APB4CpuifFlat,
            AXI4LiteCpuif,
            AXI4LiteCpuifFlat,
        ]
        decoders = []
        for cpuif_cls in all_cpuifs:
            design = export_design(SOC_RDL, top="soc", cpuif_cls=cpuif_cls)
            decoders.append(parse_decode_assigns(design.module_text, "wr"))

        reference = decoders[0]
        assert reference, "reference decoder parsed as empty"
        for cpuif_cls, decoder in zip(all_cpuifs[1:], decoders[1:], strict=True):
            assert decoder == reference, f"{cpuif_cls.__name__} decodes differently"


class TestPackageConsistency:
    """The generated package must describe the same address map as the module."""

    def test_package_parameters_match_compiled_address_map(self, soc: ExportedDesign) -> None:
        params = parse_package_localparams(soc.package_text)
        top = soc.top
        prefix = top.inst_name.upper()

        assert params[f"{prefix}_DATA_WIDTH"] == 32
        assert params[f"{prefix}_SIZE"] == top.size
        assert params[f"{prefix}_MIN_ADDR_WIDTH"] == clog2(top.size)

        for block in top_level_blocks(top):
            name = f"{prefix}_{block.inst_name.upper()}_ADDR_WIDTH"
            assert params[name] == clog2(occupied_extent(block)), name

    def test_module_address_signals_match_package_width(self, soc: ExportedDesign) -> None:
        params = parse_package_localparams(soc.package_text)
        addr_width = params[f"{soc.top.inst_name.upper()}_MIN_ADDR_WIDTH"]

        m = re.search(r"logic \[(\d+):0\] cpuif_wr_addr;", soc.module_text)
        assert m is not None
        assert int(m.group(1)) + 1 == addr_width
