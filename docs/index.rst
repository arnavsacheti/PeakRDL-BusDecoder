Introduction
============

PeakRDL-BusDecoder is a free and open-source bus decoder generator for hierarchical
SystemRDL address maps. It produces a synthesizable SystemVerilog RTL module that
accepts a single CPU interface (slave side) and fans transactions out to multiple
child address spaces (master side).

This tool **does not** generate register storage or field logic. It is strictly a
bus-routing layer that decodes addresses and forwards requests to child blocks.

.. note::

    This documentation describes the **0.8.0 candidate**, pending integration
    verification and not yet shipped. Python **3.11 or newer** is required.
    The candidate adds ordered AXI4-Lite and single-manager AHB-Lite routing;
    it does not implement full AXI4 or separate custom read/write layouts.

    Upgrading an existing design? See :doc:`migrating` for preserved APB defaults,
    Python import changes, and the new AXI4-Lite clock/reset requirement.

This is particularly useful for:

* Creating hierarchical register maps with multiple sub-components
* Splitting a single CPU interface bus to serve multiple independent register blocks
* Organizing large address spaces into logical sub-regions
* Implementing address decode logic for multi-drop bus architectures

The generated bus decoder provides:

* Fully synthesizable SystemVerilog RTL (IEEE 1800-2012)
* A top-level slave CPU interface and per-child master CPU interfaces
* Address decode logic that routes transactions to child address maps
* Support for APB3, APB4, AXI4-Lite, and AHB-Lite (plus plugin-defined CPU interfaces)
* Configurable decode depth and array unrolling


Quick Start
-----------
The easiest way to use PeakRDL-BusDecoder is via the
`PeakRDL command line tool <https://peakrdl.readthedocs.io/>`_:

.. code-block:: bash

    # Install PeakRDL-BusDecoder along with the command-line tool
    python3 -m pip install peakrdl-busdecoder[cli]

    # Export!
    peakrdl busdecoder atxmega_spi.rdl -o busdecoder/ --cpuif axi4-lite

The exporter writes two files:

* A SystemVerilog module (the bus decoder)
* A SystemVerilog package (constants like data width and per-child address widths)

Key command-line options:

* ``--cpuif``: Select APB3, APB4, AXI4-Lite, or AHB-Lite, in interface or ``-flat`` form
* ``--module-name``: Override the generated module name
* ``--package-name``: Override the generated package name
* ``--addr-width``: Override the slave address width
* ``--data-width``: Override TOML ``data_width`` or inferred data width; a power of two of at least 8 and no smaller than any internal register ``accesswidth``
* ``--debug``: Include a full Python traceback for export failures (TOML type/domain validation remains concise)
* ``--unroll`` / ``--no-unroll``: Enable/disable unrolling arrayed children into discrete interfaces
* ``--max-decode-depth``: Control how far the decoder descends into hierarchy
* ``--parametrize`` / ``--no-parametrize``: Enable/disable propagation of top-level SystemRDL parameters into the generated module
* ``--clk-src``: Select ``off``, ``cpuif``, or ``design``. Unspecified in CLI and TOML: unbuffered APB uses ``off``; buffered APB and AXI4-Lite use ``design``. AHB always uses ingress ``HCLK/HRESETn`` and rejects ``off``.
* ``--gate-signals`` / ``--no-gate-signals``: Enable/disable gating APB broadcast signals with each slave's select (built-in default: disabled)
* ``--apb-buffer``: Select transaction-aware APB request/response buffering (``none`` (built-in default), ``in``, ``out``, ``both``); buffered modes require ``design``, selected automatically if neither CLI nor TOML selects ``clk_src``
* ``--axi4lite-max-outstanding``: Set each AXI4-Lite ordered-response queue depth (default ``4``)

Project-wide defaults can be set under ``[busdecoder]`` in ``peakrdl.toml``.
Explicit CLI options take precedence over TOML, then built-in defaults apply.
See :doc:`configuring` for supported keys, discovery, and validation; per-design
module/package names and address widths remain CLI overrides.


Looking for VHDL?
-----------------
This project generates SystemVerilog RTL. If you prefer using VHDL, check out
the sister project which aims to be a feature-equivalent fork of
PeakRDL-BusDecoder: `PeakRDL-busdecoder-VHDL <https://peakrdl-busdecoder-vhdl.readthedocs.io>`_


Links
-----

- `Source repository <https://github.com/arnavsacheti/PeakRDL-BusDecoder>`_
- `Release Notes <https://github.com/arnavsacheti/PeakRDL-BusDecoder/releases>`_
- `Issue tracker <https://github.com/arnavsacheti/PeakRDL-BusDecoder/issues>`_
- `PyPi <https://pypi.org/project/peakrdl-busdecoder>`_
- `SystemRDL Specification <http://accellera.org/downloads/standards/systemrdl>`_


.. toctree::
    :hidden:

    self
    architecture
    generated_structure
    parameters
    configuring
    migrating
    limitations
    licensing
    api

.. toctree::
    :hidden:
    :caption: CPU Interfaces

    cpuif/introduction
    cpuif/apb
    cpuif/axi4lite
    cpuif/axi4lite_response_ordering
    cpuif/ahblite
    cpuif/internal_protocol
    cpuif/customizing
    cpuif/upcoming
