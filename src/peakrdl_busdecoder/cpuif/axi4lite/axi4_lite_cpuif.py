from collections import deque
from typing import TYPE_CHECKING, overload

from systemrdl.node import AddressableNode

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif
from .axi4_lite_interface import AXI4LiteSVInterface

if TYPE_CHECKING:
    from ...exporter import BusDecoderExporter


class AXI4LiteCpuif(BaseCpuif):
    template_path = "axi4_lite_tmpl.sv"

    def __init__(self, exp: "BusDecoderExporter") -> None:
        super().__init__(exp)
        self._interface = AXI4LiteSVInterface(self)

    @property
    def is_interface(self) -> bool:
        return self._interface.is_interface

    @property
    def port_declaration(self) -> str:
        """Returns the port declaration for the AXI4-Lite interface."""
        return self._interface.get_port_declaration("s_axil", "m_axil_")

    @overload
    def signal(self, signal: str, node: None = None, indexer: None = None) -> str: ...
    @overload
    def signal(self, signal: str, node: AddressableNode, indexer: str | None = None) -> str: ...
    def signal(self, signal: str, node: AddressableNode | None = None, indexer: str | None = None) -> str:
        return self._interface.signal(signal, node, indexer)

    def fanout(self, node: AddressableNode, array_stack: deque[int]) -> str:
        fanout: dict[str, str] = {}

        idx = "gi" if self.check_is_array(node) else None
        wr_sel = f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        rd_sel = f"cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"

        # Write address channel
        fanout[self.signal("AWVALID", node, idx)] = wr_sel
        fanout[self.signal("AWADDR", node, idx)] = self.signal("AWADDR")
        fanout[self.signal("AWPROT", node, idx)] = self.signal("AWPROT")

        # Write data channel
        fanout[self.signal("WVALID", node, idx)] = wr_sel
        fanout[self.signal("WDATA", node, idx)] = "cpuif_wr_data"
        fanout[self.signal("WSTRB", node, idx)] = "cpuif_wr_byte_en"

        # Write response channel (master -> slave)
        fanout[self.signal("BREADY", node, idx)] = self.signal("BREADY")

        # Read address channel
        fanout[self.signal("ARVALID", node, idx)] = rd_sel
        fanout[self.signal("ARADDR", node, idx)] = self.signal("ARADDR")
        fanout[self.signal("ARPROT", node, idx)] = self.signal("ARPROT")

        # Read data channel (master -> slave)
        fanout[self.signal("RREADY", node, idx)] = self.signal("RREADY")

        return "\n".join(f"assign {lhs} = {rhs};" for lhs, rhs in fanout.items())

    def fanin(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_ack"] = "'0"
            fanin["cpuif_rd_err"] = "'0"
        else:
            # Use intermediate signals for interface arrays to avoid
            # non-constant indexing of interface arrays in procedural blocks
            is_array = self.check_is_array(node)
            if self.is_interface and is_array and node.array_dimensions:
                # Generate array index string [i0][i1]... for the intermediate signal
                array_idx = "".join(f"[i{i}]" for i in range(len(node.array_dimensions)))
                fanin["cpuif_rd_ack"] = f"{node.inst_name}_fanin_ready{array_idx}"
                fanin["cpuif_rd_err"] = f"{node.inst_name}_fanin_err{array_idx}"
            else:
                # Read side: ack comes from RVALID; err if RRESP[1] is set (SLVERR/DECERR)
                idx = "i" if self.check_is_array(node) else None
                fanin["cpuif_rd_ack"] = self.signal("RVALID", node, idx)
                fanin["cpuif_rd_err"] = f"{self.signal('RRESP', node, idx)}[1]"

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())

    def readback(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_data"] = "'0"
        else:
            # Use intermediate signals for interface arrays to avoid
            # non-constant indexing of interface arrays in procedural blocks
            is_array = self.check_is_array(node)
            if self.is_interface and is_array and node.array_dimensions:
                # Generate array index string [i0][i1]... for the intermediate signal
                array_idx = "".join(f"[i{i}]" for i in range(len(node.array_dimensions)))
                fanin["cpuif_rd_data"] = f"{node.inst_name}_fanin_data{array_idx}"
            else:
                idx = "i" if self.check_is_array(node) else None
                fanin["cpuif_rd_data"] = self.signal("RDATA", node, idx)

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())

    def fanin_intermediate_assignments(
        self, node: AddressableNode, inst_name: str, array_idx: str, master_prefix: str, indexed_path: str
    ) -> list[str]:
        """Generate intermediate signal assignments for AXI4-Lite interface arrays."""
        return [
            f"assign {inst_name}_fanin_ready{array_idx} = {master_prefix}{indexed_path}.RVALID;",
            f"assign {inst_name}_fanin_err{array_idx} = {master_prefix}{indexed_path}.RRESP[1];",
            f"assign {inst_name}_fanin_data{array_idx} = {master_prefix}{indexed_path}.RDATA;",
        ]
