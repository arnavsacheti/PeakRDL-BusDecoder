"""Helpers for cross-block integration tests.

These utilities extract *structural facts* from generated SystemVerilog so
tests can cross-check the different generator stages (ports, select struct,
address decoder, fanout, fanin, package) against each other and against the
compiled SystemRDL address map.

The address decoder is additionally *evaluated* in Python: :func:`route`
walks the parsed if/else + for-loop structure for a concrete address and
returns which select signals fire. This lets tests verify end-to-end routing
behavior (address in -> block select out) without an HDL simulator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import product

from systemrdl.node import AddressableNode, AddrmapNode, MemNode, RegNode

# ---------------------------------------------------------------------------
# Decode logic parsing / evaluation
# ---------------------------------------------------------------------------

_RE_IF = re.compile(r"^if \((?P<cond>.*)\) begin$")
_RE_ELSE_IF = re.compile(r"^end else if \((?P<cond>.*)\) begin$")
_RE_ELSE = re.compile(r"^end else begin$")
_RE_FOR = re.compile(r"^for \(int (?P<var>\w+) = 0; (?P=var) < (?P<bound>\d+); (?P=var)\+\+\) begin$")
_RE_END = re.compile(r"^end$")
_RE_ASSIGN = re.compile(r"^cpuif_(?:wr|rd)_sel\.(?P<target>[\w.\[\]]+) = 1'b1;$")

# SystemVerilog expression -> Python expression rewrites
_RE_WIDTH_CAST = re.compile(r"(\d+)'\(")  # 14'( ... )  -> _wcast(14, ... )
_RE_HEX = re.compile(r"(?:\d+)?'h([0-9a-fA-F_]+)")
_RE_DEC = re.compile(r"(?:\d+)?'d([0-9_]+)")
_RE_BIN = re.compile(r"(?:\d+)?'b([01_]+)")


def _sv_expr_to_python(expr: str) -> str:
    expr = _RE_WIDTH_CAST.sub(r"_wcast(\1,", expr)
    expr = _RE_HEX.sub(lambda m: str(int(m.group(1).replace("_", ""), 16)), expr)
    expr = _RE_DEC.sub(lambda m: m.group(1).replace("_", ""), expr)
    expr = _RE_BIN.sub(lambda m: str(int(m.group(1).replace("_", ""), 2)), expr)
    expr = expr.replace("&&", " and ").replace("||", " or ")
    return expr


@dataclass
class DecodeAssign:
    """One ``cpuif_*_sel.<target> = 1'b1;`` statement and its guards."""

    target: str  # e.g. "uarts[i0]", "rf_a.ra", "cpuif_err"
    conditions: list[str] = field(default_factory=list)  # python exprs, all must hold
    loops: list[tuple[str, int]] = field(default_factory=list)  # enclosing (var, bound)


@dataclass
class _Frame:
    kind: str  # "cond" or "loop"
    cond: str | None = None  # python expr of the taken branch (None for plain else)
    prior: list[str] = field(default_factory=list)  # negated earlier branches
    loop: tuple[str, int] | None = None

    def guards(self) -> list[str]:
        result = [f"not ({c})" for c in self.prior]
        if self.cond is not None:
            result.append(self.cond)
        return result


def parse_decode_assigns(module_text: str, flavor: str) -> list[DecodeAssign]:
    """Parse the read or write address decoder into a list of guarded assigns.

    Parameters
    ----------
    module_text:
        Full text of the generated module.
    flavor:
        ``"wr"`` or ``"rd"``.
    """
    marker = {"wr": "// Write Address Decoder", "rd": "// Read Address Decoder"}[flavor]
    start = module_text.index(marker)
    body = module_text[start:]
    body = body[body.index("always_comb begin") + len("always_comb begin") :]

    assigns: list[DecodeAssign] = []
    stack: list[_Frame] = []

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue

        if m := _RE_FOR.match(line):
            stack.append(_Frame(kind="loop", loop=(m.group("var"), int(m.group("bound")))))
        elif m := _RE_IF.match(line):
            stack.append(_Frame(kind="cond", cond=_sv_expr_to_python(m.group("cond"))))
        elif m := _RE_ELSE_IF.match(line):
            frame = stack[-1]
            assert frame.kind == "cond", f"unexpected 'else if' nesting near: {line}"
            assert frame.cond is not None
            frame.prior.append(frame.cond)
            frame.cond = _sv_expr_to_python(m.group("cond"))
        elif _RE_ELSE.match(line):
            frame = stack[-1]
            assert frame.kind == "cond", f"unexpected 'else' nesting near: {line}"
            assert frame.cond is not None
            frame.prior.append(frame.cond)
            frame.cond = None
        elif _RE_END.match(line):
            if not stack:
                # closed the always_comb block itself; decoder is done
                break
            stack.pop()
        elif m := _RE_ASSIGN.match(line):
            conditions: list[str] = []
            loops: list[tuple[str, int]] = []
            for frame in stack:
                if frame.kind == "loop":
                    assert frame.loop is not None
                    loops.append(frame.loop)
                else:
                    conditions.extend(frame.guards())
            assigns.append(DecodeAssign(m.group("target"), conditions, loops))
        # anything else (default '{...} assignment, endmodule, ...) is ignored

    return assigns


