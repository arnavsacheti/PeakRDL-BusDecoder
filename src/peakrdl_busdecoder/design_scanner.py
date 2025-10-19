from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode, AddrmapNode, Node, RegNode
from systemrdl.walker import RDLListener, RDLWalker, WalkerAction

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

    @property
    def top_node(self) -> AddrmapNode:
        return self.ds.top_node

    def do_scan(self) -> None:
        RDLWalker().walk(self.top_node, self)
        if self.msg.had_error:
            self.msg.fatal("Unable to export due to previous errors")

    def enter_Component(self, node: Node) -> WalkerAction:
        if node.external and (node != self.top_node):
            # Do not inspect external components. None of my business
            return WalkerAction.SkipDescendants

        # Collect any signals that are referenced by a property
        for prop_name in node.list_properties():
            _ = node.get_property(prop_name)

        return WalkerAction.Continue

    def enter_AddressableComponent(self, node: AddressableNode) -> None:
        if node.external and node != self.top_node:
            self.ds.has_external_addressable = True
            if not isinstance(node, RegNode):
                self.ds.has_external_block = True
