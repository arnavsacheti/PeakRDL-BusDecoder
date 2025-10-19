import os
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

import jinja2 as jj
from systemrdl.node import AddrmapNode, RootNode
from typing_extensions import Unpack

from .cpuif import BaseCpuif
from .cpuif.apb4 import APB4Cpuif
from .decoder import AddressDecode, DecodeLogicFlavor
from .design_state import DesignState
from .identifier_filter import kw_filter as kwf
from .sv_int import SVInt
from .validate_design import DesignValidator


class ExporterKwargs(TypedDict, total=False):
    cpuif_cls: type[BaseCpuif]
    module_name: str
    package_name: str
    address_width: int
    cpuif_unroll: bool
    reuse_hwif_typedefs: bool


if TYPE_CHECKING:
    pass


class BusDecoderExporter:
    cpuif: BaseCpuif
    address_decode: type[AddressDecode]
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
        """
        # If it is the root node, skip to top addrmap
        if isinstance(node, RootNode):
            top_node = node.top
        else:
            top_node = node

        self.ds = DesignState(top_node, kwargs)

        cpuif_cls: type[BaseCpuif] = kwargs.pop("cpuif_cls", None) or APB4Cpuif

        # Check for stray kwargs
        if kwargs:
            raise TypeError(f"got an unexpected keyword argument '{next(iter(kwargs.keys()))}'")

        # Construct exporter components
        self.cpuif = cpuif_cls(self)
        self.address_decode = AddressDecode

        # Validate that there are no unsupported constructs
        DesignValidator(self).do_validate()

        # Build Jinja template context
        context = {
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "version": version("peakrdl-busdecoder"),
            "cpuif": self.cpuif,
            "address_decode": self.address_decode,
            "DecodeLogicFlavor": DecodeLogicFlavor,
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
