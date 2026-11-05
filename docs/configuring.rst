.. _peakrdl_cfg:

Configuring PeakRDL-BusDecoder
==============================

If using the `PeakRDL command line tool <https://peakrdl.readthedocs.io/>`_,
some aspects of the ``busdecoder`` command can be configured via the PeakRDL
TOML file.

All busdecoder-specific options are defined under the ``[busdecoder]`` heading.

.. data:: cpuifs

    Mapping of additional CPU Interface implementation classes to load.
    The mapping's key indicates the cpuif's name.
    The value is a string that describes the import path and cpuif class to
    load.

    For example:

    .. code-block:: toml

        [busdecoder]
        cpuifs.my-cpuif-name = "my_cpuif_module:MyCPUInterfaceClass"


Command-Line Options
--------------------

The following options are available on the ``peakrdl busdecoder`` command:

See :ref:`generated_decoder_structure` for diagrams showing which options
change ports, routing boundaries, queues, or pipeline state.

* ``--cpuif``: Select the CPU interface (``apb3``, ``apb3-flat``, ``apb4``,
  ``apb4-flat``, ``axi4-lite``, ``axi4-lite-flat``, ``ahb-lite``, ``ahb-lite-flat``)
* ``--module-name``: Override the generated module name
* ``--package-name``: Override the generated package name
* ``--addr-width``: Override the slave address width; values smaller than the
  decoder's required minimum are rejected. Omit the option to infer the width.
* ``--data-width``: Set the data width in bits for all decoder interfaces
  (a power of two, at least 8, and no smaller than any internal register
  ``accesswidth``). Without this option, the width is inferred from internal
  registers, or defaults to 32 bits with a warning when no internal register
  ``accesswidth`` is available. Set it explicitly for external-only maps;
  the decoder does not convert widths between interfaces.
* ``--debug``: Include the full Python traceback when busdecoder export fails.
  By default, expected export errors produce concise diagnostics and a nonzero
  exit status. ``-o`` must name a writable directory, not an existing file.
* ``--unroll``: Unroll arrayed children into discrete interfaces
* ``--max-decode-depth``: Control how far the decoder descends into hierarchy
* ``--parametrize``: Propagate top-level SystemRDL parameters into the
  generated module (see :doc:`parameters`)
* ``--clk-src``: Select ``off``, ``cpuif``, or ``design``. If omitted,
  unbuffered APB (``--apb-buffer none``) uses ``off``; buffered APB and AXI4-Lite
  use ``design``. ``off`` preserves the clockless 0.7.x APB decoder ports,
  ``design`` adds top-level ``clk``/``rst``, and ``cpuif`` uses protocol
  clock/reset. AHB-Lite always uses ingress ``HCLK/HRESETn``; ``design`` and
  ``cpuif`` are ignored for that protocol, while explicit ``off`` is rejected.
  When present, these are fixed ports and polarities, not names derived from
  SystemRDL ``cpuif_reset`` declarations: ``rst`` is active-high asynchronous,
  while ``PRESETn``, ``ARESETn``, and ``HRESETn`` are active-low asynchronous.
* ``--gate-signals``: Gate APB broadcast payload signals with each slave's
  select so unselected slaves see all-zero payload inputs (off by default)
* ``--apb-buffer``: Select transaction-aware APB request/response buffering
  (``none`` (default), ``in``, ``out``, ``both``). Non-``none`` modes require
  ``design``, selected automatically if ``--clk-src`` is omitted. Explicit
  ``off`` or ``cpuif`` with buffering is rejected: omit ``--clk-src``, select
  ``--clk-src design``, or disable buffering with ``--apb-buffer none``.
  See :doc:`cpuif/apb` for timing and reset behavior.
* ``--axi4lite-max-outstanding``: Set the separate AXI4-Lite read and write
  order-queue depths (default ``4``; minimum ``1``)

AXI4-Lite rejects explicit ``--clk-src off`` because its holding registers and
ordered-response queues require a clock/reset. Omit the option or select
``design`` or ``cpuif`` and wire the selected clock/reset. AHB-Lite also rejects
``off``: omit the option or select ``design`` or ``cpuif``; all accepted settings
still use ingress ``HCLK/HRESETn``.

The Python exporter uses the equivalent ``clk_src`` keyword. Omitting it or
passing ``clk_src=None`` selects the same protocol-dependent defaults; the
explicit values are ``"off"``, ``"cpuif"``, and ``"design"``. ``None`` is not a
command-line choice. See :doc:`cpuif/introduction` for the clock/reset wiring
contract and :doc:`migrating` for changes from 0.7.x.
