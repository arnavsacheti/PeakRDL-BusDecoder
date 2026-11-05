.. _peakrdl_cfg:

Configuring PeakRDL-BusDecoder
==============================

When using the `PeakRDL command line tool <https://peakrdl.readthedocs.io/>`_,
project-wide defaults for ``peakrdl busdecoder`` can be stored in
``peakrdl.toml`` under ``[busdecoder]``. The Python exporter API does not load
this configuration file.


Configuration discovery and precedence
--------------------------------------

PeakRDL's global ``--peakrdl-cfg FILE`` option selects a configuration file
explicitly. Otherwise, PeakRDL uses the first existing file in this order:

#. ``peakrdl.toml`` in the current working directory
#. ``.peakrdl.toml`` in the current working directory
#. The file named by the ``PEAKRDL_CFG`` environment variable
#. ``~/.peakrdl.toml``
#. ``~/.config/peakrdl.toml``
#. ``/etc/peakrdl.toml``

Discovery starts in the working directory, not the input RDL file's directory;
it does not walk parent directories or merge multiple files. In particular,
PeakRDL does **not** read ``pyproject.toml`` for these settings.

Each setting is resolved independently:

#. An explicitly supplied command-line option wins.
#. Otherwise, the value in the selected TOML file is used.
#. Otherwise, the built-in default below is used.

For booleans, ``--gate-signals``, ``--unroll``, and ``--parametrize`` explicitly
enable the setting; ``--no-gate-signals``, ``--no-unroll``, and
``--no-parametrize`` explicitly disable it, including when TOML enables it.
Omitting a flag leaves its TOML value in effect. With no configuration file,
existing command-line behavior and defaults are unchanged.


Supported project settings
--------------------------

Use the underscore-separated key names below inside ``[busdecoder]``.
Defaults refer to the built-in values used when neither CLI nor TOML supplies
a value.

.. list-table:: Supported ``[busdecoder]`` keys
    :header-rows: 1
    :widths: 23 40 37

    * - Key
      - TOML type and allowed values
      - Built-in default / meaning
    * - ``cpuif``
      - String: ``"apb3"``, ``"apb3-flat"``, ``"apb4"``, ``"apb4-flat"``,
        ``"axi4-lite"``, ``"axi4-lite-flat"``, ``"ahb-lite"``, or
        ``"ahb-lite-flat"``; also installed entry-point names and aliases
        defined in ``cpuifs``.
      - ``"apb4"``
    * - ``data_width``
      - Integer power of two greater than or equal to ``8``; must not be
        smaller than the widest internal register ``accesswidth``.
      - Inferred from internal registers when omitted; falls back to ``32``
        with a warning if no internal register ``accesswidth`` is available.
    * - ``clk_src``
      - String: ``"off"``, ``"cpuif"``, or ``"design"``.
      - Automatic when omitted: unbuffered APB uses ``off``; buffered APB and
        AXI4-Lite use ``design``. AHB-Lite always uses ingress ``HCLK/HRESETn``.
    * - ``apb_buffer``
      - String: ``"none"``, ``"in"``, ``"out"``, or ``"both"``.
      - ``"none"``; transaction-aware APB buffering is opt-in.
    * - ``gate_signals``
      - Boolean: ``true`` or ``false``.
      - ``false``; enable to mask unselected APB payload signals.
    * - ``max_decode_depth``
      - Integer greater than or equal to ``0``.
      - ``1``; ``0`` means unlimited descent to leaf or opaque boundaries.
    * - ``unroll``
      - Boolean: ``true`` or ``false``.
      - ``false``; enable to unroll arrayed children into discrete interfaces.
    * - ``axi4lite_max_outstanding``
      - Integer greater than or equal to ``1``.
      - ``4``; depth of each separate AXI4-Lite read/write order queue.
    * - ``parametrize``
      - Boolean: ``true`` or ``false``.
      - ``false``; expose eligible top-level SystemRDL parameters as module
        parameters (see :doc:`parameters`).
    * - ``cpuifs``
      - Table mapping alias names to Python import-path strings.
      - Empty mapping; adds custom CPU interfaces as described below.

``clk_src`` has no TOML ``None`` value: leave the key out for automatic
protocol-dependent selection. Only APB interfaces support non-``none``
``apb_buffer`` modes, and those modes require ``clk_src = "design"``.
AXI4-Lite and AHB-Lite reject ``clk_src = "off"``. AHB-Lite accepts
``"design"`` and ``"cpuif"`` but ignores that selection and always uses its
ingress clock/reset.

