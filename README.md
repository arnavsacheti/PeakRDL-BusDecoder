[![Build](https://github.com/arnavsacheti/PeakRDL-BusDecoder/actions/workflows/build.yml/badge.svg)](https://github.com/arnavsacheti/PeakRDL-BusDecoder/actions/workflows/build.yml)
[![Test](https://github.com/arnavsacheti/PeakRDL-BusDecoder/actions/workflows/test.yml/badge.svg)](https://github.com/arnavsacheti/PeakRDL-BusDecoder/actions/workflows/test.yml)
[![Documentation](https://github.com/arnavsacheti/PeakRDL-BusDecoder/actions/workflows/docs.yml/badge.svg)](https://github.com/arnavsacheti/PeakRDL-BusDecoder/actions/workflows/docs.yml)
[![Coverage Status](https://coveralls.io/repos/github/arnavsacheti/PeakRDL-BusDecoder/badge.svg?branch=tests/coveralls)](https://coveralls.io/github/arnavsacheti/PeakRDL-BusDecoder?branch=tests/coveralls)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/peakrdl-busdecoder.svg)](https://pypi.org/project/peakrdl-busdecoder)

# PeakRDL-BusDecoder
Generate a SystemVerilog bus decoder from SystemRDL that splits CPU interface signals to multiple sub-address spaces. This tool is designed for creating hierarchical register address maps by decoding bus transactions and routing them to the appropriate child address maps.

## 0.8.0 candidate — not yet released

This branch prepares 0.8.0 and is **pending integration verification**, not a
shipped release. It requires **Python 3.11 or newer**.

- APB3 and APB4 remain supported in interface and flat-port forms.
- Ordered **AXI4-Lite** accepts AW and W independently, with separate bounded
  read/write queues, FIFO responses, backpressure, and reset recovery.
- Single-manager **AHB-Lite** provides retained address/data-phase routing and
  two-cycle local ERROR responses in interface and flat-port forms. Decoded
  apertures must be at least 1 KiB and aligned/sized in 1 KiB units.

This is not full AXI4: IDs, bursts, exclusives, and cross-ID reordering are not
implemented. Read and write routing share one SystemRDL layout; standalone
custom read/write layouts are not implemented.

For the command line tool, see the [PeakRDL project](https://peakrdl.readthedocs.io).

## Documentation
See the [PeakRDL-BusDecoder Documentation](https://peakrdl-busdecoder.readthedocs.io) for more details
