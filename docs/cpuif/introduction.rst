Introduction
============

The CPU interface logic layer provides an abstraction between the
application-specific bus protocol and the internal bus decoder logic.
When exporting a design, you can select from supported CPU interface protocols.
These are described in more detail in the pages that follow.


Bus Width
^^^^^^^^^
By default, the CPU interface bus width is inferred as the widest
``accesswidth`` among internal registers in the exported addrmap. Registers
inside external blocks do not participate in inference. If no internal register
``accesswidth`` is available, the width defaults to 32 bits and a warning
explains the fallback.

Use ``--data-width N`` (``data_width=N`` in the exporter API) to select the width
explicitly, including for an external-only map. It must be a power of two of at
least 8 bits and no smaller than any inferred internal register ``accesswidth``.
An explicit choice suppresses the fallback warning. All decoder data ports
use this width; it must match the connected interfaces because the decoder
does not perform width conversion. Address offsets and array strides must be
aligned to the selected width in bytes.


Clock and Reset
^^^^^^^^^^^^^^^
For APB and AXI4-Lite, ``--clk-src`` accepts ``off``, ``cpuif``, or ``design``.
Omitting it (or omitting the Python ``clk_src`` keyword or passing ``None``)
selects a default based on the protocol and APB buffering:

.. list-table::
    :header-rows: 1

    * - Configuration
      - Clock/reset when unspecified
    * - APB3/APB4 with ``--apb-buffer none`` (the default)
      - ``off``
    * - APB3/APB4 with ``--apb-buffer in``, ``out``, or ``both``
      - ``design``
    * - AXI4-Lite
      - ``design``
    * - AHB-Lite
      - Always ingress ``HCLK/HRESETn``

``off``
    Only unbuffered APB supports this mode among the built-in adapters. The
    generated decoder has no ``clk``/``rst`` ports, no standalone
    ``PCLK``/``PRESETn`` ports, and no clock/reset forwarding or sequential
    state. This preserves the 0.7.x APB decoder port shape. It does not remove
    the clock/reset needed by the surrounding APB manager and children.

``design``
    The generated module exposes top-level ``clk`` and active-high asynchronous
    ``rst`` input ports. Flat CPU-interface ports omit protocol clock/reset.
    The surrounding design distributes the same clock/reset domain to the
    decoder and downstream slaves. APB remains combinational unless buffering
    is enabled; AXI4-Lite always uses this source for its holding registers and
    ordered-response queues.

``cpuif``
    The upstream interface supplies protocol-defined clock/reset:
    ``PCLK``/``PRESETn`` for APB, ``ACLK``/``ARESETn`` for AXI4-Lite. Separate
    ``clk``/``rst`` ports are omitted. Flat-port variants expose upstream
    clock/reset inputs and pass-through outputs to every master port.
    SystemVerilog-interface clock/reset members are inputs on both modports,
    so connect every interface instance externally to the same domain.
    The protocol reset is active-low and asynchronous.

The bundled SystemVerilog interface definitions retain their clock/reset
members in every mode. With ``off``, the APB decoder does not use or forward
them; with ``design``, decoder state uses the separate ``clk``/``rst`` ports.
Only ``cpuif`` selects an upstream APB/AXI interface member as the decoder's
clock/reset source.

Buffered APB requires ``design``: explicit ``off`` or ``cpuif`` is rejected.
Omit ``--clk-src`` to select ``design`` automatically, select it explicitly, or
use ``--apb-buffer none`` to disable buffering. AXI4-Lite rejects explicit
``off``; omit the option or select ``design`` or ``cpuif``.

AHB-Lite always uses ingress ``HCLK`` and active-low asynchronous ``HRESETn``.
It ignores ``design`` and ``cpuif`` and rejects explicit ``off``; omit the
option or choose either accepted setting. No accepted setting adds generic
``clk``/``rst`` ports. Flat AHB ports include ``s_ahb_HCLK`` and
``s_ahb_HRESETn``. Interface instances receive the same clock/reset externally
on both ingress and children; the router does not distribute clocks or resets
through child output ports. See :doc:`ahblite`.

When a reset port is present, built-in adapters use these fixed ports, not
SystemRDL ``cpuif_reset`` metadata. A declaration whose name, scope, explicitly
declared polarity, or explicit synchronization disagrees with the selected
port produces a warning naming the actual port and polarity. Connect the
generated port accordingly; changing the RDL declaration does not change its
reset logic. Clockless APB (``off``) has no reset port and emits no such warning.


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


Simulation Interface-Width Checks
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The built-in SystemVerilog-interface adapters check their connected interface
widths at the start of simulation:

* APB3/APB4 ingress ``PADDR`` and AXI4-Lite ingress ``AWADDR``/``ARADDR`` must
  be at least the generated ``MIN_ADDR_WIDTH``. Wider address interfaces are
  allowed, including when ``--addr-width`` selects a larger decoder width.
* APB3/APB4 ingress ``PWDATA`` and AXI4-Lite ingress ``WDATA`` must exactly
  match the generated ``DATA_WIDTH``.
* AHB-Lite ingress ``HADDR`` must exactly match the decoder address width;
  each child ``HADDR`` must exactly match that child's generated address width.
  Ingress and child ``HWDATA``/``HRDATA`` must all exactly match ``DATA_WIDTH``.

A mismatch terminates simulation immediately with ``$fatal(1, ...)`` rather than
allowing execution with truncated or extended signals. The diagnostic names the
decoder instance and affected interface signals, reports their actual widths,
and states the required width and whether it is a minimum or an exact match.
Correct-width interfaces produce no diagnostic output.

These checks are excluded when ``SYNTHESIS`` is defined and require simulation
assertions to be enabled (for example, Verilator's ``--assert``). Simulator
width warnings during compilation are separate from these runtime checks;
enabling assertions does not replace structural width checking by synthesis or
lint tools.
