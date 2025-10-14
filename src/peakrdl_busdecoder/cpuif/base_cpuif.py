from typing import TYPE_CHECKING
import inspect
import os

import jinja2 as jj
from systemrdl.node import AddressableNode

from ..utils import clog2, is_pow2, roundup_pow2

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
            f"parameter N_{child.inst_name.upper()}S = {child.n_elements}"
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
        return node.is_array and not self.unroll

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

        context = {
            "cpuif": self,
            "ds": self.exp.ds,
        }

        template = jj_env.get_template(self.template_path)
        return template.render(context)
