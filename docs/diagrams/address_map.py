"""Render the address-map example figure from an elaborated SystemRDL design.

The figure is computed, not drawn: every row comes from decoding each byte
address of the exported addrmap at ``max_decode_depth = 1`` using the
documented decoder rules:

* targets are the top-level addressable children (array elements individually);
* a register target is selected for reads only if it has a software-readable
  field and for writes only if it has a software-writable field;
* block targets (addrmaps, regfiles, memories) forward both directions;
* any byte selecting no target returns a local error (gaps, stride holes and
  the region above the map's size up to the decoder address width).
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from math import ceil, log2
from pathlib import Path

from systemrdl import RDLCompiler
from systemrdl.node import AddressableNode, AddrmapNode, RegNode


@dataclass(frozen=True)
class Element:
    label: str
    start: int
    size: int
    reads: bool
    writes: bool
    is_block: bool


@dataclass
class Segment:
    start: int
    end: int  # exclusive
    read: Element | None
    write: Element | None


def _elements(top: AddrmapNode) -> list[Element]:
    out: list[Element] = []
    for child in top.children():
        if not isinstance(child, AddressableNode):
            continue
        is_reg = isinstance(child, RegNode)
        reads = child.has_sw_readable if is_reg else True
        writes = child.has_sw_writable if is_reg else True
        if child.is_array:
            assert child.array_stride is not None
            for idx in range(child.n_elements):
                out.append(
                    Element(
                        f"{child.inst_name}[{idx}]",
                        child.raw_address_offset + idx * child.array_stride,
                        child.size,
                        reads,
                        writes,
                        not is_reg,
                    )
                )
        else:
            out.append(Element(child.inst_name, child.raw_address_offset, child.size, reads, writes, not is_reg))
    return out


def _addr_width(top: AddrmapNode, data_width: int) -> int:
    return max(ceil(log2(top.size)) if top.size > 1 else 1, ceil(log2(data_width // 8)) + 1)


def _segments(elements: list[Element], space: int) -> list[Segment]:
    def pick(addr: int, reads: bool) -> Element | None:
        for e in elements:
            if e.start <= addr < e.start + e.size and (e.reads if reads else e.writes):
                return e
        return None

    segments: list[Segment] = []
    for addr in range(space):
        rd, wr = pick(addr, True), pick(addr, False)
        if segments and segments[-1].read is rd and segments[-1].write is wr:
            segments[-1].end = addr + 1
        else:
            segments.append(Segment(addr, addr + 1, rd, wr))
    return segments


# -- SVG drawing -------------------------------------------------------------

ROW_H = 30
TOP = 92
COL_ADDR, COL_RD, COL_WR, COL_LOCAL = 20, 196, 386, 576
LANE_W = 180
WIDTH = 760

STYLE = {
    "reg": ("#dbeafe", "#1d4ed8"),
    "block": ("#dcfce7", "#15803d"),
    "error": ("#fee2e2", "#b91c1c"),
}


def _text(x: float, y: float, s: str, *, size: int = 13, anchor: str = "start", weight: str = "normal",
          fill: str = "#111827", family: str = "sans-serif") -> str:
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" text-anchor="{anchor}" '
            f'font-weight="{weight}" fill="{fill}">{escape(s)}</text>')


def _lane(x: int, y: int, h: int, e: Element | None) -> str:
    kind = "error" if e is None else ("block" if e.is_block else "reg")
    fill, stroke = STYLE[kind]
    label = "local error" if e is None else e.label
    style = "italic" if e is None else "normal"
    return (f'<rect x="{x}" y="{y + 2}" width="{LANE_W}" height="{h - 4}" rx="4" fill="{fill}" stroke="{stroke}"/>'
            f'<text x="{x + LANE_W / 2}" y="{y + h / 2 + 4.5}" font-family="sans-serif" font-size="13" '
            f'text-anchor="middle" font-style="{style}" fill="{stroke}">{escape(label)}</text>')


def _hex(v: int, w: int) -> str:
    return f"0x{v:0{w}X}"


def render(rdl_path: Path, data_width: int = 32) -> str:
    compiler = RDLCompiler()
    compiler.compile_file(str(rdl_path))
    top = compiler.elaborate().top

    width = _addr_width(top, data_width)
    space = 1 << width
    segments = _segments(_elements(top), space)
    digits = max(2, ceil(width / 4))

    rows: list[str] = []
    y = TOP
    for seg in segments:
        rows.append(_text(COL_ADDR, y + ROW_H / 2 + 4.5,
                          f"{_hex(seg.start, digits)} – {_hex(seg.end - 1, digits)}", family="monospace"))
        rows.append(_lane(COL_RD, y, ROW_H, seg.read))
        rows.append(_lane(COL_WR, y, ROW_H, seg.write))
        target = seg.read or seg.write
        if target is not None:
            lo = seg.start - target.start
            local = f"A − {_hex(target.start, digits)} → {_hex(lo, 1)}–{_hex(lo + seg.end - seg.start - 1, 1)}"
            rows.append(_text(COL_LOCAL, y + ROW_H / 2 + 4.5, local, size=12, family="monospace", fill="#374151"))
        y += ROW_H

    legend_y = y + 26
    legend: list[str] = []
    x = COL_ADDR
    for kind, text in (("reg", "register target"), ("block", "block target (both directions)"),
                       ("error", "no target: local error response")):
        fill, stroke = STYLE[kind]
        legend.append(f'<rect x="{x}" y="{legend_y - 11}" width="14" height="14" rx="3" fill="{fill}" stroke="{stroke}"/>')
        legend.append(_text(x + 20, legend_y, text, size=12))
        x += 20 + 7.2 * len(text) + 28

    height = legend_y + 20
    header = [
        _text(COL_ADDR, 26, f"Exported addrmap “{top.inst_name}”: {top.size} bytes, "
              f"decoder address width {width} bits, data width {data_width} bits", size=14, weight="bold"),
        _text(COL_ADDR, 46, "Addresses are relative to the exported addrmap: A = system address − system base. "
              "max_decode_depth = 1.", size=12, fill="#374151"),
        _text(COL_ADDR, TOP - 10, "Decoder address A", size=12, weight="bold"),
        _text(COL_RD + LANE_W / 2, TOP - 10, "Read selects", size=12, weight="bold", anchor="middle"),
        _text(COL_WR + LANE_W / 2, TOP - 10, "Write selects", size=12, weight="bold", anchor="middle"),
        _text(COL_LOCAL, TOP - 10, "Child-local address", size=12, weight="bold"),
    ]
    body = "\n".join(header + rows + legend)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
            f'viewBox="0 0 {WIDTH} {height}" role="img" aria-label="Decoded address map of {escape(top.inst_name)}">\n'
            f'<rect width="100%" height="100%" fill="#ffffff"/>\n{body}\n</svg>\n')
