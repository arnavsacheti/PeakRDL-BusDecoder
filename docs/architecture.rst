Bus Decoder Architecture
========================

The generated RTL is a pure bus-routing layer. It accepts a single CPU interface
on the slave side and fans transactions out to a set of child interfaces on the
master side. No register storage or field logic is generated.

Although you do not need to know the inner workings to use the exporter, the
sections below explain the structure of the generated module and how it maps to
SystemRDL hierarchy.


CPU Interface Adapter
---------------------
Each supported CPU interface protocol (APB3, APB4, AXI4-Lite) provides a small
adapter that translates the external bus protocol into internal request/response
signals. These internal signals are then used by the address decoder and fanout
logic.

If you write a custom CPU interface, it must implement the internal signals
described in :ref:`cpuif_protocol`.


Address Decode
--------------
The address decoder computes per-child select signals based on address ranges.
The decode boundary is controlled by ``max_decode_depth``:

* ``0``: Decode all the way down to leaf registers
* ``1`` (default): Decode only top-level children
* ``N``: Decode down to depth ``N`` from the top-level

This allows you to choose whether the bus decoder routes to large blocks (e.g.,
child addrmaps) or to smaller sub-blocks.


Fanout to Child Interfaces
--------------------------
For each decoded child, the bus decoder drives a master-side CPU interface.
All address, data, and control signals are forwarded to the selected child.

Arrayed children can be kept as arrays or unrolled into discrete interfaces using
``--unroll``. This only affects port structure and naming; decode semantics are
unchanged.


Fanin and Error Handling
------------------------
Read and write responses are muxed back from the selected child to the slave
interface. If no child is selected for a transaction, the decoder generates an
error response on the slave interface.

The exact error signaling depends on the chosen CPU interface protocol (e.g.,
``PSLVERR`` for APB, ``RRESP/BRESP`` for AXI4-Lite).
