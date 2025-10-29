from typing import TypedDict

from systemrdl.node import AddressableNode, AddrmapNode
from systemrdl.rdltypes.user_enum import UserEnum

from .design_scanner import DesignScanner
from .identifier_filter import kw_filter as kwf
from .utils import clog2


class DesignStateKwargs(TypedDict, total=False):
    reuse_hwif_typedefs: bool
    module_name: str
    package_name: str
    address_width: int
    cpuif_unroll: bool
    max_decode_depth: int


class DesignState:
    """
    Dumping ground for all sorts of variables that are relevant to a particular
    design.
    """

    def __init__(self, top_node: AddrmapNode, kwargs: DesignStateKwargs) -> None:
        self.top_node = top_node
        msg = top_node.env.msg

        # ------------------------
        # Extract compiler args
        # ------------------------
        self.reuse_hwif_typedefs: bool = kwargs.pop("reuse_hwif_typedefs", True)
        self.module_name: str = kwargs.pop("module_name", None) or kwf(self.top_node.inst_name)
        self.package_name: str = kwargs.pop("package_name", None) or f"{self.module_name}_pkg"
        user_addr_width: int | None = kwargs.pop("address_width", None)

        self.cpuif_unroll: bool = kwargs.pop("cpuif_unroll", False)
        self.max_decode_depth: int = kwargs.pop("max_decode_depth", 1)

        # ------------------------
        # Info about the design
        # ------------------------
        self.cpuif_data_width = 0

        # Track any referenced enums
        self.user_enums: list[type[UserEnum]] = []

        self.has_external_addressable = False
        self.has_external_block = False

        # Scan the design to fill in above variables
        DesignScanner(self).do_scan()

        if self.cpuif_data_width == 0:
            # Scanner did not find any registers in the design being exported,
            # so the width is not known.
            # Assume 32-bits
            msg.warning(
                "Addrmap being exported only contains external components. Unable to infer the CPUIF bus width. Assuming 32-bits.",
                self.top_node.inst.def_src_ref,
            )
            self.cpuif_data_width = 32

        # ------------------------
        # Min address width encloses the total size AND at least 1 useful address bit
        self.addr_width = max(clog2(self.top_node.size), clog2(self.cpuif_data_width // 8) + 1)

        if user_addr_width is None:
            return

        if user_addr_width < self.addr_width:
            msg.fatal(f"User-specified address width shall be greater than or equal to {self.addr_width}.")
        self.addr_width = user_addr_width

    def get_addressable_children_at_depth(self, unroll: bool = False) -> list[AddressableNode]:
        """
        Get addressable children at the decode boundary based on max_decode_depth.

        max_decode_depth semantics:
        - 0: decode all levels (return leaf registers)
        - 1: decode only top level (return children at depth 1)
        - 2: decode top + 1 level (return children at depth 2)
        - N: decode down to depth N (return children at depth N)

        Args:
            unroll: Whether to unroll arrayed nodes

        Returns:
            List of addressable nodes at the decode boundary
        """
        from systemrdl.node import RegNode

        def collect_nodes(node: AddressableNode, current_depth: int) -> list[AddressableNode]:
            """Recursively collect nodes at the decode boundary."""
            result: list[AddressableNode] = []

            # For depth 0, collect all leaf registers
            if self.max_decode_depth == 0:
                # If this is a register, it's a leaf
                if isinstance(node, RegNode):
                    result.append(node)
                else:
                    # Recurse into children
                    for child in node.children(unroll=unroll):
                        if isinstance(child, AddressableNode):
                            result.extend(collect_nodes(child, current_depth + 1))
            else:
                # For depth N, collect children at depth N
                if current_depth == self.max_decode_depth:
                    # We're at the decode boundary - return this node
                    result.append(node)
                elif current_depth < self.max_decode_depth:
                    # We haven't reached the boundary yet - recurse
                    for child in node.children(unroll=unroll):
                        if isinstance(child, AddressableNode):
                            result.extend(collect_nodes(child, current_depth + 1))

            return result

        # Start collecting from top node's children
        nodes: list[AddressableNode] = []
        for child in self.top_node.children(unroll=unroll):
            if isinstance(child, AddressableNode):
                nodes.extend(collect_nodes(child, 1))

        return nodes
