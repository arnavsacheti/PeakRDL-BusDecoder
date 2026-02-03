.. _cpuif_axi4lite:

AMBA AXI4-Lite
==============

Implements the bus decoder using an
`AMBA AXI4-Lite <https://developer.arm.com/documentation/ihi0022/e/AMBA-AXI4-Lite-Interface-Specification>`_
CPU interface.

The AXI4-Lite CPU interface comes in two i/o port flavors:

SystemVerilog Interface
    * Command line: ``--cpuif axi4-lite``
    * Interface Definition: :download:`axi4lite_intf.sv <../../hdl-src/axi4lite_intf.sv>`
    * Class: :class:`peakrdl_busdecoder.cpuif.axi4lite.AXI4LiteCpuif`

Flattened inputs/outputs
    Flattens the interface into discrete input and output ports.

    * Command line: ``--cpuif axi4-lite-flat``
    * Class: :class:`peakrdl_busdecoder.cpuif.axi4lite.AXI4LiteCpuifFlat`


Protocol Notes
--------------
The AXI4-Lite adapter is intentionally simplified:

* AW and W channels must be asserted together for writes. The adapter does not
  support decoupled address/data for writes.
* Only a single outstanding transaction is supported. Masters should wait for
  the corresponding response before issuing the next request.
* Burst transfers are not supported (single-beat transfers only), consistent
  with AXI4-Lite.