def route(assigns: list[DecodeAssign], addr: int) -> list[str]:
    """Evaluate the parsed decoder for one address.

    Returns the list of select targets that fire, with loop indices resolved,
    e.g. ``["uarts[1]"]`` or ``["cpuif_err"]``. An empty list means the
    address is dead: no block is selected and no error is flagged.
    """
    base_env = {
        "_wcast": lambda width, value: value & ((1 << width) - 1),
        "cpuif_req": 1,
        "cpuif_wr_en": 1,
        "cpuif_rd_en": 1,
        "cpuif_wr_addr": addr,
        "cpuif_rd_addr": addr,
    }

    fired: list[str] = []
    for assign in assigns:
        loop_vars = [var for var, _ in assign.loops]
        bounds = [bound for _, bound in assign.loops]
        for indices in product(*(range(b) for b in bounds)):
            env = dict(base_env, **dict(zip(loop_vars, indices, strict=True)))
            if all(eval(cond, {"__builtins__": {}}, env) for cond in assign.conditions):
                target = assign.target
                for var, value in zip(loop_vars, indices, strict=True):
                    target = target.replace(f"[{var}]", f"[{value}]")
                fired.append(target)
    return fired


# ---------------------------------------------------------------------------
# Module structure parsing
# ---------------------------------------------------------------------------

_RE_INTF_MASTER_PORT = re.compile(
    r"^\s*\w+_intf\.master\s+m_(?:apb|axil)_(?P<name>\w+)\s*(?P<dims>(?:\[\w+\]\s*)*),?\s*$",
    re.MULTILINE,
)
_RE_LOCALPARAM = re.compile(r"localparam\s+(?P<name>\w+)\s*=\s*(?P<value>[^;,)\s]+)")
_RE_DIM = re.compile(r"\[(\w+)\]")


def _resolve_dim(dim: str, localparams: dict[str, int]) -> int:
    return int(dim) if dim.isdigit() else localparams[dim]


def parse_module_localparams(module_text: str) -> dict[str, int]:
    """Extract integer localparams declared in the module header."""
    header = module_text[: module_text.index(");")]
    params: dict[str, int] = {}
    for m in _RE_LOCALPARAM.finditer(header):
        value = m.group("value")
        if value.isdigit():
            params[m.group("name")] = int(value)
    return params


def parse_interface_master_ports(module_text: str) -> dict[str, tuple[int, ...]]:
    """Return master interface ports as ``{name: dims}`` (name has bus prefix stripped).

    Duplicate port names are surfaced via a trailing ``#<n>`` suffix so tests
    can assert on (absence of) collisions.
    """
    header = module_text[: module_text.index(");")]
    localparams = parse_module_localparams(module_text)
    ports: dict[str, tuple[int, ...]] = {}
    for m in _RE_INTF_MASTER_PORT.finditer(header):
        name = m.group("name")
        dims = tuple(_resolve_dim(d, localparams) for d in _RE_DIM.findall(m.group("dims")))
        if name in ports:
            suffix = 2
            while f"{name}#{suffix}" in ports:
                suffix += 1
            name = f"{name}#{suffix}"
        ports[name] = dims
    return ports


def parse_flat_master_ports(module_text: str, select_signal: str) -> dict[str, tuple[int, ...]]:
    """Return flat-style master ports as ``{name: dims}``.

    Masters are identified by their select/valid signal (``PSEL`` for APB,
    ``AWVALID`` for AXI4-Lite) to count each master exactly once.
    """
    header = module_text[: module_text.index(");")]
    localparams = parse_module_localparams(module_text)
    pattern = re.compile(
        rf"^\s*output\s+logic\s+m_(?:apb|axil)_(?P<name>\w+)_{select_signal}"
        rf"(?P<dims>(?:\[\w+\])*)\s*,?\s*$",
        re.MULTILINE,
    )
    ports: dict[str, tuple[int, ...]] = {}
    for m in pattern.finditer(header):
        dims = tuple(_resolve_dim(d, localparams) for d in _RE_DIM.findall(m.group("dims")))
        ports[m.group("name")] = dims
    return ports


