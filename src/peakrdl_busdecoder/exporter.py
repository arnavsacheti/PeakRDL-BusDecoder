import os
from typing import TYPE_CHECKING, Any

import jinja2 as jj
from systemrdl.node import AddrmapNode, RootNode
from systemrdl.rdltypes.user_enum import UserEnum

from .addr_decode import AddressDecode
from .dereferencer import Dereferencer
from .identifier_filter import kw_filter as kwf
from .utils import clog2
from .scan_design import DesignScanner
from .validate_design import DesignValidator
from .cpuif import BaseCpuif
from .cpuif.apb4 import APB4Cpuif
from .sv_int import SVInt

if TYPE_CHECKING:
    pass


class BusDecoderExporter:
    cpuif: BaseCpuif
    address_decode: AddressDecode
    dereferencer: Dereferencer
    ds: "DesignState"

    def __init__(self, **kwargs: Any) -> None:
        # Check for stray kwargs
        if kwargs:
            raise TypeError(f"got an unexpected keyword argument '{list(kwargs.keys())[0]}'")

        loader = jj.ChoiceLoader(
            [
                jj.FileSystemLoader(os.path.dirname(__file__)),
                jj.PrefixLoader(
                    {
                        "base": jj.FileSystemLoader(os.path.dirname(__file__)),
                    },
                    delimiter=":",
                ),
            ]
        )

        self.jj_env = jj.Environment(
            loader=loader,
            undefined=jj.StrictUndefined,
        )

    def export(self, node: RootNode | AddrmapNode, output_dir: str, **kwargs: Any) -> None:
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
        unroll: bool
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
            raise TypeError(f"got an unexpected keyword argument '{list(kwargs.keys())[0]}'")

        # Construct exporter components
        self.cpuif = cpuif_cls(self)
        self.address_decode = AddressDecode(self)
        self.dereferencer = Dereferencer(self)

        # Validate that there are no unsupported constructs
        DesignValidator(self).do_validate()

        # Build Jinja template context
        context = {
            "cpuif": self.cpuif,
            "address_decode": self.address_decode,
            "ds": self.ds,
            "kwf": kwf,
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

        if hwif_report_file:
            hwif_report_file.close()


class DesignState:
    """
    Dumping ground for all sorts of variables that are relevant to a particular
    design.
    """

    def __init__(self, top_node: AddrmapNode, kwargs: Any) -> None:
        self.top_node = top_node
        msg = top_node.env.msg

        # ------------------------
        # Extract compiler args
        # ------------------------
        self.reuse_hwif_typedefs: bool = kwargs.pop("reuse_hwif_typedefs", True)
        self.module_name: str = kwargs.pop("module_name", None) or kwf(self.top_node.inst_name)
        self.package_name: str = kwargs.pop("package_name", None) or (self.module_name + "_pkg")
        user_addr_width: int | None = kwargs.pop("address_width", None)

        self.cpuif_unroll: bool = kwargs.pop("cpuif_unroll", False)

        # ------------------------
        # Info about the design
        # ------------------------
        self.cpuif_data_width = 0

        # Track any referenced enums
        self.user_enums: list[type[UserEnum]] = []

        # Scan the design to fill in above variables
        DesignScanner(self).do_scan()

        if self.cpuif_data_width == 0:
            # Scanner did not find any registers in the design being exported,
            # so the width is not known.
            # Assume 32-bits
            msg.warning(
                "Addrmap being exported only contains external components. Unable to infer the CPUIF bus width. Assuming 32-bits.",
                self.top_node.inst.def_src_ref,
            )
            self.cpuif_data_width = 32

        # ------------------------
        # Min address width encloses the total size AND at least 1 useful address bit
        self.addr_width = max(clog2(self.top_node.size), clog2(self.cpuif_data_width // 8) + 1)

        if user_addr_width is not None:
            if user_addr_width < self.addr_width:
                msg.fatal(
                    f"User-specified address width shall be greater than or equal to {self.addr_width}."
                )
            self.addr_width = user_addr_width
