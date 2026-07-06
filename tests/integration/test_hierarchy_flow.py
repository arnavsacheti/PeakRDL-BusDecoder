"""Cross-block flow tests for hierarchical, arrayed, and unrolled designs.

These exercise combinations where several generator stages must cooperate:
multi-dimensional arrays, decode boundaries inside regfiles, sibling blocks
at deeper decode depths, and CPU-interface unrolling.

Several of these are regression tests for cross-generator inconsistencies
found while building this suite, where the port list (from
``DesignState.get_addressable_children_at_depth``) disagreed with the
decoder/select-struct/fanout walkers about where the decode boundary sits.
Both sides now share the same boundary rules; these tests pin that down.
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

    def test_depth2_routes_arrayed_regfile_registers_per_element(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        """Regression: the decoder used to leak its depth counter and select the
        whole parent regfile (`cpuif_wr_sel.rf_b = 1'b1;`, an invalid
        struct-to-bit assignment) instead of the per-element `rc` array."""
        design = export_design(REGFILE_RDL, top="rfsoc", max_decode_depth=2)
        assigns = parse_decode_assigns(design.module_text, "wr")

        assert route(assigns, 0x100) == ["rf_b.rc[0]"]
        assert route(assigns, 0x104) == ["rf_b.rc[1]"]

        ports = parse_interface_master_ports(design.module_text)
        assert ports == {"ra": (), "rb": (), "rc": (2,)}
        assert parse_fanout_masters(design.module_text) == set(ports)

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

    def test_depth2_ports_agree_with_decode_targets(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        """Regression: the port list used to descend past the all-external
        boundary into the leaf addrmaps (emitting duplicate `m_apb_leaf0`/
        `m_apb_leaf1` ports) while decode/fanout stopped at the mid-level
        blocks and referenced undeclared `m_apb_mid_*` ports."""
        design = export_design(SIBLING_RDL, top="topblk", max_decode_depth=2)

        ports = parse_interface_master_ports(design.module_text)
        assert not any("#" in name for name in ports), f"duplicate ports: {ports}"

        decode_targets = {
            re.sub(r"\[\w+\]", "", a.target)
            for a in parse_decode_assigns(design.module_text, "wr")
            if a.target != "cpuif_err"
        }
        assert set(ports) == decode_targets == {"mid_a", "mid_b", "zero_reg"}
        assert parse_fanout_masters(design.module_text) == set(ports)

    def test_depth2_keeps_ports_for_shallow_registers(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        """Regression: a register shallower than max_decode_depth (zero_reg at
        depth 1 with depth=2) used to be silently dropped from the port list,
        leaving its addresses unreachable."""
        design = export_design(SIBLING_RDL, top="topblk", max_decode_depth=2)

        assigns = parse_decode_assigns(design.module_text, "wr")
        assert route(assigns, 0x2000) == ["zero_reg"]  # decoder handles it...

        ports = parse_interface_master_ports(design.module_text)
        assert "zero_reg" in ports  # ...so the module must expose its port


class TestCpuifUnroll:
    """cpuif_unroll semantics: master ports are unrolled into scalar
    interfaces (`m_apb_uarts_0`), while the internal select struct and
    decoder stay rolled (`uarts[2]` + for-loops). Fanout/fanin bridge the
    two with constant indices (`cpuif_wr_sel.uarts[0]` -> `m_apb_uarts_0`).

    Regression: fanout used to drive the rolled `m_apb_uarts[gi0]` interface
    array, which was never declared as a port, so the module did not
    elaborate."""

    def test_unrolled_ports_agree_with_fanout_and_struct(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(UNROLL_RDL, top="unroll_soc", cpuif_unroll=True)

        ports = parse_interface_master_ports(design.module_text)
        assert ports == {"uarts_0": (), "uarts_1": (), "ctrl": ()}

        fanout = parse_fanout_masters(design.module_text)
        assert fanout == set(ports)

        # The select struct stays rolled; fanout indexes it with constants
        sel_leaves = parse_sel_struct_leaves(design.module_text)
        assert sel_leaves == {"uarts": (2,), "ctrl": ()}
        assert "cpuif_wr_sel.uarts[0]|cpuif_rd_sel.uarts[0]" in design.module_text
        assert "m_apb_uarts[" not in design.module_text

    def test_unrolled_decode_still_routes_correctly(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(UNROLL_RDL, top="unroll_soc", cpuif_unroll=True)
        assigns = parse_decode_assigns(design.module_text, "wr")

        assert route(assigns, 0x000) == ["uarts[0]"]
        assert route(assigns, 0x100) == ["uarts[1]"]
        assert route(assigns, 0x1000) == ["ctrl"]

    def test_unrolled_fanin_reads_scalar_interfaces_directly(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(UNROLL_RDL, top="unroll_soc", cpuif_unroll=True)

        # Each element is a scalar interface, so no fanin intermediate
        # signals are needed and none may be left undriven.
        assert "uarts_fanin_ready" not in design.module_text
        assert "m_apb_uarts_0.PREADY" in design.module_text
        assert "m_apb_uarts_1.PREADY" in design.module_text


class TestPortNameCollisions:
    COLLIDE_RDL = """
    addrmap collide {
        regfile {
            reg { field { sw=rw; hw=r; } d[31:0]; } status @ 0x0;
        } blk_a @ 0x0;
        regfile {
            reg { field { sw=rw; hw=r; } d[31:0]; } status @ 0x0;
            reg { field { sw=rw; hw=r; } d[31:0]; } irq[2] @ 0x10 += 0x4;
        } blk_b @ 0x100;
        regfile {
            reg { field { sw=rw; hw=r; } d[31:0]; } irq[2] @ 0x0 += 0x4;
        } blk_c @ 0x200;
    };
    """

    def test_colliding_boundary_names_are_path_qualified(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        """Boundary nodes with the same instance name under different parents
        get path-qualified master ports instead of colliding declarations."""
        design = export_design(self.COLLIDE_RDL, top="collide", max_decode_depth=2)

        ports = parse_interface_master_ports(design.module_text)
        assert ports == {
            "blk_a_status": (),
            "blk_b_status": (),
            "blk_b_irq": (2,),
            "blk_c_irq": (2,),
        }
        assert parse_fanout_masters(design.module_text) == set(ports)

        # Decode/select stay hierarchical; only the port namespace is flattened
        assigns = parse_decode_assigns(design.module_text, "wr")
        assert route(assigns, 0x000) == ["blk_a.status"]
        assert route(assigns, 0x100) == ["blk_b.status"]
        assert route(assigns, 0x110) == ["blk_b.irq[0]"]
        assert route(assigns, 0x204) == ["blk_c.irq[1]"]

        # Qualified names carry through to array params, address-width
        # params, and fanin intermediate signals
        assert "N_BLK_B_IRQS" in design.module_text
        assert "COLLIDE_BLK_A_STATUS_ADDR_WIDTH" in design.package_text
        assert "blk_b_irq_fanin_ready" in design.module_text
        assert "m_apb_status" not in design.module_text
        assert "m_apb_irq " not in design.module_text

    def test_non_conflicting_names_stay_unqualified(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(REGFILE_RDL, top="rfsoc", max_decode_depth=2)
        assert parse_interface_master_ports(design.module_text) == {
            "ra": (),
            "rb": (),
            "rc": (2,),
        }

    def test_pathological_collisions_are_still_rejected(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        """If a literal instance name matches another node's qualified name,
        qualification cannot help and the exporter must reject the design."""
        rdl = """
        addrmap collide {
            regfile {
                reg { field { sw=rw; hw=r; } d[31:0]; } status @ 0x0;
            } blk_a @ 0x0;
            regfile {
                reg { field { sw=rw; hw=r; } d[31:0]; } status @ 0x0;
            } blk_b @ 0x100;
            reg { field { sw=rw; hw=r; } d[31:0]; } blk_a_status @ 0x200;
        };
        """
        from systemrdl import RDLCompileError

        with pytest.raises(RDLCompileError):
            export_design(rdl, top="collide", max_decode_depth=2)
