import inspect
import os
from typing import TYPE_CHECKING

import jinja2 as jj
from systemrdl.node import AddressableNode

from ..utils import clog2, get_indexed_path, is_pow2, roundup_pow2
from .fanin_gen import FaninGenerator
from .fanout_gen import FanoutGenerator

if TYPE_CHECKING:
    from ..exporter import BusDecoderExporter


class BaseCpuif:
    # Path is relative to the location of the class that assigns this variable
    template_path = ""

    def __init__(self, exp: "BusDecoderExporter") -> None:
        self.exp = exp
        self.reset = exp.ds.top_node.cpuif_reset
        self.unroll = exp.ds.cpuif_unroll

    @property
    def addressable_children(self) -> list[AddressableNode]:
        return [
            child
            for child in self.exp.ds.top_node.children(unroll=self.unroll)
            if isinstance(child, AddressableNode)
        ]

    @property
    def addr_width(self) -> int:
        return self.exp.ds.addr_width

    @property
    def data_width(self) -> int:
        return self.exp.ds.cpuif_data_width

    @property
    def data_width_bytes(self) -> int:
        return self.data_width // 8

    @property
    def port_declaration(self) -> str:
        raise NotImplementedError()

    @property
    def parameters(self) -> list[str]:
        """
        Optional list of additional parameters this CPU interface provides to
        the module's definition
        """
        array_parameters = [
            f"localparam N_{child.inst_name.upper()}S = {child.n_elements}"
            for child in self.addressable_children
            if self.check_is_array(child)
        ]
        return array_parameters

    def _get_template_path_class_dir(self) -> str:
        """
        Traverse up the MRO and find the first class that explicitly assigns
        template_path. Returns the directory that contains the class definition.
        """
        for cls in inspect.getmro(self.__class__):
            if "template_path" in cls.__dict__:
                class_dir = os.path.dirname(inspect.getfile(cls))
                return class_dir
        raise RuntimeError

    def check_is_array(self, node: AddressableNode) -> bool:
        # When unrolling is enabled, children(unroll=True) returns individual
        # array elements with current_idx set. These should NOT be treated as arrays.
        if self.unroll and hasattr(node, 'current_idx') and node.current_idx is not None:
            return False
        return node.is_array

    def get_implementation(self) -> str:
        class_dir = self._get_template_path_class_dir()
        loader = jj.FileSystemLoader(class_dir)
        jj_env = jj.Environment(
            loader=loader,
            undefined=jj.StrictUndefined,
        )
        jj_env.tests["array"] = self.check_is_array  # type: ignore
        jj_env.filters["clog2"] = clog2  # type: ignore
        jj_env.filters["is_pow2"] = is_pow2  # type: ignore
        jj_env.filters["roundup_pow2"] = roundup_pow2  # type: ignore
        jj_env.filters["address_slice"] = self.get_address_slice  # type: ignore
        jj_env.filters["get_path"] = lambda x: get_indexed_path(self.exp.ds.top_node, x, "i")  # type: ignore
        jj_env.filters["walk"] = self.exp.walk  # type: ignore

        context = {  # type: ignore
            "cpuif": self,
            "ds": self.exp.ds,
            "fanout": FanoutGenerator,
            "fanin": FaninGenerator,
        }

        template = jj_env.get_template(self.template_path)
        return template.render(context)

    def get_address_slice(self, node: AddressableNode, cpuif_addr: str = "cpuif_addr") -> str:
        addr = node.raw_absolute_address - self.exp.ds.top_node.raw_absolute_address
        size = node.size

        return f"({cpuif_addr} - 'h{addr:x})[{clog2(size) - 1}:0]"

    def fanout(self, node: AddressableNode) -> str:
        raise NotImplementedError

    def fanin(self, node: AddressableNode | None = None) -> str:
        raise NotImplementedError

    def readback(self, node: AddressableNode | None = None) -> str:
        raise NotImplementedError
