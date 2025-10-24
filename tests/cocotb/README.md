# Cocotb Integration Tests

This directory contains cocotb-based integration tests that verify the functionality
of generated bus decoder RTL for different CPU interfaces.

## Overview

These tests:
1. Generate SystemVerilog decoder modules from SystemRDL specifications
2. Simulate the generated RTL using cocotb
3. Verify read/write operations work correctly for different bus protocols

## Supported CPU Interfaces

- APB3 (AMBA APB3)
- APB4 (AMBA APB4 with strobe support)
- AXI4-Lite (AMBA AXI4-Lite)

## Running the Tests

### Install Dependencies

```bash
pip install -e .[cocotb-test]
```

### Run All Cocotb Tests

```bash
pytest tests/cocotb/testbenches/
```

### Run Specific Interface Tests

```bash
# Test APB4 interface
pytest tests/cocotb/testbenches/test_apb4_decoder.py

# Test APB3 interface
pytest tests/cocotb/testbenches/test_apb3_decoder.py

# Test AXI4-Lite interface
pytest tests/cocotb/testbenches/test_axi4lite_decoder.py
```

## Test Structure

- `common/`: Shared utilities and base classes for cocotb tests
- `testbenches/`: Individual testbenches for each CPU interface
