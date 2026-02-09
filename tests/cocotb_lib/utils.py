"""Common utilities for cocotb testbenches."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from systemrdl import RDLCompiler
from systemrdl.node import AddressableNode, AddrmapNode, RegNode

from peakrdl_busdecoder.cpuif.base_cpuif import BaseCpuif
from peakrdl_busdecoder.exporter import BusDecoderExporter

RESET = "\x1b[0m"
DIM = "\x1b[2m"

LEVEL_COLORS = {
    "DEBUG": "\x1b[35m",  # magenta
    "INFO": "\x1b[36m",  # cyan
    "WARNING": "\x1b[33m",  # yellow
    "ERROR": "\x1b[31m",  # red
    "CRITICAL": "\x1b[1;31m",  # bold red
}

# Matches lines like:
# "  0.00ns INFO     cocotb   ..." or "-.--ns INFO gpi ..."
LINE_RE = re.compile(
    r"^(?P<prefix>\s*)"  # leading spaces
    r"(?P<time>[-0-9\.]+[a-zA-Z]+)"  # timestamp (e.g. 0.00ns, -.--ns)
    r"\s+"
    r"(?P<level>[A-Z]+)"  # log level
    r"(?P<rest>.*)$"  # the rest of the line
)


def colorize_cocotb_log(text: str) -> str:
    """
    Colorizes cocotb log lines for improved readability in terminal output.

    Each log line is parsed to identify the timestamp and log level, which are then
    colorized using ANSI escape codes. The timestamp is dimmed, and the log level
    is colored according to its severity (e.g., INFO, WARNING, ERROR).

    Args:
        text: The input string containing cocotb log lines.

    Returns:
        A string with colorized log lines.
    """

    def _color_line(match: re.Match) -> str:
        prefix = match.group("prefix")
        time = match.group("time")
        level = match.group("level")
        rest = match.group("rest")

        level_color = LEVEL_COLORS.get(level, "")
        # dim timestamp, color level
        time_colored = f"{DIM}{time}{RESET}"
        level_colored = f"{level_color}{level}{RESET}" if level_color else level

        return f"{prefix}{time_colored} {level_colored}{rest}"

    lines = []
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m:
            lines.append(_color_line(m))
        else:
            lines.append(line)
    return "\n".join(lines)


def compile_rdl_and_export(
    rdl_source: str, top_name: str, output_dir: Path, cpuif_cls: type[BaseCpuif], **kwargs: Any
) -> tuple[Path, Path]:
    """
    Compile RDL source and export to SystemVerilog.

    Args:
        rdl_source: SystemRDL source code path
        top_name: Name of the top-level addrmap
        output_dir: Directory to write generated files
        cpuif_cls: CPU interface class to use
        **kwargs: Additional arguments to pass to exporter

    Returns:
        Tuple of (module_path, package_path) for generated files
    """
    # Compile RDL source
    compiler = RDLCompiler()

    compiler.compile_file(rdl_source)
    top = compiler.elaborate(top_name)

    # Export to SystemVerilog
    exporter = BusDecoderExporter()
    exporter.export(top, str(output_dir), cpuif_cls=cpuif_cls, **kwargs)

    # Return paths to generated files
    module_name = kwargs.get("module_name", top_name)
    package_name = kwargs.get("package_name", f"{top_name}_pkg")

    module_path = Path(output_dir) / f"{module_name}.sv"
    package_path = Path(output_dir) / f"{package_name}.sv"

    return module_path, package_path


def get_verilog_sources(module_path: Path, package_path: Path, intf_files: list[Path]) -> list[str]:
    """
    Get list of Verilog source files needed for simulation.

    Args:
        module_path: Path to the generated module file
        package_path: Path to the generated package file
        intf_files: List of paths to interface definition files

    Returns:
        List of source file paths as strings
    """
    sources = []
    # Add interface files first
    sources.extend([str(f) for f in intf_files])
    # Add package file
    sources.append(str(package_path))
    # Add module file
    sources.append(str(module_path))
    return sources


def prepare_cpuif_case(
    rdl_source: str,
    top_name: str,
    output_dir: Path,
    cpuif_cls: type[BaseCpuif],
    *,
    control_signal: str,
    max_samples_per_master: int = 3,
    exporter_kwargs: dict[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    """
    Compile SystemRDL, export the CPUIF, and build a configuration payload for cocotb tests.

    Parameters
    ----------
    rdl_source:
        Path to the SystemRDL source file.
    top_name:
        Name of the top-level addrmap to elaborate.
    output_dir:
        Directory where generated HDL will be written.
    cpuif_cls:
        CPUIF implementation class to use during export.
    control_signal:
        Name of the control signal used to identify master ports
        (``"PSEL"`` for APB, ``"AWVALID"`` for AXI4-Lite, etc.).
    max_samples_per_master:
        Limit for the number of register addresses sampled per master in the test matrix.
    exporter_kwargs:
        Optional keyword overrides passed through to :class:`BusDecoderExporter`.

    Returns
    -------
    tuple
        ``(module_path, package_path, config_dict)``, where the configuration dictionary
        is JSON-serializable and describes masters, indices, and sampled transactions.
    """
    compiler = RDLCompiler()
    compiler.compile_file(rdl_source)
    root = compiler.elaborate(top_name)
    top_node = root.top

    export_kwargs: dict[str, Any] = {"cpuif_cls": cpuif_cls}
    if exporter_kwargs:
        export_kwargs.update(exporter_kwargs)

    exporter = BusDecoderExporter()
    exporter.export(root, str(output_dir), **export_kwargs)

    module_name = export_kwargs.get("module_name", top_name)
    package_name = export_kwargs.get("package_name", f"{top_name}_pkg")

    module_path = Path(output_dir) / f"{module_name}.sv"
    package_path = Path(output_dir) / f"{package_name}.sv"

    config = _build_case_config(
        top_node,
        exporter.cpuif,
        control_signal,
        max_samples_per_master=max_samples_per_master,
    )

    config["address_width"] = exporter.cpuif.addr_width
    config["data_width"] = exporter.cpuif.data_width
    config["byte_width"] = exporter.cpuif.data_width // 8
    config["cpuif_style"] = "interface" if exporter.cpuif.is_interface else "flat"

    return module_path, package_path, config


def _derive_port_prefix(
    cpuif: BaseCpuif, control_signal: str, node: AddressableNode
) -> str:
    """Derive the port prefix (handle name) for a master node.

    For flat CPUIF, the signal looks like ``m_apb_tiles_PSEL[N_TILESS]`` and
    the prefix is ``m_apb_tiles``.  For interface CPUIF, a dummy indexer is
    used to obtain ``m_apb_tiles[i0].PSEL`` and the prefix is extracted as
    the part before any ``[`` or ``.`` separator.
    """
    if cpuif.is_interface:
        signal_ref = cpuif.signal(control_signal, node, "i")
        # e.g. "m_apb_tiles.PSEL" or "m_apb_tiles[i0].PSEL"
        handle_part = signal_ref.rsplit(".", 1)[0]
        return handle_part.split("[", 1)[0]

    signal = cpuif.signal(control_signal, node)
    base = signal.split("[", 1)[0]
    suffix = f"_{control_signal}"
    if not base.endswith(suffix):
        raise ValueError(f"Unable to derive port prefix from '{signal}'")
    return base[: -len(suffix)]


def _build_case_config(
    top_node: AddrmapNode,
    cpuif: BaseCpuif,
    control_signal: str,
    *,
    max_samples_per_master: int,
) -> dict[str, Any]:
    master_entries: dict[str, dict[str, Any]] = {}

    for child in cpuif.addressable_children:
        port_prefix = _derive_port_prefix(cpuif, control_signal, child)

        master_entries[child.inst_name] = {
            "inst_name": child.inst_name,
            "port_prefix": port_prefix,
            "is_array": bool(child.is_array),
            "dimensions": list(child.array_dimensions or []),
            "indices": set(),
            "inst_size": child.array_stride if child.is_array else child.size,
            "child_size": child.size,
            "inst_address": child.raw_absolute_address,
        }

    # Map each register to its top-level master and collect addresses
    groups: dict[tuple[str, tuple[int, ...]], list[tuple[int, str]]] = defaultdict(list)

    def visit(node: AddressableNode) -> None:
        if isinstance(node, RegNode):
            master = node  # type: AddressableNode
            while master.parent is not top_node:
                parent = master.parent
                if not isinstance(parent, AddressableNode):
                    raise RuntimeError("Encountered unexpected hierarchy while resolving master node")
                master = parent

            inst_name = master.inst_name
            if inst_name not in master_entries:
                # Handles cases where the register itself is the master (direct child of top)
                port_prefix = _derive_port_prefix(cpuif, control_signal, master)
                master_entries[inst_name] = {
                    "inst_name": inst_name,
                    "port_prefix": port_prefix,
                    "is_array": bool(master.is_array),
                    "dimensions": list(master.array_dimensions or []),
                    "indices": set(),
                    "inst_size": master.array_stride if master.is_array else master.size,
                    "child_size": master.size,
                    "inst_address": master.raw_absolute_address,
                }

            idx_tuple = tuple(master.current_idx or [])
            master_entries[inst_name]["indices"].add(idx_tuple)

            relative_addr = int(node.absolute_address) - int(top_node.absolute_address)
            full_path = node.get_path()
            label = full_path.split(".", 1)[1] if "." in full_path else full_path
            groups[(inst_name, idx_tuple)].append((relative_addr, label))

        for child in node.children(unroll=True):
            if isinstance(child, AddressableNode):
                visit(child)

    visit(top_node)

    masters_list = []
    for entry in master_entries.values():
        indices = entry["indices"] or {()}
        entry["indices"] = [list(idx) for idx in sorted(indices)]
        masters_list.append(
            {
                "inst_name": entry["inst_name"],
                "port_prefix": entry["port_prefix"],
                "is_array": entry["is_array"],
                "dimensions": entry["dimensions"],
                "indices": entry["indices"],
                "inst_size": entry["inst_size"],
                "child_size": entry["child_size"],
                "inst_address": entry["inst_address"],
            }
        )

    transactions = []
    for (inst_name, idx_tuple), items in groups.items():
        addresses = sorted({addr for addr, _ in items})
        samples = _sample_addresses(addresses, max_samples_per_master)
        for addr in samples:
            label = next(lbl for candidate, lbl in items if candidate == addr)
            transactions.append(
                {
                    "address": addr,
                    "master": inst_name,
                    "index": list(idx_tuple),
                    "label": label,
                }
            )

    transactions.sort(key=lambda item: (item["master"], item["index"], item["address"]))

    masters_list.sort(key=lambda item: item["inst_name"])

    return {
        "masters": masters_list,
        "transactions": transactions,
    }


def _sample_addresses(addresses: list[int], max_samples: int) -> list[int]:
    if len(addresses) <= max_samples:
        return addresses

    samples: list[int] = []
    samples.append(addresses[0])
    if len(addresses) > 1:
        samples.append(addresses[-1])

    if len(addresses) > 2:
        mid = addresses[len(addresses) // 2]
        if mid not in samples:
            samples.append(mid)

    idx = 1
    while len(samples) < max_samples:
        pos = (len(addresses) * idx) // max_samples
        candidate = addresses[min(pos, len(addresses) - 1)]
        if candidate not in samples:
            samples.append(candidate)
        idx += 1

    samples.sort()
    return samples
