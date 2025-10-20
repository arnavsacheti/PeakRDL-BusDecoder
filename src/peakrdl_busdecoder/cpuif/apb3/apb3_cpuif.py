from systemrdl.node import AddressableNode

from ..base_cpuif import BaseCpuif


class APB3Cpuif(BaseCpuif):
    template_path = "apb3_tmpl.sv"
    is_interface = True

    def _port_declaration(self, child: AddressableNode) -> str:
        base = f"apb3_intf.master m_apb_{child.inst_name}"
        if not child.is_array:
            return base
        if child.current_idx is not None:
            return f"{base}_{'_'.join(map(str, child.current_idx))}"
        return f"{base} [N_{child.inst_name.upper()}S]"

    @property
    def port_declaration(self) -> str:
        slave_ports: list[str] = ["apb3_intf.slave s_apb"]
        master_ports: list[str] = list(map(self._port_declaration, self.addressable_children))

        return ",\n".join(slave_ports + master_ports)

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        idx: str | int | None = None,
    ) -> str:
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