Per-design ``module_name``, ``package_name``, and ``addr_width`` are **not**
supported project keys; continue to use ``--module-name``, ``--package-name``,
and ``--addr-width`` for those overrides. ``data_width`` is a project setting
and can be overridden with ``--data-width``. A value supplied by either TOML
or CLI suppresses the no-internal-register-width warning; it sets the width
for all decoder interfaces, without converting widths between interfaces.

For example, place this file in the directory from which PeakRDL is invoked:

.. code-block:: toml

    # peakrdl.toml
    [busdecoder]
    cpuif = "apb4-flat"
    data_width = 32
    clk_src = "design"
    apb_buffer = "both"
    gate_signals = true
    max_decode_depth = 2
    unroll = true
    axi4lite_max_outstanding = 4  # Used only for AXI4-Lite.
    parametrize = false

Then a one-off invocation can override just the settings it needs:

.. code-block:: bash

    peakrdl busdecoder design.rdl -o generated/ --data-width 64 --no-gate-signals --no-unroll

The data width becomes 64 bits instead of the project's 32 bits, while payload
gating and array unrolling are disabled for that invocation. The buffered APB
selection remains in effect.


Custom CPU interfaces
---------------------

The existing ``[busdecoder.cpuifs]`` import mapping remains supported alongside
the project defaults. Its aliases can be selected by either ``cpuif`` in TOML
or ``--cpuif`` on the command line. Installed plugins registered under the
``peakrdl_busdecoder.cpuif`` entry-point group are also available.

.. data:: cpuifs

    Mapping of additional CPU Interface implementation classes to load.
    The mapping's key indicates the cpuif's name.
    The value is a string that describes the import path and cpuif class to
    load.

    For example:

    .. code-block:: toml

        [busdecoder]
        cpuifs.my-cpuif-name = "my_cpuif_module:MyCPUInterfaceClass"

    The equivalent table form can also select the alias as a project default:

    .. code-block:: toml

        [busdecoder]
        cpuif = "my-cpuif-name"

        [busdecoder.cpuifs]
        my-cpuif-name = "my_cpuif_module:MyCPUInterfaceClass"

    The imported class must extend ``BaseCpuif``. Alias names must not collide
    with built-in or installed CPU-interface names. See :doc:`cpuif/customizing`
    for implementation details.


Validation and conflicts
------------------------

Project settings are validated for their TOML types and allowed values.
Booleans are not accepted as integers for ``data_width``, ``max_decode_depth``,
or ``axi4lite_max_outstanding``; use actual integer values in the stated ranges.
Likewise, boolean settings require ``true`` or ``false``, not strings or
integers. ``cpuif`` is checked against the available built-ins, installed
entry points, and configured aliases rather than a fixed built-in-only list.

Invalid project settings stop the command with a nonzero exit status and a
concise diagnostic naming the configuration file and ``busdecoder.<key>``,
without a traceback, including with ``--debug``. An explicit CLI override does
not excuse an invalid TOML type, value, or unknown CPU-interface name. For
example, ``data_width = true``, ``data_width = 4``, and ``data_width = 24`` are
invalid even if a valid ``--data-width`` is also supplied.

Clock/buffer compatibility is checked after applying precedence, using the same
rules as the CLI. Conflicts involving effective TOML values identify the
contributing configuration file and key. Individually valid but conflicting
TOML selections can be repaired by CLI overrides. For example, TOML
``clk_src = "off"`` with ``apb_buffer = "both"`` is incompatible for APB;
``--clk-src design`` or ``--apb-buffer none`` makes the effective selections
compatible.

The minimum data width depends on the elaborated design. A TOML
``data_width = 32`` is valid by itself, but fails if it remains the effective
selection for a design with a 64-bit internal register ``accesswidth``. The
diagnostic identifies the configuration file and ``busdecoder.data_width``.
``--data-width 64`` repairs that selection because the valid TOML value is
overridden before the design-dependent minimum is checked. Without CLI or
TOML selection, the width is inferred from the widest internal register
``accesswidth``; registers beneath external blocks do not contribute. With
no internal register width available, the decoder uses 32 bits and warns.
Set ``data_width`` or ``--data-width`` explicitly for external-only maps.

A too-narrow effective TOML width is an export error: it is concise without
a traceback by default, while ``--debug`` includes its full Python traceback.


