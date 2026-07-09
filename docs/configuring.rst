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

* ``--cpuif``: Select the CPU interface (``apb3``, ``apb3-flat``, ``apb4``,
  ``apb4-flat``, ``axi4-lite``, ``axi4-lite-flat``)
* ``--module-name``: Override the generated module name
* ``--package-name``: Override the generated package name
* ``--addr-width``: Override the slave address width
* ``--unroll``: Unroll arrayed children into discrete interfaces
* ``--max-decode-depth``: Control how far the decoder descends into hierarchy
* ``--parametrize``: Propagate top-level SystemRDL parameters into the
  generated module (see :doc:`parameters`)
* ``--clk-src``: Select where the decoder gets its clock and reset (``off``
  (default) uses no clock/reset at all — the decoder is combinational;
  ``design`` adds top-level ``clk``/``rst`` ports that are consumed internally
  but not fanned out; ``cpuif`` bundles clock/reset with the CPU interface bus
  and fans them out to each master)
* ``--gate-signals``: Gate APB broadcast signals with each slave's select so
  unselected slaves see all-zero inputs (off by default)
* ``--apb-buffer``: Insert a single-flop register slice on the APB slave-side
  I/O (``none`` (default), ``in``, ``out``, ``both``); requires
  ``--clk-src design``
