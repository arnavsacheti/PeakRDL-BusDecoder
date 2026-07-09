AMBA APB
========

Both APB3 and APB4 standards are supported.

.. warning::
    Some IP vendors will incorrectly implement the address signalling
    assuming word-addresses. (that each increment of ``PADDR`` is the next word)

    For this exporter, values on the interface's ``PADDR`` input are interpreted
    as byte-addresses. (an APB interface with 32-bit wide data increments
    ``PADDR`` in steps of 4 for every word). Even though APB protocol does not
    allow for unaligned transfers, this is in accordance to the official AMBA
    specification.

    Be sure to double-check the interpretation of your interconnect IP. A simple
    bit-shift operation can be used to correct this if necessary.


APB3
----

Implements the bus decoder using an
`AMBA 3 APB <https://developer.arm.com/documentation/ihi0024/b/Introduction/About-the-AMBA-3-APB>`_
CPU interface.

The APB3 CPU interface comes in two i/o port flavors:

SystemVerilog Interface
    * Command line: ``--cpuif apb3``
    * Interface Definition: :download:`apb3_intf.sv <../../hdl-src/apb3_intf.sv>`
    * Class: :class:`peakrdl_busdecoder.cpuif.apb3.APB3Cpuif`

Flattened inputs/outputs
    Flattens the interface into discrete input and output ports.

    * Command line: ``--cpuif apb3-flat``
    * Class: :class:`peakrdl_busdecoder.cpuif.apb3.APB3CpuifFlat`


APB4
----

Implements the bus decoder using an
`AMBA 4 APB <https://developer.arm.com/documentation/ihi0024/d/?lang=en>`_
CPU interface.

The APB4 CPU interface comes in two i/o port flavors:

SystemVerilog Interface
    * Command line: ``--cpuif apb4``
    * Interface Definition: :download:`apb4_intf.sv <../../hdl-src/apb4_intf.sv>`
    * Class: :class:`peakrdl_busdecoder.cpuif.apb4.APB4Cpuif`

Flattened inputs/outputs
    Flattens the interface into discrete input and output ports.

    * Command line: ``--cpuif apb4-flat``
    * Class: :class:`peakrdl_busdecoder.cpuif.apb4.APB4CpuifFlat`


Broadcast Signal Gating
-----------------------

By default, the broadcast signals ``PENABLE``, ``PADDR``, ``PWDATA``,
``PSTRB``, and ``PPROT`` fan out to every master port unmodified, keeping the
master-to-slave datapath free of extra logic stages. Per the AMBA APB
specification, conformant slaves only sample these signals while their
``PSEL`` is asserted, so this is protocol-safe.

Passing ``--gate-signals`` masks each broadcast signal with the slave's select
expression, so unselected slaves see all-zero inputs. This costs one extra mux
stage on the datapath, but reduces switching activity on quiet sub-blocks
(power/EMI), produces cleaner debug waveforms, and defends against
non-conformant slaves that latch inputs without checking ``PSEL``. ``PSEL``
and ``PWRITE`` are always driven per-slave and are unaffected by this option.


Slave-Side Register Slice
-------------------------

``--apb-buffer`` inserts a single-flop register slice on the APB slave-side
I/O:

* ``none`` (default): no buffering
* ``in``: registers the slave-side inputs
  (``PSEL``/``PENABLE``/``PWRITE``/``PADDR``/``PWDATA``/``PSTRB``/``PPROT``)
* ``out``: registers the slave-side outputs (``PRDATA``/``PREADY``/``PSLVERR``)
* ``both``: registers both directions

The APB handshake is preserved through ``PREADY``-stretching: each buffered
direction adds one cycle to the access phase, which the protocol allows. The
buffer flops use the design clock and reset, so this option requires
``--clk-src design``. Non-APB CPU interfaces reject the option.
