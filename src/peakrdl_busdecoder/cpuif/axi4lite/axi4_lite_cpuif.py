from collections import deque
from typing import ClassVar

from systemrdl.node import AddressableNode

from peakrdl_busdecoder.sv_int import SVInt

from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif
from .axi4_lite_interface import AXI4LiteFlatInterface, AXI4LiteSVInterface


class AXI4LiteCpuifFlat(BaseCpuif):
    """Verilator-friendly AXI4-Lite decoder with flattened interface ports.

    AW and W are accepted independently, downstream VALID/READY handshakes are
    honored, and read/write responses are returned in request order using
    separate bounded queues. See :ref:`cpuif_axi4lite_response_ordering`.
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
        ("axil_wr_resp", "_fanin_wr_resp", "BRESP"),
    ]
    sv_array_fanin_rd: ClassVar[list[tuple[str, str, str]]] = [
        ("cpuif_rd_ack", "_fanin_ready", "RVALID"),
        ("cpuif_rd_err", "_fanin_err", "RRESP[1]"),
        ("cpuif_rd_data", "_fanin_data", "RDATA"),
        ("axil_rd_resp", "_fanin_resp", "RRESP"),
    ]
    sv_array_ready_fanin_wr: ClassVar[list[tuple[str, str, str]]] = [
        ("axil_wr_issue_aw_ready", "_fanin_aw_ready", "AWREADY"),
        ("axil_wr_issue_w_ready", "_fanin_w_ready", "WREADY"),
    ]
    sv_array_ready_fanin_rd: ClassVar[list[tuple[str, str, str]]] = [
        ("axil_rd_issue_ar_ready", "_fanin_ar_ready", "ARREADY"),
    ]

    @property
    def parameters(self) -> list[str]:
        params = super().parameters
        params.append(f"localparam AXI4LITE_MAX_OUTSTANDING = {self.exp.ds.axi4lite_max_outstanding}")
        return params

    @property
    def fanin_wr_select(self) -> str:
        return "axil_wr_resp_sel"

    @property
    def fanin_rd_select(self) -> str:
        return "axil_rd_resp_sel"

    @property
    def clock_signal(self) -> str:
        return "clk" if self.clk_src == "design" else self.signal("ACLK")

    @property
    def reset_sensitivity(self) -> str:
        return "posedge rst" if self.clk_src == "design" else f"negedge {self.signal('ARESETn')}"

    @property
    def reset_asserted(self) -> str:
        return "rst" if self.clk_src == "design" else f"!{self.signal('ARESETn')}"

    def fanout(self, node: AddressableNode, array_stack: deque[int]) -> str:
        fanout: dict[str, str] = {}
        waddr_comp = ["axil_wr_issue_addr", f"{SVInt(self.node_base_address(node), self.addr_width)}"]
        raddr_comp = ["axil_rd_issue_addr", f"{SVInt(self.node_base_address(node), self.addr_width)}"]
        for i, stride in enumerate(array_stack):
            offset = f"{self.addr_width}'(gi{i}*{SVInt(stride, self.addr_width)})"
            waddr_comp.append(offset)
            raddr_comp.append(offset)

        addr_width = self.addr_width_param(node)

        path = get_indexed_path(self.exp.ds.top_node, node, "gi")
        wr_issue_sel = f"axil_wr_issue_sel.{path}"
        rd_issue_sel = f"axil_rd_issue_sel.{path}"
        wr_resp_sel = f"axil_wr_resp_sel.{path}"
        rd_resp_sel = f"axil_rd_resp_sel.{path}"

        if self.clk_src == "cpuif" and not self.is_interface:
            fanout[self.signal("ACLK", node, "gi")] = self.signal("ACLK")
            fanout[self.signal("ARESETn", node, "gi")] = self.signal("ARESETn")

        # Write address channel
        fanout[self.signal("AWVALID", node, "gi")] = (
            f"axil_wr_issue_valid & !axil_wr_issue_aw_sent & {wr_issue_sel}"
        )
        if self._can_truncate_addr(node, array_stack):
            # Size is a power of 2 and aligned, so we can directly use the address bits as the slave address
            fanout[self.signal("AWADDR", node, "gi")] = f"axil_wr_issue_addr[{addr_width}-1:0]"
        else:
            fanout[self.signal("AWADDR", node, "gi")] = f"{addr_width}'({'-'.join(waddr_comp)})"
        fanout[self.signal("AWPROT", node, "gi")] = "axil_wr_issue_prot"

        # Write data channel
        fanout[self.signal("WVALID", node, "gi")] = (
            f"axil_wr_issue_valid & !axil_wr_issue_w_sent & {wr_issue_sel}"
        )
        fanout[self.signal("WDATA", node, "gi")] = "axil_wr_issue_data"
        fanout[self.signal("WSTRB", node, "gi")] = "axil_wr_issue_strb"

        # Write response channel (master -> slave)
        fanout[self.signal("BREADY", node, "gi")] = f"{wr_resp_sel} & {self.signal('BREADY')}"

        # Read address channel
        fanout[self.signal("ARVALID", node, "gi")] = f"axil_rd_issue_valid & {rd_issue_sel}"
        if self._can_truncate_addr(node, array_stack):
            # Size is a power of 2 and aligned, so we can directly use the address bits as the slave address
            fanout[self.signal("ARADDR", node, "gi")] = f"axil_rd_issue_addr[{addr_width}-1:0]"
        else:
            fanout[self.signal("ARADDR", node, "gi")] = f"{addr_width}'({'-'.join(raddr_comp)})"
        fanout[self.signal("ARPROT", node, "gi")] = "axil_rd_issue_prot"

        # Read data channel (master -> slave)
        fanout[self.signal("RREADY", node, "gi")] = f"{rd_resp_sel} & {self.signal('RREADY')}"

        return "\n".join(f"assign {lhs} = {rhs};" for lhs, rhs in fanout.items())

    def _default_fanin_wr(self, node: AddressableNode | None, *, error: bool) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_wr_ack"] = "'0"
            fanin["cpuif_wr_err"] = "'0"
            fanin["axil_wr_resp"] = "2'b00"
            if error:
                fanin["cpuif_wr_ack"] = "'1"
                fanin["cpuif_wr_err"] = f"{self.fanin_wr_select}.cpuif_err"
                fanin["axil_wr_resp"] = "2'b11"
        else:
            fanin["cpuif_wr_ack"] = self.signal("BVALID", node, "i")
            fanin["cpuif_wr_err"] = f"{self.signal('BRESP', node, 'i')}[1]"
            fanin["axil_wr_resp"] = self.signal("BRESP", node, "i")

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())

    def _default_fanin_rd(self, node: AddressableNode | None, *, error: bool) -> str:
        fanin: dict[str, str] = {}
        if node is None:
            fanin["cpuif_rd_ack"] = "'0"
            fanin["cpuif_rd_err"] = "'0"
            fanin["cpuif_rd_data"] = "'0"
            fanin["axil_rd_resp"] = "2'b00"
            if error:
                fanin["cpuif_rd_ack"] = "'1"
                fanin["cpuif_rd_err"] = f"{self.fanin_rd_select}.cpuif_err"
                fanin["axil_rd_resp"] = "2'b11"
        else:
            fanin["cpuif_rd_ack"] = self.signal("RVALID", node, "i")
            fanin["cpuif_rd_err"] = f"{self.signal('RRESP', node, 'i')}[1]"
            fanin["cpuif_rd_data"] = self.signal("RDATA", node, "i")
            fanin["axil_rd_resp"] = self.signal("RRESP", node, "i")

        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())

    def ready_fanin_wr(self, node: AddressableNode | None = None) -> str:
        if node is None:
            return "axil_wr_issue_aw_ready = '0;\naxil_wr_issue_w_ready = '0;"
        if self._should_apply_sv_array_override(node):
            return self._sv_array_override(node, self.sv_array_ready_fanin_wr)
        return (
            f"axil_wr_issue_aw_ready = {self.signal('AWREADY', node, 'i')};\n"
            f"axil_wr_issue_w_ready = {self.signal('WREADY', node, 'i')};"
        )

    def ready_fanin_rd(self, node: AddressableNode | None = None) -> str:
        if node is None:
            return "axil_rd_issue_ar_ready = '0;"
        if self._should_apply_sv_array_override(node):
            return self._sv_array_override(node, self.sv_array_ready_fanin_rd)
        return f"axil_rd_issue_ar_ready = {self.signal('ARREADY', node, 'i')};"

    def fanin_intermediate_declarations(self, node: AddressableNode) -> list[str]:
        dims = self.master_array_dims(node)
        if not dims:
            return []

        array_str = "".join(f"[{dim}]" for dim in dims)
        return [
            f"logic {self.exp.ds.master_port_name(node)}_fanin_wr_valid{array_str};",
            f"logic {self.exp.ds.master_port_name(node)}_fanin_wr_err{array_str};",
            f"logic [1:0] {self.exp.ds.master_port_name(node)}_fanin_wr_resp{array_str};",
            f"logic [1:0] {self.exp.ds.master_port_name(node)}_fanin_resp{array_str};",
            f"logic {self.exp.ds.master_port_name(node)}_fanin_aw_ready{array_str};",
            f"logic {self.exp.ds.master_port_name(node)}_fanin_w_ready{array_str};",
            f"logic {self.exp.ds.master_port_name(node)}_fanin_ar_ready{array_str};",
        ]


class AXI4LiteCpuif(AXI4LiteCpuifFlat):
    use_sv_interface = True
