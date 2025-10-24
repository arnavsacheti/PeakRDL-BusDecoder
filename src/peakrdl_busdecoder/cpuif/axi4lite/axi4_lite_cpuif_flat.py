from typing import overload

from systemrdl.node import AddressableNode

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif


class AXI4LiteCpuifFlat(BaseCpuif):
    template_path = "axi4lite_tmpl.sv"
    is_interface = True

    def _port_declaration(self, child: AddressableNode) -> str:
        base = f"axi4lite_intf.master m_axil_{child.inst_name}"

        # When unrolled, current_idx is set - append it to the name
        if child.current_idx is not None:
            base = f"{base}_{'_'.join(map(str, child.current_idx))}"

        # Only add array dimensions if this should be treated as an array
        if self.check_is_array(child):
            return f"{base} {''.join(f'[{dim}]' for dim in child.array_dimensions)}"

        return base

    @property
    def port_declaration(self) -> str:
        """Returns the port declaration for the AXI4-Lite interface."""
        slave_ports: list[str] = ["axi4lite_intf.slave s_axil"]
        master_ports: list[str] = list(map(self._port_declaration, self.addressable_children))

        return ",\n".join(slave_ports + master_ports)

    @overload
    def signal(self, signal: str, node: None = None, indexer: None = None) -> str: ...
    @overload
    def signal(self, signal: str, node: AddressableNode, indexer: str) -> str: ...
    def signal(self, signal: str, node: AddressableNode | None = None, indexer: str | None = None) -> str:
        if node is None or indexer is None:
            # Node is none, so this is a slave signal
            return f"s_axil.{signal}"

        # Master signal
        return f"m_axil_{get_indexed_path(node.parent, node, indexer, skip_kw_filter=True)}.{signal}"

    def fanout(self, node: AddressableNode) -> str:
        fanout: dict[str, str] = {}

        wr_sel = f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        rd_sel = f"cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"

        # Write address channel
        fanout[self.signal("AWVALID", node, "gi")] = wr_sel
        fanout[self.signal("AWADDR", node, "gi")] = self.signal("AWADDR")
        fanout[self.signal("AWPROT", node, "gi")] = self.signal("AWPROT")

        # Write data channel
        fanout[self.signal("WVALID", node, "gi")] = wr_sel
        fanout[self.signal("WDATA", node, "gi")] = "cpuif_wr_data"
        fanout[self.signal("WSTRB", node, "gi")] = "cpuif_wr_byte_en"

        # Write response channel (master -> slave)
        fanout[self.signal("BREADY", node, "gi")] = self.signal("BREADY")

        # Read address channel
        fanout[self.signal("ARVALID", node, "gi")] = rd_sel
        fanout[self.signal("ARADDR", node, "gi")] = self.signal("ARADDR")
        fanout[self.signal("ARPROT", node, "gi")] = self.signal("ARPROT")

        # Read data channel (master -> slave)
        fanout[self.signal("RREADY", node, "gi")] = self.signal("RREADY")

        return "\n".join(f"assign {lhs} = {rhs};" for lhs, rhs in fanout.items())

    def fanin(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_ack"] = "'0"
            fanin["cpuif_rd_err"] = "'0"
        else:
            # Read side: ack comes from RVALID; err if RRESP[1] is set (SLVERR/DECERR)
            fanin["cpuif_rd_ack"] = self.signal("RVALID", node, "i")
            fanin["cpuif_rd_err"] = f"{self.signal('RRESP', node, 'i')}[1]"

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())

    def readback(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_data"] = "'0"
        else:
            fanin["cpuif_rd_data"] = self.signal("RDATA", node, "i")

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())
