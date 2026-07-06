"""Cross-block flow tests for hierarchical, arrayed, and unrolled designs.

These exercise combinations where several generator stages must cooperate:
multi-dimensional arrays, decode boundaries inside regfiles, sibling blocks
at deeper decode depths, and CPU-interface unrolling.

Tests marked ``xfail(strict=True)`` document *known* cross-generator
inconsistencies found while building this suite: the port list is derived
from ``DesignState.get_addressable_children_at_depth`` while the decoder,
select struct, and fanout come from walker-based generators with different
boundary rules. When the underlying bug is fixed, the strict xfail will flip
and the test can be promoted to a plain assertion.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from .conftest import ExportedDesign
from .helpers import (
    iter_reg_expectations,
    parse_decode_assigns,
    parse_fanout_masters,
    parse_interface_master_ports,
    parse_sel_struct_leaves,
    route,
)

GRID_RDL = """
addrmap tile {
    reg { field { sw=rw; hw=r; } d[31:0]; } r0 @ 0x0;
    reg { field { sw=rw; hw=r; } d[31:0]; } r1 @ 0x4;
};

addrmap grid {
    external tile tiles[2][3] @ 0x0 += 0x100;
};
"""

REGFILE_RDL = """
addrmap rfsoc {
    regfile {
        reg { field { sw=rw; hw=r; } d[31:0]; } ra @ 0x0;
        reg { field { sw=rw; hw=r; } d[31:0]; } rb @ 0x4;
    } rf_a @ 0x0;

    regfile {
        reg { field { sw=rw; hw=r; } d[31:0]; } rc[2] @ 0x0 += 0x4;
    } rf_b @ 0x100;
};
"""

SIBLING_RDL = """
addrmap leafblk {
    reg { field { sw=rw; hw=r; } d[31:0]; } r0 @ 0x0;
    reg { field { sw=rw; hw=r; } d[31:0]; } r1 @ 0x4;
};

addrmap midblk {
    leafblk leaf0 @ 0x0;
    leafblk leaf1 @ 0x100;
};

addrmap topblk {
    midblk mid_a @ 0x0000;
    midblk mid_b @ 0x1000;
    reg { field { sw=rw; hw=r; } d[31:0]; } zero_reg @ 0x2000;
};
"""

UNROLL_RDL = """
addrmap uart {
    reg { field { sw=rw; hw=r; } data[7:0]; } tx @ 0x0;
};

