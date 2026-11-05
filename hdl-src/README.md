# HDL Source Files
This folder contains some SystemVerilog definitions that are useful collateral
to be used alongside this project.

Bundled interface definitions:

- `apb3_intf.sv`: AMBA APB3.
- `apb4_intf.sv`: AMBA APB4.
- `axi4lite_intf.sv`: AMBA AXI4-Lite (not full AXI4 with IDs or bursts).
- `ahblite_intf.sv`: single-manager AMBA AHB-Lite with separate address/data
  phases and one shared read/write pipeline.
- `avalon_mm_intf.sv`: Avalon-MM reference collateral; not a selectable decoder
  adapter.

The generated adapters support SystemVerilog interface and flat-port forms.
`--clk-src` accepts `off`, `cpuif`, and `design`. Omitting the option (or using
Python `clk_src=None`) selects `off` for APB with `--apb-buffer none`, preserving
the 0.7.x clockless decoder module ports: no `clk`/`rst`, no standalone
`PCLK`/`PRESETn`, and no clock/reset forwarding. Buffered APB and AXI4-Lite
default to `design`, which adds explicit `clk`/`rst` inputs. Opting into `cpuif`
uses ingress protocol clock/reset; flat variants expose those inputs and
pass-through clock/reset outputs for every child. The bundled SystemVerilog
interface definitions retain clock/reset members in every mode; those members
are inputs on both modports and must be connected externally. `off` does not
remove the clock/reset required by the surrounding APB manager and children.

APB buffering requires `design`, selected automatically when the clock-source
option is omitted. Explicit `off` or `cpuif` with buffering is rejected: omit
`--clk-src`, select `design`, or disable buffering with `--apb-buffer none`.
AXI4-Lite rejects `off`: omit the option or select `design` or `cpuif` and wire
the selected source.

Connect AHB-Lite ingress and children externally to the same `HCLK`/`HRESETn`
domain. Its adapter always uses ingress clock/reset: `design` and `cpuif` are
accepted but ignored, while explicit `off` is rejected. Omit `--clk-src` or
choose either accepted setting; none adds generic `clk`/`rst` ports or child
clock/reset outputs.

These reference files are free to use for any purpose and are not covered by
this project's LGPLv3 license.

If for whatever reason you feel the need to reference a license when using
these, then lets go with the [MIT License](https://choosealicense.com/licenses/mit/)
