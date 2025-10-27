from typing import overload

from systemrdl.node import AddressableNode

from .axi4_lite_cpuif import AXI4LiteCpuif


class AXI4LiteCpuifFlat(AXI4LiteCpuif):
    """Verilator-friendly variant that flattens the AXI4-Lite interface ports."""

    template_path = "axi4lite_tmpl.sv"
    is_interface = False

    def _port_declaration(self, child: AddressableNode) -> list[str]:
        return [
            f"input  logic {self.signal('AWREADY', child)}",
            f"output logic {self.signal('AWVALID', child)}",
            f"output logic [{self.addr_width - 1}:0] {self.signal('AWADDR', child)}",
            f"output logic [2:0] {self.signal('AWPROT', child)}",
            f"input  logic {self.signal('WREADY', child)}",
            f"output logic {self.signal('WVALID', child)}",
            f"output logic [{self.data_width - 1}:0] {self.signal('WDATA', child)}",
            f"output logic [{self.data_width_bytes - 1}:0] {self.signal('WSTRB', child)}",
            f"output logic {self.signal('BREADY', child)}",
            f"input  logic {self.signal('BVALID', child)}",
            f"input  logic [1:0] {self.signal('BRESP', child)}",
            f"input  logic {self.signal('ARREADY', child)}",
            f"output logic {self.signal('ARVALID', child)}",
            f"output logic [{self.addr_width - 1}:0] {self.signal('ARADDR', child)}",
            f"output logic [2:0] {self.signal('ARPROT', child)}",
            f"output logic {self.signal('RREADY', child)}",
            f"input  logic {self.signal('RVALID', child)}",
            f"input  logic [{self.data_width - 1}:0] {self.signal('RDATA', child)}",
            f"input  logic [1:0] {self.signal('RRESP', child)}",
        ]

    @property
    def port_declaration(self) -> str:
        slave_ports: list[str] = [
            f"input  logic {self.signal('ACLK')}",
            f"input  logic {self.signal('ARESETn')}",
            f"output logic {self.signal('AWREADY')}",
            f"input  logic {self.signal('AWVALID')}",
            f"input  logic [{self.addr_width - 1}:0] {self.signal('AWADDR')}",
            f"input  logic [2:0] {self.signal('AWPROT')}",
            f"output logic {self.signal('WREADY')}",
            f"input  logic {self.signal('WVALID')}",
            f"input  logic [{self.data_width - 1}:0] {self.signal('WDATA')}",
            f"input  logic [{self.data_width_bytes - 1}:0] {self.signal('WSTRB')}",
            f"input  logic {self.signal('BREADY')}",
            f"output logic {self.signal('BVALID')}",
            f"output logic [1:0] {self.signal('BRESP')}",
            f"output logic {self.signal('ARREADY')}",
            f"input  logic {self.signal('ARVALID')}",
            f"input  logic [{self.addr_width - 1}:0] {self.signal('ARADDR')}",
            f"input  logic [2:0] {self.signal('ARPROT')}",
            f"input  logic {self.signal('RREADY')}",
            f"output logic {self.signal('RVALID')}",
            f"output logic [{self.data_width - 1}:0] {self.signal('RDATA')}",
            f"output logic [1:0] {self.signal('RRESP')}",
        ]

        master_ports: list[str] = []
        for child in self.addressable_children:
            master_ports.extend(self._port_declaration(child))

        return ",\n".join(slave_ports + master_ports)

    @overload
    def signal(self, signal: str, node: None = None, indexer: None = None) -> str: ...

    @overload
    def signal(self, signal: str, node: AddressableNode, indexer: str) -> str: ...

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        indexer: str | None = None,
    ) -> str:
        if node is None:
            return f"s_axil_{signal}"

        base = f"m_axil_{node.inst_name}_{signal}"
        if not self.check_is_array(node):
            if node.current_idx is not None:
                return f"{base}_{'_'.join(map(str, node.current_idx))}"
            return base

        if indexer is None:
            return f"{base}[N_{node.inst_name.upper()}S]"
        return f"{base}[{indexer}]"
