Migrating from 0.7.x
====================

This guide covers migration to **0.8.0**. The AXI4-Lite and decode-depth
behavioral comparisons below use 0.7.4 as the baseline. Changes already present
in 0.7.3 are not repeated here.


Python requirement
------------------
Use **Python 3.11 or newer** for 0.8.0, including environments that
install the CLI or invoke the exporter API. The 0.7.4 package allowed Python
3.10; upgrade those environments before installing 0.8.0.


Project-wide defaults in peakrdl.toml
----------------------------------------
Version 0.8.0 supports project-wide generator settings in ``peakrdl.toml``
under ``[busdecoder]``: ``cpuif``, ``data_width``, ``clk_src``, ``apb_buffer``,
``gate_signals``, ``max_decode_depth``, ``unroll``,
``axi4lite_max_outstanding``, and ``parametrize``. Existing
``[busdecoder.cpuifs]`` custom-interface imports remain supported, and their
aliases can also be selected by the new ``cpuif`` setting.

Explicit command-line options override TOML values, which override built-in
defaults. Use ``--no-gate-signals``, ``--no-unroll``, or ``--no-parametrize``
to disable an option enabled by the project; the existing positive forms
remain available. Clock/buffer conflicts are checked on the effective settings
after those overrides.

Existing command behavior is unchanged when no configuration supplies these
settings. Per-design ``module_name``, ``package_name``, and ``addr_width`` are
not project keys; module/package names and address-width overrides remain CLI
options. PeakRDL does not read these settings from ``pyproject.toml``. See
:doc:`configuring` for discovery, the complete key reference, and validation
diagnostics.


Data width and export diagnostics
---------------------------------
Use TOML ``data_width`` or CLI ``--data-width`` to select a common data width
in bits for all decoder interfaces. ``--data-width`` overrides the project
value. The value must be an integer power of two of at least 8, and no smaller
than the widest internal register ``accesswidth``. Boolean values are not
integers for TOML validation. The decoder does not convert interface widths.

When neither CLI nor TOML supplies a width, it is inferred from internal
registers; registers beneath external blocks do not contribute. If no internal
register ``accesswidth`` is available, the decoder falls back to 32 bits and
warns. An explicit CLI or TOML width suppresses that warning, so external-only
maps can state their intended bus width directly.

Invalid TOML types or domains stop with a nonzero exit status and a diagnostic
naming the file and ``busdecoder.data_width``, without a traceback even with
``--debug`` or a valid CLI override. A valid project width can still be too
narrow for a particular design: ``data_width = 32`` fails for an internal
64-bit register ``accesswidth``, with the file and key in the diagnostic.
``--data-width 64`` repairs that selection before the design-dependent check.

Expected export errors now produce concise diagnostics and a nonzero exit
status by default; use ``--debug`` for the full Python traceback on export
failures. This does not enable tracebacks for TOML type/domain validation
errors. Undersized ``--addr-width`` values are rejected rather than silently
truncating addresses. The ``-o`` output path must name a writable directory,
not an existing file.


APB defaults preserve the clockless decoder ports
-------------------------------------------------
For APB3/APB4, the default ``--apb-buffer none`` keeps the combinational routing
path. Omitting ``--clk-src`` now resolves to ``off``, preserving the 0.7.x
decoder module port shape: **no** ``clk``/``rst`` inputs, **no** standalone
``PCLK``/``PRESETn`` inputs or outputs, and no clock/reset forwarding. Existing
unbuffered APB users do not need to add clock/reset connections to the decoder.
Explicit ``--clk-src off`` selects the same shape.

The explicit choices are ``off``, ``cpuif``, and ``design``. When neither the
command line nor TOML selects ``clk_src``, or when the Python ``clk_src``
keyword is omitted or ``None``, these defaults apply:

.. list-table:: Clock/reset defaults
    :header-rows: 1

    * - Configuration
      - When the clock source is unspecified
    * - APB3/APB4, ``apb_buffer="none"`` (default)
      - ``off``; clockless decoder ports
    * - APB3/APB4, ``apb_buffer="in"``, ``"out"``, or ``"both"``
      - ``design``; adds ``clk``/``rst`` inputs
    * - AXI4-Lite
      - ``design``; adds ``clk``/``rst`` inputs
    * - AHB-Lite
      - Always ingress ``HCLK/HRESETn``; no generic ``clk``/``rst`` ports

