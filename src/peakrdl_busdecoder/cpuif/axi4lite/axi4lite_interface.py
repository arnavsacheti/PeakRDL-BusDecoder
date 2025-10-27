"""AXI4-Lite-specific interface implementations."""

from systemrdl.node import AddressableNode

from ..interface import FlatInterface, SVInterface


class AXI4LiteSVInterface(SVInterface):
    """AXI4-Lite SystemVerilog interface."""

    def get_interface_type(self) -> str:
        return "axi4lite_intf"

    def get_slave_name(self) -> str:
        return "s_axil"

    def get_master_prefix(self) -> str:
        return "m_axil_"


class AXI4LiteFlatInterface(FlatInterface):
    """AXI4-Lite flat signal interface."""

    def get_slave_prefix(self) -> str:
        return "s_axil_"

    def get_master_prefix(self) -> str:
        return "m_axil_"

    def _get_slave_port_declarations(self, slave_prefix: str) -> list[str]:
        return [
            # Write address channel
            f"input  logic {slave_prefix}AWVALID",
            f"output logic {slave_prefix}AWREADY",
            f"input  logic [{self.cpuif.addr_width - 1}:0] {slave_prefix}AWADDR",
            f"input  logic [2:0] {slave_prefix}AWPROT",
            # Write data channel
            f"input  logic {slave_prefix}WVALID",
            f"output logic {slave_prefix}WREADY",
            f"input  logic [{self.cpuif.data_width - 1}:0] {slave_prefix}WDATA",
            f"input  logic [{self.cpuif.data_width // 8 - 1}:0] {slave_prefix}WSTRB",
            # Write response channel
            f"output logic {slave_prefix}BVALID",
            f"input  logic {slave_prefix}BREADY",
            f"output logic [1:0] {slave_prefix}BRESP",
            # Read address channel
            f"input  logic {slave_prefix}ARVALID",
            f"output logic {slave_prefix}ARREADY",
            f"input  logic [{self.cpuif.addr_width - 1}:0] {slave_prefix}ARADDR",
            f"input  logic [2:0] {slave_prefix}ARPROT",
            # Read data channel
            f"output logic {slave_prefix}RVALID",
            f"input  logic {slave_prefix}RREADY",
            f"output logic [{self.cpuif.data_width - 1}:0] {slave_prefix}RDATA",
            f"output logic [1:0] {slave_prefix}RRESP",
        ]

    def _get_master_port_declarations(self, child: AddressableNode, master_prefix: str) -> list[str]:
        return [
            # Write address channel
            f"output logic {self.signal('AWVALID', child)}",
            f"input  logic {self.signal('AWREADY', child)}",
            f"output logic [{self.cpuif.addr_width - 1}:0] {self.signal('AWADDR', child)}",
            f"output logic [2:0] {self.signal('AWPROT', child)}",
            # Write data channel
            f"output logic {self.signal('WVALID', child)}",
            f"input  logic {self.signal('WREADY', child)}",
            f"output logic [{self.cpuif.data_width - 1}:0] {self.signal('WDATA', child)}",
            f"output logic [{self.cpuif.data_width // 8 - 1}:0] {self.signal('WSTRB', child)}",
            # Write response channel
            f"input  logic {self.signal('BVALID', child)}",
            f"output logic {self.signal('BREADY', child)}",
            f"input  logic [1:0] {self.signal('BRESP', child)}",
            # Read address channel
            f"output logic {self.signal('ARVALID', child)}",
            f"input  logic {self.signal('ARREADY', child)}",
            f"output logic [{self.cpuif.addr_width - 1}:0] {self.signal('ARADDR', child)}",
            f"output logic [2:0] {self.signal('ARPROT', child)}",
            # Read data channel
            f"input  logic {self.signal('RVALID', child)}",
            f"output logic {self.signal('RREADY', child)}",
            f"input  logic [{self.cpuif.data_width - 1}:0] {self.signal('RDATA', child)}",
            f"input  logic [1:0] {self.signal('RRESP', child)}",
        ]
