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
# Using uv (recommended)
uv sync --group test

# Or using pip
python -m pip install -e . parameterized pytest pytest-cov pytest-xdist
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
# Install with cocotb support using uv (recommended)
uv sync --group test

# Or using pip
python -m pip install -e . parameterized pytest pytest-cov pytest-xdist cocotb cocotb-bus

# Install HDL simulator (choose one)
apt-get install iverilog  # Icarus Verilog
apt-get install verilator # Verilator
```

### Running the tests

#### Integration tests (no simulator required)

These tests validate cross-generator routing and public interface structure
without requiring an HDL simulator:

```bash
PYTHONPATH=src uv run pytest tests/integration -v
```


#### Simulation layout

Simulation-oriented tests are grouped by CPU interface under
`tests/cocotb/<cpuif>/<group>/`. For example, the APB4 smoke test lives in
`tests/cocotb/apb4/smoke/` alongside its pytest runner module. Each runner
compiles the appropriate SystemRDL design, adds the interface wrapper from
`hdl-src/`, and invokes cocotb via Verilator.

#### Full simulation tests (requires simulator)

To execute the APB3, APB4, and AXI4-Lite cocotb smoke runners:

```bash
PYTHONPATH=src uv run pytest tests/cocotb/*/smoke/test_runner.py -v
```

To target a single interface, point pytest at that runner module:

```bash
PYTHONPATH=src uv run pytest tests/cocotb/apb3/smoke/test_runner.py -v
PYTHONPATH=src uv run pytest tests/cocotb/apb4/smoke/test_runner.py -v
PYTHONPATH=src uv run pytest tests/cocotb/axi4lite/smoke/test_runner.py -v
```

#### Stateful and cross-feature regressions

The APB4 stress runner attaches a separate autonomous RTL RAM to each physical
downstream endpoint. Only downstream `PSEL && PENABLE && PREADY` clock edges
commit writes, with byte strobes applied to stored data. The request-side ledger
checks initial state, partial and zero-strobe overwrites, later readback, stalls,
and exact child completion counts; it never supplies expected child `PRDATA`.
The fixed APB back-to-back regression separately covers side-effecting children.

```bash
PYTHONPATH=src uv run pytest tests/cocotb/apb4/smoke/test_runner_stress.py -v
PYTHONPATH=src uv run pytest tests/formal/test_apb_back_to_back.py -v
PYTHONPATH=src uv run pytest tests/unit/test_rdl_params.py -v
PYTHONPATH=src uv run pytest tests/formal/test_formal_equivalence.py -v
```

The parameter regression compiles parameterized generated RTL with actual
module-parameter overrides: disabled entries must error without child activity,
enabled entries retain their maximum-layout addresses, and invalid overrides
must fail the emitted runtime bounds assertion. Cross-feature cases compare
APB4 and AXI4-Lite RTL with the independent SystemRDL-node oracle for nested
arrays, rolled/unrolled ports, permissions, holes, and an exported nonzero-base
submap. These are finite behavioral scenarios, not unbounded proofs or evidence
of compatibility with simulators that the tests do not invoke.

### AHB-Lite and full regression

AHB-Lite uses an independent C++ cycle scoreboard driven against generated RTL
compiled by Verilator, rather than a cocotb smoke runner. It covers flat and SV
interface ports, rolled/unrolled and ancestor arrays, local submap addresses,
32/64-bit data, direction permissions, stalls, two-cycle errors, and reset.
Interface-width contract cases enable Verilator assertions and require a real
mismatched interface to fail.

```bash
PYTHONPATH=src uv run pytest tests/ahblite/test_ahblite.py -v
PYTHONPATH=src uv run pytest tests -q
```

The complete suite also includes the finite generated-RTL conformance and naming
regressions in `tests/formal`. These commands are verification instructions, not
a verification receipt for the 0.8.0 candidate.
