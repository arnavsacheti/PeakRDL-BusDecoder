import os
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict, cast

import jinja2 as jj
from systemrdl.node import AddrmapNode, RootNode
from systemrdl.walker import RDLSteerableWalker
from typing_extensions import Unpack

from .cpuif import BaseCpuif
from .cpuif.ahblite import AHBLiteCpuifFlat
from .cpuif.apb import APB4Cpuif
from .cpuif.apb.apb_cpuif import APBCpuifBase
from .cpuif.axi4lite import AXI4LiteCpuifFlat
from .decode_logic_gen import DecodeLogicFlavor, DecodeLogicGenerator
from .design_state import DesignState, DesignStateKwargs
from .identifier_filter import kw_filter as kwf
from .listener import BusDecoderListener
from .struct_gen import StructGenerator
from .sv_int import SVInt
from .utils import clog2
from .validate_design import DesignValidator


class ExporterKwargs(TypedDict, total=False):
    cpuif_cls: type[BaseCpuif]
    module_name: str
    package_name: str
    address_width: int
    cpuif_unroll: bool
    parametrize: bool
    reuse_hwif_typedefs: bool
    max_decode_depth: int
    clk_src: str | None
    gate_signals: bool
    apb_buffer: str
    axi4lite_max_outstanding: int


if TYPE_CHECKING:
    pass


def resolve_clk_src(cpuif_cls: type[BaseCpuif], clk_src: str | None, apb_buffer: str = "none") -> str:
    """Resolve and validate the shared CLI/API protocol, clock, and buffer settings."""
    if clk_src is not None and clk_src not in ("off", "cpuif", "design"):
        raise ValueError(f"clk_src must be 'off', 'cpuif' or 'design', got {clk_src!r}")
    if apb_buffer not in ("none", "in", "out", "both"):
        raise ValueError(f"apb_buffer must be one of 'none', 'in', 'out', 'both', got {apb_buffer!r}")

    if clk_src is None:
        clk_src = "off" if issubclass(cpuif_cls, APBCpuifBase) and apb_buffer == "none" else "design"
    elif clk_src == "off":
        if issubclass(cpuif_cls, AHBLiteCpuifFlat):
            raise ValueError(
                "--clk-src off is not supported by AHB-Lite; it always requires "
                "ingress HCLK/HRESETn. Omit --clk-src or select cpuif."
            )
        if issubclass(cpuif_cls, AXI4LiteCpuifFlat):
            raise ValueError(
                "--clk-src off is not supported by AXI4-Lite ordered queues; "
                "use --clk-src design (the default) or --clk-src cpuif."
            )

    if apb_buffer != "none":
        if clk_src != "design":
            raise ValueError(
                "--apb-buffer requires --clk-src design (the buffer flops use clk/rst); "
                "omit --clk-src to select design automatically, or set --apb-buffer none"
            )
        if not cpuif_cls.supports_apb_buffer:
            raise ValueError(
                f"apb_buffer={apb_buffer!r} is not supported by "
                f"{cpuif_cls.__name__}; only APB cpuifs honor this option."
            )
    return clk_src


