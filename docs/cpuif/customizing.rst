Customizing the CPU interface
=============================

Use your own existing SystemVerilog interface definition
--------------------------------------------------------

This exporter comes pre-bundled with its own SystemVerilog interface declarations.
What if you already have your own SystemVerilog interface declaration that you prefer?

As long as your interface has the same protocol signals and behavior, customize
the existing adapter's interface helper rather than replacing its routed ports.


As an example, let's use the SystemVerilog interface definition for
:ref:`cpuif_axi4lite` that is bundled with this project. This interface uses
the following style and naming conventions:

* SystemVerilog interface type name is ``axi4lite_intf``
* Defines modports named ``master`` and ``slave``
* Interface signals are all upper-case: ``AWREADY``, ``AWVALID``, etc...

Let's assume your preferred SV interface definition uses a slightly different naming convention:

* SystemVerilog interface type name is ``axi4_lite_interface``
* Modports are capitalized and use suffixes ``Master_mp`` and ``Slave_mp``
* Interface signals are all lower-case: ``awready``, ``awvalid``, etc...

Rather than rewriting a new CPU interface definition, you can extend and adjust the existing one:

.. code-block:: python

    from peakrdl_busdecoder.cpuif.axi4lite import AXI4LiteCpuif
    from peakrdl_busdecoder.cpuif.axi4lite.axi4_lite_interface import (
        AXI4LiteSVInterface,
    )

    class MyAXI4LiteInterface(AXI4LiteSVInterface):
        slave_modport_name = "Slave_mp"
        master_modport_name = "Master_mp"

        def get_interface_type(self) -> str:
            return "axi4_lite_interface"

        def signal(self, signal: str, node=None, indexer=None) -> str:
            # Preserve endpoint selection and all array indices.
            return super().signal(signal.lower(), node, indexer)

    class MyAXI4Lite(AXI4LiteCpuif):
        sv_interface_cls = MyAXI4LiteInterface

The inherited port-declaration helper emits the new interface type and modports
for the upstream endpoint **and every downstream endpoint**. Passing the signal,
node, and indexer through the inherited signal helper also preserves routing
for rolled arrays, array ancestors, and unrolled endpoints. The signal-name
mapping applies to clock/reset members as well as request and response members.
Do not replace ``port_declaration`` with a single upstream port or return an
upstream-only name from ``signal``: that discards the child declarations or
misroutes their references.

``AXI4LiteCpuif`` already selects the SystemVerilog interface form through
``use_sv_interface = True``. ``BaseCpuif`` chooses ``sv_interface_cls`` for this
form and ``flat_interface_cls`` for discrete ports; the adapter's protocol
implementation remains unchanged. Downstream identities come from the shared
``DesignState.get_target_name(node)`` allocation, so custom signal spelling
does not need to reproduce collision handling or construct target names.

Then use your custom CPUIF during export:

.. code-block:: python

   from peakrdl_busdecoder import BusDecoderExporter

   exporter = BusDecoderExporter()
   exporter.export(
      root, "path/to/output_dir",
      cpuif_cls=MyAXI4Lite
   )



Custom CPU Interface Protocol
-----------------------------

If you require a CPU interface protocol that is not included in this project,
you can define your own.

1. Create a SystemVerilog CPUIF implementation template file.

    This contains the SystemVerilog implementation of the bus protocol and
    connects it to the shared request/decode signals described in
    :ref:`cpuif_protocol`. The adapter must implement the protocol's acceptance,
    retained destination/direction, and response timing; the shared decoder
    does not retain those on its behalf. For example, AHB-Lite accepts its next
    destination and direction only with ``HREADY`` high and selects responses
    from that retained data phase rather than the live address.

    Reminder that this template will be preprocessed using
    `Jinja <https://jinja.palletsprojects.com>`_, so you can use
    some templating tags to dynamically render content. See the implementations of
    existing CPU interfaces as an example.

2. Create a Python class that defines your CPUIF

    Extend your class from :class:`peakrdl_busdecoder.cpuif.BaseCpuif`.
    Set ``template_path`` and ``flat_interface_cls``; provide ``sv_interface_cls``
    and select ``use_sv_interface = True`` for a SystemVerilog interface
    variant. Reuse the existing ``Interface``, ``FlatInterface``, and
    ``SVInterface`` helpers in ``peakrdl_busdecoder.cpuif.interface`` to declare
    and reference every endpoint. Keep target names on the shared
    ``DesignState.get_target_name(node)`` path rather than allocating adapter-local
    names. Read/write decode qualification is part of the adapter; there is no
    standalone option for separate custom read and write address layouts.

3. Use your new CPUIF definition when exporting.
4. If you think the CPUIF protocol is something others might find useful, let me
   know and I can add it to PeakRDL!


Loading into the PeakRDL command line tool
------------------------------------------
There are two ways to make your custom CPUIF class visible to the
`PeakRDL command-line tool <https://peakrdl.readthedocs.io>`_.

Via the PeakRDL TOML
^^^^^^^^^^^^^^^^^^^^
The easiest way to add your cpuif is via the TOML config file. See the
:ref:`peakrdl_cfg` section for more details.

Via a package's entry point definition
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
If you are publishing a collection of PeakRDL plugins as an installable Python
package, you can advertise them to PeakRDL using an entry point.
This advertises your custom CPUIF class to the PeakRDL-BusDecoder tool as a plugin
that should be loaded, and made available as a command-line option in PeakRDL.

.. code-block:: toml

    [project.entry-points."peakrdl_busdecoder.cpuif"]
    my-cpuif = "my_package.my_module:MyCPUIF"


*   ``my_package``: The name of your installable Python module
*   ``peakrdl_busdecoder.cpuif``: This is the namespace that PeakRDL-BusDecoder will
    search. Any cpuif plugins you create must be enclosed in this namespace in
    order to be discovered.
*   ``my_package.my_module:MyCPUIF``: This is the import path that
    points to your CPUIF class definition.
*   ``my-cpuif``: The lefthand side of the assignment is your cpuif's name. This
    text is what the end-user uses in the command line interface to select your
    CPUIF implementation.
