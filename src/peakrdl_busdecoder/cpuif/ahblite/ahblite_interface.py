"""AHB-Lite port declarations and constant-index signal references."""

from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode

from ..interface import FlatInterface, SVInterface

if TYPE_CHECKING:
    from .ahblite_cpuif import AHBLiteCpuifFlat, _Target


class AHBLiteSVInterface(SVInterface):
    """AHB-Lite SystemVerilog interfaces, including hierarchical arrays."""

    cpuif: "AHBLiteCpuifFlat"

    def get_interface_type(self) -> str:
        return "ahblite_intf"

    def get_slave_name(self) -> str:
        return "s_ahb"

    def get_master_prefix(self) -> str:
        return "m_ahb_"

    def get_port_declaration(self, slave_name: str, master_prefix: str) -> str:
        ports = [f"ahblite_intf.slave {slave_name}"]
        for target in self.cpuif.targets:
            for indices in self.cpuif.port_indices(target):
                name = f"{master_prefix}{target.name}"
                if indices is not None:
                    name += "_" + "_".join(map(str, indices)) if indices else ""
                else:
                    name += "".join(f" [{dim.count}]" for dim in target.dimensions)
                ports.append(f"ahblite_intf.master {name}")
        return ",\n".join(ports)

    def target_signal(self, signal: str, target: "_Target", indices: tuple[int | str, ...]) -> str:
        name = f"m_ahb_{target.name}"
        if self.cpuif.unroll:
            name += "_" + "_".join(map(str, indices)) if indices else ""
        else:
            name += "".join(f"[{idx}]" for idx in indices)
        return f"{name}.{signal}"

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        indexer: str | int | None = None,
    ) -> str:
        if node is None:
            return f"s_ahb.{signal}"
        target = self.cpuif.target_for_node(node)
        return self.target_signal(signal, target, self.cpuif.signal_indices(target, node, indexer))


class AHBLiteFlatInterface(FlatInterface):
    """AHB-Lite flat ports with an explicit ingress clock and reset."""

    cpuif: "AHBLiteCpuifFlat"

    def get_slave_prefix(self) -> str:
        return "s_ahb_"

    def get_master_prefix(self) -> str:
        return "m_ahb_"

    def get_port_declaration(self, slave_name: str, master_prefix: str) -> str:
        ports = self._get_slave_port_declarations(slave_name)
        for target in self.cpuif.targets:
            ports.extend(self._get_master_port_declarations(target.node, master_prefix))
        return ",\n".join(ports)

    def target_signal(self, signal: str, target: "_Target", indices: tuple[int | str, ...]) -> str:
        name = f"m_ahb_{target.name}_{signal}"
        if self.cpuif.unroll:
            name += "_" + "_".join(map(str, indices)) if indices else ""
        else:
            name += "".join(f"[{idx}]" for idx in indices)
        return name

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        indexer: str | int | None = None,
    ) -> str:
        if node is None:
            return f"s_ahb_{signal}"
        target = self.cpuif.target_for_node(node)
        return self.target_signal(signal, target, self.cpuif.signal_indices(target, node, indexer))

    def _get_slave_port_declarations(self, slave_prefix: str) -> list[str]:
        return [
            f"input  logic {slave_prefix}HCLK",
            f"input  logic {slave_prefix}HRESETn",
            f"input  logic {slave_prefix}HSEL",
            f"input  logic {slave_prefix}HREADY",
            f"input  logic [{self.cpuif.addr_width - 1}:0] {slave_prefix}HADDR",
            f"input  logic [1:0] {slave_prefix}HTRANS",
            f"input  logic {slave_prefix}HWRITE",
            f"input  logic [2:0] {slave_prefix}HSIZE",
            f"input  logic [2:0] {slave_prefix}HBURST",
            f"input  logic [3:0] {slave_prefix}HPROT",
            f"input  logic {slave_prefix}HMASTLOCK",
            f"input  logic [{self.cpuif.data_width - 1}:0] {slave_prefix}HWDATA",
            f"output logic [{self.cpuif.data_width - 1}:0] {slave_prefix}HRDATA",
            f"output logic {slave_prefix}HREADYOUT",
            f"output logic {slave_prefix}HRESP",
        ]

    def _get_master_port_declarations(self, child: AddressableNode, master_prefix: str) -> list[str]:
        target = self.cpuif.target_for_node(child)
        ports: list[str] = []
        fields = [
            ("output", "", "HSEL"),
            ("output", "", "HREADY"),
            ("output", f"[{target.addr_width - 1}:0] ", "HADDR"),
            ("output", "[1:0] ", "HTRANS"),
            ("output", "", "HWRITE"),
            ("output", "[2:0] ", "HSIZE"),
            ("output", "[2:0] ", "HBURST"),
            ("output", "[3:0] ", "HPROT"),
            ("output", "", "HMASTLOCK"),
            ("output", f"[{self.cpuif.data_width - 1}:0] ", "HWDATA"),
            ("input ", f"[{self.cpuif.data_width - 1}:0] ", "HRDATA"),
            ("input ", "", "HREADYOUT"),
            ("input ", "", "HRESP"),
        ]
        for indices in self.cpuif.port_indices(target):
            suffix = ""
            if indices is not None:
                suffix = "_" + "_".join(map(str, indices)) if indices else ""
            dimensions = "" if indices is not None else "".join(f"[{dim.count}]" for dim in target.dimensions)
            for direction, width, signal in fields:
                ports.append(
                    f"{direction} logic {width}{master_prefix}{target.name}_{signal}{suffix}{dimensions}"
                )
        return ports
