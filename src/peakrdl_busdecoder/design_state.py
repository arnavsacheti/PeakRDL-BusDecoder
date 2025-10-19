from typing import TypedDict

from systemrdl.node import AddrmapNode
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
