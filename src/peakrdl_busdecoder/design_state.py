from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import TypedDict

from systemrdl.node import AddressableNode, AddrmapNode, RegNode
from systemrdl.rdltypes.user_enum import UserEnum

from .design_scanner import DesignScanner
from .identifier_filter import kw_filter as kwf
from .node_meta import NodeMeta
from .rdl_params import ParameterUsage, RdlParameter
from .utils import clog2


class DesignStateKwargs(TypedDict, total=False):
    reuse_hwif_typedefs: bool
    module_name: str
    package_name: str
    address_width: int
    cpuif_unroll: bool
    parametrize: bool
    max_decode_depth: int
    clk_src: str
    gate_signals: bool
    apb_buffer: str
    axi4lite_max_outstanding: int


class DesignState:
    """
    Dumping ground for all sorts of variables that are relevant to a particular
    design.
    """

    def __init__(self, top_node: AddrmapNode, kwargs: DesignStateKwargs) -> None:
        self.top_node = top_node
        msg = top_node.env.msg

        # ------------------------
        # Extract compiler args
        # ------------------------
        self.reuse_hwif_typedefs: bool = kwargs.pop("reuse_hwif_typedefs", True)
        self.module_name: str = kwargs.pop("module_name", None) or kwf(self.top_node.inst_name)
        self.package_name: str = kwargs.pop("package_name", None) or f"{self.module_name}_pkg"
        user_addr_width: int | None = kwargs.pop("address_width", None)

        self.cpuif_unroll: bool = kwargs.pop("cpuif_unroll", False)
        self.parametrize: bool = kwargs.pop("parametrize", False)
        self.max_decode_depth: int = kwargs.pop("max_decode_depth", 1)
        self.clk_src: str = kwargs.pop("clk_src", "design")
        if self.clk_src not in ("cpuif", "design"):
            msg.fatal(f"clk_src must be 'cpuif' or 'design', got {self.clk_src!r}")
        self.gate_signals: bool = kwargs.pop("gate_signals", False)

        self.axi4lite_max_outstanding: int = kwargs.pop("axi4lite_max_outstanding", 4)
        if self.axi4lite_max_outstanding < 1:
            msg.fatal(
                "axi4lite_max_outstanding must be greater than or equal to 1, "
                f"got {self.axi4lite_max_outstanding}"
            )

        self.apb_buffer: str = kwargs.pop("apb_buffer", "none")
        if self.apb_buffer not in ("none", "in", "out", "both"):
            msg.fatal(f"apb_buffer must be one of 'none', 'in', 'out', 'both', got {self.apb_buffer!r}")
        if self.apb_buffer != "none" and self.clk_src != "design":
            msg.fatal("apb_buffer requires clk_src='design' (the buffer flops use the design clk/rst)")

        # ------------------------
        # Info about the design
        # ------------------------
        self.cpuif_data_width = 0

        # Track any referenced enums
        self.user_enums: list[type[UserEnum]] = []

        self.has_external_addressable = False
        self.has_external_block = False

        # Per-node facts cached during the scan walk so downstream listeners
        # don't recompute the same predicates on each pass.
        self._node_meta: dict[str, NodeMeta] = {}
        self._addressable_children_cache: dict[tuple[int, bool], list[AddressableNode]] = {}

        # Scan the design to fill in above variables.
        scanner = DesignScanner(self)
        scanner.do_scan()

        self._target_names = self._build_target_names()
        self._struct_type_names = self._compute_struct_type_names()

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

        # ------------------------
        # Extract root-level RDL parameters (only when --parametrize is set)
        # ------------------------
        self.rdl_params: list[RdlParameter]
        self.enable_rdl_params: list[RdlParameter]
        self._enable_params_by_node_dim: dict[tuple[str, int], RdlParameter | None]

        if self.parametrize:
            assert scanner.param_extractor is not None
            self.rdl_params = scanner.param_extractor.classify()

            # Cache the enable params list (extract() only returns ADDRESS_MODIFYING)
            self.enable_rdl_params = [
                p for p in self.rdl_params if p.usage == ParameterUsage.ADDRESS_MODIFYING
            ]

            # Build lookup: (node rel_path, dimension index) -> enable parameter.
            # If multiple parameters map to the same dimension, mark ambiguous so
            # we can safely fall back to static bounds instead of picking one by order.
            self._enable_params_by_node_dim = {}
            for param in self.enable_rdl_params:
                for ae in param.array_enables:
                    key = (ae.node_path, ae.dimension_index)
                    existing = self._enable_params_by_node_dim.get(key)
                    if existing is None and key in self._enable_params_by_node_dim:
                        continue
                    if existing is not None and existing.name != param.name:
                        self._enable_params_by_node_dim[key] = None
                    else:
                        self._enable_params_by_node_dim[key] = param
        else:
            self.rdl_params = []
            self.enable_rdl_params = []
            self._enable_params_by_node_dim = {}

    def _target_path(self, node: AddressableNode) -> str:
        """Identify a target independently of array indices and node wrappers."""
        return node.get_rel_path(self.top_node, array_suffix="", empty_array_suffix="")

    def _build_unique_names(
        self, paths: dict[str, str], reserved: Iterable[str] = ()
    ) -> dict[str, str]:
        # Package constants fold names to upper case. Reserve unique legacy
        # names before qualifying duplicates, then disambiguate flattened paths.
        counts = Counter(name.upper() for name in paths.values())
        used = {name.upper() for name in reserved}
        names = {
            path: name
            for path, name in paths.items()
            if counts[name.upper()] == 1 and name.upper() not in used
        }
        used.update(name.upper() for name in names.values())
        for path in sorted(paths):
            if path in names:
                continue
            base = path.replace(".", "_")
            name = base
            suffix = 2
            while name.upper() in used:
                name = f"{base}__{suffix}"
                suffix += 1
            names[path] = name
            used.add(name.upper())
        return names

    def _build_target_names(self) -> dict[str, str]:
        # MIN_ADDR_WIDTH belongs to the decoder itself, not a routed target.
        paths = {
            self._target_path(node): node.inst_name
            for node in self.get_addressable_children_at_depth()
        }
        return self._build_unique_names(paths, reserved=("MIN",))

    def get_target_name(self, node: AddressableNode) -> str:
        """Return the shared identifier for a target's ports and constants."""
        return self._target_names[self._target_path(node)]

    def _compute_struct_type_names(self) -> dict[str, str]:
        """Name selector typedefs by their full top-relative paths."""
        emitters: dict[str, AddressableNode] = {}
        for boundary in self.get_addressable_children_at_depth():
            parent = boundary.parent
            while isinstance(parent, AddressableNode) and parent != self.top_node:
                emitters[self._target_path(parent)] = parent
                parent = parent.parent
        names = self._build_unique_names({path: path.replace(".", "_") for path in emitters})
        return {path: f"cpuif_sel_{name}_t" for path, name in names.items()}

    def struct_type_name(self, node: AddressableNode) -> str:
        """SystemVerilog type name for a node's nested select struct."""
        return self._struct_type_names[self._target_path(node)]

    def open_array_dims(self, node: AddressableNode) -> list[int]:
        """Rolled dimensions from the top node through the target, outermost first."""
        dims: list[int] = []
        current: AddressableNode | None = node
        while current is not None and current != self.top_node:
            if current.array_dimensions and current.current_idx is None:
                dims = list(current.array_dimensions) + dims
            parent = current.parent
            current = parent if isinstance(parent, AddressableNode) else None
        return dims

    def unrolled_indices(self, node: AddressableNode) -> list[int]:
        """Concrete array indices along a target's path, outermost first."""
        indices: list[int] = []
        current: AddressableNode | None = node
        while current is not None and current != self.top_node:
            if current.current_idx is not None:
                indices = list(current.current_idx) + indices
            parent = current.parent
            current = parent if isinstance(parent, AddressableNode) else None
        return indices

    def node_base_address(self, node: AddressableNode) -> int:
        """Top-relative base, including concrete indices but not rolled dimensions."""
        address = 0
        current: AddressableNode | None = node
        while current is not None and current != self.top_node:
            address += (
                current.address_offset
                if current.current_idx is not None
                else current.raw_address_offset
            )
            parent = current.parent
            current = parent if isinstance(parent, AddressableNode) else None
        return address

    def node_meta(self, node: AddressableNode) -> NodeMeta:
        return self._node_meta[self._target_path(node)]

    def get_enable_param_for_dimension(self, node: AddressableNode, dim_index: int) -> RdlParameter | None:
        """
        Look up the enable parameter for a specific array dimension of a node.

        Returns the RdlParameter if this dimension is controlled by a
        root-level ADDRESS_MODIFYING parameter, or None otherwise.
        """
        node_path = self.node_meta(node).rel_path
        return self._enable_params_by_node_dim.get((node_path, dim_index))

    def resolve_loop_bound(self, node: AddressableNode, dim_index: int, dim: int) -> int | str:
        """Return the parameter name if this dimension is enable-controlled, else the static dim."""
        param = self.get_enable_param_for_dimension(node, dim_index)
        return param.name if param is not None else dim

    def is_decode_boundary(self, node: AddressableNode, depth: int) -> bool:
        """Use one boundary policy for target collection and RTL generators."""
        if self.max_decode_depth > 0 and depth >= self.max_decode_depth:
            return True

        meta = self.node_meta(node)
        # Containers whose addressable children are all external remain opaque.
        if node != self.top_node and not isinstance(node, RegNode):
            if meta.has_only_external_addressable_children:
                return True

        # Registers, external memories, and empty blocks are boundaries even
        # when they occur before a positive depth limit.
        return not meta.has_addressable_children

    def get_addressable_children_at_depth(self, unroll: bool = False) -> list[AddressableNode]:
        """
        Get addressable children at the decode boundary based on max_decode_depth.

        max_decode_depth semantics:
        - 0: decode all levels (return addressable leaves and early external boundaries)
        - 1: decode only top level (return children at depth 1)
        - 2: decode top + 1 level (return children at depth 2)
        - N: decode down to depth N (return children at depth N)

        Leaves and containers whose addressable children are all external stop
        decoding early, using the same policy as every walker-based generator.

        Args:
            unroll: Whether to unroll arrayed nodes

        Returns:
            List of addressable nodes at the decode boundary
        """

        cache_key = (self.max_decode_depth, unroll)
        cached = self._addressable_children_cache.get(cache_key)
        if cached is not None:
            return cached

        def collect_nodes(node: AddressableNode, current_depth: int) -> list[AddressableNode]:
            if self.is_decode_boundary(node, current_depth):
                return [node]
            result: list[AddressableNode] = []
            for child in node.children(unroll=unroll):
                if isinstance(child, AddressableNode):
                    result.extend(collect_nodes(child, current_depth + 1))
            return result

        # Start collecting from top node's children
        nodes: list[AddressableNode] = []
        for child in self.top_node.children(unroll=unroll):
            if isinstance(child, AddressableNode):
                nodes.extend(collect_nodes(child, 1))

        self._addressable_children_cache[cache_key] = nodes
        return nodes
