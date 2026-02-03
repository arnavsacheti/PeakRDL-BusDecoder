Introduction
============

PeakRDL-BusDecoder is a free and open-source bus decoder generator for hierarchical
SystemRDL address maps. It produces a synthesizable SystemVerilog RTL module that
accepts a single CPU interface (slave side) and fans transactions out to multiple
child address spaces (master side).

This tool **does not** generate register storage or field logic. It is strictly a
bus-routing layer that decodes addresses and forwards requests to child blocks.

This is particularly useful for:

* Creating hierarchical register maps with multiple sub-components
* Splitting a single CPU interface bus to serve multiple independent register blocks
* Organizing large address spaces into logical sub-regions
* Implementing address decode logic for multi-drop bus architectures

The generated bus decoder provides:

* Fully synthesizable SystemVerilog RTL (IEEE 1800-2012)
* A top-level slave CPU interface and per-child master CPU interfaces
* Address decode logic that routes transactions to child address maps
* Support for APB3, APB4, and AXI4-Lite (plus plugin-defined CPU interfaces)
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

* ``--cpuif``: Select the CPU interface (``apb3``, ``apb3-flat``, ``apb4``, ``apb4-flat``, ``axi4-lite``, ``axi4-lite-flat``)
* ``--module-name``: Override the generated module name
* ``--package-name``: Override the generated package name
* ``--addr-width``: Override the slave address width
* ``--unroll``: Unroll arrayed children into discrete interfaces
* ``--max-decode-depth``: Control how far the decoder descends into hierarchy


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
    configuring
    limitations
    licensing
    api

.. toctree::
    :hidden:
    :caption: CPU Interfaces

    cpuif/introduction
    cpuif/apb
    cpuif/axi4lite
    cpuif/internal_protocol
    cpuif/customizing