def parse_sel_struct_leaves(module_text: str) -> dict[str, tuple[int, ...]]:
    """Expand the ``cpuif_sel_t`` typedef tree into ``{leaf_path: dims}``.

    Nested struct typedefs (``cpuif_sel_<inst>_t``) are expanded recursively,
    e.g. ``{"rf_a.ra": (), "rf_b.rc": (2,)}``. The ``cpuif_err`` field is
    excluded.
    """
    typedefs: dict[str, list[tuple[str, str, tuple[int, ...]]]] = {}
    for m in re.finditer(r"typedef struct \{(?P<body>.*?)\} (?P<name>\w+);", module_text, re.DOTALL):
        fields: list[tuple[str, str, tuple[int, ...]]] = []
        for fm in re.finditer(r"(?P<type>\w+)\s+(?P<name>\w+)(?P<dims>(?:\[\d+\])*);", m.group("body")):
            dims = tuple(int(d) for d in _RE_DIM.findall(fm.group("dims")))
            fields.append((fm.group("type"), fm.group("name"), dims))
        typedefs[m.group("name")] = fields

    leaves: dict[str, tuple[int, ...]] = {}

    def expand(typedef_name: str, prefix: str, outer_dims: tuple[int, ...]) -> None:
        for field_type, field_name, dims in typedefs[typedef_name]:
            path = f"{prefix}{field_name}"
            if field_type in typedefs:
                expand(field_type, f"{path}.", outer_dims + dims)
            elif field_name != "cpuif_err":
                leaves[path] = outer_dims + dims

    expand("cpuif_sel_t", "", ())
    return leaves


def parse_fanout_masters(module_text: str) -> set[str]:
    """Master instance names referenced by the fanout stage (interface style)."""
    start = module_text.index("// Fanout CPU Bus interface signals")
    end = module_text.index("// Fanin CPU Bus interface signals")
    section = module_text[start:end]
    return {m.group(1) for m in re.finditer(r"assign m_(?:apb|axil)_(\w+?)(?:\[\w+\])*\.", section)}


def parse_fanin_sel_paths(module_text: str) -> set[str]:
    """Select-struct paths consumed by the fanin stage (indices stripped)."""
    start = module_text.index("// Fanin CPU Bus interface signals")
    section = module_text[start:]
    end = section.index("// Write Address Decoder")
    section = section[:end]
    paths = {
        re.sub(r"\[\w+\]", "", m.group(1))
        for m in re.finditer(r"if \(cpuif_(?:wr|rd)_sel\.([\w.\[\]]+)\)", section)
    }
    return paths - {"cpuif_err"}


def parse_package_localparams(package_text: str) -> dict[str, int]:
    """Extract ``localparam NAME = value;`` entries from the generated package."""
    params: dict[str, int] = {}
    for m in re.finditer(r"localparam\s+(\w+)\s*=\s*([^;]+);", package_text):
        value = m.group(2).strip()
        params[m.group(1)] = int(_sv_expr_to_python(value), 0)
    return params


# ---------------------------------------------------------------------------
# SystemRDL ground-truth oracle
# ---------------------------------------------------------------------------


def occupied_extent(node: AddressableNode) -> int:
    """Bytes from a node's base address to the end of its last implemented leaf.

    The generated decoder bounds each block by its *occupied* extent (end of
    the last register/memory), not by the declared size of the component.
    """
    if isinstance(node, (RegNode, MemNode)):
        return node.size

    ends = []
    for child in node.children(unroll=False):
        if not isinstance(child, AddressableNode):
            continue
        end = child.raw_address_offset + occupied_extent(child)
        if child.is_array:
            assert child.array_stride is not None
            end += child.array_stride * (child.n_elements - 1)
        ends.append(end)
    return max(ends) if ends else node.size


def top_level_blocks(top: AddrmapNode) -> list[AddressableNode]:
    """Addressable children directly under the exported top node (rolled-up)."""
    return [c for c in top.children(unroll=False) if isinstance(c, AddressableNode)]


def iter_reg_expectations(top: AddrmapNode) -> list[tuple[int, str]]:
    """Yield ``(relative_address, expected_select_target)`` for every register.

    The expected target is the decoder select for the *top-level* block
    enclosing the register (default ``max_decode_depth=1`` semantics),
    including array indices, e.g. ``uarts[1]`` or ``ctrl``.
    """
    expectations: list[tuple[int, str]] = []

    def visit(node: AddressableNode) -> None:
        for child in node.children(unroll=True):
            if not isinstance(child, AddressableNode):
                continue
            if isinstance(child, RegNode):
                # Find the ancestor that is a direct child of top
                block: AddressableNode = child
                while block.parent is not top:
                    parent = block.parent
                    assert isinstance(parent, AddressableNode)
                    block = parent
                target = block.inst_name
                for idx in block.current_idx or []:
                    target += f"[{idx}]"
                rel_addr = child.absolute_address - top.absolute_address
                expectations.append((rel_addr, target))
            else:
                visit(child)

    visit(top)
    return expectations
