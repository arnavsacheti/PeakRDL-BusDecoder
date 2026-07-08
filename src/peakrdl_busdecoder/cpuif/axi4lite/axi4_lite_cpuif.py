from collections import deque
from typing import ClassVar

from systemrdl.node import AddressableNode

from peakrdl_busdecoder.sv_int import SVInt

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif
from .axi4_lite_interface import AXI4LiteFlatInterface, AXI4LiteSVInterface


class AXI4LiteCpuifFlat(BaseCpuif):
    """Verilator-friendly variant that flattens the AXI4-Lite interface ports.

    Limitations: per-slave back-pressure on the AW/W/AR/B/R handshakes is not
    honored -- CPU-side ``*READY`` is asserted unconditionally on ``*VALID``,
    and downstream slave ``*READY`` is never consumed. See
    :ref:`cpuif_axi4lite_backpressure` in the docs and
    `issue #59 <https://github.com/arnavsacheti/PeakRDL-BusDecoder/issues/59>`_.
    """

    template_path = "axi4_lite_tmpl.sv"

    flat_interface_cls = AXI4LiteFlatInterface
    sv_interface_cls = AXI4LiteSVInterface
    slave_name_flat = "s_axil_"
    slave_name_sv = "s_axil"
    master_signal_prefix = "m_axil_"

    sv_array_fanin_wr: ClassVar[list[tuple[str, str, str]]] = [
        ("cpuif_wr_ack", "_fanin_wr_valid", "BVALID"),
        ("cpuif_wr_err", "_fanin_wr_err", "BRESP[1]"),
    ]
    sv_array_fanin_rd: ClassVar[list[tuple[str, str, str]]] = [
        ("cpuif_rd_ack", "_fanin_ready", "RVALID"),
        ("cpuif_rd_err", "_fanin_err", "RRESP[1]"),
        ("cpuif_rd_data", "_fanin_data", "RDATA"),
    ]

    def fanout(self, node: AddressableNode, array_stack: deque[int]) -> str:
        fanout: dict[str, str] = {}
        waddr_comp = [f"{self.signal('AWADDR')}", f"{SVInt(self.node_base_address(node), self.addr_width)}"]
        raddr_comp = [f"{self.signal('ARADDR')}", f"{SVInt(self.node_base_address(node), self.addr_width)}"]
        for i, stride in enumerate(array_stack):
            offset = f"{self.addr_width}'(gi{i}*{SVInt(stride, self.addr_width)})"
            waddr_comp.append(offset)
            raddr_comp.append(offset)

        addr_width = self.addr_width_param(node)

        wr_sel = f"cpuif_wr_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"
        rd_sel = f"cpuif_rd_sel.{get_indexed_path(self.exp.ds.top_node, node, 'gi')}"

        if self.clk_src == "cpuif" and not self.is_interface:
            # Flat style only: the SV interface's master modport declares
            # ACLK/ARESETn as inputs, so the decoder cannot drive them; in
            # interface style the design clocks each interface at instantiation.
            fanout[self.signal("ACLK", node, "gi")] = self.signal("ACLK")
            fanout[self.signal("ARESETn", node, "gi")] = self.signal("ARESETn")

        # Write address channel
        fanout[self.signal("AWVALID", node, "gi")] = wr_sel
        if self._can_truncate_addr(node, array_stack):
            # Size is a power of 2 and aligned, so we can directly use the address bits as the slave address
            fanout[self.signal("AWADDR", node, "gi")] = f"{self.signal('AWADDR')}[{addr_width}-1:0]"
        else:
            fanout[self.signal("AWADDR", node, "gi")] = f"{addr_width}'({'-'.join(waddr_comp)})"
        fanout[self.signal("AWPROT", node, "gi")] = self.signal("AWPROT")

        # Write data channel
        fanout[self.signal("WVALID", node, "gi")] = wr_sel
        fanout[self.signal("WDATA", node, "gi")] = "cpuif_wr_data"
        fanout[self.signal("WSTRB", node, "gi")] = "cpuif_wr_byte_en"

        # Write response channel (master -> slave)
        fanout[self.signal("BREADY", node, "gi")] = self.signal("BREADY")

        # Read address channel
        fanout[self.signal("ARVALID", node, "gi")] = rd_sel
        if self._can_truncate_addr(node, array_stack):
            # Size is a power of 2 and aligned, so we can directly use the address bits as the slave address
            fanout[self.signal("ARADDR", node, "gi")] = f"{self.signal('ARADDR')}[{addr_width}-1:0]"
        else:
            fanout[self.signal("ARADDR", node, "gi")] = f"{addr_width}'({'-'.join(raddr_comp)})"
        fanout[self.signal("ARPROT", node, "gi")] = self.signal("ARPROT")

        # Read data channel (master -> slave)
        fanout[self.signal("RREADY", node, "gi")] = self.signal("RREADY")

        return "\n".join(f"assign {lhs} = {rhs};" for lhs, rhs in fanout.items())

    def _default_fanin_wr(self, node: AddressableNode | None, *, error: bool) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_wr_ack"] = "'0"
            fanin["cpuif_wr_err"] = "'0"
            if error:
                fanin["cpuif_wr_ack"] = "'1"
                fanin["cpuif_wr_err"] = "cpuif_wr_sel.cpuif_err"
        else:
            fanin["cpuif_wr_ack"] = self.signal("BVALID", node, "i")
            fanin["cpuif_wr_err"] = f"{self.signal('BRESP', node, 'i')}[1]"

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())

    def _default_fanin_rd(self, node: AddressableNode | None, *, error: bool) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_ack"] = "'0"
            fanin["cpuif_rd_err"] = "'0"
            fanin["cpuif_rd_data"] = "'0"
            if error:
                fanin["cpuif_rd_ack"] = "'1"
                fanin["cpuif_rd_err"] = "cpuif_rd_sel.cpuif_err"
        else:
            fanin["cpuif_rd_ack"] = self.signal("RVALID", node, "i")
            fanin["cpuif_rd_err"] = f"{self.signal('RRESP', node, 'i')}[1]"
            fanin["cpuif_rd_data"] = self.signal("RDATA", node, "i")

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())

    def fanin_intermediate_declarations(self, node: AddressableNode) -> list[str]:
        dims = self.master_array_dims(node)
        if not dims:
            return []

        array_str = "".join(f"[{dim}]" for dim in dims)
        return [
            f"logic {self.exp.ds.master_port_name(node)}_fanin_wr_valid{array_str};",
            f"logic {self.exp.ds.master_port_name(node)}_fanin_wr_err{array_str};",
        ]


class AXI4LiteCpuif(AXI4LiteCpuifFlat):
    use_sv_interface = True