Command-Line Options
--------------------

The following options are available on the ``peakrdl busdecoder`` command:

See :ref:`generated_decoder_structure` for diagrams showing which options
change ports, routing boundaries, queues, or pipeline state.

* ``--cpuif``: Select the CPU interface (``apb3``, ``apb3-flat``, ``apb4``,
  ``apb4-flat``, ``axi4-lite``, ``axi4-lite-flat``, ``ahb-lite``, ``ahb-lite-flat``)
* ``--module-name``: Override the generated module name
* ``--package-name``: Override the generated package name
* ``--addr-width``: Override the slave address width; values smaller than the
  decoder's required minimum are rejected. Omit the option to infer the width.
* ``--data-width``: Set the data width in bits for all decoder interfaces
  (a power of two, at least 8, and no smaller than any internal register
  ``accesswidth``). Overrides TOML ``data_width``; if neither is supplied,
  the width is inferred from internal registers, or defaults to 32 bits with
  a warning when no internal register ``accesswidth`` is available. An
  explicit CLI or TOML value suppresses that warning. Set it explicitly for
  external-only maps; the decoder does not convert widths between interfaces.
* ``--debug``: Include the full Python traceback when busdecoder export fails.
  By default, expected export errors produce concise diagnostics and a nonzero
  exit status. TOML type/domain validation errors remain concise without a
  traceback, even with ``--debug``. ``-o`` must name a writable directory, not
  an existing file.
* ``--unroll`` / ``--no-unroll``: Enable/disable unrolling arrayed children into
  discrete interfaces (built-in default: disabled)
* ``--max-decode-depth``: Control how far the decoder descends into hierarchy
* ``--parametrize`` / ``--no-parametrize``: Enable/disable propagation of
  top-level SystemRDL parameters into the generated module (built-in default:
  disabled; see :doc:`parameters`)
* ``--clk-src``: Select ``off``, ``cpuif``, or ``design``. When neither CLI nor
  TOML selects a clock source, unbuffered APB (``apb_buffer = "none"``) uses
  ``off``; buffered APB and AXI4-Lite use ``design``.
  ``off`` preserves the clockless 0.7.x APB decoder ports,
  ``design`` adds top-level ``clk``/``rst``, and ``cpuif`` uses protocol
  clock/reset. AHB-Lite always uses ingress ``HCLK/HRESETn``; ``design`` and
  ``cpuif`` are ignored for that protocol, while explicit ``off`` is rejected.
  When present, these are fixed ports and polarities, not names derived from
  SystemRDL ``cpuif_reset`` declarations: ``rst`` is active-high asynchronous,
  while ``PRESETn``, ``ARESETn``, and ``HRESETn`` are active-low asynchronous.
* ``--gate-signals`` / ``--no-gate-signals``: Enable/disable gating APB
  broadcast payload signals with each slave's select so unselected slaves see
  all-zero payload inputs (built-in default: disabled)
* ``--apb-buffer``: Select transaction-aware APB request/response buffering
  (``none`` (built-in default), ``in``, ``out``, ``both``). Non-``none`` modes
  require ``design``, selected automatically if neither CLI nor TOML selects
  ``clk_src``. Explicit ``off`` or ``cpuif`` with buffering is rejected: leave
  the clock source unspecified, select ``--clk-src design``, or disable
  buffering with ``--apb-buffer none``.
  See :doc:`cpuif/apb` for timing and reset behavior.
* ``--axi4lite-max-outstanding``: Set the separate AXI4-Lite read and write
  order-queue depths (default ``4``; minimum ``1``)

AXI4-Lite rejects an effective ``clk_src = "off"`` because its holding registers
and ordered-response queues require a clock/reset. Leave the clock source
unspecified in both CLI and TOML, or select ``design`` or ``cpuif`` and wire
the selected clock/reset. AHB-Lite also rejects ``off``: leave the clock source
unspecified or select ``design`` or ``cpuif``; all accepted settings still use
ingress ``HCLK/HRESETn``.

The Python exporter uses the equivalent ``clk_src`` keyword. Omitting it or
passing ``clk_src=None`` selects the same protocol-dependent defaults; the
explicit values are ``"off"``, ``"cpuif"``, and ``"design"``. ``None`` is not a
command-line choice. See :doc:`cpuif/introduction` for the clock/reset wiring
contract and :doc:`migrating` for changes from 0.7.x.
