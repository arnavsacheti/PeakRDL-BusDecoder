"""APB4-specific interface implementations."""

from systemrdl.node import AddressableNode

from ..interface import FlatInterface, SVInterface


class APB4SVInterface(SVInterface):
    """APB4 SystemVerilog interface."""

    def get_interface_type(self) -> str:
        return "apb4_intf"

    def get_slave_name(self) -> str:
        return "s_apb"

    def get_master_prefix(self) -> str:
        return "m_apb_"


class APB4FlatInterface(FlatInterface):
    """APB4 flat signal interface."""

    def get_slave_prefix(self) -> str:
        return "s_apb_"

    def get_master_prefix(self) -> str:
        return "m_apb_"

    def _get_slave_port_declarations(self, slave_prefix: str) -> list[str]:
        return [
            f"input  logic {slave_prefix}PCLK",
            f"input  logic {slave_prefix}PRESETn",
            f"input  logic {slave_prefix}PSEL",
            f"input  logic {slave_prefix}PENABLE",
            f"input  logic {slave_prefix}PWRITE",
            f"input  logic [{self.cpuif.addr_width - 1}:0] {slave_prefix}PADDR",
            f"input  logic [2:0] {slave_prefix}PPROT",
            f"input  logic [{self.cpuif.data_width - 1}:0] {slave_prefix}PWDATA",
            f"input  logic [{self.cpuif.data_width // 8 - 1}:0] {slave_prefix}PSTRB",
            f"output logic [{self.cpuif.data_width - 1}:0] {slave_prefix}PRDATA",
            f"output logic {slave_prefix}PREADY",
            f"output logic {slave_prefix}PSLVERR",
        ]

    def _get_master_port_declarations(self, child: AddressableNode, master_prefix: str) -> list[str]:
        return [
            f"output logic {self.signal('PCLK', child)}",
            f"output logic {self.signal('PRESETn', child)}",
            f"output logic {self.signal('PSEL', child)}",
            f"output logic {self.signal('PENABLE', child)}",
            f"output logic {self.signal('PWRITE', child)}",
            f"output logic [{self.cpuif.addr_width - 1}:0] {self.signal('PADDR', child)}",
            f"output logic [2:0] {self.signal('PPROT', child)}",
            f"output logic [{self.cpuif.data_width - 1}:0] {self.signal('PWDATA', child)}",
            f"output logic [{self.cpuif.data_width // 8 - 1}:0] {self.signal('PSTRB', child)}",
            f"input  logic [{self.cpuif.data_width - 1}:0] {self.signal('PRDATA', child)}",
            f"input  logic {self.signal('PREADY', child)}",
            f"input  logic {self.signal('PSLVERR', child)}",
        ]
