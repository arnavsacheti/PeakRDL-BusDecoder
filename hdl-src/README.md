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
Connect AHB-Lite ingress and children externally to the same `HCLK`/`HRESETn`
domain; its adapter always uses the ingress clock/reset, independent of
`--clk-src`. APB and AXI4-Lite select design `clk`/`rst` or ingress protocol
clock/reset with that option. Their flat `cpuif`-clocked variants provide child
clock/reset outputs; SystemVerilog interface clock/reset members are inputs and
must be connected externally.

These reference files are free to use for any purpose and are not covered by
this project's LGPLv3 license.

If for whatever reason you feel the need to reference a license when using
these, then lets go with the [MIT License](https://choosealicense.com/licenses/mit/)
