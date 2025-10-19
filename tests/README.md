# Unit tests

The bus decoder exporter now ships with a small unit test suite built around
`pytest`. The tests exercise the Python implementation directly and use the
[`systemrdl-compiler`](https://github.com/SystemRDL/systemrdl-compiler)
package to elaborate inline SystemRDL snippets.

## Install dependencies

Create an isolated environment if desired and install the minimal requirements:

```bash
python -m pip install -r tests/requirements.txt
```

## Running the suite

Invoke `pytest` from the repository root (or the `tests` directory) and point it
at the unit tests:

```bash
pytest tests/unit
```

Pytest will automatically discover tests that follow the `test_*.py` naming
pattern and can make use of the `compile_rdl` fixture defined in
`tests/unit/conftest.py` to compile inline SystemRDL sources.
