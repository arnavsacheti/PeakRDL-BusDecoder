# Tests

The bus decoder exporter includes comprehensive test suites to validate both the
Python implementation and the generated SystemVerilog RTL.

## Unit Tests

The unit test suite is built around `pytest` and exercises the Python implementation
directly using the [`systemrdl-compiler`](https://github.com/SystemRDL/systemrdl-compiler)
package to elaborate inline SystemRDL snippets.

### Install dependencies

Create an isolated environment if desired and install the minimal requirements:

```bash
python -m pip install -e .[test]
```

### Running the suite

Invoke `pytest` from the repository root (or the `tests` directory) and point it
at the unit tests:

```bash
pytest tests/unit
```

Pytest will automatically discover tests that follow the `test_*.py` naming
pattern and can make use of the `compile_rdl` fixture defined in
`tests/unit/conftest.py` to compile inline SystemRDL sources.

## Cocotb Integration Tests

The cocotb test suite validates the functionality of generated SystemVerilog RTL
through simulation. These tests generate bus decoders for different CPU interfaces
(APB3, APB4, AXI4-Lite) and verify that read/write operations work correctly.

### Install dependencies

```bash
# Install with cocotb support
python -m pip install -e .[cocotb-test]

# Install HDL simulator (choose one)
apt-get install iverilog  # Icarus Verilog
apt-get install verilator # Verilator
```

### Running the tests

#### Integration tests (no simulator required)

These tests validate code generation without requiring an HDL simulator:

```bash
pytest tests/cocotb/testbenches/test_integration.py -v
```

#### Example code generation

Run examples to see generated code for different configurations:

```bash
python tests/cocotb/examples.py
```

#### Full simulation tests (requires simulator)

To run the full cocotb simulation tests:

```bash
# Run all cocotb simulation tests
pytest tests/cocotb/testbenches/test_*_runner.py -v

# Run specific interface tests
pytest tests/cocotb/testbenches/test_apb4_runner.py -v
```

For more information about cocotb tests, see [`tests/cocotb/README.md`](cocotb/README.md).
