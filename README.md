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

- APB3 and APB4 remain supported in interface and flat-port forms. With default
  `--apb-buffer none`, omitting `--clk-src` preserves the 0.7.x clockless decoder
  ports (`off`). Optional transaction-aware buffering (`in`/`out`/`both`)
  automatically selects `design` clock/reset when unspecified and retires each
  child transfer exactly once. No-wait upstream ACCESS takes 1/2/2/3 cycles for
  `none`/`in`/`out`/`both`. Buffered reset aborts pending work and requires a fresh
  upstream SETUP. See [APB timing and reset behavior](docs/cpuif/apb.rst).
- Ordered **AXI4-Lite** accepts AW and W independently, with separate bounded
  read/write queues, FIFO responses, backpressure, and reset recovery. It now
  requires clock/reset wiring: the default is `design`; `cpuif` is also
  supported, while `off` is rejected.
- Single-manager **AHB-Lite** provides retained address/data-phase routing and
  two-cycle local ERROR responses in interface and flat-port forms. Decoded
  apertures must be at least 1 KiB and aligned/sized in 1 KiB units.
- Project-wide generator defaults in `[busdecoder]` in `peakrdl.toml`, with
  explicit CLI overrides and `--no-gate-signals`/`--no-unroll`/`--no-parametrize`
  to disable project-enabled options. Existing custom CPU-interface aliases
  remain supported. See [configuration](docs/configuring.rst).

This is not full AXI4: IDs, bursts, exclusives, and cross-ID reordering are not
implemented. Read and write routing share one SystemRDL layout; standalone
custom read/write layouts are not implemented.

See [Migrating from 0.7.x](docs/migrating.rst) for Python import updates,
clock/reset choices, and changed decode-depth and AXI4-Lite behavior.

For the command line tool, see the [PeakRDL project](https://peakrdl.readthedocs.io).

## Documentation
See the [PeakRDL-BusDecoder Documentation](https://peakrdl-busdecoder.readthedocs.io) for more details
