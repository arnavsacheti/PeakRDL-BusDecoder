"""Shared APB3 / APB4 interface implementations.

Differences are driven by class attributes on the cpuif:
- ``apb_interface_type`` — SV interface type name ("apb3_intf" / "apb4_intf")
- ``has_pprot`` — include PPROT in the port list and signal table (APB4 only)
- ``has_pstrb`` — include PSTRB in the port list and signal table (APB4 only)
"""

from systemrdl.node import AddressableNode

from ...utils import clog2
from ..interface import FlatInterface, SVInterface


class APBSVInterface(SVInterface):
    """APB3/APB4 SystemVerilog interface."""

    def get_interface_type(self) -> str:
        return self.cpuif.apb_interface_type  # type: ignore[attr-defined]

    def get_slave_name(self) -> str:
        return self.cpuif.slave_name_sv

    def get_master_prefix(self) -> str:
        return self.cpuif.master_signal_prefix


class APBFlatInterface(FlatInterface):
    """APB3/APB4 flat signal interface."""

    def get_slave_prefix(self) -> str:
        return self.cpuif.slave_name_flat

    def get_master_prefix(self) -> str:
        return self.cpuif.master_signal_prefix

    def _get_slave_port_declarations(self, slave_prefix: str) -> list[str]:
        cpuif = self.cpuif
        ports: list[str] = []
        if cpuif.clk_src == "cpuif":
            ports += [
                f"input  logic {slave_prefix}PCLK",
                f"input  logic {slave_prefix}PRESETn",
            ]
        ports += [
            f"input  logic {slave_prefix}PSEL",
            f"input  logic {slave_prefix}PENABLE",
            f"input  logic {slave_prefix}PWRITE",
            f"input  logic [{cpuif.addr_width - 1}:0] {slave_prefix}PADDR",
        ]
        if cpuif.has_pprot:  # type: ignore[attr-defined]
            ports.append(f"input  logic [2:0] {slave_prefix}PPROT")
        ports.append(f"input  logic [{cpuif.data_width - 1}:0] {slave_prefix}PWDATA")
        if cpuif.has_pstrb:  # type: ignore[attr-defined]
            ports.append(f"input  logic [{cpuif.data_width // 8 - 1}:0] {slave_prefix}PSTRB")
        ports += [
            f"output logic [{cpuif.data_width - 1}:0] {slave_prefix}PRDATA",
            f"output logic {slave_prefix}PREADY",
            f"output logic {slave_prefix}PSLVERR",
        ]
        return ports

    def _get_master_port_declarations(self, child: AddressableNode, master_prefix: str) -> list[str]:
        cpuif = self.cpuif
        ports: list[str] = []
        if cpuif.clk_src == "cpuif":
            ports += [
                f"output logic {self.signal('PCLK', child)}",
                f"output logic {self.signal('PRESETn', child)}",
            ]
        ports += [
            f"output logic {self.signal('PSEL', child)}",
            f"output logic {self.signal('PENABLE', child)}",
            f"output logic {self.signal('PWRITE', child)}",
            f"output logic [{clog2(child.size) - 1}:0] {self.signal('PADDR', child)}",
        ]
        if cpuif.has_pprot:  # type: ignore[attr-defined]
            ports.append(f"output logic [2:0] {self.signal('PPROT', child)}")
        ports.append(f"output logic [{cpuif.data_width - 1}:0] {self.signal('PWDATA', child)}")
        if cpuif.has_pstrb:  # type: ignore[attr-defined]
            ports.append(f"output logic [{cpuif.data_width // 8 - 1}:0] {self.signal('PSTRB', child)}")
        ports += [
            f"input  logic [{cpuif.data_width - 1}:0] {self.signal('PRDATA', child)}",
            f"input  logic {self.signal('PREADY', child)}",
            f"input  logic {self.signal('PSLVERR', child)}",
        ]
        return ports
