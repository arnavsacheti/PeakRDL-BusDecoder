Exporter API
============

If you are not using the `PeakRDL command-line tool <https://peakrdl.readthedocs.io>`_,
you can still generate busdecoders programmatically using the exporter API:

.. autoclass:: peakrdl_busdecoder.BusDecoderExporter
    :members:

Clock/reset selection
---------------------
Omitting ``clk_src`` or passing ``clk_src=None`` selects ``"off"`` for
unbuffered APB and ``"design"`` for buffered APB and AXI4-Lite. The explicit
values are ``"off"``, ``"cpuif"``, and ``"design"``. Unbuffered APB's default
preserves its clockless 0.7.x decoder port shape. Non-``"none"`` ``apb_buffer``
requires ``"design"``; explicit ``"off"`` or ``"cpuif"`` with buffering is
rejected. Omit ``clk_src``, select ``"design"``, or disable buffering.

AXI4-Lite rejects ``"off"``; use the default ``"design"`` or select ``"cpuif"``
and connect the corresponding clock/reset. AHB-Lite always requires ingress
``HCLK/HRESETn``: it ignores ``"design"`` and ``"cpuif"`` and rejects ``"off"``.
See :doc:`cpuif/introduction` for port and wiring details and :doc:`migrating`
for updated APB imports.


Example
-------
Below is a simple example that demonstrates how to generate a SystemVerilog
implementation from SystemRDL source.

.. code-block:: python
    :emphasize-lines: 3-5, 25-30

    import sys

    from systemrdl import RDLCompiler, RDLCompileError
    from peakrdl_busdecoder import BusDecoderExporter
    from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif

    input_files = [
        "PATH/TO/my_register_block.rdl"
    ]

    # Create an instance of the compiler
    rdlc = RDLCompiler()

    try:
        # Compile your RDL files
        for input_file in input_files:
            rdlc.compile_file(input_file)

        # Elaborate the design
        root = rdlc.elaborate()
    except RDLCompileError:
        # A compilation error occurred. Exit with error code
        sys.exit(1)

    # Export a SystemVerilog implementation
    exporter = BusDecoderExporter()
    exporter.export(
        root, "path/to/output_dir",
        cpuif_cls=AXI4LiteCpuif,
        clk_src="design",  # Wire the generated clk/rst inputs in the RTL design.
    )
