from systemrdl.node import AddressableNode

from ..base_cpuif import BaseCpuif


class APB4CpuifFlat(BaseCpuif):
    template_path = "apb4_tmpl.sv"
    is_interface = False

    def _port_declaration(self, child: AddressableNode) -> list[str]:
        return [
            f"input  logic {self.signal('PCLK', child)}",
            f"input  logic {self.signal('PRESETn', child)}",
            f"input  logic {self.signal('PSELx', child)}",
            f"input  logic {self.signal('PENABLE', child)}",
            f"input  logic {self.signal('PWRITE', child)}",
            f"input  logic [{self.addr_width - 1}:0] {self.signal('PADDR', child)}",
            f"input  logic [2:0] {self.signal('PPROT', child)}",
            f"input  logic [{self.data_width - 1}:0] {self.signal('PWDATA', child)}",
            f"input  logic [{self.data_width // 8 - 1}:0] {self.signal('PSTRB', child)}",
            f"output logic [{self.data_width - 1}:0] {self.signal('PRDATA', child)}",
            f"output logic {self.signal('PREADY', child)}",
            f"output logic {self.signal('PSLVERR', child)}",
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
        if node is None:
            # Node is none, so this is a slave signal
            return f"s_apb_{signal}"

        # Master signal
        base = f"m_apb_{node.inst_name}"
        if not self.check_is_array(node):
            # Not an array or an unrolled element
            if node.current_idx is not None:
                # This is a specific instance of an unrolled array
                return f"{base}_{signal}_{'_'.join(map(str, node.current_idx))}"
            return f"{base}_{signal}"
        # Is an array
        if idx is not None:
            return f"{base}_{signal}[{idx}]"
        return f"{base}_{signal}[N_{node.inst_name.upper()}S]"
