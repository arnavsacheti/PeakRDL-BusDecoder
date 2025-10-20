from systemrdl.node import AddressableNode

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif


class APB3Cpuif(BaseCpuif):
    template_path = "apb3_tmpl.sv"
    is_interface = True

    def _port_declaration(self, child: AddressableNode) -> str:
        base = f"apb3_intf.master m_apb_{child.inst_name}"
        if not child.is_array:
            return base
        if child.current_idx is not None:
            return f"{base}_{'_'.join(map(str, child.current_idx))}"
        return f"{base} [N_{child.inst_name.upper()}S]"

    @property
    def port_declaration(self) -> str:
        slave_ports: list[str] = ["apb3_intf.slave s_apb"]
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

    def fanout(self, node: AddressableNode, idx: str | None = None) -> str:
        fanout: dict[str, str] = {}
        fanout[self.signal("PSEL", node, idx)] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node)}|cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node)}"
        )
        fanout[self.signal("PSEL", node, idx)] = self.signal("PSEL")
        fanout[self.signal("PWRITE", node, idx)] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node)}"
        )
        fanout[self.signal("PADDR", node, idx)] = self.signal("PADDR")
        fanout[self.signal("PWDATA", node, idx)] = "cpuif_wr_data"

        return "\n".join(map(lambda kv: f"assign {kv[0]} = {kv[1]};", fanout.items()))

    def fanin(self, node: AddressableNode, idx: str | None = None) -> str:
        fanin: dict[str, str] = {}
        fanin["cpuif_rd_data"] = self.signal("PRDATA", node, idx)
        fanin["cpuif_rd_ack"] = self.signal("PREADY", node, idx)
        fanin["cpuif_rd_err"] = self.signal("PSLVERR", node, idx)

        return "\n".join(map(lambda kv: f"{kv[0]} = {kv[1]};", fanin.items()))
