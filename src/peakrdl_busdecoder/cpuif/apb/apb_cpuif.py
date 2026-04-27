from collections import deque
from typing import ClassVar

from systemrdl.node import AddressableNode

from ...sv_int import SVInt
from ...utils import get_indexed_path
from ..base_cpuif import BaseCpuif
from .apb_interface import APBFlatInterface, APBSVInterface

# Slave-side input signals that may be buffered. Order is the buffer-block emit order.
_BUFFERABLE_IN_NAMES: tuple[str, ...] = ("PSEL", "PENABLE", "PWRITE", "PADDR", "PWDATA")
# Optional input signals: name -> cpuif class attr that gates inclusion.
_BUFFERABLE_IN_OPTIONAL: dict[str, str] = {"PPROT": "has_pprot", "PSTRB": "has_pstrb"}
# Slave-side output signals that may be buffered.
_BUFFERABLE_OUT_NAMES: tuple[str, ...] = ("PRDATA", "PREADY", "PSLVERR")


class APBCpuifBase(BaseCpuif):
    """Shared APB3/APB4 cpuif. Variants differ by ``apb_interface_type`` and
    whether ``has_pprot`` / ``has_pstrb`` are set."""

    template_path = "apb_tmpl.sv"

    flat_interface_cls = APBFlatInterface
    sv_interface_cls = APBSVInterface
    slave_name_flat = "s_apb_"
    slave_name_sv = "s_apb"
    master_signal_prefix = "m_apb_"
    supports_apb_buffer = True

    apb_interface_type: ClassVar[str] = ""  # set by concrete subclasses
    has_pprot: ClassVar[bool] = False
    has_pstrb: ClassVar[bool] = False

    # ---- I/O buffer ----

    @property
    def _apb_buffer(self) -> str:
        return self.exp.ds.apb_buffer

    @property
    def buffer_in(self) -> bool:
        return self._apb_buffer in ("in", "both")

    @property
    def buffer_out(self) -> bool:
        return self._apb_buffer in ("out", "both")

    @property
    def has_apb_buffer(self) -> bool:
        return self.buffer_in or self.buffer_out

    def _active_buffer_in_names(self) -> list[str]:
        names = list(_BUFFERABLE_IN_NAMES)
        for nm, attr in _BUFFERABLE_IN_OPTIONAL.items():
            if getattr(self, attr):
                names.append(nm)
        return names

    def _signal_width_decl(self, name: str) -> str:
        if name in ("PSEL", "PENABLE", "PWRITE", "PREADY", "PSLVERR"):
            return ""
        if name == "PADDR":
            return f"[{self.addr_width - 1}:0] "
        if name in ("PWDATA", "PRDATA"):
            return f"[{self.data_width - 1}:0] "
        if name == "PSTRB":
            return f"[{self.data_width // 8 - 1}:0] "
        if name == "PPROT":
            return "[2:0] "
        raise ValueError(f"unknown APB signal {name!r}")

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        idx: str | int | None = None,
    ) -> str:
        # Slave-side reference (no node) gets redirected to the buffer wire
        # when buffering is enabled for that direction.
        if node is None and idx is None:
            if self.buffer_in and signal in self._active_buffer_in_names():
                return f"apb_in_{signal}"
            if self.buffer_out and signal in _BUFFERABLE_OUT_NAMES:
                return f"apb_out_{signal}"
        return super().signal(signal, node, idx)

    def apb_buffer_block(self) -> str:
        """SV snippet that declares apb_in_*/apb_out_* wires and (when enabled)
        flops them on/off the slave port. Returns empty string when no buffering."""
        if not self.has_apb_buffer:
            return ""

        in_names = self._active_buffer_in_names() if self.buffer_in else []
        out_names = list(_BUFFERABLE_OUT_NAMES) if self.buffer_out else []

        lines: list[str] = []
        for nm in in_names:
            lines.append(f"logic {self._signal_width_decl(nm)}apb_in_{nm};")
        for nm in out_names:
            lines.append(f"logic {self._signal_width_decl(nm)}apb_out_{nm};")

        if in_names:
            lines.append("")
            lines.append("always_ff @(posedge clk or posedge rst) begin")
            lines.append("    if (rst) begin")
            for nm in in_names:
                lines.append(f"        apb_in_{nm} <= '0;")
            lines.append("    end else begin")
            for nm in in_names:
                src = self._interface.signal(nm)
                lines.append(f"        apb_in_{nm} <= {src};")
            lines.append("    end")
            lines.append("end")

        if out_names:
            lines.append("")
            lines.append("always_ff @(posedge clk or posedge rst) begin")
            lines.append("    if (rst) begin")
            for nm in out_names:
                sink = self._interface.signal(nm)
                lines.append(f"        {sink} <= '0;")
            lines.append("    end else begin")
            for nm in out_names:
                sink = self._interface.signal(nm)
                lines.append(f"        {sink} <= apb_out_{nm};")
            lines.append("    end")
            lines.append("end")

        return "\n".join(lines)

    sv_array_fanin_wr: ClassVar[list[tuple[str, str, str]]] = [
        ("cpuif_wr_ack", "_fanin_ready", "PREADY"),
        ("cpuif_wr_err", "_fanin_err", "PSLVERR"),
    ]
    sv_array_fanin_rd: ClassVar[list[tuple[str, str, str]]] = [
        ("cpuif_rd_ack", "_fanin_ready", "PREADY"),
        ("cpuif_rd_err", "_fanin_err", "PSLVERR"),
        ("cpuif_rd_data", "_fanin_data", "PRDATA"),
    ]

    def fanout(self, node: AddressableNode, array_stack: deque[int]) -> str:
        fanout: dict[str, str] = {}

        addr_width = f"{self.exp.ds.module_name.upper()}_{node.inst_name.upper()}_ADDR_WIDTH"

        sel_path = get_indexed_path(self.exp.ds.top_node, node, "gi")
        sel_expr = f"cpuif_wr_sel.{sel_path}|cpuif_rd_sel.{sel_path}"

        if self.clk_src == "cpuif":
            fanout[self.signal("PCLK", node, "gi")] = self.signal("PCLK")
            fanout[self.signal("PRESETn", node, "gi")] = self.signal("PRESETn")

        fanout[self.signal("PSEL", node, "gi")] = sel_expr
        fanout[self.signal("PENABLE", node, "gi")] = f"({sel_expr}) & {self.signal('PENABLE')}"
        fanout[self.signal("PWRITE", node, "gi")] = f"cpuif_wr_sel.{sel_path}"

        if self._can_truncate_addr(node, array_stack):
            # Size is a power of 2 and aligned, so we can directly use the address bits as the slave address
            addr_value = f"{self.signal('PADDR')}[{addr_width}-1:0]"
        else:
            addr_comp = [self.signal("PADDR"), f"{SVInt(node.raw_absolute_address, self.addr_width)}"]
            for i, stride in enumerate(array_stack):
                addr_comp.append(f"{self.addr_width}'(gi{i}*{SVInt(stride, self.addr_width)})")
            addr_value = f"{addr_width}'({' - '.join(addr_comp)})"
        fanout[self.signal("PADDR", node, "gi")] = f"({sel_expr}) ? {addr_value} : '0"

        if self.has_pprot:
            fanout[self.signal("PPROT", node, "gi")] = f"({sel_expr}) ? {self.signal('PPROT')} : '0"
        fanout[self.signal("PWDATA", node, "gi")] = f"({sel_expr}) ? cpuif_wr_data : '0"
        if self.has_pstrb:
            fanout[self.signal("PSTRB", node, "gi")] = f"({sel_expr}) ? cpuif_wr_byte_en : '0"

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
            fanin["cpuif_wr_ack"] = self.signal("PREADY", node, "i")
            fanin["cpuif_wr_err"] = self.signal("PSLVERR", node, "i")
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
            fanin["cpuif_rd_ack"] = self.signal("PREADY", node, "i")
            fanin["cpuif_rd_err"] = self.signal("PSLVERR", node, "i")
            fanin["cpuif_rd_data"] = self.signal("PRDATA", node, "i")
        return "\n".join(f"{lhs} = {rhs};" for lhs, rhs in fanin.items())


class APB3CpuifFlat(APBCpuifBase):
    apb_interface_type = "apb3_intf"


class APB3Cpuif(APB3CpuifFlat):
    use_sv_interface = True


class APB4CpuifFlat(APBCpuifBase):
    apb_interface_type = "apb4_intf"
    has_pprot = True
    has_pstrb = True


class APB4Cpuif(APB4CpuifFlat):
    use_sv_interface = True
