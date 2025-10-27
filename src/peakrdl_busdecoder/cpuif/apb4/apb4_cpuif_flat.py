from systemrdl.node import AddressableNode

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif


class APB4CpuifFlat(BaseCpuif):
    template_path = "apb4_tmpl.sv"
    is_interface = False

    def _port_declaration(self, child: AddressableNode) -> list[str]:
        return [
            f"input  logic {self.signal('PCLK', child)}",
            f"input  logic {self.signal('PRESETn', child)}",
            f"output logic {self.signal('PSELx', child)}",
            f"output logic {self.signal('PENABLE', child)}",
            f"output logic {self.signal('PWRITE', child)}",
            f"output logic [{self.addr_width - 1}:0] {self.signal('PADDR', child)}",
            f"output logic [2:0] {self.signal('PPROT', child)}",
            f"output logic [{self.data_width - 1}:0] {self.signal('PWDATA', child)}",
            f"output logic [{self.data_width // 8 - 1}:0] {self.signal('PSTRB', child)}",
            f"input  logic [{self.data_width - 1}:0] {self.signal('PRDATA', child)}",
            f"input  logic {self.signal('PREADY', child)}",
            f"input  logic {self.signal('PSLVERR', child)}",
        ]

    @property
    def port_declaration(self) -> str:
        slave_ports: list[str] = [
            f"input  logic {self.signal('PCLK')}",
            f"input  logic {self.signal('PRESETn')}",
            f"input  logic {self.signal('PSELx')}",
            f"input  logic {self.signal('PENABLE')}",
            f"input  logic {self.signal('PWRITE')}",
            f"input  logic [{self.addr_width - 1}:0] {self.signal('PADDR')}",
            f"input  logic [2:0] {self.signal('PPROT')}",
            f"input  logic [{self.data_width - 1}:0] {self.signal('PWDATA')}",
            f"input  logic [{self.data_width // 8 - 1}:0] {self.signal('PSTRB')}",
            f"output logic [{self.data_width - 1}:0] {self.signal('PRDATA')}",
            f"output logic {self.signal('PREADY')}",
            f"output logic {self.signal('PSLVERR')}",
        ]
        master_ports: list[str] = []
        for child in self.addressable_children:
            master_ports.extend(self._port_declaration(child))

        return ",\n".join(slave_ports + master_ports)

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        idx: str | int | None = None,
    ) -> str:
        mapped_signal = "PSELx" if signal == "PSEL" else signal
        if node is None:
            # Node is none, so this is a slave signal
            return f"s_apb_{mapped_signal}"

        # Master signal
        base = f"m_apb_{node.inst_name}"
        if not self.check_is_array(node):
            # Not an array or an unrolled element
            if node.current_idx is not None:
                # This is a specific instance of an unrolled array
                return f"{base}_{mapped_signal}_{'_'.join(map(str, node.current_idx))}"
            return f"{base}_{mapped_signal}"
        # Is an array
        if idx is not None:
            return f"{base}_{mapped_signal}[{idx}]"
        return f"{base}_{mapped_signal}[N_{node.inst_name.upper()}S]"

    def fanout(self, node: AddressableNode) -> str:
        fanout: dict[str, str] = {}
        fanout[self.signal("PSELx", node)] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'i')}|cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node, 'i')}"
        )
        fanout[self.signal("PENABLE", node)] = self.signal("PENABLE")
        fanout[self.signal("PWRITE", node)] = (
            f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'i')}"
        )
        fanout[self.signal("PADDR", node)] = self.signal("PADDR")
        fanout[self.signal("PPROT", node)] = self.signal("PPROT")
        fanout[self.signal("PWDATA", node)] = "cpuif_wr_data"
        fanout[self.signal("PSTRB", node)] = "cpuif_wr_byte_en"

        return "\n".join(map(lambda kv: f"assign {kv[0]} = {kv[1]};", fanout.items()))

    def fanin(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_ack"] = "'0"
            fanin["cpuif_rd_err"] = "'0"
        else:
            fanin["cpuif_rd_ack"] = self.signal("PREADY", node)
            fanin["cpuif_rd_err"] = self.signal("PSLVERR", node)

        return "\n".join(map(lambda kv: f"{kv[0]} = {kv[1]};", fanin.items()))

    def readback(self, node: AddressableNode | None = None) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_data"] = "'0"
        else:
            fanin["cpuif_rd_data"] = self.signal("PRDATA", node)

        return "\n".join(map(lambda kv: f"{kv[0]} = {kv[1]};", fanin.items()))
