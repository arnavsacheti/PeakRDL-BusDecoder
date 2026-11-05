"""Pipelined, single-manager AHB-Lite routing adapters."""

from dataclasses import dataclass
from itertools import product
from math import prod
from typing import TYPE_CHECKING

from systemrdl.node import AddressableNode

from ...sv_int import SVInt
from ...utils import clog2, get_indexed_path
from ..base_cpuif import BaseCpuif
from .ahblite_interface import AHBLiteFlatInterface, AHBLiteSVInterface

if TYPE_CHECKING:
    from ...exporter import BusDecoderExporter


@dataclass(frozen=True)
class _ArrayDimension:
    count: int
    stride: int
    component: AddressableNode
    index: int


@dataclass(frozen=True)
class _Target:
    node: AddressableNode
    name: str
    dimensions: tuple[_ArrayDimension, ...]

    @property
    def addr_width(self) -> int:
        return clog2(self.node.size)


@dataclass(frozen=True)
class _Binding:
    target: _Target
    indices: tuple[int, ...]
    select_path: str
    address: int


class AHBLiteCpuifFlat(BaseCpuif):
    """AHB-Lite with discrete ports and an asynchronously reset data phase."""

    template_path = "ahblite_tmpl.sv"

    flat_interface_cls = AHBLiteFlatInterface
    sv_interface_cls = AHBLiteSVInterface
    slave_name_flat = "s_ahb_"
    slave_name_sv = "s_ahb"
    master_signal_prefix = "m_ahb_"

    _interface: AHBLiteFlatInterface | AHBLiteSVInterface

    def __init__(self, exp: "BusDecoderExporter") -> None:
        super().__init__(exp)

        self.targets = tuple(
            self._make_target(node) for node in exp.ds.get_addressable_children_at_depth(unroll=False)
        )
        self._targets_by_name = {target.name: target for target in self.targets}
        self._validate_layout()

        self.bindings = tuple(
            self._make_binding(target, indices)
            for target in self.targets
            for indices in self._element_indices(target)
        )

    @property
    def addressable_children(self) -> list[AddressableNode]:
        # Address-width constants describe target types, not individual array
        # ports. Keeping one entry per target also avoids duplicate constants
        # when the public ports are unrolled.
        return [target.node for target in self.targets]

    @property
    def parameters(self) -> list[str]:
        # Ports retain the elaborated maximum dimensions. Enable parameters
        # only change which elements the address decoder can select.
        return [
            f"parameter {param.sv_type} {param.name} = {param.sv_value}"
            for param in self.exp.ds.enable_rdl_params
        ]

    @property
    def port_declaration(self) -> str:
        slave_name = self.slave_name_sv if self.use_sv_interface else self.slave_name_flat
        return self._interface.get_port_declaration(slave_name, self.master_signal_prefix)

    @property
    def fixed_reset(self) -> tuple[str, bool]:
        return self.signal("HRESETn"), True

    @property
    def target_count(self) -> int:
        # A default-only router still needs legal, nonempty SV vector bounds.
        return max(1, len(self.bindings))

    def target_for_node(self, node: AddressableNode) -> _Target:
        return self._targets_by_name[self.exp.ds.get_target_name(node)]

    def _make_target(self, node: AddressableNode) -> _Target:
        components: list[AddressableNode] = []
        ancestor = node
        while ancestor != self.exp.ds.top_node:
            components.append(ancestor)
            assert isinstance(ancestor.parent, AddressableNode)
            ancestor = ancestor.parent

        dimensions: list[_ArrayDimension] = []
        for component in reversed(components):
            if component.array_dimensions:
                assert component.array_stride is not None
                for dim_index, count in enumerate(component.array_dimensions):
                    stride = component.array_stride * prod(component.array_dimensions[dim_index + 1 :])
                    dimensions.append(_ArrayDimension(count, stride, component, dim_index))

        return _Target(node, self.exp.ds.get_target_name(node), tuple(dimensions))

    @staticmethod
    def _element_indices(target: _Target) -> tuple[tuple[int, ...], ...]:
        return tuple(product(*(range(dim.count) for dim in target.dimensions)))

    def port_indices(self, target: _Target) -> tuple[tuple[int, ...] | None, ...]:
        return self._element_indices(target) if self.unroll else (None,)

    def signal_indices(
        self, target: _Target, node: AddressableNode, indexer: str | int | None
    ) -> tuple[int | str, ...]:
        known = tuple(self.exp.ds.unrolled_indices(node))
        if known:
            return known
        if isinstance(indexer, str):
            return tuple(f"{indexer}{i}" for i in range(len(target.dimensions)))
        if isinstance(indexer, int):
            if len(target.dimensions) != 1:
                raise ValueError("An integer AHB array index requires exactly one array dimension")
            return (indexer,)
        return tuple(dim.count for dim in target.dimensions)

    def _make_binding(self, target: _Target, indices: tuple[int, ...]) -> _Binding:
        select_path = get_indexed_path(self.exp.ds.top_node, target.node, "ahb_index")
        for dim_index, index in enumerate(indices):
            select_path = select_path.replace(f"[ahb_index{dim_index}]", f"[{index}]")
        address = self.exp.ds.node_base_address(target.node)
        address += sum(index * dim.stride for index, dim in zip(indices, target.dimensions, strict=True))
        return _Binding(target, indices, select_path, address)

    def _validate_layout(self) -> None:
        msg = self.exp.ds.top_node.env.msg
        if self.data_width not in (32, 64, 128, 256, 512, 1024):
            msg.error(
                "AHB-Lite requires a common power-of-two data width from 32 through 1024 bits; "
                f"the selected width is {self.data_width} bits. Choose --data-width "
                "32, 64, 128, 256, 512, or 1024, no smaller than the internal register accesswidth.",
                self.exp.ds.top_node.inst.def_src_ref,
            )

        port_names: dict[str, str] = {}
        for target in self.targets:
            node = target.node
            path = node.get_rel_path(self.exp.ds.top_node)
            if self.unroll:
                for indices in self._element_indices(target):
                    port_name = target.name + ("_" + "_".join(map(str, indices)) if indices else "")
                    if port_name in port_names:
                        msg.error(
                            f"AHB-Lite target names '{port_names[port_name]}' and '{path}' "
                            f"collide at unrolled interface port 'm_ahb_{port_name}'.",
                            node.inst.inst_src_ref,
                        )
                    port_names[port_name] = path

            base = self.exp.ds.node_base_address(node)
            if base % 1024 != 0:
                msg.error(
                    f"AHB-Lite target '{path}' base 0x{base:x} must be aligned to a 1 KiB boundary.",
                    node.inst.inst_src_ref,
                )
            if node.size < 1024 or node.size % 1024 != 0:
                msg.error(
                    f"AHB-Lite target '{path}' aperture size {node.size} bytes must be at least "
                    "1 KiB and a multiple of 1 KiB. Place small register maps inside an "
                    "explicitly sized downstream block.",
                    node.inst.inst_src_ref,
                )
            if any(dim.stride % 1024 != 0 for dim in target.dimensions):
                details = ", ".join(
                    f"'{dim.component.get_path()}' dimension {dim.index} "
                    f"(size {dim.count}): {dim.stride} bytes"
                    for dim in target.dimensions
                    if dim.stride % 1024 != 0
                )
                msg.error(
                    f"AHB-Lite target '{path}' has unaligned array strides: {details}. "
                    "Each stride must be a multiple of 1024 bytes (1 KiB); adjust the array's += stride.",
                    node.inst.inst_src_ref,
                )
            end = base + node.size + sum((dim.count - 1) * dim.stride for dim in target.dimensions)
            if base < 0 or end > (1 << self.addr_width):
                msg.error(
                    f"AHB-Lite address width {self.addr_width} cannot represent target '{path}' "
                    f"aperture ending at byte offset 0x{end:x}.",
                    node.inst.inst_src_ref,
                )
        if msg.had_error:
            msg.fatal("Unable to export AHB-Lite due to previous errors")

    def _child_signal(self, binding: _Binding, signal: str) -> str:
        return self._interface.target_signal(signal, binding.target, binding.indices)

    @property
    def target_assignments(self) -> str:
        assignments: list[str] = []
        for index, binding in enumerate(self.bindings):
            target = binding.target
            select = f"cpuif_wr_sel.{binding.select_path} | cpuif_rd_sel.{binding.select_path}"
            assignments.append(f"assign ahb_addr_sel[{index}] = {select};")
            assignments.append(f"assign {self._child_signal(binding, 'HSEL')} = ahb_addr_sel[{index}];")
            address = SVInt(binding.address, self.addr_width)
            assignments.append(
                f"assign {self._child_signal(binding, 'HADDR')} = "
                f"{target.addr_width}'({self.signal('HADDR')} - {address});"
            )
            for signal in ("HREADY", "HTRANS", "HWRITE", "HSIZE", "HBURST", "HPROT", "HMASTLOCK", "HWDATA"):
                assignments.append(f"assign {self._child_signal(binding, signal)} = {self.signal(signal)};")
            assignments.extend(
                (
                    f"assign ahb_child_ready[{index}] = {self._child_signal(binding, 'HREADYOUT')};",
                    f"assign ahb_child_resp[{index}] = {self._child_signal(binding, 'HRESP')};",
                    f"assign ahb_child_rdata[{index}] = {self._child_signal(binding, 'HRDATA')};",
                )
            )
        if not self.bindings:
            assignments.extend(
                (
                    "assign ahb_addr_sel = '0;",
                    "assign ahb_child_ready = '1;",
                    "assign ahb_child_resp = '0;",
                    "assign ahb_child_rdata[0] = '0;",
                )
            )
        return "\n".join(assignments)

    @property
    def interface_checks(self) -> str:
        if not self.is_interface:
            return ""
        checks = ["`ifndef SYNTHESIS"]
        endpoints = [("s_ahb", self.addr_width)]
        for binding in self.bindings:
            endpoint = self._interface.target_signal("HADDR", binding.target, binding.indices).rsplit(".", 1)[
                0
            ]
            endpoints.append((endpoint, binding.target.addr_width))
        for endpoint, addr_width in endpoints:
            checks.extend(
                (
                    "initial begin",
                    f"    assert ($bits({endpoint}.HADDR) == {addr_width})",
                    f'        else $fatal(1, "Interface address width mismatch at %m: '
                    f'{endpoint}.HADDR is %0d bits; expected exactly %0d bits", '
                    f"$bits({endpoint}.HADDR), {addr_width});",
                    f"    assert ($bits({endpoint}.HWDATA) == {self.data_width}",
                    f"        && $bits({endpoint}.HRDATA) == {self.data_width})",
                    f'        else $fatal(1, "Interface data width mismatch at %m: '
                    f"{endpoint}.HWDATA is %0d bits and {endpoint}.HRDATA is %0d bits; "
                    'expected exactly %0d bits each", '
                    f"$bits({endpoint}.HWDATA), $bits({endpoint}.HRDATA), {self.data_width});",
                    "end",
                )
            )
        checks.append("`endif")
        return "\n".join(checks)


class AHBLiteCpuif(AHBLiteCpuifFlat):
    """AHB-Lite using externally clocked ``ahblite_intf`` instances."""

    use_sv_interface = True
