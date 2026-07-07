"""Interface abstraction for handling flat and non-flat signal declarations."""

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode

from ..utils import get_indexed_path

if TYPE_CHECKING:
    from .base_cpuif import BaseCpuif


def _open_dim_brackets(top_node: AddressableNode, node: AddressableNode, indexer: str) -> str:
    """Bracket-index string covering every open array dimension of ``node``.

    Walks the path from the top node so rolled array *ancestors* contribute
    their brackets too (e.g. ``blk[gi0].myreg[gi1]`` -> ``[gi0][gi1]``). The
    loop-variable numbers match those allocated positionally from the open-dim
    stride stack (see ``BusDecoderListener.loop_base_index``).
    """
    indexed = get_indexed_path(top_node, node, indexer, skip_kw_filter=True)
    return "".join(re.findall(r"\[[^\]]*\]", indexed))


class Interface(ABC):
    """Abstract base class for interface signal handling."""

    def __init__(self, cpuif: "BaseCpuif") -> None:
        self.cpuif = cpuif

    def master_base_name(self, node: AddressableNode) -> str:
        """Master port base name for a node (path-qualified on conflicts)."""
        return self.cpuif.exp.ds.master_port_name(node)

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
            base = (
                f"{self.get_interface_type()}.{self.master_modport_name} "
                f"{master_prefix}{self.master_base_name(child)}"
            )

            # When unrolled, current_idx is set - append it to the name
            if child.current_idx is not None:
                base = f"{base}_{'_'.join(map(str, child.current_idx))}"

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
        base = self.master_base_name(node)

        if not self.cpuif.is_master_array(node) and node.current_idx is not None:
            # A specific element of an unrolled array: the master port is a
            # scalar interface named with an index suffix (e.g. m_apb_blk_0)
            return f"{master_prefix}{base}_{'_'.join(map(str, node.current_idx))}.{signal}"

        # Index by *all* open dimensions: walk from the top node so ancestor
        # array brackets (e.g. blk[gi0]) are included, then keep only the
        # bracket expressions to append after the (possibly qualified) base.
        brackets = _open_dim_brackets(self.cpuif.exp.ds.top_node, node, indexer)
        return f"{master_prefix}{base}{brackets}.{signal}"

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
        base = f"{master_prefix}{self.master_base_name(node)}"

        if not self.cpuif.is_master_array(node):
            # Not an array or an unrolled element
            if node.current_idx is not None:
                # This is a specific instance of an unrolled array
                return f"{base}_{signal}_{'_'.join(map(str, node.current_idx))}"
            return f"{base}_{signal}"

        # Is an array (possibly by virtue of rolled array ancestors)
        if indexer is not None:
            if isinstance(indexer, str):
                brackets = _open_dim_brackets(self.cpuif.exp.ds.top_node, node, indexer)
                return f"{base}_{signal}{brackets}"

            return f"{base}_{signal}[{indexer}]"
        # No indexer: this is a declaration -- size by every open dimension.
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
