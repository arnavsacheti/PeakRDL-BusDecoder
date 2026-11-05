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
* ``--clk-src``: Select APB/AXI clock/reset (``design`` (default) adds top-level
  ``clk``/``rst`` ports; ``cpuif`` uses the CPU-interface clock/reset).
  AHB-Lite always uses ingress ``HCLK/HRESETn`` and does not add generic clock/reset ports.
  These are fixed ports and polarities, not names derived from SystemRDL
  ``cpuif_reset`` declarations: ``rst`` is active-high asynchronous, while
  ``PRESETn``, ``ARESETn``, and ``HRESETn`` are active-low asynchronous.
* ``--gate-signals``: Gate APB broadcast payload signals with each slave's
  select so unselected slaves see all-zero payload inputs (off by default)
* ``--apb-buffer``: Select transaction-aware APB request/response buffering
  (``none`` (default), ``in``, ``out``, ``both``); non-``none`` modes require
  ``--clk-src design``. See :doc:`cpuif/apb` for timing and reset behavior.
* ``--axi4lite-max-outstanding``: Set the separate AXI4-Lite read and write
  order-queue depths (default ``4``; minimum ``1``)
