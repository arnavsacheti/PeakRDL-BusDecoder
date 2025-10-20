from systemrdl.node import AddressableNode

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif


class APB4Cpuif(BaseCpuif):
    template_path = "apb4_tmpl.sv"
    is_interface = True

    def _port_declaration(self, child: AddressableNode) -> str:
        base = f"apb4_intf.master m_apb_{child.inst_name}"
        if not child.is_array:
            return base
        if child.current_idx is not None:
            return f"{base}_{'_'.join(map(str, child.current_idx))} [N_{child.inst_name.upper()}S]"
        return f"{base} [N_{child.inst_name.upper()}S]"

    @property
    def port_declaration(self) -> str:
        """Returns the port declaration for the APB4 interface."""
        slave_ports: list[str] = ["apb4_intf.slave s_apb"]
        master_ports: list[str] = list(map(self._port_declaration, self.addressable_children))

        return ",\n".join(slave_ports + master_ports)

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
    ) -> str:
        if node is None:
            # Node is none, so this is a slave signal
            return f"s_apb.{signal}"

        # Master signal
        return f"m_apb_{node.inst_name}.{signal}"

    def fanout(self, node: AddressableNode) -> str:
        fanout: dict[str, str] = {}
        fanout[f"m_apb_{get_indexed_path(node.parent, node, 'gi')}.PSEL"] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node)}|cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node)}"
        )
        fanout[f"m_apb_{get_indexed_path(node.parent, node, 'gi')}.PSEL"] = self.signal("PSEL")
        fanout[f"m_apb_{get_indexed_path(node.parent, node, 'gi')}.PWRITE"] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        )
        fanout[f"m_apb_{get_indexed_path(node.parent, node, 'gi')}.PADDR"] = self.signal("PADDR")
        fanout[f"m_apb_{get_indexed_path(node.parent, node, 'gi')}.PPROT"] = self.signal("PPROT")
        fanout[f"m_apb_{get_indexed_path(node.parent, node, 'gi')}.PWDATA"] = "cpuif_wr_data"
        fanout[f"m_apb_{get_indexed_path(node.parent, node, 'gi')}.PSTRB"] = "cpuif_wr_byte_en"

        return "\n".join(map(lambda kv: f"assign {kv[0]} = {kv[1]};", fanout.items()))

    def fanin(self, node: AddressableNode) -> str:
        fanin: dict[str, str] = {}
        fanin["cpuif_rd_data"] = self.signal("PRDATA", node)
        fanin["cpuif_rd_ack"] = self.signal("PREADY", node)
        fanin["cpuif_rd_err"] = self.signal("PSLVERR", node)

        return "\n".join(map(lambda kv: f"{kv[0]} = {kv[1]};", fanin.items()))
