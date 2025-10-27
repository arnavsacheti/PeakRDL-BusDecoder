import functools
from typing import TYPE_CHECKING, Any

from peakrdl.config import schema
from peakrdl.plugins.entry_points import get_entry_points
from peakrdl.plugins.exporter import ExporterSubcommandPlugin

from .cpuif import BaseCpuif, apb3, apb4, axi4lite
from .exporter import BusDecoderExporter
from .udps import ALL_UDPS

if TYPE_CHECKING:
    import argparse

    from systemrdl.node import AddrmapNode


@functools.lru_cache
def get_cpuifs(config: list[tuple[str, Any]]) -> dict[str, type[BaseCpuif]]:
    # All built-in CPUIFs
    cpuifs: dict[str, type[BaseCpuif]] = {
        # "passthrough": passthrough.PassthroughCpuif,
        "apb3": apb3.APB3Cpuif,
        "apb3-flat": apb3.APB3CpuifFlat,
        "apb4": apb4.APB4Cpuif,
        "apb4-flat": apb4.APB4CpuifFlat,
        "axi4-lite": axi4lite.AXI4LiteCpuif,
        "axi4-lite-flat": axi4lite.AXI4LiteCpuifFlat,
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
    }

    def get_cpuifs(self) -> dict[str, type[BaseCpuif]]:
        return get_cpuifs(map(tuple, self.cfg["cpuifs"].items()))

    def add_exporter_arguments(self, arg_group: "argparse.ArgumentParser") -> None:  # type: ignore
        cpuifs = self.get_cpuifs()

        arg_group.add_argument(
            "--cpuif",
            choices=cpuifs.keys(),
            default="apb4",
            help="Select the CPU interface protocol to use [apb3]",
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
            "--unroll",
            action="store_true",
            default=False,
            help="""Unroll arrayed addressable nodes into separate instances in
            the CPU interface. By default, arrayed nodes are kept as arrays.
            """,
        )

        arg_group.add_argument(
            "--max-decode-depth",
            type=int,
            default=1,
            help="""Maximum depth for address decoder to descend into nested
            addressable components. Value of 0 decodes all levels (infinite depth).
            Value of 1 decodes only top-level children. Value of 2 decodes top-level
            and one level deeper, etc. Default is 1.
            """,
        )

    def do_export(self, top_node: "AddrmapNode", options: "argparse.Namespace") -> None:
        cpuifs = self.get_cpuifs()

        x = BusDecoderExporter()
        x.export(
            top_node,
            options.output,
            cpuif_cls=cpuifs[options.cpuif],
            module_name=options.module_name,
            package_name=options.package_name,
            address_width=options.addr_width,
            cpuif_unroll=options.unroll,
            max_decode_depth=options.max_decode_depth,
        )
