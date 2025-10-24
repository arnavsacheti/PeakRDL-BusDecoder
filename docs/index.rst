Introduction
============

PeakRDL-BusDecoder is a free and open-source bus decoder generator for hierarchical register address maps.
This code generator translates your SystemRDL register description into a synthesizable 
SystemVerilog RTL module that decodes CPU interface transactions and routes them to 
multiple sub-address spaces (child addrmaps). This is particularly useful for:

* Creating hierarchical register maps with multiple sub-components
* Splitting a single CPU interface bus to serve multiple independent register blocks
* Organizing large register designs into logical sub-address spaces
* Implementing address decode logic for multi-drop bus architectures

The generated bus decoder provides:

* Fully synthesizable SystemVerilog RTL (IEEE 1800-2012)
* Support for many popular CPU interface protocols (AMBA APB, AXI4-Lite, and more)
* Address decode logic that routes transactions to child address maps
* Configurable pipelining options for designs with fast clock rates
* Broad support for SystemRDL 2.0 features


Quick Start
-----------
The easiest way to use PeakRDL-BusDecoder is via the  `PeakRDL command line tool <https://peakrdl.readthedocs.io/>`_:

.. code-block:: bash

    # Install PeakRDL-BusDecoder along with the command-line tool
    python3 -m pip install peakrdl-busdecoder[cli]

    # Export!
    peakrdl busdecoder atxmega_spi.rdl -o busdecoder/ --cpuif axi4-lite


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
    hwif
    configuring
    limitations
    faq
    licensing
    api

.. toctree::
    :hidden:
    :caption: CPU Interfaces

    cpuif/introduction
    cpuif/apb
    cpuif/axi4lite
    cpuif/avalon
    cpuif/passthrough
    cpuif/internal_protocol
    cpuif/customizing

.. toctree::
    :hidden:
    :caption: SystemRDL Properties

    props/field
    props/reg
    props/addrmap
    props/signal
    props/rhs_props

.. toctree::
    :hidden:
    :caption: Other SystemRDL Features

    rdl_features/external

.. toctree::
    :hidden:
    :caption: Extended Properties

    udps/intro
