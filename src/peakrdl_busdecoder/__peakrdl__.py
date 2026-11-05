from __future__ import annotations

import functools
import sys
import traceback
from argparse import BooleanOptionalAction
from typing import TYPE_CHECKING, Any, TypeVar, cast

from peakrdl.config import schema
from peakrdl.plugins.entry_points import get_entry_points
from peakrdl.plugins.exporter import ExporterSubcommandPlugin
from systemrdl import RDLCompileError

from .cpuif import BaseCpuif, ahblite, apb, axi4lite
from .exporter import BusDecoderExporter, resolve_clk_src
from .udps import ALL_UDPS

if TYPE_CHECKING:
    import argparse

    from peakrdl.config.loader import AppConfig
    from systemrdl.node import AddrmapNode

_OptionValue = TypeVar("_OptionValue")


class _IntegerAtLeast(schema.Integer):
    def __init__(self, minimum: int) -> None:
        self.minimum = minimum

    def extract(self, data: object, path: str, err_ctx: str) -> int:
        # Python's bool is an int subclass, but TOML booleans are not integers.
        if isinstance(data, bool):
            raise schema.SchemaException(f"{err_ctx}: Expected int. Got bool")
        value = super().extract(data, path, err_ctx)
        if value < self.minimum:
            raise schema.SchemaException(
                f"{err_ctx}: Expected an integer greater than or equal to {self.minimum}. Got {value}"
            )
        return value


class _DataWidth(_IntegerAtLeast):
    def __init__(self) -> None:
        super().__init__(8)

    def extract(self, data: object, path: str, err_ctx: str) -> int:
        value = super().extract(data, path, err_ctx)
        if value & (value - 1):
            raise schema.SchemaException(
                f"{err_ctx}: Expected a power of two of at least 8 bits. Got {value}"
            )
        return value


@functools.lru_cache
def get_cpuifs(config: tuple[tuple[str, Any], ...]) -> dict[str, type[BaseCpuif]]:
    # All built-in CPUIFs
    cpuifs: dict[str, type[BaseCpuif]] = {
        # "passthrough": passthrough.PassthroughCpuif,
        "apb3": apb.APB3Cpuif,
        "apb3-flat": apb.APB3CpuifFlat,
        "apb4": apb.APB4Cpuif,
        "apb4-flat": apb.APB4CpuifFlat,
        "axi4-lite": axi4lite.AXI4LiteCpuif,
        "axi4-lite-flat": axi4lite.AXI4LiteCpuifFlat,
        "ahb-lite": ahblite.AHBLiteCpuif,
        "ahb-lite-flat": ahblite.AHBLiteCpuifFlat,
    }

    # Load any cpuifs specified via entry points
    for ep, _ in get_entry_points("peakrdl_busdecoder.cpuif"):
        name = ep.name
        cpuif = ep.load()
        if name in cpuifs:
            raise RuntimeError(
                f"A plugin for 'peakrdl-busdecoder' tried to load cpuif '{name}' but it already exists"
            )
        if not issubclass(cpuif, BaseCpuif):
            raise RuntimeError(
                f"A plugin for 'peakrdl-busdecoder' tried to load cpuif '{name}' but it not a BaseCpuif class"
            )
        cpuifs[name] = cpuif

    # Load any CPUIFs via config import
    for name, cpuif in config:
        if name in cpuifs:
            raise RuntimeError(
                f"A plugin for 'peakrdl-busdecoder' tried to load cpuif '{name}' but it already exists"
            )
        if not issubclass(cpuif, BaseCpuif):
            raise RuntimeError(
                f"A plugin for 'peakrdl-busdecoder' tried to load cpuif '{name}' but it not a BaseCpuif class"
            )
        cpuifs[name] = cpuif

    return cpuifs


