"""Generate Verilator-compatible wrappers for SV interface-based modules.

Verilator does not support SV interface ports on the top-level module.  This
module generates a thin wrapper with flat ports that instantiates the
interface objects and the DUT internally, allowing cocotb+Verilator simulation
of interface-based bus decoder modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from peakrdl_busdecoder.utils import clog2

# ---------------------------------------------------------------------------
# Protocol signal definitions
# ---------------------------------------------------------------------------
# Each entry: (signal_name, width_kind, is_slave_input)
#   width_kind: "1" = scalar, "addr" = address width, "data" = data width,
#               "strobe" = data_width/8, "prot" = 3, "resp" = 2
#   is_slave_input: True = input in slave modport / output in master modport

_APB3_SIGNALS = [
    ("PCLK", "1", True),
    ("PRESETn", "1", True),
    ("PSEL", "1", True),
    ("PENABLE", "1", True),
    ("PWRITE", "1", True),
    ("PADDR", "addr", True),
    ("PWDATA", "data", True),
    ("PRDATA", "data", False),
    ("PREADY", "1", False),
    ("PSLVERR", "1", False),
]

_APB4_SIGNALS = [
    ("PCLK", "1", True),
    ("PRESETn", "1", True),
    ("PSEL", "1", True),
    ("PENABLE", "1", True),
    ("PWRITE", "1", True),
    ("PADDR", "addr", True),
    ("PPROT", "prot", True),
    ("PWDATA", "data", True),
    ("PSTRB", "strobe", True),
    ("PRDATA", "data", False),
    ("PREADY", "1", False),
    ("PSLVERR", "1", False),
]

_AXI4LITE_SIGNALS = [
    ("ACLK", "1", True),
    ("ARESETn", "1", True),
    ("AWVALID", "1", True),
    ("AWREADY", "1", False),
    ("AWADDR", "addr", True),
    ("AWPROT", "prot", True),
    ("WVALID", "1", True),
    ("WREADY", "1", False),
    ("WDATA", "data", True),
    ("WSTRB", "strobe", True),
    ("BVALID", "1", False),
    ("BREADY", "1", True),
    ("BRESP", "resp", False),
    ("ARVALID", "1", True),
    ("ARREADY", "1", False),
    ("ARADDR", "addr", True),
    ("ARPROT", "prot", True),
    ("RVALID", "1", False),
    ("RREADY", "1", True),
    ("RDATA", "data", False),
    ("RRESP", "resp", False),
]

_PROTOCOLS: dict[str, dict[str, Any]] = {
    "apb3": {
        "intf_type": "apb3_intf",
        "signals": _APB3_SIGNALS,
        "slave_name": "s_apb",
        "master_prefix": "m_apb_",
        "has_clock": True,
        "clock_signals": [("PCLK", True), ("PRESETn", True)],
    },
    "apb4": {
        "intf_type": "apb4_intf",
        "signals": _APB4_SIGNALS,
        "slave_name": "s_apb",
        "master_prefix": "m_apb_",
        "has_clock": True,
        "clock_signals": [("PCLK", True), ("PRESETn", True)],
    },
    "axi4lite": {
        "intf_type": "axi4lite_intf",
        "signals": _AXI4LITE_SIGNALS,
        "slave_name": "s_axil",
        "master_prefix": "m_axil_",
        "has_clock": False,
        "clock_signals": [("ACLK", True), ("ARESETn", True)],
    },
}


def _width_str(kind: str, addr_width: int, data_width: int) -> str:
    """Return the Verilog bit-range string (e.g. ``[31:0] ``) for a width kind."""
    if kind == "1":
        return ""
    if kind == "addr":
        return f"[{addr_width - 1}:0] "
    if kind == "data":
        return f"[{data_width - 1}:0] "
    if kind == "strobe":
        return f"[{data_width // 8 - 1}:0] "
    if kind == "prot":
        return "[2:0] "
    if kind == "resp":
        return "[1:0] "
    raise ValueError(f"Unknown width kind: {kind}")


def _array_suffix(dimensions: list[int]) -> str:
    """Return the unpacked array suffix, e.g. ``[4]`` or ``[2][3]``."""
    return "".join(f"[{d}]" for d in dimensions)


def generate_verilator_intf_wrapper(
    module_name: str,
    protocol: str,
    children: list[dict[str, Any]],
    global_addr_width: int,
    global_data_width: int,
    output_dir: Path,
) -> Path:
    """Generate a Verilator wrapper for an interface-based bus decoder module.

    Parameters
    ----------
    module_name:
        Name of the DUT module (interface variant).
    protocol:
        One of ``"apb3"``, ``"apb4"``, ``"axi4lite"``.
    children:
        List of dicts with keys ``inst_name``, ``child_size``, ``is_array``,
        ``dimensions``.  ``child_size`` is the size of a single element.
    global_addr_width:
        Address width of the slave bus interface.
    global_data_width:
        Data width of the bus.
    output_dir:
        Directory to write the wrapper file.

    Returns
    -------
    Path
        Path to the generated wrapper ``.sv`` file.
    """
    proto = _PROTOCOLS[protocol]
    intf_type = proto["intf_type"]
    slave_name = proto["slave_name"]
    master_prefix = proto["master_prefix"]
    signals = proto["signals"]

    wrapper_name = f"{module_name}_wrapper"
    lines: list[str] = []

    # --- Port declarations ---------------------------------------------------
    ports: list[str] = []

    # Slave flat ports
    for sig_name, wk, is_input in signals:
        direction = "input " if is_input else "output"
        width = _width_str(wk, global_addr_width, global_data_width)
        ports.append(f"    {direction} logic {width}{slave_name}_{sig_name}")

    # Master flat ports
    for child in children:
        inst = child["inst_name"]
        port_base = f"{master_prefix}{inst}"
        is_array = child["is_array"]
        dims = child.get("dimensions", [])
        child_addr_width = clog2(child["child_size"])
        arr_sfx = _array_suffix(dims) if is_array else ""

        for sig_name, wk, is_slave_input in signals:
            # Master port direction is opposite of slave for data signals
            direction = "output" if is_slave_input else "input "
            width = _width_str(wk, child_addr_width, global_data_width)
            ports.append(f"    {direction} logic {width}{port_base}_{sig_name}{arr_sfx}")

    # --- Module header -------------------------------------------------------
    lines.append(f"module {wrapper_name} (")
    lines.append(",\n".join(ports))
    lines.append(");")
    lines.append("")

    # --- Interface instantiations --------------------------------------------
    # Slave interface
    lines.append(f"    {intf_type} #(.DATA_WIDTH({global_data_width}), "
                 f".ADDR_WIDTH({global_addr_width})) {slave_name}_intf();")

    # Master interfaces
    for child in children:
        inst = child["inst_name"]
        intf_inst = f"{master_prefix}{inst}_intf"
        child_addr_width = clog2(child["child_size"])
        arr_sfx = _array_suffix(child.get("dimensions", [])) if child["is_array"] else ""
        lines.append(f"    {intf_type} #(.DATA_WIDTH({global_data_width}), "
                     f".ADDR_WIDTH({child_addr_width})) {intf_inst} {arr_sfx}();")

    lines.append("")

    # --- Slave wiring --------------------------------------------------------
    lines.append("    // Connect flat slave ports to slave interface")
    for sig_name, _wk, is_input in signals:
        flat_sig = f"{slave_name}_{sig_name}"
        intf_sig = f"{slave_name}_intf.{sig_name}"
        if is_input:
            lines.append(f"    assign {intf_sig} = {flat_sig};")
        else:
            lines.append(f"    assign {flat_sig} = {intf_sig};")

    lines.append("")

    # --- Master wiring -------------------------------------------------------
    for child in children:
        inst = child["inst_name"]
        port_base = f"{master_prefix}{inst}"
        intf_inst = f"{master_prefix}{inst}_intf"
        is_array = child["is_array"]
        dims = child.get("dimensions", [])

        lines.append(f"    // Connect master interface to flat ports: {inst}")

        if is_array:
            # Generate block for array wiring
            genvars = [f"gi{i}_{inst}" for i in range(len(dims))]
            for i, gv in enumerate(genvars):
                lines.append(f"    genvar {gv};")

            indent = "    "
            for i, (gv, dim) in enumerate(zip(genvars, dims)):
                lines.append(f"{indent}generate")
                indent += "    "
                lines.append(f"{indent}for ({gv} = 0; {gv} < {dim}; {gv}++) begin : gen_{inst}_{i}")
                indent += "    "

            idx_expr = "".join(f"[{gv}]" for gv in genvars)

            for sig_name, _wk, is_slave_input in signals:
                flat_sig = f"{port_base}_{sig_name}{idx_expr}"
                intf_sig = f"{intf_inst}{idx_expr}.{sig_name}"
                if is_slave_input:
                    # Master output → flat output
                    lines.append(f"{indent}assign {flat_sig} = {intf_sig};")
                else:
                    # Master input ← flat input
                    lines.append(f"{indent}assign {intf_sig} = {flat_sig};")

            for i in range(len(dims)):
                indent = indent[:-4]
                lines.append(f"{indent}end")
                indent = indent[:-4]
                lines.append(f"{indent}endgenerate")
        else:
            for sig_name, _wk, is_slave_input in signals:
                flat_sig = f"{port_base}_{sig_name}"
                intf_sig = f"{intf_inst}.{sig_name}"
                if is_slave_input:
                    lines.append(f"    assign {flat_sig} = {intf_sig};")
                else:
                    lines.append(f"    assign {intf_sig} = {flat_sig};")

        lines.append("")

    # --- DUT instantiation ---------------------------------------------------
    lines.append(f"    {module_name} dut (")
    dut_ports: list[str] = []
    dut_ports.append(f"        .{slave_name}({slave_name}_intf)")
    for child in children:
        inst = child["inst_name"]
        intf_inst = f"{master_prefix}{inst}_intf"
        dut_ports.append(f"        .{master_prefix}{inst}({intf_inst})")
    lines.append(",\n".join(dut_ports))
    lines.append("    );")
    lines.append("")
    lines.append("endmodule")
    lines.append("")

    wrapper_path = output_dir / f"{wrapper_name}.sv"
    wrapper_path.write_text("\n".join(lines))
    return wrapper_path
