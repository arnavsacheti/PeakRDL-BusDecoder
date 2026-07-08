Introduction
============

The CPU interface logic layer provides an abstraction between the
application-specific bus protocol and the internal bus decoder logic.
When exporting a design, you can select from supported CPU interface protocols.
These are described in more detail in the pages that follow.


Bus Width
^^^^^^^^^
The CPU interface bus width is inferred from the contents of the design.
It is intended to be equal to the widest ``accesswidth`` encountered in the
design. If the exported addrmap contains only external components, the width
cannot be inferred and will default to 32 bits.


Clock and Reset
^^^^^^^^^^^^^^^
Where the bus decoder gets its clock and reset is selected with ``--clk-src``:

``design`` (default)
    The CPU interface carries no clock or reset. The generated module exposes
    top-level ``clk`` and ``rst`` input ports instead, and the design is
    responsible for distributing clock and reset to downstream slaves. The
    decoder's datapath is purely combinational unless a register slice is
    enabled (see ``--apb-buffer``); the ports anchor the decoder's clock
    domain for such features.

``cpuif``
    Clock and reset are bundled with the CPU interface bus. The slave
    interface carries the protocol-defined clock and reset (``PCLK``/``PRESETn``
    for APB, ``ACLK``/``ARESETn`` for AXI4-Lite), and the decoder fans them out
    to every master interface.

The SystemVerilog interface definitions linked from the protocol pages declare
``PCLK``/``PRESETn`` (``ACLK``/``ARESETn``) members. These are only driven and
consumed by the decoder when ``--clk-src cpuif`` is selected.


Addressing
^^^^^^^^^^

The busdecoder exporter will always generate its address decoding logic using local
address offsets. The absolute address offset of your device shall be
handled by your system interconnect, and present addresses to the busdecoder that
only include the local offset.

For example, consider a fictional AXI4-Lite device that:

- Consumes 4 kB of address space (``0x000``-``0xFFF``).
- The device is instantiated in your system at global address range ``0x30_0000 - 0x50_0FFF``.
- After decoding transactions destined to the device, the system interconnect shall
  ensure that AxADDR values are presented to the device as relative addresses - within
  the range of ``0x000``-``0xFFF``.
- If care is taken to align the global address offset to the size of the device,
  creating a relative address is as simple as pruning down address bits.

By default, the bit-width of the address bus will be the minimum size to span the
contents of the decoded address space. If needed, the address width can be
overridden to a larger range using ``--addr-width``.
