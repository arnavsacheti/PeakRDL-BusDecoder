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


.. _cpuif_axi4lite_backpressure:

AXI4-Lite Protocol Limitations: Per-Slave Back-Pressure
---------------------------------------------------------
The generated decoder does not implement the full AXI4-Lite handshake on
either side of the bus. It treats every transaction as a single-cycle
ping-pong between the CPU master and the currently addressed child slave.
This is tracked as a known limitation in
`issue #59 <https://github.com/arnavsacheti/PeakRDL-BusDecoder/issues/59>`_.

CPU-side acceptance is unconditional
    ``AWREADY``/``WREADY`` are asserted combinationally whenever
    ``AWVALID && WVALID`` is high, and ``ARREADY`` is asserted combinationally
    whenever ``ARVALID`` is high (from ``axi4_lite_tmpl.sv``):

    .. code-block:: systemverilog

        assign AWREADY = axi_wr_valid;   // axi_wr_valid = AWVALID & WVALID
        assign WREADY  = axi_wr_valid;
        assign ARREADY = ARVALID;

    The decoder always accepts an address/data beat on the cycle it is
    presented and never deasserts ``*READY`` to stall the CPU master.

Downstream slave ``*READY`` signals are not consumed
    Each child (master-port) interface declares ``AWREADY``, ``WREADY``, and
    ``ARREADY`` as inputs coming back from the slave, but the fanin logic
    (``AXI4LiteCpuifFlat.fanin_wr`` / ``fanin_rd`` in ``axi4_lite_cpuif.py``)
    only reads back ``BVALID``/``BRESP`` and ``RVALID``/``RRESP``/``RDATA``.
    A slave's ``AWREADY``/``WREADY``/``ARREADY`` outputs are wired up on the
    port but never referenced anywhere in the generated logic, so a slave has
    no way to tell the decoder "not yet" on the address or data channels --
    slaves cannot back-pressure address/data acceptance.

``BVALID``/``RVALID`` do not honor the CPU's ``BREADY``/``RREADY`` delay
    The write and read response channels are driven combinationally straight
    through from the selected slave's response, regardless of when the CPU
    asserts ``BREADY``/``RREADY`` (from ``axi4_lite_tmpl.sv``):

    .. code-block:: systemverilog

        assign cpuif_wr_ack_int = cpuif_wr_ack | cpuif_wr_sel.cpuif_err | axi_wr_invalid;
        assign BVALID = cpuif_wr_ack_int;
        ...
        assign cpuif_rd_ack_int = cpuif_rd_ack | cpuif_rd_sel.cpuif_err;
        assign RVALID = cpuif_rd_ack_int;

    where ``cpuif_wr_ack``/``cpuif_rd_ack`` are themselves combinational
    passthroughs of the selected child's ``BVALID``/``RVALID``. No state is
    held to keep ``BVALID``/``RVALID`` asserted until the CPU raises
    ``BREADY``/``RREADY``; the decoder simply forwards whatever the addressed
    slave is driving that cycle.

Consequences
    * Slaves must accept ``AW``/``W``/``AR`` in the very cycle the decoder
      presents them, and must respond consistently with the single-outstanding
      assumption described in :ref:`cpuif_protocol`.
    * Multi-cycle slaves, CPU masters that delay asserting
      ``BREADY``/``RREADY``, and multiple outstanding transactions are **not
      supported** by this adapter.
    * This adapter is intended for simple, single-cycle-acceptance slaves --
      typically the register blocks this tool is meant to feed -- not for
      general-purpose AXI4-Lite subordinates or interconnect fabrics.

    Full handshake support (respecting downstream ``*READY`` and CPU-side
    ``BREADY``/``RREADY``) is tracked in
    `issue #59 <https://github.com/arnavsacheti/PeakRDL-BusDecoder/issues/59>`_.
