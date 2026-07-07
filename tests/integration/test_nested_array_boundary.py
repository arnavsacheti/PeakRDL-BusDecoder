"""Cross-generator tests for decode boundaries under rolled array ancestors.

Regression coverage for issues #56 and #57. When a decode boundary sits *below*
one or more rolled array ancestors, every generator stage must agree that the
boundary is an interface array sized by *all* open dimensions (ancestors' + its
own), and the loop-variable numbering (``i{k}`` / ``gi{k}``) must line up with
the stride order the address decoder uses.

- #56: loop-variable naming collisions and dropped ancestor dimensions
  (``blk[2].myreg[3]``) produced shadowed/undeclared loop indices, scalar
  ports for arrayed masters, and mis-sized fanin intermediates.
- #57: two rolled arrays with the same instance name under different parents
  (``group_a.bar[3]`` / ``group_b.bar[5]``) emitted duplicate module-scope
  identifiers (both the fanin intermediates and the select-struct typedefs).
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest
from systemrdl.messages import RDLCompileError
from systemrdl.node import AddressableNode, AddrmapNode, RegNode

from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif, APB4CpuifFlat
from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif

from .conftest import ExportedDesign
from .helpers import (
    parse_decode_assigns,
    parse_fanout_masters,
    parse_flat_master_ports,
    parse_interface_master_ports,
    parse_sel_struct_leaves,
    route,
)

# repro 1 (#56): a 1D array of registers under a 1D array of blocks.
NESTED_1D_RDL = """
addrmap top {
    addrmap outer_t {
        reg {regwidth=32; field {sw=rw; hw=r;} f;} myreg[3];
    } blk[2];
};
"""

# repro 2 (#57): same-named rolled arrays under sibling parents.
SIBLING_BAR_RDL = """
addrmap inner_a { reg {regwidth=32; field {sw=rw; hw=r;} f;} reg_a; };
addrmap inner_b { reg {regwidth=32; field {sw=rw; hw=r;} f;} reg_b; };
addrmap top {
    addrmap {
        reg {regwidth=32; field {sw=rw; hw=r;} f;} keep_internal;
        external inner_a bar[3];
    } group_a;
    addrmap {
        reg {regwidth=32; field {sw=rw; hw=r;} f;} keep_internal;
        external inner_b bar[5];
    } group_b;
};
"""

# 2D array of registers under a 1D array of blocks: pins the loop-number ->
# stride mapping for a boundary whose open dims interleave with an ancestor.
NESTED_1D_2D_RDL = """
addrmap top {
    addrmap outer2_t {
        reg {regwidth=32; field {sw=rw; hw=r;} f;} r2[2][3];
    } blk1[2];
};
"""


def _full_decode_expectations(top: AddrmapNode) -> list[tuple[int, str]]:
    """``(relative_address, decode_target)`` for every register, full decode.

    With ``max_decode_depth=0`` each register is its own decode boundary, so the
    expected select target is the register's full hierarchical path with
    concrete array indices, e.g. ``blk[0].myreg[1]`` -- exactly the form
    :func:`helpers.route` resolves loop indices to.
    """
    expectations: list[tuple[int, str]] = []

    def visit(node: AddressableNode) -> None:
        for child in node.children(unroll=True):
            if not isinstance(child, AddressableNode):
                continue
            if isinstance(child, RegNode):
                segments: list[str] = []
                walk: AddressableNode = child
                while walk is not top:
                    seg = walk.inst_name
                    for idx in walk.current_idx or []:
                        seg += f"[{idx}]"
                    segments.append(seg)
                    parent = walk.parent
                    assert isinstance(parent, AddressableNode)
                    walk = parent
                target = ".".join(reversed(segments))
                expectations.append((child.absolute_address - top.absolute_address, target))
            else:
                visit(child)

    visit(top)
    return expectations


def _module_logic_declarations(module_text: str) -> list[str]:
    """Identifier names of every module-scope ``logic ...;`` declaration.

    Only the module body is considered (after the port list closes), and
    ``typedef struct { ... }`` blocks are removed first so struct *fields*
    (which live in their own scope and may legitimately repeat across structs)
    are not counted. The identifier is the token immediately preceding the
    first array dimension or the terminating semicolon.
    """
    body = module_text[module_text.index(");") + 2 :]
    body = re.sub(r"typedef struct \{.*?\}\s*\w+;", "", body, flags=re.DOTALL)
    names: list[str] = []
    for m in re.finditer(r"^\s*logic\s+(?:\[[^\]]*\]\s*)?(?P<name>\w+)", body, re.MULTILINE):
        names.append(m.group("name"))
    return names


class TestNested1DArrayBoundary:
    """repro 1 (#56): ``blk[2].myreg[3]`` decoded at full depth."""

    def test_every_register_routes_to_its_own_boundary(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(NESTED_1D_RDL, top="top", max_decode_depth=0)
        expectations = _full_decode_expectations(design.top)
        assert len(expectations) == 2 * 3

        for flavor in ("wr", "rd"):
            assigns = parse_decode_assigns(design.module_text, flavor)
            for addr, target in expectations:
                assert route(assigns, addr) == [target], (
                    f"[{flavor}] address {addr:#x} should select {target}"
                )
            # A gap past the last register selects nothing but the error branch.
            assert route(assigns, 2 * 3 * 4) == ["cpuif_err"]

    def test_ports_intermediates_and_struct_carry_all_open_dims(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(NESTED_1D_RDL, top="top", max_decode_depth=0)

        # Port, select-struct leaf, and fanout all agree the boundary is 2x3.
        assert parse_interface_master_ports(design.module_text) == {"myreg": (2, 3)}
        assert parse_sel_struct_leaves(design.module_text) == {"blk.myreg": (2, 3)}
        assert parse_fanout_masters(design.module_text) == {"myreg"}

        # Fanin intermediates are declared exactly once, for the boundary only,
        # and sized by both open dimensions. No stray ancestor (``blk_*``) nets.
        decls = _module_logic_declarations(design.module_text)
        assert decls.count("myreg_fanin_ready") == 1
        assert not any(name.startswith("blk_fanin") for name in decls)
        assert "logic myreg_fanin_ready[2][3];" in design.module_text
        assert re.search(r"logic \[\d+:0\] myreg_fanin_data\[2\]\[3\];", design.module_text)

    def test_loop_indices_are_unique_and_declared(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        """#56 core symptom: inner loops shadowed / referenced undeclared vars."""
        design = export_design(NESTED_1D_RDL, top="top", max_decode_depth=0)
        # The fanin block used to emit `for i0 { for i0 { ... myreg[i1] } }`.
        assert "for (int i0 = 0; i0 < 2; i0++)" in design.module_text
        assert "for (int i1 = 0; i1 < 3; i1++)" in design.module_text
        # The old buggy decoder declared i2 but referenced i1.
        assert "i2" not in design.module_text

    @pytest.mark.parametrize(
        ("cpuif_cls", "select_signal"),
        [(APB4CpuifFlat, "PSEL")],
    )
    def test_flat_ports_carry_all_open_dims(
        self,
        export_design: Callable[..., ExportedDesign],
        cpuif_cls: type,
        select_signal: str,
    ) -> None:
        design = export_design(NESTED_1D_RDL, top="top", max_decode_depth=0, cpuif_cls=cpuif_cls)
        assert parse_flat_master_ports(design.module_text, select_signal) == {"myreg": (2, 3)}

    @pytest.mark.parametrize("cpuif_cls", [APB4Cpuif, AXI4LiteCpuif])
    def test_routing_is_cpuif_independent(
        self,
        export_design: Callable[..., ExportedDesign],
        cpuif_cls: type,
    ) -> None:
        design = export_design(NESTED_1D_RDL, top="top", max_decode_depth=0, cpuif_cls=cpuif_cls)
        assigns = parse_decode_assigns(design.module_text, "wr")
        for addr, target in _full_decode_expectations(design.top):
            assert route(assigns, addr) == [target]


class TestNested1D2DCounterMapping:
    """A 2D register array under a 1D block array pins loop-number/stride order."""

    def test_every_element_routes_by_all_three_indices(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(NESTED_1D_2D_RDL, top="top", max_decode_depth=0)
        expectations = _full_decode_expectations(design.top)
        assert len(expectations) == 2 * 2 * 3

        assigns = parse_decode_assigns(design.module_text, "wr")
        for addr, target in expectations:
            assert route(assigns, addr) == [target], f"address {addr:#x} should select {target}"

    def test_ports_and_struct_carry_three_dims(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(NESTED_1D_2D_RDL, top="top", max_decode_depth=0)
        assert parse_interface_master_ports(design.module_text) == {"r2": (2, 2, 3)}
        assert parse_sel_struct_leaves(design.module_text) == {"blk1.r2": (2, 2, 3)}
        # Three distinct, sequentially-numbered loop indices.
        for var in ("i0", "i1", "i2"):
            assert f"for (int {var} = 0;" in design.module_text


class TestSiblingSameNameArrays:
    """repro 2 (#57): ``group_a.bar[3]`` and ``group_b.bar[5]``."""

    @pytest.mark.parametrize("cpuif_cls", [APB4Cpuif, AXI4LiteCpuif])
    def test_no_module_scope_identifier_declared_twice(
        self,
        export_design: Callable[..., ExportedDesign],
        cpuif_cls: type,
    ) -> None:
        design = export_design(SIBLING_BAR_RDL, top="top", max_decode_depth=0, cpuif_cls=cpuif_cls)

        decls = _module_logic_declarations(design.module_text)
        duplicates = {name for name in decls if decls.count(name) > 1}
        assert not duplicates, f"duplicate module-scope logic declarations: {duplicates}"

        # The pre-fix bug: one `bar_fanin_ready[3]` and one `bar_fanin_ready[5]`.
        assert "bar_fanin_ready" not in decls

        # Select-struct typedefs must also be unique (no duplicate
        # `cpuif_sel_bar_t`).
        typedef_names = re.findall(r"\}\s*(cpuif_sel_\w+_t);", design.module_text)
        assert len(typedef_names) == len(set(typedef_names)), (
            f"duplicate select-struct typedefs: {typedef_names}"
        )

    def test_boundary_ports_are_per_register_and_sized_by_bar(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(SIBLING_BAR_RDL, top="top", max_decode_depth=0)
        ports = parse_interface_master_ports(design.module_text)
        assert ports == {
            "group_a_keep_internal": (),
            "reg_a": (3,),
            "group_b_keep_internal": (),
            "reg_b": (5,),
        }
        # Per-boundary intermediates, sized by the enclosing bar dimension.
        assert "logic reg_a_fanin_ready[3];" in design.module_text
        assert "logic reg_b_fanin_ready[5];" in design.module_text

    def test_fanout_and_fanin_agree_with_ports(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        design = export_design(SIBLING_BAR_RDL, top="top", max_decode_depth=0)
        ports = set(parse_interface_master_ports(design.module_text))
        assert parse_fanout_masters(design.module_text) == ports


class TestUnrollNestedArrayBoundary:
    """``cpuif_unroll`` unrolls each array element into a scalar master port.

    Under a rolled-array *ancestor* the unrolled leaf names collide (every
    ``blk[k].myreg[j]`` reduces to ``myreg_j``), so this combination cannot be
    expressed with unique scalar ports. Rather than emit broken SystemVerilog,
    the design validator rejects it up front. Rolled mode (the default) is the
    supported way to decode below a rolled array ancestor and is covered above.
    """

    def test_unroll_below_array_ancestor_is_rejected(
        self, export_design: Callable[..., ExportedDesign]
    ) -> None:
        with pytest.raises(RDLCompileError):
            export_design(NESTED_1D_RDL, top="top", max_decode_depth=0, cpuif_unroll=True)