class Exporter(ExporterSubcommandPlugin):
    short_desc = "Generate a SystemVerilog bus decoder for splitting CPU interfaces to sub-address spaces"

    udp_definitions = ALL_UDPS

    cfg_schema = {  # noqa: RUF012
        "cpuifs": {"*": schema.PythonObjectImport()},
        "cpuif": schema.String(),
        "data_width": _DataWidth(),
        "clk_src": schema.Choice(["off", "cpuif", "design"]),
        "apb_buffer": schema.Choice(["none", "in", "out", "both"]),
        "gate_signals": schema.Boolean(),
        "max_decode_depth": _IntegerAtLeast(0),
        "unroll": schema.Boolean(),
        "axi4lite_max_outstanding": _IntegerAtLeast(1),
        "parametrize": schema.Boolean(),
    }

    def _load_cfg(self, cfg: AppConfig) -> None:
        super()._load_cfg(cfg)
        self._cfg_path = cfg.path
        # CPU-interface choices depend on imports from this same configuration.
        cfg.get_namespace(
            self.name,
            schema.normalize({"cpuif": schema.Choice(list(self.get_cpuifs()))}),
        )

    def get_cpuifs(self) -> dict[str, type[BaseCpuif]]:
        return get_cpuifs(tuple(self.cfg["cpuifs"].items()))

    def add_exporter_arguments(self, arg_group: argparse._ActionsContainer) -> None:
        cpuifs = self.get_cpuifs()

        arg_group.add_argument(
            "--cpuif",
            choices=cpuifs.keys(),
            default=None,
            help="Select the CPU interface protocol to use [apb4]",
        )

        arg_group.add_argument(
            "--module-name",
            metavar="NAME",
            default=None,
            help="Override the SystemVerilog module name",
        )

        arg_group.add_argument(
            "--package-name",
            metavar="NAME",
            default=None,
            help="Override the SystemVerilog package name",
        )

        arg_group.add_argument(
            "--addr-width",
            type=int,
            default=None,
            help="""Override the CPU interface's address width. By default,
            address width is sized to the contents of the busdecoder.
            """,
        )

        arg_group.add_argument(
            "--data-width",
            type=int,
            default=None,
            help="""Set the CPU interface data width in bits (power of two, at
            least 8, and no smaller than any internal register accesswidth).
            By default, infer it from internal registers, or use 32 bits with
            a warning when the design has no internal register accesswidth.
            """,
        )

        arg_group.add_argument(
            "--debug",
            action="store_true",
            help="Show the full Python traceback when busdecoder export fails",
        )

        arg_group.add_argument(
            "--unroll",
            action=BooleanOptionalAction,
            default=None,
            help="""Unroll arrayed addressable nodes into separate instances in
            the CPU interface. By default, arrayed nodes are kept as arrays.
            """,
        )

        arg_group.add_argument(
            "--parametrize",
            action=BooleanOptionalAction,
            default=None,
            help="""Extract root-level RDL parameters that control array
            dimensions and expose them as SystemVerilog module parameters.
            By default, all array dimensions use their elaborated static values.
            """,
        )

        arg_group.add_argument(
            "--apb-buffer",
            choices=("none", "in", "out", "both"),
            default=None,
            help="""Select transaction-aware APB buffering. 'in' captures the
            request at upstream SETUP and issues one child transfer; 'out'
            captures the child response and retires the child before upstream
            acceptance; 'both' combines them. 'none' (default) is combinational.
            No-wait upstream ACCESS cycles: none=1, in=2, out=2, both=3.
            Only APB cpuifs support buffering; non-none defaults to and requires
            --clk-src=design.
            """,
        )

        arg_group.add_argument(
            "--axi4lite-max-outstanding",
            type=int,
            default=None,
            help="""Maximum number of accepted AXI4-Lite reads and paired
            writes retained by each ordered response queue. Default is 4.
            Only applies to AXI4-Lite CPU interfaces.
            """,
        )

        arg_group.add_argument(
            "--clk-src",
            choices=("off", "cpuif", "design"),
            default=None,
            help="""Select where the bus decoder gets its clock and reset.
            'off' omits clock/reset ports and is the default for unbuffered APB.
            'cpuif' takes PCLK/PRESETn or ACLK/ARESETn from the slave CPU
            interface. Flat master ports forward clock/reset; SystemVerilog
            interface endpoints require external clock/reset connections.
            'design' exposes top-level 'clk'/'rst' ports and is the default for
            buffered APB and AXI4-Lite. The design distributes clock/reset to
            downstream slaves itself. Stateful configurations reject 'off'.
            AHB-Lite always uses ingress HCLK/HRESETn and rejects 'off'.
            """,
        )

        arg_group.add_argument(
            "--max-decode-depth",
            type=int,
            default=None,
            help="""Maximum depth for address decoder to descend into nested
            addressable components. Value of 0 decodes all levels (infinite depth).
            Value of 1 decodes only top-level children. Value of 2 decodes top-level
            and one level deeper, etc. Default is 1.
            """,
        )

        arg_group.add_argument(
            "--gate-signals",
            action=BooleanOptionalAction,
            default=None,
            help="""Gate downstream broadcast payload signals with the per-slave select.
            For APB this drives PADDR/PWDATA/PSTRB/PPROT to '0 on unselected
            masters. By default, payload signals fan out without select masking.
            PENABLE is always gated with the per-slave select.
            """,
        )

    def _get_option(self, options: argparse.Namespace, key: str, default: _OptionValue) -> _OptionValue:
        value = getattr(options, key)
        if value is None:
            value = self.cfg[key]
        return default if value is None else cast(_OptionValue, value)

    def _config_context(self, options: argparse.Namespace, *keys: str) -> str:
        sources = [
            f"busdecoder.{key}={self.cfg[key]!r}"
            for key in keys
            if getattr(options, key) is None and self.cfg[key] is not None
        ]
        return f"{self._cfg_path}: {', '.join(sources)}: " if sources else ""

    def do_export(self, top_node: AddrmapNode, options: argparse.Namespace) -> None:
        cpuifs = self.get_cpuifs()
        cpuif_cls = cpuifs[self._get_option(options, "cpuif", "apb4")]
        apb_buffer = self._get_option(options, "apb_buffer", "none")
        clk_src = options.clk_src if options.clk_src is not None else self.cfg["clk_src"]
        data_width = options.data_width if options.data_width is not None else self.cfg["data_width"]
        try:
            try:
                clk_src = resolve_clk_src(cpuif_cls, clk_src, apb_buffer)
            except ValueError as exc:
                context = self._config_context(options, "cpuif", "clk_src", "apb_buffer")
                top_node.env.msg.fatal(f"{context}{exc}")

            x = BusDecoderExporter()
            x.export(
                top_node,
                options.output,
                cpuif_cls=cpuif_cls,
                module_name=options.module_name,
                package_name=options.package_name,
                address_width=options.addr_width,
                data_width=data_width,
                cpuif_unroll=self._get_option(options, "unroll", False),
                parametrize=self._get_option(options, "parametrize", False),
                max_decode_depth=self._get_option(options, "max_decode_depth", 1),
                clk_src=clk_src,
                gate_signals=self._get_option(options, "gate_signals", False),
                apb_buffer=apb_buffer,
                axi4lite_max_outstanding=self._get_option(options, "axi4lite_max_outstanding", 4),
            )
        except RDLCompileError:
            context = self._config_context(options, "data_width")
            if context:
                print(f"{context}effective project setting for this export.", file=sys.stderr)
            if options.debug:
                traceback.print_exc()
            raise
