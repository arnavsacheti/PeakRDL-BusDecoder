import inspect
import os
from collections import deque
from typing import TYPE_CHECKING, ClassVar

import jinja2 as jj
from systemrdl.node import AddressableNode

from ..utils import clog2, get_indexed_path, is_pow2, roundup_pow2
from .fanin_gen import FaninGenerator
from .fanin_intermediate_gen import FaninIntermediateGenerator
from .fanout_gen import FanoutGenerator
from .interface import FlatInterface, Interface, SVInterface

if TYPE_CHECKING:
    from ..exporter import BusDecoderExporter


class BaseCpuif:
    # Path is relative to the location of the class that assigns this variable
    template_path = ""

    # Concrete cpuif classes set these to wire up the interface helpers.
    flat_interface_cls: ClassVar[type[FlatInterface]]
    sv_interface_cls: ClassVar[type[SVInterface] | None] = None

    # Whether this cpuif uses the SystemVerilog `interface` form (vs. flat ports).
    use_sv_interface: ClassVar[bool] = False

    # Slave/master signal/interface names.
    slave_name_flat: ClassVar[str] = ""  # e.g. "s_apb_"
    slave_name_sv: ClassVar[str] = ""  # e.g. "s_apb"
    master_signal_prefix: ClassVar[str] = ""  # e.g. "m_apb_"

    # Declarative table for SV-interface array fanin overrides.
    # Each entry is (cpuif_lhs, intermediate_suffix, master_signal_or_expr).
    # When the cpuif uses SV interfaces and the slave is an array, the default
    # fanin assignments are replaced with reads from the intermediate signals
    # populated by FaninIntermediateGenerator.
    sv_array_fanin_wr: ClassVar[list[tuple[str, str, str]]] = []
    sv_array_fanin_rd: ClassVar[list[tuple[str, str, str]]] = []

    def __init__(self, exp: "BusDecoderExporter") -> None:
        self.exp = exp
        self.reset = exp.ds.top_node.cpuif_reset
        self.unroll = exp.ds.cpuif_unroll

        interface_cls: type[Interface]
        if self.use_sv_interface:
            assert self.sv_interface_cls is not None, (
                f"{type(self).__name__} sets use_sv_interface=True but sv_interface_cls is None"
            )
            interface_cls = self.sv_interface_cls
        else:
            interface_cls = self.flat_interface_cls
        self._interface = interface_cls(self)

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
    def is_interface(self) -> bool:
        """Returns True if this cpuif uses a SystemVerilog interface."""
        return self._interface.is_interface

    @property
    def port_declaration(self) -> str:
        slave_name = self.slave_name_sv if self.use_sv_interface else self.slave_name_flat
        return self._interface.get_port_declaration(slave_name, self.master_signal_prefix)

    def signal(
        self,
        signal: str,
        node: AddressableNode | None = None,
        idx: str | int | None = None,
    ) -> str:
        return self._interface.signal(signal, node, idx)

    @property
    def parameters(self) -> list[str]:
        """
        Optional list of additional parameters this CPU interface provides to
        the module's definition.

        Includes:
        - Existing array element count localparams (N_<NAME>S)
        - ADDRESS_MODIFYING RDL parameters: exposed as SV parameters with
          max-value constraints (n <= N)
        """
        params: list[str] = []
        ds = self.exp.ds

        # Collect node paths covered by enable RDL parameters so we can
        # skip the redundant auto-generated localparams for them.
        enable_covered_paths: set[str] = set()
        for rdl_param in ds.enable_rdl_params:
            for ae in rdl_param.array_enables:
                enable_covered_paths.add(ae.node_path)

        # Existing array element count localparams (skip if covered by an
        # RDL enable parameter to avoid duplicate declarations)
        for child in self.addressable_children:
            if not self.check_is_array(child):
                continue
            child_path = child.get_rel_path(ds.top_node)
            if child_path in enable_covered_paths:
                continue
            params.append(f"localparam N_{child.inst_name.upper()}S = {child.n_elements}")

        # Address-modifying RDL parameters as SV module parameters
        for rdl_param in ds.enable_rdl_params:
            params.append(f"parameter {rdl_param.sv_type} {rdl_param.name} = {rdl_param.sv_value}")

        return params

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
        jj_env.tests["array"] = self.check_is_array  # type: ignore
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

    # ---- Fanin: protocol-specific defaults + shared SV-array override ----

    def _default_fanin_wr(self, node: AddressableNode | None, *, error: bool) -> str:
        """Protocol-specific write fanin for the flat / non-array case."""
        raise NotImplementedError

    def _default_fanin_rd(self, node: AddressableNode | None, *, error: bool) -> str:
        """Protocol-specific read fanin for the flat / non-array case."""
        raise NotImplementedError

    def _sv_array_override(
        self, node: AddressableNode, signals: list[tuple[str, str, str]]
    ) -> str:
        array_idx = "".join(f"[i{i}]" for i in range(len(node.array_dimensions or ())))
        return "\n" + "\n".join(
            f"{lhs} = {node.inst_name}{suffix}{array_idx};" for lhs, suffix, _ in signals
        )

    def _should_apply_sv_array_override(self, node: AddressableNode | None) -> bool:
        return (
            node is not None
            and self.is_interface
            and node.is_array
            and bool(node.array_dimensions)
        )

    def fanin_wr(self, node: AddressableNode | None = None, *, error: bool = False) -> str:
        base = self._default_fanin_wr(node, error=error)
        if self._should_apply_sv_array_override(node) and self.sv_array_fanin_wr:
            assert node is not None
            return self._sv_array_override(node, self.sv_array_fanin_wr)
        return base

    def fanin_rd(self, node: AddressableNode | None = None, *, error: bool = False) -> str:
        base = self._default_fanin_rd(node, error=error)
        if self._should_apply_sv_array_override(node) and self.sv_array_fanin_rd:
            assert node is not None
            return self._sv_array_override(node, self.sv_array_fanin_rd)
        return base

    def fanin_intermediate_assignments(
        self, node: AddressableNode, inst_name: str, array_idx: str, master_prefix: str, indexed_path: str
    ) -> list[str]:
        """Generate intermediate signal assignments for interface array fanin.

        Built from the union of `sv_array_fanin_rd` and `sv_array_fanin_wr`,
        deduplicated by intermediate suffix (rd order first, then any wr-only
        extras).
        """
        seen: set[str] = set()
        assignments: list[str] = []
        for _, suffix, source in list(self.sv_array_fanin_rd) + list(self.sv_array_fanin_wr):
            if suffix in seen:
                continue
            seen.add(suffix)
            assignments.append(
                f"assign {inst_name}{suffix}{array_idx} = {master_prefix}{indexed_path}.{source};"
            )
        return assignments

    def fanin_intermediate_declarations(self, node: AddressableNode) -> list[str]:
        """Optional extra intermediate signal declarations for interface arrays."""
        return []
