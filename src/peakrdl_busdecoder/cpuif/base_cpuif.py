import inspect
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

import jinja2 as jj
from systemrdl.node import AddressableNode

from ..body import Body, InitialBody, SupportsStr
from ..sv_assertion import Operator, SVAssertion
from ..sv_parameters import SVLocalParam, SVParameter
from ..utils import clog2, get_indexed_path, is_pow2, roundup_pow2
from .fanin_gen import FaninGenerator
from .fanin_intermediate_gen import FaninIntermediateGenerator
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
        return self.exp.ds.get_addressable_children_at_depth(unroll=self.unroll)

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
    def parameters(self) -> list[SVParameter | SVLocalParam]:
        """
        Optional list of additional parameters this CPU interface provides to
        the module's definition
        """
        array_parameters = []
        for child in self.addressable_children:
            if not self.check_is_array(child):
                continue
            if child.array_dimensions is None or len(child.array_dimensions) == 1:
                array_parameters.append(SVParameter(f"N_{child.inst_name.upper()}S", child.n_elements))
            else:
                for i, dim in enumerate(child.array_dimensions):
                    array_parameters.append(SVParameter(f"N_{child.inst_name.upper()}S_{i}", dim))

            # Compute total number of elements for MAX_N_{child.inst_name.upper()}S
            # Should be sane, as this tells us information about the maximum address space,
            # this should be the same as n_elements
            array_parameters.append(SVLocalParam(f"MAX_N_{child.inst_name.upper()}S", child.n_elements))
        return sorted(array_parameters)

    def _get_template_path_class_dir(self) -> Path:
        """
        Traverse up the MRO and find the first class that explicitly assigns
        template_path. Returns the directory that contains the class definition.
        """
        for cls in inspect.getmro(self.__class__):
            if "template_path" in cls.__dict__:
                class_dir = Path(inspect.getfile(cls)).parent
                return class_dir
        raise RuntimeError

    def check_is_array(self, node: AddressableNode) -> bool:
        # When unrolling is enabled, children(unroll=True) returns individual
        # array elements with current_idx set. These should NOT be treated as arrays.
        if self.unroll and hasattr(node, "current_idx") and node.current_idx is not None:
            return False
        return node.is_array

    def get_implementation(self) -> str:
        class_dir = self._get_template_path_class_dir()
        loader = jj.FileSystemLoader(class_dir)
        jj_env = jj.Environment(
            loader=loader,
            undefined=jj.StrictUndefined,
        )
        jj_env.tests["array"] = self.check_is_array
        jj_env.filters["clog2"] = clog2
        jj_env.filters["is_pow2"] = is_pow2
        jj_env.filters["roundup_pow2"] = roundup_pow2
        jj_env.filters["address_slice"] = self.get_address_slice
        jj_env.filters["get_path"] = lambda x: get_indexed_path(self.exp.ds.top_node, x, "i")
        jj_env.filters["walk"] = self.exp.walk

        context = {
            "cpuif": self,
            "ds": self.exp.ds,
            "fanout": FanoutGenerator,
            "fanin": FaninGenerator,
            "fanin_intermediate": FaninIntermediateGenerator,
        }

        template = jj_env.get_template(self.template_path)
        return template.render(context)

    def get_address_slice(self, node: AddressableNode, cpuif_addr: str = "cpuif_addr") -> str:
        addr = node.raw_absolute_address - self.exp.ds.top_node.raw_absolute_address
        size = node.size

        return f"({cpuif_addr} - 'h{addr:x})[{clog2(size) - 1}:0]"

    def _can_truncate_addr(self, node: AddressableNode, array_stack: deque[int]) -> bool:
        if node.size.bit_count() != 1:
            return False
        if node.raw_absolute_address % node.size != 0:
            return False
        for stride in array_stack:
            if stride % node.size != 0:
                return False
        return True

    def fanout(self, node: AddressableNode, array_stack: deque[int]) -> str:
        raise NotImplementedError

    def fanin_wr(self, node: AddressableNode | None = None, *, error: bool = False) -> str:
        raise NotImplementedError

    def fanin_rd(self, node: AddressableNode | None = None, *, error: bool = False) -> str:
        raise NotImplementedError

    def fanin_intermediate_assignments(
        self, node: AddressableNode, inst_name: str, array_idx: str, master_prefix: str, indexed_path: str
    ) -> list[str]:
        """Generate intermediate signal assignments for interface array fanin.

        This method should be implemented by cpuif classes that use interfaces.
        It returns a list of assignment strings that copy signals from interface
        arrays to intermediate unpacked arrays using constant (genvar) indexing.

        Args:
            node: The addressable node
            inst_name: Instance name for the intermediate signals
            array_idx: Array index string (e.g., "[gi0][gi1]")
            master_prefix: Master interface prefix
            indexed_path: Indexed path to the interface element

        Returns:
            List of assignment strings
        """
        return []  # Default: no intermediate assignments needed

    def fanin_intermediate_declarations(self, node: AddressableNode) -> list[str]:
        """Optional extra intermediate signal declarations for interface arrays."""
        return []

    def get_assertions(self) -> list[SupportsStr]:
        """
        Optional list of assertions to include in the CPU interface module
        """
        return []

    def get_initial_assertions(self) -> list[SupportsStr]:
        """
        Optional list of initial assertions to include in the CPU interface module
        """
        initial_assertions = []

        for child in self.addressable_children:
            if not self.check_is_array(child):
                continue

            array_params = []

            if child.array_dimensions is None or len(child.array_dimensions) == 1:
                array_params.append(f"N_{child.inst_name.upper()}S")
            else:
                for i, _ in enumerate(child.array_dimensions):
                    array_params.append(f"N_{child.inst_name.upper()}S_{i}")

            initial_assertions.append(
                SVAssertion(
                    left_expr=f"MAX_N_{child.inst_name.upper()}S",
                    right_expr=" * ".join(array_params),
                    operator=Operator.GREATER_EQUAL,
                    name=f"assert_max_n_{child.inst_name.lower()}s",
                    message=f"MAX_N_{child.inst_name.upper()}S must be at least the product of its dimension parameters.",
                )
            )

        return initial_assertions

    def get_assertion_block(self) -> str:
        """
        Optional assertion block to include in the CPU interface module
        """

        assertion_block = Body()

        if initial_assertions := self.get_initial_assertions():
            init_body = InitialBody()
            for assertion in initial_assertions:
                init_body += f"{assertion!s}"
            assertion_block += init_body

        if assertions := self.get_assertions():
            for assertion in assertions:
                assertion_block += f"{assertion!s}"

        return str(assertion_block)
