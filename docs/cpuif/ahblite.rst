.. _cpuif_ahblite:

AMBA AHB-Lite
=============

The AHB-Lite adapter implements a single-manager router with one subordinate
interface and a manager-side interface for each decoded target. It follows the
classic AHB-Lite profile in the
`Arm AMBA AHB Protocol Specification, IHI 0033C <https://documentation-service.arm.com/static/6141bf0d674a052ae36ca811>`_.
It does not implement multi-manager arbitration, SPLIT/RETRY, AHB5 exclusives,
security extensions, data-width conversion, or burst-address generation.

This adapter is part of the 0.8.0 candidate, pending integration verification;
the candidate has not shipped.

SystemVerilog interface
    * Command line: ``--cpuif ahb-lite``
    * Interface definition: :download:`ahblite_intf.sv <../../hdl-src/ahblite_intf.sv>`
    * Class: :class:`peakrdl_busdecoder.cpuif.ahblite.AHBLiteCpuif`

Flattened inputs/outputs
    * Command line: ``--cpuif ahb-lite-flat``
    * Class: :class:`peakrdl_busdecoder.cpuif.ahblite.AHBLiteCpuifFlat`

For example::

    peakrdl busdecoder design.rdl -o busdecoder/ --cpuif ahb-lite-flat

Both forms support rolled arrays and ``--unroll``, including targets nested
inside arrayed blocks.


Signals, clock, and reset
-------------------------

The subordinate interface is named ``s_ahb`` in the interface form; flat signals
have the prefix ``s_ahb_``. Ingress address/control signals are ``HSEL``,
``HREADY``, ``HADDR``, ``HTRANS[1:0]``, ``HWRITE``, ``HSIZE[2:0]``,
``HBURST[2:0]``, ``HPROT[3:0]``, and ``HMASTLOCK``. ``HWDATA`` carries write
data. The router returns ``HRDATA``, ``HREADYOUT``, and **one-bit** ``HRESP``
(0 = OKAY, 1 = ERROR). Each child receives the same address/control and data
signal set and supplies its own response signals.

Unlike the default unbuffered APB adapter, this adapter has sequential state:

* Flat ports include ``s_ahb_HCLK`` and active-low ``s_ahb_HRESETn``.
* ``ahblite_intf`` takes ``HCLK`` and ``HRESETn`` as interface-constructor
  inputs. Connect the same clock and reset externally to the subordinate and
  every child interface instance. These signals are inputs in both modports;
  the router does not distribute clocks or resets through child output ports.
* All endpoints must operate in that one clock domain. There is no clock-domain
  crossing logic.
* ``HRESETn`` asynchronously clears the pending data-phase destination and
  local-error state. During reset, all child ``HSEL`` outputs are low and the
  subordinate returns ``HREADYOUT=1``, ``HRESP=0``, and zero read data. The
  canonical ``HRESETn`` input is used regardless of RDL ``cpuif_reset`` metadata.
* ``--clk-src design`` and ``--clk-src cpuif`` are accepted but ignored:
  neither changes the AHB clock/reset ports or adds generic ``clk``/``rst``
  ports. Explicit ``--clk-src off`` is rejected because data-phase state
  requires ingress ``HCLK/HRESETn``. Omit the option or select either accepted
  setting; the ingress clock/reset wiring is always required.

.. important::

    ``HREADY`` is the **global bus-ready feedback**, not a synonym for
    ``HREADYOUT``. Connect the router's ``HREADY`` input to the system's selected
    data-phase ready signal. In a system where this router is the only
    subordinate, that feedback is its own ``HREADYOUT``. The router broadcasts
    this global ``HREADY`` to every child; do not connect a child to its own
    ``HREADYOUT`` instead.

Instantiate the interface form with the generated package widths. For example,
for a scalar child named ``peripheral`` in a module named ``router``:

.. code-block:: systemverilog

    import router_pkg::*;
    ahblite_intf #(
        .ADDR_WIDTH(ROUTER_MIN_ADDR_WIDTH),
        .DATA_WIDTH(ROUTER_DATA_WIDTH)
    ) upstream (.HCLK(clk), .HRESETn(reset_n));
    ahblite_intf #(
        .ADDR_WIDTH(ROUTER_PERIPHERAL_ADDR_WIDTH),
        .DATA_WIDTH(ROUTER_DATA_WIDTH)
    ) peripheral (.HCLK(clk), .HRESETn(reset_n));
    router decoder (.s_ahb(upstream), .m_ahb_peripheral(peripheral));

The generated interface adapter includes initial assertions checking each
endpoint's address and data widths. Enable assertions in the simulator to
exercise them. Flat ports encode these widths in their declarations.


Address apertures and widths
----------------------------

AHB-Lite subordinate regions must start and end on 1 KiB boundaries. The exporter
rejects a decoded target unless:

* Its local base is a multiple of 1024 bytes.
* Its element size is at least 1024 bytes and a multiple of 1024 bytes.
* Every array stride, including ancestor-array strides, is a multiple of
  1024 bytes.
