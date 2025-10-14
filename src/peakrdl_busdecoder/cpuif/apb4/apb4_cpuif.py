from systemrdl.node import AddressableNode
from ..base_cpuif import BaseCpuif


class APB4Cpuif(BaseCpuif):
    template_path = "apb4_tmpl.sv"
    is_interface = True

    def _port_declaration(self, child: AddressableNode) -> str:
        base = f"apb4_intf.master m_apb_{child.inst_name}"
        if not child.is_array:
            return base
        if child.current_idx is not None:
            return f"{base}_{'_'.join(map(str, child.current_idx))} [N_{child.inst_name.upper()}S]"
        return f"{base} [N_{child.inst_name.upper()}S]"

    @property
    def port_declaration(self) -> str:
        """Returns the port declaration for the APB4 interface."""
        slave_ports: list[str] = ["apb4_intf.slave s_apb"]
        master_ports: list[str] = list(map(self._port_declaration, self.addressable_children))

        return ",\n".join(slave_ports + master_ports)

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        idx: str | int | None = None,
    ) -> str:
        """Returns the signal name for the given signal and node."""
        if node is None:
            # Node is none, so this is a slave signal
            return f"s_apb.{signal}"

        # Master signal
        base = f"m_apb_{node.inst_name}"
        if not node.is_array:
            return f"{base}.{signal}"
        if node.current_idx is not None:
            # This is a specific instance of an array
            return f"{base}_{'_'.join(map(str, node.current_idx))}.{signal}"
        if idx is not None:
            return f"{base}[{idx}].{signal}"

        raise ValueError("Must provide an index for arrayed interface signals")

    def get_address_predicate(self, node: AddressableNode) -> str:
        """
        Returns a SystemVerilog expression that evaluates to true when the
        address on the bus matches the address range of the given node.
        """

        addr_mask = (1 << self.addr_width) - 1
        addr = node.absolute_address & addr_mask
        size = node.size
        if size == 0:
            raise ValueError("Node size must be greater than 0")
        if (addr % size) != 0:
            raise ValueError("Node address must be aligned to its size")

        # Calculate the address range of the node
        addr_start = addr
        addr_end = addr + size - 1
        if addr_end > addr_mask:
            raise ValueError("Node address range exceeds address width")

        if addr_start == addr_end:
            return f"({self.signal('PADDR')} == 'h{addr_start:X})"

        return f"({self.signal('PADDR')} >= 'h{addr_start:X} && {self.signal('PADDR')} <= 'h{addr_end:X})"

    def get_address_decode_condition(self, node: AddressableNode) -> str:
        """
        Returns a SystemVerilog expression that evaluates to true when the
        address on the bus matches the address range of the given node.
        """
        addr_pred = self.get_address_predicate(node)
        return addr_pred