addrmap unroll_soc {
    external uart uarts[2] @ 0x0 += 0x100;
    reg { field { sw=rw; hw=r; } v[31:0]; } ctrl @ 0x1000;
};
"""


class TestMultiDimensionalArrays:
    def test_2d_array_elements_route_by_index(self, export_design: Callable[..., ExportedDesign]) -> None:
        design = export_design(GRID_RDL, top="grid")
        assigns = parse_decode_assigns(design.module_text, "wr")

        expectations = iter_reg_expectations(design.top)
        assert len(expectations) == 2 * 3 * 2  # 6 tiles x 2 regs
        for addr, expected_target in expectations:
            assert route(assigns, addr) == [expected_target], (
                f"address {addr:#x} should select {expected_target}"
            )

    def test_2d_array_ports_and_struct_keep_both_dimensions(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(GRID_RDL, top="grid")
        assert parse_interface_master_ports(design.module_text) == {"tiles": (2, 3)}
        assert parse_sel_struct_leaves(design.module_text) == {"tiles": (2, 3)}


class TestRegfileHierarchy:
    def test_depth2_routes_individual_regfile_registers(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(REGFILE_RDL, top="rfsoc", max_decode_depth=2)
        assigns = parse_decode_assigns(design.module_text, "wr")

        assert route(assigns, 0x0) == ["rf_a.ra"]
        assert route(assigns, 0x4) == ["rf_a.rb"]

        ports = parse_interface_master_ports(design.module_text)
        assert {"ra", "rb"} <= set(ports)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Known bug: an arrayed register at the max_decode_depth boundary is "
            "decoded as its whole parent regfile (`cpuif_wr_sel.rf_b = 1'b1;`, an "
            "invalid struct-to-bit assignment) while ports and the select struct "
            "expose the per-element `rc[2]` array."
        ),
    )
    def test_depth2_routes_arrayed_regfile_registers_per_element(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(REGFILE_RDL, top="rfsoc", max_decode_depth=2)
        assigns = parse_decode_assigns(design.module_text, "wr")

        assert route(assigns, 0x100) == ["rf_b.rc[0]"]
        assert route(assigns, 0x104) == ["rf_b.rc[1]"]

    def test_depth0_full_decode_is_internally_consistent(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(REGFILE_RDL, top="rfsoc", max_decode_depth=0)
        assigns = parse_decode_assigns(design.module_text, "wr")

        assert route(assigns, 0x0) == ["rf_a.ra"]
        assert route(assigns, 0x4) == ["rf_a.rb"]
        assert route(assigns, 0x100) == ["rf_b.rc[0]"]
        assert route(assigns, 0x104) == ["rf_b.rc[1]"]
        assert route(assigns, 0x8) == ["cpuif_err"]

        # Ports are named after the leaf registers; the select struct keeps
        # the full hierarchical path. Leaf names and shapes must line up.
        ports = parse_interface_master_ports(design.module_text)
        sel_leaves = parse_sel_struct_leaves(design.module_text)
        assert ports == {path.rsplit(".", 1)[-1]: dims for path, dims in sel_leaves.items()}
        assert parse_fanout_masters(design.module_text) == set(ports)


class TestDeepSiblingBlocks:
    """Sibling addrmaps at max_decode_depth=2 with identically named children."""

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Known bug: with sibling addrmap blocks at max_decode_depth=2, the "
            "port list descends to leaf addrmaps (emitting duplicate "
            "`m_apb_leaf0`/`m_apb_leaf1` ports) while decode/fanout stop at the "
            "mid-level blocks and reference undeclared `m_apb_mid_*` ports."
        ),
    )
    def test_depth2_ports_agree_with_decode_targets(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(SIBLING_RDL, top="topblk", max_decode_depth=2)

        ports = parse_interface_master_ports(design.module_text)
        assert not any("#" in name for name in ports), f"duplicate ports: {ports}"

        decode_targets = {
            re.sub(r"\[\w+\]", "", a.target)
            for a in parse_decode_assigns(design.module_text, "wr")
            if a.target != "cpuif_err"
        }
        assert set(ports) == decode_targets
        assert parse_fanout_masters(design.module_text) <= set(ports)

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Known bug: a register that sits shallower than max_decode_depth "
            "(here zero_reg at depth 1 with depth=2) is decoded and fanned out "
            "but silently dropped from the module's port list."
        ),
    )
    def test_depth2_keeps_ports_for_shallow_registers(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(SIBLING_RDL, top="topblk", max_decode_depth=2)

        assigns = parse_decode_assigns(design.module_text, "wr")
        assert route(assigns, 0x2000) == ["zero_reg"]  # decoder handles it...

        ports = parse_interface_master_ports(design.module_text)
        assert "zero_reg" in ports  # ...so the module must expose its port


class TestCpuifUnroll:
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Known bug: with cpuif_unroll=True the port list unrolls arrays into "
            "`m_apb_uarts_0`/`m_apb_uarts_1`, but fanout still drives the rolled "
            "`m_apb_uarts[gi0]` interface array and the select struct keeps "
            "`uarts[2]` — the generated module does not elaborate."
        ),
    )
    def test_unrolled_ports_agree_with_fanout_and_struct(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(UNROLL_RDL, top="unroll_soc", cpuif_unroll=True)

        ports = parse_interface_master_ports(design.module_text)
        fanout = parse_fanout_masters(design.module_text)
        assert fanout <= set(ports)

        sel_leaves = parse_sel_struct_leaves(design.module_text)
        assert set(sel_leaves) == set(ports)

    def test_unrolled_decode_still_routes_correctly(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(UNROLL_RDL, top="unroll_soc", cpuif_unroll=True)
        assigns = parse_decode_assigns(design.module_text, "wr")

        assert route(assigns, 0x000) == ["uarts[0]"]
        assert route(assigns, 0x100) == ["uarts[1]"]
        assert route(assigns, 0x1000) == ["ctrl"]