Opting into ``--clk-src design`` adds top-level input ``clk`` and active-high
asynchronous ``rst``. Flat APB/AXI ports omit protocol clock/reset; distribute
the common clock/reset externally to decoder and children. Unbuffered APB
remains combinational even when these ports are explicitly requested.

Opting into ``--clk-src cpuif`` omits generic ``clk``/``rst``. Flat APB ports add
``s_apb_PCLK``/``s_apb_PRESETn`` inputs and pass-through clock/reset outputs for
every child; AXI4-Lite uses ``ACLK``/``ARESETn`` in the equivalent way.
SystemVerilog interfaces retain clock/reset members in all modes, with those
members declared as inputs on both modports. Connect interface instances
externally to the same domain. In ``off`` mode the APB decoder neither uses nor
forwards those members; the surrounding APB manager and children still need a
clock/reset.

Invalid explicit selections are rejected, rather than silently changed:

* Buffered APB requires ``design``. With ``--apb-buffer in``, ``out``, or
  ``both``, explicit ``off`` **or** ``cpuif`` is rejected. Omit ``--clk-src`` to
  select ``design`` automatically, select ``--clk-src design``, or disable
  buffering with ``--apb-buffer none``.
* AXI4-Lite rejects explicit ``off``. Omit ``--clk-src`` or select ``design`` or
  ``cpuif`` and wire that clock/reset source; there is no clockless mode for
  its stateful queues.
* AHB-Lite rejects explicit ``off``. Omit the option or select ``design`` or
  ``cpuif``. Both accepted values are ignored by AHB-Lite: it always uses
  ingress ``HCLK`` and active-low asynchronous ``HRESETn``. Flat ingress exposes
  ``s_ahb_HCLK``/``s_ahb_HRESETn``; connect all children externally to that domain.
  Neither accepted value adds generic clock/reset ports or child clock outputs.

The same restrictions apply to explicit Python ``clk_src`` strings. Python
``None`` means automatic selection, not ``"off"``; it is not a CLI choice.
See :doc:`cpuif/introduction` for the full wiring contract.


APB Python imports move to one module
----------------------------------------
The APB implementation is consolidated under ``peakrdl_busdecoder.cpuif.apb``.
Replace the old imports:

.. code-block:: python

    from peakrdl_busdecoder.cpuif.apb3 import APB3Cpuif, APB3CpuifFlat
    from peakrdl_busdecoder.cpuif.apb4 import APB4Cpuif, APB4CpuifFlat

with:

.. code-block:: python

    from peakrdl_busdecoder.cpuif.apb import (
        APB3Cpuif,
        APB3CpuifFlat,
        APB4Cpuif,
        APB4CpuifFlat,
    )

Direct implementation-module imports move from
``peakrdl_busdecoder.cpuif.apb3.apb3_cpuif`` and
``peakrdl_busdecoder.cpuif.apb4.apb4_cpuif`` to
``peakrdl_busdecoder.cpuif.apb.apb_cpuif``. The old modules are removed; there
are **no compatibility import shims**. The CLI names ``apb3``, ``apb3-flat``,
``apb4``, and ``apb4-flat`` are unchanged.


Deeper decoding retains shallower leaves
----------------------------------------
``--max-decode-depth`` is a maximum descent depth, not a requirement that every
target occur at exactly that depth. Addressable leaves shallower than a positive
depth limit are now retained instead of being dropped. The default depth remains
``1``; ``0`` still means unlimited descent to leaf or opaque boundaries.

For example, consider this hierarchy (child offsets are relative to their
parent):

.. code-block:: text

    top
    +-- top_reg @ 0x0
    +-- blk @ 0x100
        +-- a @ 0x0
        +-- b @ 0x4

With ``--max-decode-depth 2``:

.. list-table:: Shallow-leaf change
    :header-rows: 1

    * - Behavior
      - 0.7.4
      - 0.8.0
    * - Generated master targets
      - ``a``, ``b``
      - ``top_reg``, ``a``, ``b``
    * - Request at top-relative address ``0x0``
      - No target; local decode miss
      - Routed to ``top_reg``

