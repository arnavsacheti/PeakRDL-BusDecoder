"""Interface abstraction for handling flat and non-flat signal declarations."""

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode

from ..utils import get_indexed_path

if TYPE_CHECKING:
    from .base_cpuif import BaseCpuif


class Interface(ABC):
    """Abstract base class for interface signal handling."""

    def __init__(self, cpuif: "BaseCpuif") -> None:
        self.cpuif = cpuif

    @property
    @abstractmethod
    def is_interface(self) -> bool:
        """Whether this uses SystemVerilog interfaces."""
        ...

    @abstractmethod
    def get_port_declaration(self, slave_name: str, master_prefix: str) -> str:
        """
        Generate port declarations for the interface.

        Args:
            slave_name: Name of the slave interface/signal prefix
            master_prefix: Prefix for master interfaces/signals

        Returns:
            Port declarations as a string
        """
        ...

    @abstractmethod
    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        indexer: str | int | None = None,
    ) -> str:
        """
        Generate signal reference.

        Args:
            signal: Signal name
            node: Optional addressable node for master signals
            indexer: Optional indexer for arrays.
                     For SVInterface: str like "i" or "gi" for loop indices
                     For FlatInterface: str or int for array subscript

        Returns:
            Signal reference as a string
        """
        ...


class SVInterface(Interface):
    """SystemVerilog interface-based signal handling."""

    @property
    def is_interface(self) -> bool:
        return True

    def get_port_declaration(self, slave_name: str, master_prefix: str) -> str:
        """Generate SystemVerilog interface port declarations."""
        slave_ports: list[str] = [f"{self.get_interface_type()}.slave {slave_name}"]
        master_ports: list[str] = []

        for child in self.cpuif.addressable_children:
            base = f"{self.get_interface_type()}.master {master_prefix}{child.inst_name}"

            # When unrolled, current_idx is set - append it to the name
            if child.current_idx is not None:
                base = f"{base}_{'_'.join(map(str, child.current_idx))}"

            # Only add array dimensions if this should be treated as an array
            if self.cpuif.check_is_array(child):
                assert child.array_dimensions is not None
                base = f"{base} {''.join(f'[{dim}]' for dim in child.array_dimensions)}"

            master_ports.append(base)

        return ",\n".join(slave_ports + master_ports)

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        indexer: str | int | None = None,
    ) -> str:
        """Generate SystemVerilog interface signal reference."""

        # SVInterface only supports string indexers (loop variable names like "i", "gi")
        if indexer is not None and not isinstance(indexer, str):
            raise TypeError(f"SVInterface.signal() requires string indexer, got {type(indexer).__name__}")

        if node is None or indexer is None:
            # Node is none, so this is a slave signal
            slave_name = self.get_slave_name()
            return f"{slave_name}.{signal}"

        # Master signal
        master_prefix = self.get_master_prefix()
        return f"{master_prefix}{get_indexed_path(node.parent, node, indexer, skip_kw_filter=True)}.{signal}"

    @abstractmethod
    def get_interface_type(self) -> str:
        """Get the SystemVerilog interface type name."""
        ...

    @abstractmethod
    def get_slave_name(self) -> str:
        """Get the slave interface instance name."""
        ...

    @abstractmethod
    def get_master_prefix(self) -> str:
        """Get the master interface name prefix."""
        ...


class FlatInterface(Interface):
    """Flat signal-based interface handling."""

    @property
    def is_interface(self) -> bool:
        return False

    def get_port_declaration(self, slave_name: str, master_prefix: str) -> str:
        """Generate flat port declarations."""
        slave_ports = self._get_slave_port_declarations(slave_name)
        master_ports: list[str] = []

        for child in self.cpuif.addressable_children:
            master_ports.extend(self._get_master_port_declarations(child, master_prefix))

        return ",\n".join(slave_ports + master_ports)

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        indexer: str | int | None = None,
    ) -> str:
        """Generate flat signal reference."""
        if node is None:
            # Node is none, so this is a slave signal
            slave_prefix = self.get_slave_prefix()
            return f"{slave_prefix}{signal}"

        # Master signal
        master_prefix = self.get_master_prefix()
        base = f"{master_prefix}{node.inst_name}"

        if not self.cpuif.check_is_array(node):
            # Not an array or an unrolled element
            if node.current_idx is not None:
                # This is a specific instance of an unrolled array
                return f"{base}_{signal}_{'_'.join(map(str, node.current_idx))}"
            return f"{base}_{signal}"

        # Is an array
        if indexer is not None:
            if isinstance(indexer, str):
                indexed_path = get_indexed_path(node.parent, node, indexer, skip_kw_filter=True)
                pattern = r"\[.*?\]"
                indexes = re.findall(pattern, indexed_path)

                return f"{base}_{signal}{''.join(indexes)}"

            return f"{base}_{signal}[{indexer}]"
        return f"{base}_{signal}[N_{node.inst_name.upper()}S]"

    @abstractmethod
    def _get_slave_port_declarations(self, slave_prefix: str) -> list[str]:
        """Get slave port declarations."""
        ...

    @abstractmethod
    def _get_master_port_declarations(self, child: AddressableNode, master_prefix: str) -> list[str]:
        """Get master port declarations for a child node."""
        ...

    @abstractmethod
    def get_slave_prefix(self) -> str:
        """Get the slave signal name prefix."""
        ...

    @abstractmethod
    def get_master_prefix(self) -> str:
        """Get the master signal name prefix."""
        ...