class BusDecoderExporter:
    cpuif: BaseCpuif
    ds: DesignState

    def __init__(self, **kwargs: Unpack[ExporterKwargs]) -> None:
        # Check for stray kwargs
        if kwargs:
            raise TypeError(f"got an unexpected keyword argument '{next(iter(kwargs.keys()))}'")

        fs_loader = jj.FileSystemLoader(Path(__file__).parent)
        c_loader = jj.ChoiceLoader(
            [
                fs_loader,
                jj.PrefixLoader(
                    {"base": fs_loader},
                    delimiter=":",
                ),
            ]
        )

        self.jj_env = jj.Environment(
            loader=c_loader,
            undefined=jj.StrictUndefined,
        )
        self.jj_env.filters["kwf"] = kwf
        self.jj_env.filters["walk"] = self.walk
        self.jj_env.filters["clog2"] = clog2

    def export(self, node: RootNode | AddrmapNode, output_dir: str, **kwargs: Unpack[ExporterKwargs]) -> None:
        """
        Parameters
        ----------
        node: AddrmapNode
            Top-level SystemRDL node to export.
        output_dir: str
            Path to the output directory where generated SystemVerilog will be written.
            Output includes two files: a module definition and package definition.
        cpuif_cls: :class:`peakrdl_busdecoder.cpuif.CpuifBase`
            Specify the class type that implements the CPU interface of your choice.
            Defaults to AMBA APB4.
        module_name: str
            Override the SystemVerilog module name. By default, the module name
            is the top-level node's name.
        package_name: str
            Override the SystemVerilog package name. By default, the package name
            is the top-level node's name with a "_pkg" suffix.
        address_width: int
            Override the CPU interface's address width. By default, address width
            is sized to the contents of the busdecoder.
        cpuif_unroll: bool
            Unroll arrayed addressable nodes into separate instances in the CPU
            interface. By default, arrayed nodes are kept as arrays.
        max_decode_depth: int
            Maximum depth for address decoder to descend into nested addressable
            components. A value of 0 decodes all levels (infinite depth). A value
            of 1 decodes only top-level children. A value of 2 decodes top-level
            and one level deeper, etc. By default, the decoder descends 1 level deep.
        clk_src: str | None
            Selects where the bus decoder gets its clock and reset. None
            (default) resolves to "off" for unbuffered APB and "design" for
            buffered APB and AXI4-Lite.

            - "off": no clock/reset ports or logic. Only unbuffered APB
              supports this mode, preserving the 0.7.x APB port shape.
            - "cpuif": clk/reset are bundled with the CPU interface. The slave
              bus carries the protocol-defined clock/reset (PCLK/PRESETn for
              APB, ACLK/ARESETn for AXI4-Lite). Flat master ports forward
              clock/reset; SystemVerilog interface endpoints must be wired
              externally because their modports treat these as inputs.
            - "design": the CPU interface carries no clk/reset. The module
              exposes top-level ``clk`` and ``rst`` ports; the design is
              responsible for distributing clock/reset to downstream slaves.

            AHB-Lite always uses ingress HCLK/HRESETn, ignores "design" and
            "cpuif", and rejects "off".
        gate_signals: bool
            Gate downstream broadcast payload signals with the per-slave select.
            For APB this drives PADDR/PWDATA/PSTRB/PPROT to '0 on unselected
            masters. By default, payload signals fan out unmodified. PENABLE
            is always gated with the per-slave select.
        apb_buffer: str
            Select transaction-aware APB request/response buffering.
            "none" (default) leaves the combinational path unchanged. "in"
            captures request payload at the upstream SETUP edge and holds it
            through one downstream SETUP/ACCESS transfer; the response remains
            combinational and child/upstream completion share an edge. "out"
            forwards live upstream payload, captures the child response at
            completion, removes the child request, and retains the registered
            response until upstream acceptance. "both" combines these stages.
            Only one transfer may be outstanding. With no child waits, upstream
            ACCESS takes 1/2/2/3 cycles for none/in/out/both; minimum completion
            spacing including SETUP is 2/3/3/4 cycles. Each child wait adds one.
            Non-"none" modes require APB and ``clk_src='design'`` (selected
            automatically when clk_src is None) and use design clk and
            active-high asynchronous rst. Reset clears retained
            state, suppresses child requests/upstream ready, and aborts pending
            work without undoing completed child side effects. A fresh upstream
            SETUP is required after reset; held stale ACCESS is not replayed.
        axi4lite_max_outstanding: int
            Maximum accepted AXI4-Lite read transactions and paired write
            transactions retained by their respective order queues. Defaults
            to 4. AW and W each also have one independent holding register.
        """
        # If it is the root node, skip to top addrmap
        if isinstance(node, RootNode):
            top_node = node.top
        else:
            top_node = node

        cpuif_cls: type[BaseCpuif] = kwargs.pop("cpuif_cls", None) or APB4Cpuif
        try:
            kwargs["clk_src"] = resolve_clk_src(
                cpuif_cls, kwargs.get("clk_src"), kwargs.get("apb_buffer", "none")
            )
        except ValueError as exc:
            top_node.env.msg.fatal(str(exc))
        self.ds = DesignState(top_node, cast(DesignStateKwargs, kwargs))

        # Check for stray kwargs
        if kwargs:
            raise TypeError(f"got an unexpected keyword argument '{next(iter(kwargs.keys()))}'")

        # Construct exporter components
        self.cpuif = cpuif_cls(self)

        # Validate that there are no unsupported constructs
        DesignValidator(self).do_validate()

        # Build Jinja template context
        context = {
            "version": version("peakrdl-busdecoder"),
            "cpuif": self.cpuif,
            "cpuif_decode": DecodeLogicGenerator,
            "cpuif_select": StructGenerator,
            "cpuif_decode_flavor": DecodeLogicFlavor,
            "ds": self.ds,
            "SVInt": SVInt,
        }

        # Write out design
        os.makedirs(output_dir, exist_ok=True)
        package_file_path = os.path.join(output_dir, self.ds.package_name + ".sv")
        template = self.jj_env.get_template("package_tmpl.sv")
        stream = template.stream(context)
        stream.dump(package_file_path)

        module_file_path = os.path.join(output_dir, self.ds.module_name + ".sv")
        template = self.jj_env.get_template("module_tmpl.sv")
        stream = template.stream(context)
        stream.dump(module_file_path)

    def walk(self, listener_cls: type[BusDecoderListener], **kwargs: dict[str, Any]) -> str:
        # Port-referencing listeners walk unrolled when cpuif_unroll is set, so
        # each array element is fanned out/in as an individual master port.
        unroll = self.ds.cpuif_unroll and listener_cls.walk_unrolled
        walker = RDLSteerableWalker(unroll=unroll)
        listener = listener_cls(self.ds, **kwargs)
        walker.walk(self.ds.top_node, listener, skip_top=True)
        return str(listener)
