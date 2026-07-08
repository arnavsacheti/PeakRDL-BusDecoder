from __future__ import annotations

import re
from collections import defaultdict
from typing import TypedDict

from systemrdl.node import AddressableNode, AddrmapNode
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

        # Per-node facts cached during the scan walk so downstream listeners
        # don't recompute the same predicates on each pass.
        self._node_meta: dict[str, NodeMeta] = {}
        self._addressable_children_cache: dict[tuple[int, bool], list[AddressableNode]] = {}

        # Scan the design to fill in above variables.
        scanner = DesignScanner(self)
        scanner.do_scan()

        # Pre-label master port names for the decode boundary: instance name
        # by default, path-qualified when siblings elsewhere in the hierarchy
        # would otherwise collide on the same port name.
        self._master_port_names = self._compute_master_port_names()
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

    @staticmethod
    def _normalized_path(node: AddressableNode) -> str:
        """Node path with concrete array indices rolled up, so every element
        of an unrolled array shares one key."""
        return re.sub(r"\[\d+\]", "[]", node.get_path())

    def _compute_master_port_names(self) -> dict[str, str]:
        """Label every decode-boundary node with its master port base name.

        The base name is the instance name. When two boundary nodes under
        different parents share an instance name (e.g. two regfiles that each
        contain a register named ``status``), every member of the colliding
        group is qualified with its path relative to the top node
        (``blk_a_status``, ``blk_b_status``) so the generated ports stay
        unique. Index suffixes/dimensions for arrays are appended separately
        by the interface layer.
        """
        groups: dict[str, dict[str, AddressableNode]] = defaultdict(dict)
        for child in self.get_addressable_children_at_depth(unroll=self.cpuif_unroll):
            # Keyed by rolled-up path: elements of one array are one master
            groups[child.inst_name][self._normalized_path(child)] = child

        names: dict[str, str] = {}
        for inst_name, nodes in groups.items():
            if len(nodes) == 1:
                names[next(iter(nodes))] = inst_name
            else:
                for key, node in nodes.items():
                    rel_path = node.get_rel_path(self.top_node, empty_array_suffix="")
                    names[key] = re.sub(r"\[[^\]]*\]", "", rel_path).replace(".", "_")
        return names

    def master_port_name(self, node: AddressableNode) -> str:
        """Master port base name for a decode-boundary node.

        Falls back to the instance name for nodes outside the boundary map.
        """
        return self._master_port_names.get(self._normalized_path(node), node.inst_name)

    def _compute_struct_type_names(self) -> dict[str, str]:
        """Assign a unique SystemVerilog type name to every nested select-struct.

        The select struct nests one ``cpuif_sel_<inst>_t`` typedef per internal
        (non-boundary) addressable node on the path to the decode boundaries.
        Two such nodes under different parents can share an instance name (e.g.
        ``group_a.bar`` and ``group_b.bar``), which would emit duplicate
        typedefs. As with master port names, colliding members are qualified
        with their top-relative path so each generated typedef is unique.
        """
        # Nodes that emit a nested struct: the internal ancestors (excluding the
        # top node) of every decode boundary. The struct is always rolled, so
        # boundaries are computed rolled too.
        emitters: dict[str, AddressableNode] = {}
        for boundary in self.get_addressable_children_at_depth(unroll=False):
            parent = boundary.parent
            while isinstance(parent, AddressableNode) and parent is not self.top_node:
                emitters[self._normalized_path(parent)] = parent
                parent = parent.parent

        groups: dict[str, dict[str, AddressableNode]] = defaultdict(dict)
        for key, node in emitters.items():
            groups[node.inst_name][key] = node

        names: dict[str, str] = {}
        for inst_name, nodes in groups.items():
            if len(nodes) == 1:
                names[next(iter(nodes))] = f"cpuif_sel_{inst_name}_t"
            else:
                for key, node in nodes.items():
                    rel_path = node.get_rel_path(self.top_node, empty_array_suffix="")
                    qualified = re.sub(r"\[[^\]]*\]", "", rel_path).replace(".", "_")
                    names[key] = f"cpuif_sel_{qualified}_t"
        return names

    def struct_type_name(self, node: AddressableNode) -> str:
        """SystemVerilog type name for a node's nested select struct."""
        return self._struct_type_names.get(self._normalized_path(node), f"cpuif_sel_{node.inst_name}_t")

    def open_array_dims(self, node: AddressableNode) -> list[int]:
        """All rolled array dimensions open along the path from top down to
        ``node`` inclusive, outermost-first.

        A boundary node that sits below rolled array ancestors is really an
        array of interfaces sized by *every* open dimension (ancestors' + its
        own), not just its own. For repro ``blk[2].myreg[3]`` this returns
        ``[2, 3]``; for a scalar ``reg_a`` under ``bar[3]`` it returns ``[3]``.

        Unrolled elements (``current_idx`` set) contribute no dimension, so a
        fully unrolled path yields ``[]`` (a scalar master).
        """
        dims: list[int] = []
        current: AddressableNode | None = node
        while current is not None and current is not self.top_node:
            if current.array_dimensions and current.current_idx is None:
                dims = list(current.array_dimensions) + dims
            parent = current.parent
            current = parent if isinstance(parent, AddressableNode) else None
        return dims

    def node_meta(self, node: AddressableNode) -> NodeMeta:
        path = node.get_path()
        meta = self._node_meta.get(path)
        if meta is None:
            # Unrolled element nodes carry concrete indices in their path
            # ("blk[2]"), but the scanner records rolled-up paths ("blk[]").
            meta = self._node_meta[re.sub(r"\[\d+\]", "[]", path)]
        return meta

    def get_enable_param_for_dimension(self, node: AddressableNode, dim_index: int) -> RdlParameter | None:
        """
        Look up the enable parameter for a specific array dimension of a node.

        Returns the RdlParameter if this dimension is controlled by a
        root-level ADDRESS_MODIFYING parameter, or None otherwise.
        """
        meta = self._node_meta.get(node.get_path())
        node_path = meta.rel_path if meta is not None else node.get_rel_path(self.top_node)
        return self._enable_params_by_node_dim.get((node_path, dim_index))

    def resolve_loop_bound(self, node: AddressableNode, dim_index: int, dim: int) -> int | str:
        """Return the parameter name if this dimension is enable-controlled, else the static dim."""
        param = self.get_enable_param_for_dimension(node, dim_index)
        return param.name if param is not None else dim

    def get_addressable_children_at_depth(self, unroll: bool = False) -> list[AddressableNode]:
        """
        Get addressable children at the decode boundary based on max_decode_depth.

        max_decode_depth semantics:
        - 0: decode all levels (descend as deep as possible)
        - 1: decode only top level (children at depth 1)
        - N: decode down to depth N

        A node is a decode boundary when any of these hold, matching the rules
        the walker-based generators apply in ``BusDecoderListener.should_skip_node``
        (the port list and the decode/fanout/fanin logic must always agree on
        the same set of nodes):

        - it sits at ``max_decode_depth`` (when a depth limit is set),
        - it has no addressable children (a register, memory, or empty block),
        - it is a block whose addressable children are all external.

        Args:
            unroll: Whether to unroll arrayed nodes

        Returns:
            List of addressable nodes at the decode boundary
        """
        from systemrdl.node import RegNode

        cache_key = (self.max_decode_depth, unroll)
        cached = self._addressable_children_cache.get(cache_key)
        if cached is not None:
            return cached

        def is_boundary(node: AddressableNode, current_depth: int) -> bool:
            if self.max_decode_depth > 0 and current_depth >= self.max_decode_depth:
                return True

            # Compute child facts directly: unrolled nodes are not present in
            # the scanner's node_meta cache (their paths carry indices).
            addressable_children = [c for c in node.children() if isinstance(c, AddressableNode)]
            if not addressable_children:
                return True
            if not isinstance(node, RegNode) and all(c.external for c in addressable_children):
                return True
            return False

        def collect_nodes(node: AddressableNode, current_depth: int) -> list[AddressableNode]:
            if is_boundary(node, current_depth):
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
