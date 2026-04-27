from contextlib import nullcontext
from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode, AddrmapNode, Node, RegNode
from systemrdl.walker import RDLListener, RDLWalker, WalkerAction

from .node_meta import NodeMeta
from .rdl_params import RdlParameterExtractor

if TYPE_CHECKING:
    from .design_state import DesignState


class DesignScanner(RDLListener):
    """
    Scans through the register model and validates that any unsupported features
    are not present.

    Also collects any information that is required prior to the start of the export process.
    """

    def __init__(self, ds: "DesignState") -> None:
        self.ds = ds
        self.msg = self.top_node.env.msg
        self.param_extractor: RdlParameterExtractor | None = (
            RdlParameterExtractor(self.top_node) if ds.parametrize else None
        )

    @property
    def top_node(self) -> AddrmapNode:
        return self.ds.top_node

    def do_scan(self) -> None:
        trace_cm = self.param_extractor.trace() if self.param_extractor else nullcontext()
        with trace_cm:
            RDLWalker().walk(self.top_node, self)
        if self.msg.had_error:
            self.msg.fatal("Unable to export due to previous errors")

    def _record_meta(self, node: Node) -> None:
        if not isinstance(node, AddressableNode):
            return

        addressable_children = [c for c in node.children() if isinstance(c, AddressableNode)]
        has_addressable_children = bool(addressable_children)
        has_only_external_addressable_children = has_addressable_children and all(
            c.external for c in addressable_children
        )

        array_strides: tuple[int, ...] | None
        if node.array_dimensions:
            assert node.array_stride is not None, "Array stride should be defined for arrayed components"
            # Stored innermost-first: [stride, stride*dim_last, stride*dim_last*dim_prev, ...].
            # Listener replays as append(strides[0]) then appendleft for the rest, matching
            # the original nested-stride bookkeeping exactly.
            strides_list: list[int] = [node.array_stride]
            current = node.array_stride
            for dim in node.array_dimensions[-1:0:-1]:
                current = current * dim
                strides_list.append(current)
            array_strides = tuple(strides_list)
        else:
            array_strides = None

        rel_path = "" if node is self.top_node else node.get_rel_path(self.top_node)

        self.ds._node_meta[node.get_path()] = NodeMeta(
            has_only_external_addressable_children=has_only_external_addressable_children,
            has_addressable_children=has_addressable_children,
            array_strides=array_strides,
            rel_path=rel_path,
        )

    def enter_Component(self, node: Node) -> WalkerAction:
        self._record_meta(node)

        if self.param_extractor is not None:
            self.param_extractor.reevaluate_node(node)
            self.param_extractor.record_arrayed_node(node)

        if node.external and (node != self.top_node):
            # Do not inspect external components' properties (none of my business),
            # but continue descending so per-node meta is populated for children
            # that downstream listeners will still visit.
            return WalkerAction.Continue

        # Collect any signals that are referenced by a property
        for prop_name in node.list_properties():
            _ = node.get_property(prop_name)

        return WalkerAction.Continue

    def enter_AddressableComponent(self, node: AddressableNode) -> None:
        if node.external and node != self.top_node:
            self.ds.has_external_addressable = True
            if not isinstance(node, RegNode):
                self.ds.has_external_block = True

    def enter_Reg(self, node: RegNode) -> None:
        if node.external and node != self.top_node:
            return

        accesswidth = node.get_property("accesswidth")
        if accesswidth is None:
            return

        if accesswidth > self.ds.cpuif_data_width:
            self.ds.cpuif_data_width = accesswidth