Regenerate the decoder and update instantiations for any newly retained master
ports when using depths greater than one. Requests at ``0x100`` and ``0x104``
continue to address ``a`` and ``b``. See :doc:`generated_structure` for depth
and port diagrams.


New opt-in APB controls
------------------------
``--apb-buffer none|in|out|both`` selects transaction-aware buffering. ``none``
is the default and leaves the existing combinational path unchanged. ``in``
retains the upstream SETUP request, ``out`` retains the completed child response,
and ``both`` combines them. Buffered modes own one transaction at a time and
retire the child exactly once, even while a registered response awaits upstream
acceptance. They select ``design`` automatically when the clock source is
unspecified.

For a child with no wait states, current implementation timing is:

.. list-table:: APB buffering timing
    :header-rows: 1

    * - Mode
      - Upstream ACCESS cycles through completion
      - Minimum cycles between upstream completions
    * - ``none``
      - 1
      - 2
    * - ``in``
      - 2
      - 3
    * - ``out``
      - 2
      - 3
    * - ``both``
      - 3
      - 4

Completion spacing includes the mandatory SETUP cycle between transfers. Each
child wait adds one cycle to both measures. Buffered reset aborts pending work
without undoing a completed child side effect; the upstream manager must restart
with a fresh SETUP after reset. A stale ACCESS is not replayed.

``--gate-signals`` is also opt-in (default off). It masks ``PADDR``, ``PWDATA``,
``PSTRB``, and ``PPROT`` to zero on unselected APB children. It adds no transaction
state and works with unbuffered ``off`` mode. ``PENABLE`` remains select-gated
with or without this option; ``PWRITE`` is not changed by it. See
:doc:`cpuif/apb` for timing, reset, and gating details.


AXI4-Lite changes from 0.7.4
----------------------------
The previous simplified combinational AXI adapter is replaced by a stateful
AXI4-Lite adapter:

* ``AW`` and ``W`` are accepted independently, whether address-first,
  data-first, or simultaneous. Each channel has one holding register; a complete
  pair enters the write queue.
* Separate bounded read and write queues retain accepted request payloads and
  destinations. Responses are ordered FIFO **within each direction**, with
  backpressure and intentional head-of-line blocking. Reads and writes have no
  relative ordering requirement.
* ``--axi4lite-max-outstanding`` (Python ``axi4lite_max_outstanding``) sets each
  queue's capacity, default ``4`` and minimum ``1``. The write capacity counts
  paired requests, not individual ``AW`` or ``W`` beats; their one-entry holding
  registers are additional state.
* Local decode errors now return ``DECERR`` (``2'b11``), rather than the previous
  ``SLVERR`` (``2'b10``), in normal response-queue order. Child ``BRESP`` and
  ``RRESP`` codes are preserved in full rather than retaining only bit 1.
* For a wider upstream SystemVerilog interface, nonzero address bits **above the
  configured decoder address width** return ``DECERR`` instead of aliasing a
  mapped low address. Flat upstream ports already have the configured width.
* Clock/reset wiring is now operationally required. The default ``design`` adds
  ``clk``/``rst`` inputs; explicit ``cpuif`` uses ``ACLK``/``ARESETn`` instead.
  ``off`` is rejected. All connected children must share the clock/reset domain
  so abandoned pre-reset responses cannot reappear as new transactions.

This remains AXI4-Lite, not full AXI4 with IDs, bursts, exclusives, or cross-ID
reordering. See :doc:`cpuif/axi4lite` and
:doc:`cpuif/axi4lite_response_ordering` for the current protocol contract.


New single-manager AHB-Lite adapter
-----------------------------------
``--cpuif ahb-lite`` and ``--cpuif ahb-lite-flat`` add single-manager AHB-Lite
routing with one shared read/write address/data pipeline, a retained data-phase
destination, and two-cycle local ERROR responses. Decoded apertures must be at
least 1 KiB and start/end on 1 KiB boundaries; array strides must also satisfy
the alignment requirement. Clock/reset always comes from ingress
``HCLK/HRESETn``, regardless of the accepted ``design``/``cpuif`` selection.
This is not multi-manager AHB, full AHB, or AHB5 extension support. See
:doc:`cpuif/ahblite` for integration and supported-layout requirements.
