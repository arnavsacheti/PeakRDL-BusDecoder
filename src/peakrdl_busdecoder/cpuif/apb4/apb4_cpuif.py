from typing import overload

from systemrdl.node import AddressableNode

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif


class APB4Cpuif(BaseCpuif):
    template_path = "apb4_tmpl.sv"
    is_interface = True

    def _port_declaration(self, child: AddressableNode) -> str:
        base = f"apb4_intf.master m_apb_{child.inst_name}"
        
        # When unrolled, current_idx is set - append it to the name
        if child.current_idx is not None:
            base = f"{base}_{'_'.join(map(str, child.current_idx))}"
        
        # Only add array dimensions if this should be treated as an array
        if self.check_is_array(child):
            return f"{base} {''.join(f'[{dim}]' for dim in child.array_dimensions)}"
        
        return base

    @property
    def port_declaration(self) -> str:
        """Returns the port declaration for the APB4 interface."""
        slave_ports: list[str] = ["apb4_intf.slave s_apb"]
        master_ports: list[str] = list(map(self._port_declaration, self.addressable_children))

        return ",\n".join(slave_ports + master_ports)

    @overload
    def signal(self, signal: str, node: None = None, indexer: None = None) -> str: ...
    @overload
    def signal(self, signal: str, node: AddressableNode, indexer: str) -> str: ...
    def signal(self, signal: str, node: AddressableNode | None = None, indexer: str | None = None) -> str:
        if node is None or indexer is None:
            # Node is none, so this is a slave signal
            return f"s_apb.{signal}"

        # Master signal
        return f"m_apb_{get_indexed_path(node.parent, node, indexer, skip_kw_filter=True)}.{signal}"

    def fanout(self, node: AddressableNode) -> str:
        fanout: dict[str, str] = {}
        fanout[self.signal("PSEL", node, "gi")] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}|cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        )
        fanout[self.signal("PENABLE", node, "gi")] = self.signal("PENABLE")
        fanout[self.signal("PWRITE", node, "gi")] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        )
        fanout[self.signal("PADDR", node, "gi")] = self.signal("PADDR")
        fanout[self.signal("PPROT", node, "gi")] = self.signal("PPROT")
        fanout[self.signal("PWDATA", node, "gi")] = "cpuif_wr_data"
        fanout[self.signal("PSTRB", node, "gi")] = "cpuif_wr_byte_en"

        return "\n".join(map(lambda kv: f"assign {kv[0]} = {kv[1]};", fanout.items()))

    def fanin(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_ack"] = "'0"
            fanin["cpuif_rd_err"] = "'0"
        else:
            fanin["cpuif_rd_ack"] = self.signal("PREADY", node, "i")
            fanin["cpuif_rd_err"] = self.signal("PSLVERR", node, "i")

        return "\n".join(map(lambda kv: f"{kv[0]} = {kv[1]};", fanin.items()))

    def readback(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_data"] = "'0"
        else:
            fanin["cpuif_rd_data"] = self.signal("PRDATA", node, "i")

        return "\n".join(map(lambda kv: f"{kv[0]} = {kv[1]};", fanin.items()))
