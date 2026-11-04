from __future__ import annotations

from collections import Counter
from typing import TypedDict

from systemrdl.node import AddressableNode, AddrmapNode, RegNode
from systemrdl.rdltypes.user_enum import UserEnum

from .design_scanner import DesignScanner
from .identifier_filter import kw_filter as kwf
from .rdl_params import ParameterUsage, RdlParameter, RdlParameterExtractor
from .utils import clog2


class DesignStateKwargs(TypedDict, total=False):
    reuse_hwif_typedefs: bool
    module_name: str
    package_name: str
    address_width: int
    cpuif_unroll: bool
    parametrize: bool
    max_decode_depth: int


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

        # ------------------------
        # Info about the design
        # ------------------------
        self.cpuif_data_width = 0

        # Track any referenced enums
        self.user_enums: list[type[UserEnum]] = []

        self.has_external_addressable = False
        self.has_external_block = False

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

        # ------------------------
        # Extract root-level RDL parameters (only when --parametrize is set)
        # ------------------------
        self.rdl_params: list[RdlParameter]
        self.enable_rdl_params: list[RdlParameter]
        self._enable_params_by_node_dim: dict[tuple[str, int], RdlParameter | None]

        if self.parametrize:
            extractor = RdlParameterExtractor(self.top_node)
            self.rdl_params = extractor.extract()

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

        self._target_names = self._build_target_names()

    def _target_path(self, node: AddressableNode) -> str:
        """Identify a target independently of array indices and node wrappers."""
        return node.get_rel_path(self.top_node, array_suffix="", empty_array_suffix="")

    def _build_target_names(self) -> dict[str, str]:
        paths = {self._target_path(node): node.inst_name for node in self.get_addressable_children_at_depth()}
        # Constants use upper-case names, so uniqueness must hold there as well
        # as in the case-sensitive port and intermediate-signal namespaces.
        counts = Counter(name.upper() for name in paths.values())
        names = {path: name for path, name in paths.items() if counts[name.upper()] == 1}
        used = {name.upper() for name in names.values()}

        # Reserve unique legacy names before assigning hierarchical names. Both
        # flattening (a_b.c versus a.b_c) and case folding can still collide.
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

    def get_target_name(self, node: AddressableNode) -> str:
        """Return the shared identifier for a target's ports and constants."""
        return self._target_names[self._target_path(node)]

    def get_enable_param_for_dimension(self, node: AddressableNode, dim_index: int) -> RdlParameter | None:
        """
        Look up the enable parameter for a specific array dimension of a node.

        Returns the RdlParameter if this dimension is controlled by a
        root-level ADDRESS_MODIFYING parameter, or None otherwise.
        """
        node_path = node.get_rel_path(self.top_node)
        return self._enable_params_by_node_dim.get((node_path, dim_index))

    def resolve_loop_bound(self, node: AddressableNode, dim_index: int, dim: int) -> int | str:
        """Return the parameter name if this dimension is enable-controlled, else the static dim."""
        param = self.get_enable_param_for_dimension(node, dim_index)
        return param.name if param is not None else dim

    def is_decode_boundary(self, node: AddressableNode, depth: int) -> bool:
        """Use one boundary policy for target collection and RTL generators."""
        if self.max_decode_depth > 0 and depth >= self.max_decode_depth:
            return True

        children = [child for child in node.children() if isinstance(child, AddressableNode)]
        # Preserve the existing early boundary for containers whose addressable
        # children are all external.
        if node != self.top_node and not isinstance(node, RegNode):
            if children and all(child.external for child in children):
                return True

        # Unlimited depth includes any addressable leaf, not just registers.
        return self.max_decode_depth == 0 and not children

    def get_addressable_children_at_depth(self, unroll: bool = False) -> list[AddressableNode]:
        """
        Get addressable children at the decode boundary based on max_decode_depth.

        max_decode_depth semantics:
        - 0: decode all levels (return addressable leaves and early external boundaries)
        - 1: decode only top level (return children at depth 1)
        - 2: decode top + 1 level (return children at depth 2)
        - N: decode down to depth N (return children at depth N)

        Args:
            unroll: Whether to unroll arrayed nodes

        Returns:
            List of addressable nodes at the decode boundary
        """

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

        return nodes
