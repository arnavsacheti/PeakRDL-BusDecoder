"""Interface abstraction for handling flat and non-flat signal declarations."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode

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

    slave_modport_name = "slave"
    master_modport_name = "master"

    @property
    def is_interface(self) -> bool:
        return True

    def get_port_declaration(self, slave_name: str, master_prefix: str) -> str:
        """Generate SystemVerilog interface port declarations."""
        slave_ports: list[str] = [f"{self.get_interface_type()}.{self.slave_modport_name} {slave_name}"]
        master_ports: list[str] = []

        for child in self.cpuif.addressable_children:
            target_name = self.cpuif.exp.ds.get_target_name(child)
            base = f"{self.get_interface_type()}.{self.master_modport_name} {master_prefix}{target_name}"

            indices = self.cpuif.exp.ds.unrolled_indices(child)
            if indices:
                base = f"{base}_{'_'.join(map(str, indices))}"

            # Size the interface array by *all* open dimensions (rolled array
            # ancestors' + the node's own), so a boundary under array ancestors
            # gets one interface per element.
            dims = self.cpuif.master_array_dims(child)
            if dims:
                base = f"{base} {''.join(f'[{dim}]' for dim in dims)}"

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
        target_name = self.cpuif.exp.ds.get_target_name(node)
        indices = self.cpuif.exp.ds.unrolled_indices(node)
        if indices:
            target_name += f"_{'_'.join(map(str, indices))}"
        brackets = self.cpuif.open_dim_index(node, indexer) if self.cpuif.is_master_array(node) else ""
        return f"{master_prefix}{target_name}{brackets}.{signal}"

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
        target_name = self.cpuif.exp.ds.get_target_name(node)
        base = f"{master_prefix}{target_name}"

        if not self.cpuif.is_master_array(node):
            # Not an array or an unrolled element
            indices = self.cpuif.exp.ds.unrolled_indices(node)
            if indices:
                return f"{base}_{signal}_{'_'.join(map(str, indices))}"
            return f"{base}_{signal}"

        # Is an array (possibly by virtue of rolled array ancestors)
        if indexer is not None:
            if isinstance(indexer, str):
                brackets = self.cpuif.open_dim_index(node, indexer)
                return f"{base}_{signal}{brackets}"

            return f"{base}_{signal}[{indexer}]"
        # Declarations are sized by every open ancestor and target dimension.
        dims = self.cpuif.master_array_dims(node)
        return f"{base}_{signal}" + "".join(f"[{dim}]" for dim in dims)

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