* The configured ingress address width represents the complete aperture.

Sizes need not be powers of two. Every child receives a byte address relative
to its own element base, including non-power-of-two apertures and unrolled
arrays. A standalone sub-addrmap export uses addresses local to that exported
root, not its original parent placement. Array-stride holes are unmapped; the
router does not silently widen apertures to cover them.

Small register maps must be contained in explicitly sized, 1 KiB-or-larger
downstream blocks. Selecting individual small registers with
``--max-decode-depth`` is rejected instead of rounding their ranges. An external
memory with 256 32-bit entries, for example, has a 1024-byte aperture; use an
accurate downstream model rather than changing the actual register addresses.
Invalid aperture and data-width layouts produce source diagnostics before RTL
is written. The normal opaque-block boundary rules still apply: a block whose
addressable children are all external remains a downstream target even when a
deeper decode depth is requested.

The data width is common to all endpoints and is inferred using the usual
:doc:`bus-width rules <introduction>`. Supported widths are 32, 64, 128, 256,
512, and 1024 bits. Narrower or wider buses are rejected; 1024 bits is the
largest transfer represented by the three-bit ``HSIZE`` field. The router does
not adapt a downstream bus of a different width.


Address and data phases
-----------------------

An address is accepted on a rising ``HCLK`` edge only when ``HRESETn``,
``HREADY``, ``HSEL``, and ``HTRANS[1]`` are high. Thus NONSEQ and SEQ transfers
are active; IDLE and BUSY are bubbles. Each active burst beat is decoded
independently. The manager is responsible for burst-address progression and
legal burst boundaries.

Child ``HSEL`` is an address-phase decode and is not gated by ``HREADY``.
The router retains the accepted destination for the following data phase, so
changes in the next address cannot retarget an older response. While
``HREADY=0``, the destination and direction are held. A completed data phase
and a new address may share an edge: zero-wait children can sustain one beat
per cycle without a mandatory bubble.

``HADDR``, ``HTRANS``, ``HWRITE``, ``HSIZE``, ``HBURST``, ``HPROT``, and
``HMASTLOCK`` are forwarded in the address phase. ``HWDATA`` is forwarded
**live**, not captured with the address: its value belongs to the preceding
accepted write and must be held by the manager during that write's wait states.
There is no write-strobe signal or byte-lane conversion.

The retained child alone supplies ``HRDATA``, ``HREADYOUT``, and ``HRESP``.
Its wait states and legal two-cycle ERROR response pass through unchanged.
With no pending data phase the router returns ready/OKAY and zero read data.
An IDLE, BUSY, or unselected address clears the pending marker only on an
``HREADY=1`` edge; it never discards a stalled data phase.

An accepted address that selects no permitted target produces a local two-cycle
ERROR response:

#. First data-response cycle: ``HREADYOUT=0``, ``HRESP=1``.
#. Second data-response cycle: ``HREADYOUT=1``, ``HRESP=1``.

Local-error read data is zero and the denied address asserts no child ``HSEL``.
The error phase advances across the first forced wait cycle even though global
``HREADY`` is low. The following address can be cancelled according to AHB-Lite
error timing, and the next active address is accepted only when ``HREADY`` is
high. Unmapped IDLE/BUSY phases do not create errors.

Where a decode target is a register, reads require a present software-readable
field and writes require a present software-writable field. Opaque block targets
route both directions; their downstream implementation enforces field
permissions and side effects. ``HPROT`` is forwarded, not interpreted as an
authorization policy.

The router assumes legal manager/child timing, supported and aligned transfer
sizes, stable active address/control and write data during stalls, and legal
child ERROR sequencing. It is not a protocol firewall and does not validate
malformed traffic. A child that never becomes ready can stall its pending
transaction indefinitely.


Target names and arrays
-----------------------

AHB uses the same target-name allocator as APB and AXI4-Lite. A unique local
target name is retained, so ``outer.inner`` normally uses ``m_ahb_inner``,
``m_ahb_inner_HSEL``, and ``ROUTER_INNER_ADDR_WIDTH``. Repeated or case-folded
names are disambiguated with flattened relative paths and deterministic suffixes;
reserved package names are also disambiguated. See :doc:`../architecture`.

Rolled ports collect all ancestor and target dimensions in outer-to-inner order.
For example, a uniquely named target ``outer[2].inner[3]`` produces flat signals
such as ``m_ahb_inner_HSEL[2][3]`` and interface port ``m_ahb_inner[2][3]``.
With ``--unroll``, element ``[0][1]`` uses ``m_ahb_inner_HSEL_0_1`` and
``m_ahb_inner_0_1``. Address-width constants are emitted once per target
identity rather than repeated for each unrolled element. A collision between
fully expanded unrolled public-port names is diagnosed.

Physical array dimensions retain their elaborated maximum sizes. When
``--parametrize`` exposes root-level array-enable parameters, disabled elements
remain unselected and accesses to them receive the local two-cycle ERROR;
parameter changes do not resize the public ports.
