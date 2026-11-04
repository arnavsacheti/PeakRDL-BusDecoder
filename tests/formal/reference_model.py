"""Formal Reference Model for SystemRDL address space and PeakRDL-BusDecoder.

This module implements the mathematical reference model defined in
`spec/systemrdl.md` and `spec/busdecoder.md`. It evaluates address-decode
semantics directly from the elaborated SystemRDL `Node` tree, completely
independent of `peakrdl_busdecoder` generator internals.

It serves as the gold-standard test oracle for:
1. Pure mathematical properties (disjointness, completeness, coverage).
2. Conformance audits against generated SystemVerilog RTL.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum

from systemrdl.node import AddressableNode, AddrmapNode, MemNode, RegNode, RootNode


class Direction(Enum):
    READ = "rd"
    WRITE = "wr"


@dataclass(frozen=True)
class TargetElement:
    """A concrete, fully-indexed decode target element."""

    target_name: str
    hierarchical_path: str
    indices: tuple[int, ...]
    rel_start: int
    size: int
    data_width: int
    is_readable: bool
    is_writable: bool
    node_type: str

    @property
    def rel_end(self) -> int:
        return self.rel_start + self.size

    def contains(self, addr: int) -> bool:
        return self.rel_start <= addr < self.rel_end

    def local_offset(self, addr: int) -> int:
        assert self.contains(addr)
        return addr - self.rel_start

    def permits(self, direction: Direction) -> bool:
        if direction == Direction.READ:
            return self.is_readable
        return self.is_writable

    @property
    def unique_id(self) -> str:
        if not self.indices:
            return self.hierarchical_path
        idx_str = "_".join(str(i) for i in self.indices)
        return f"{self.hierarchical_path}_{idx_str}"


@dataclass
class DecodeResult:
    """Outcome of evaluating an address against the formal decode model."""

    address: int
    direction: Direction
    hit: TargetElement | None
    is_error: bool
    local_offset: int | None
    competing_hits: list[TargetElement] = field(default_factory=list)


class FormalBusDecoderModel:
    """Formal mathematical model of the BusDecoder.

    Constructed strictly from an elaborated AddrmapNode and decoder configuration.
    """

    def __init__(
        self,
        top_node: AddrmapNode | RootNode,
        *,
        max_decode_depth: int = 1,
        address_width: int | None = None,
        cpuif_unroll: bool = False,
    ) -> None:
        if isinstance(top_node, RootNode):
            self.top_node: AddrmapNode = top_node.top
        else:
            self.top_node = top_node

        self.max_decode_depth = max_decode_depth
        self.cpuif_unroll = cpuif_unroll

        # Calculate data width per BD-CFG-DATA-WIDTH
        self.data_width = self._infer_data_width()
        self.data_width_bytes = max(self.data_width // 8, 1)

        # Calculate address width per BD-CFG-ADDR-WIDTH
        min_addr_width = max(
            (self.top_node.size - 1).bit_length(),
            (self.data_width_bytes).bit_length(),
        )
        if address_width is not None:
            if address_width < min_addr_width:
                raise ValueError(
                    f"Address width {address_width} is smaller than minimum required {min_addr_width}"
                )
            self.address_width = address_width
        else:
            self.address_width = max(min_addr_width, 1)

        self.address_space_size = 1 << self.address_width

        # Collect targets according to BD-CFG-MAX-DEPTH
        self.targets: list[TargetElement] = self._collect_targets()

    def _infer_data_width(self) -> int:
        """Maximum accesswidth in internal scope, never crossing external blocks."""
        max_w = 0

        def collect(node: AddressableNode) -> None:
            nonlocal max_w
            for child in node.children(unroll=False):
                if not isinstance(child, AddressableNode) or child.external:
                    continue
                if isinstance(child, RegNode):
                    max_w = max(max_w, child.get_property("accesswidth"))
                else:
                    collect(child)

        collect(self.top_node)
        return max_w or 32

    def _is_sw_readable(self, node: AddressableNode) -> bool:
        if isinstance(node, MemNode):
            return True
        if isinstance(node, RegNode):
            return node.has_sw_readable
        return True

    def _is_sw_writable(self, node: AddressableNode) -> bool:
        if isinstance(node, MemNode):
            return True
        if isinstance(node, RegNode):
            return node.has_sw_writable
        return True

    def _collect_targets(self) -> list[TargetElement]:
        """Collect all concrete target elements at the decode boundary."""
        target_elements: list[TargetElement] = []

        def get_rel_offset(node: AddressableNode) -> int:
            """Return the raw base offset relative to the exported top node."""
            curr: AddressableNode | None = node
            base_offset = 0
            while curr is not None and curr != self.top_node:
                base_offset += curr.raw_address_offset
                parent = curr.parent
                curr = parent if isinstance(parent, AddressableNode) else None
            return base_offset

        boundary_nodes = self._get_boundary_nodes()

        for node in boundary_nodes:
            rel_path = node.get_rel_path(self.top_node)
            base_offset = get_rel_offset(node)

            # Dimensions to iterate: collect all array dimensions along the path
            # For each arrayed ancestor + node itself, generate Cartesian product
            dims_lists: list[list[int]] = []
            strides: list[int] = []

            # Ancestor arrays (outermost to innermost)
            curr: AddressableNode | None = node
            anc_chain: list[AddressableNode] = []
            while curr is not None and curr != self.top_node:
                anc_chain.append(curr)
                parent = curr.parent
                curr = parent if isinstance(parent, AddressableNode) else None
            anc_chain.reverse()

            for anc in anc_chain:
                if anc.is_array:
                    assert anc.array_dimensions is not None
                    assert anc.array_stride is not None
                    # Multidimensional indexing in SystemRDL:
                    # Dimensions [D0, D1, D2] with element stride S
                    # D0 is slowest, D2 fastest.
                    # Strides for each dim:
                    # dim K has stride = S * prod(D_{K+1}..D_{N-1})
                    cum_stride = anc.array_stride
                    dim_strides = [cum_stride]
                    for d in reversed(anc.array_dimensions[1:]):
                        cum_stride *= d
                        dim_strides.append(cum_stride)
                    dim_strides.reverse()

                    for dim, s in zip(anc.array_dimensions, dim_strides, strict=False):
                        dims_lists.append(list(range(dim)))
                        strides.append(s)

            if not dims_lists:
                # Scalar target
                target_elements.append(
                    TargetElement(
                        target_name=node.inst_name,
                        hierarchical_path=rel_path,
                        indices=(),
                        rel_start=base_offset,
                        size=node.size,
                        data_width=self.data_width,
                        is_readable=self._is_sw_readable(node),
                        is_writable=self._is_sw_writable(node),
                        node_type=type(node).__name__,
                    )
                )
            else:
                for idx_tuple in itertools.product(*dims_lists):
                    offset = base_offset + sum(i * s for i, s in zip(idx_tuple, strides, strict=False))
                    target_elements.append(
                        TargetElement(
                            target_name=node.inst_name,
                            hierarchical_path=rel_path,
                            indices=idx_tuple,
                            rel_start=offset,
                            size=node.size,
                            data_width=self.data_width,
                            is_readable=self._is_sw_readable(node),
                            is_writable=self._is_sw_writable(node),
                            node_type=type(node).__name__,
                        )
                    )

        return target_elements

    def _get_boundary_nodes(self) -> list[AddressableNode]:
        """Locate addressable nodes positioned at the decode boundary."""
        nodes: list[AddressableNode] = []

        def collect(curr: AddressableNode, depth: int) -> None:
            if self.max_decode_depth == 0:
                # Depth 0: leaf registers and leaf memories
                has_addressable_children = False
                for child in curr.children(unroll=False):
                    if isinstance(child, AddressableNode):
                        has_addressable_children = True
                        collect(child, depth + 1)
                if not has_addressable_children:
                    nodes.append(curr)
            elif depth == self.max_decode_depth:
                nodes.append(curr)
            elif depth < self.max_decode_depth:
                # Recurse, or if this is a leaf before reaching max depth, treat as target
                has_addressable_children = False
                for child in curr.children(unroll=False):
                    if isinstance(child, AddressableNode):
                        has_addressable_children = True
                        collect(child, depth + 1)
                if not has_addressable_children:
                    nodes.append(curr)

        for top_child in self.top_node.children(unroll=False):
            if isinstance(top_child, AddressableNode):
                collect(top_child, 1)

        return nodes

    def decode(self, address: int, direction: Direction = Direction.READ) -> DecodeResult:
        """Formal decode function: maps (address, direction) to DecodeResult.

        Implements BD-DEC-SOUNDNESS, BD-DEC-EXCLUSIVITY, BD-DEC-COMPLETENESS,
        and BD-DEC-UNMAPPED-ERROR.
        """
        if address < 0 or address >= self.address_space_size:
            return DecodeResult(
                address=address,
                direction=direction,
                hit=None,
                is_error=True,
                local_offset=None,
            )

        matching: list[TargetElement] = []
        for t in self.targets:
            if t.contains(address) and t.permits(direction):
                matching.append(t)

        if not matching:
            return DecodeResult(
                address=address,
                direction=direction,
                hit=None,
                is_error=True,
                local_offset=None,
            )

        if len(matching) > 1:
            # Overlap ambiguity (violates BD-DEC-EXCLUSIVITY)
            return DecodeResult(
                address=address,
                direction=direction,
                hit=matching[0],
                is_error=False,
                local_offset=matching[0].local_offset(address),
                competing_hits=matching,
            )

        hit = matching[0]
        return DecodeResult(
            address=address,
            direction=direction,
            hit=hit,
            is_error=False,
            local_offset=hit.local_offset(address),
        )

    def check_disjointness(self, direction: Direction) -> list[tuple[TargetElement, TargetElement]]:
        """Verify the Disjointness Axiom (BD-DEC-EXCLUSIVITY): no two targets overlap."""
        conflicts: list[tuple[TargetElement, TargetElement]] = []
        for i, t1 in enumerate(self.targets):
            if not t1.permits(direction):
                continue
            for t2 in self.targets[i + 1 :]:
                if not t2.permits(direction):
                    continue
                # Test interval overlap [start, end)
                if max(t1.rel_start, t2.rel_start) < min(t1.rel_end, t2.rel_end):
                    conflicts.append((t1, t2))
        return conflicts
