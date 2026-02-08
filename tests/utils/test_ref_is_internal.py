from collections.abc import Callable

from systemrdl.node import AddrmapNode, Node
from systemrdl.rdltypes.references import PropertyReference

from peakrdl_busdecoder.utils import ref_is_internal


def _find_child_by_name(node: AddrmapNode, inst_name: str) -> Node:
    for child in node.children():
        if child.inst_name == inst_name:
            return child
    raise AssertionError(f"Child with name {inst_name} not found")


class TestRefIsInternal:
    """Tests for ref_is_internal utility."""

    def test_external_components_flagged(self, compile_rdl: Callable[..., AddrmapNode]) -> None:
        """External components should be treated as non-internal."""
        rdl_source = """
        reg reg_t {
            field { sw=rw; hw=r; } data[7:0];
        };

        addrmap top {
            external reg_t ext @ 0x0;
            reg_t intrnl @ 0x10;
        };
        """
        top = compile_rdl(rdl_source, top="top")

        internal_reg = _find_child_by_name(top, "intrnl")
        assert ref_is_internal(top, internal_reg) is True

        external_reg = _find_child_by_name(top, "ext")
        assert external_reg.external is True
        assert ref_is_internal(top, external_reg) is False

        external_prop_ref = PropertyReference.__new__(PropertyReference)
        external_prop_ref.node = external_reg
        assert ref_is_internal(top, external_prop_ref) is False

    def test_property_reference_without_node_defaults_internal(
        self, compile_rdl: Callable[..., AddrmapNode]
    ) -> None:
        """Root-level property references should be treated as internal."""
        rdl_source = """
        addrmap top {
            reg {
                field { sw=rw; hw=r; } data[7:0];
            } reg0 @ 0x0;
        };
        """
        top = compile_rdl(rdl_source, top="top")

        prop_ref = PropertyReference.__new__(PropertyReference)
        prop_ref.node = None

        assert ref_is_internal(top, prop_ref) is True
