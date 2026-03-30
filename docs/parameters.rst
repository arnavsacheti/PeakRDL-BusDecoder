SystemRDL Parameters
====================

PeakRDL-BusDecoder can detect root-level SystemRDL parameters on the top-level
addrmap and, when they affect the address map layout, expose them as
synthesizable SystemVerilog module parameters. This lets the instantiating RTL
adjust the *effective* size of arrayed children at elaboration time without
re-running the SystemRDL compiler.


Which Parameters Are Extracted
------------------------------

Only **address-modifying** parameters are extracted. A parameter is considered
address-modifying when it controls an array dimension of a child node in the
address map. All other parameters (reset values, field widths, mode selectors,
etc.) are silently ignored because they do not change the decoder's routing
logic.

Consider this SystemRDL source:

.. code-block:: systemrdl

    addrmap my_block #(
        longint unsigned N_ENGINES   = 4,
        longint unsigned DEFAULT_MODE = 7
    ) {
        reg { field { sw=rw; hw=r; reset=DEFAULT_MODE; } mode[7:0]; }
            engine_ctrl[N_ENGINES] @ 0x0;
    };

``N_ENGINES`` drives the array dimension of ``engine_ctrl`` and is therefore
**address-modifying**. ``DEFAULT_MODE`` only sets a field reset value and does
not change the address layout, so it is ignored.


How Parameters Are Detected
----------------------------

Detection works in three phases:

1. **Monkeypatch tracing** -- The extractor temporarily patches the SystemRDL
   compiler's internal ``ParameterRef.get_value()`` method. Every time a
   parameter reference resolves, the patch records which root-level parameter
   was accessed and from which node in the component tree.

2. **Cache-clear & re-evaluation** -- After installing the patch, the extractor
   clears the cached values on every ``Parameter`` object in the tree and forces
   a top-down re-evaluation pass. This guarantees the patched method fires for
   every live reference, not just uncached ones. The original method is always
   restored in a ``finally`` block.

3. **Classification** -- For each root parameter, the extractor walks the
   component tree looking for arrayed addressable nodes whose dimensions match
   the parameter's elaborated value. Both the monkeypatch trace and a fallback
   value-match heuristic are used to associate a parameter with specific array
   dimensions.


How Parameters Appear in Generated RTL
---------------------------------------

When an address-modifying parameter is found, the generated output changes in
four places:


Module parameter declaration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The parameter becomes a SystemVerilog module parameter with its elaborated
(maximum) value as the default:

.. code-block:: systemverilog

    module my_block #(
        parameter int N_ENGINES = 4
    ) ( ... );

The auto-generated ``localparam`` that would normally be emitted for the array
(e.g. ``localparam N_ENGINE_CTRLS = 4``) is suppressed to avoid a duplicate
constant.


Runtime assertions
^^^^^^^^^^^^^^^^^^

An ``initial begin`` / ``assert`` block constrains the runtime value to
``0 <= n <= N``:

.. code-block:: systemverilog

    initial begin
        assert (N_ENGINES >= 0 && N_ENGINES <= 4)
            else $fatal(1, "N_ENGINES must be in range [0, 4]");
    end

This catches invalid parameterizations at simulation time.


For-loop bounds
^^^^^^^^^^^^^^^

Wherever the decoder iterates over the array (address decode, fanout, fanin),
the loop bound uses the parameter **name** instead of the static integer:

.. code-block:: systemverilog

    for (int i0 = 0; i0 < N_ENGINES; i0++) begin
        ...
    end

This means the decoder only routes transactions to the first ``n`` elements
(where ``n`` is the elaboration-time value of ``N_ENGINES``), even though the
address space is sized for the maximum ``N``.


Struct dimensions (static)
^^^^^^^^^^^^^^^^^^^^^^^^^^

SystemVerilog struct members must have compile-time-constant sizes. The struct
that holds per-child select signals always uses the **maximum** dimension, not
the parameter name:

.. code-block:: systemverilog

    typedef struct packed {
        logic engine_ctrl[4];  // always the max N
    } cpuif_sel_t;


Package MAX constant
^^^^^^^^^^^^^^^^^^^^

The generated package includes a ``MAX`` localparam so that downstream modules
can reference the upper bound:

.. code-block:: systemverilog

    package my_block_pkg;
        ...
        localparam MY_BLOCK_MAX_N_ENGINES = 4;
    endpackage


Example
-------

Given the following input:

.. code-block:: systemrdl

    addrmap router #(longint unsigned N_PORTS = 8) {
        reg { field { sw=rw; hw=r; } data[31:0]; } port[N_PORTS] @ 0x0;
    };

The generated module starts with:

.. code-block:: systemverilog

    module router #(
        parameter int N_PORTS = 8
    ) ( ... );
        import router_pkg::*;

        initial begin
            assert (N_PORTS >= 0 && N_PORTS <= 8)
                else $fatal(1, "N_PORTS must be in range [0, 8]");
        end

And the package contains:

.. code-block:: systemverilog

    localparam ROUTER_MAX_N_PORTS = 8;

An instantiating module can then do:

.. code-block:: systemverilog

    router #(.N_PORTS(3)) u_router ( ... );

The decoder will route to the first 3 ports while the address space and struct
sizes remain at the maximum of 8.
