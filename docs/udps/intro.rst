Introduction
============

Although the official SystemRDL spec defines numerous properties that allow you
to define complex register map structures, sometimes they are not enough to
accurately describe a necessary feature. Fortunately the SystemRDL spec allows
the language to be extended using "User Defined Properties" (UDPs).

Current UDP Support
-------------------

**Note:** PeakRDL-BusDecoder currently does not implement any User Defined Properties.
The focus of this tool is on bus decoding and address space routing rather than 
field-level or register-level behavioral extensions.

If you need UDPs for field-level behaviors (such as buffering, signedness, or 
fixed-point representations), consider using `PeakRDL-regblock <https://github.com/SystemRDL/PeakRDL-regblock>`_,
which is designed for comprehensive register block generation with extensive UDP support.

Extending with Custom UDPs
---------------------------

If your bus decoder design requires custom User Defined Properties, you can extend
PeakRDL-BusDecoder by:

1. **Define your UDP in SystemRDL**

   Create a ``.rdl`` file that defines your custom properties:

   .. code-block:: systemrdl

      property my_custom_prop {
          component = addrmap;
          type = boolean;
      };

2. **Implement the UDP in Python**

   Create a Python UDP definition class in your project:

   .. code-block:: python

      from systemrdl.udp import UDPDefinition

      class MyCustomUDP(UDPDefinition):
          name = "my_custom_prop"
          valid_components = {"addrmap"}
          valid_type = bool
          default = False

3. **Register the UDP with the compiler**

   When using PeakRDL-BusDecoder programmatically, register your UDP:

   .. code-block:: python

      from systemrdl import RDLCompiler
      from peakrdl_busdecoder import BusDecoderExporter

      rdlc = RDLCompiler()
      rdlc.register_udp(MyCustomUDP)
      
      # Compile your RDL files
      rdlc.compile_file("my_udp_defs.rdl")
      rdlc.compile_file("my_design.rdl")
      
      root = rdlc.elaborate()
      
      # Export
      exporter = BusDecoderExporter()
      exporter.export(root, "output/")

4. **Access UDP values in your design**

   UDP values can be accessed from nodes in the SystemRDL tree and used to
   customize the generated bus decoder logic as needed.

For more information on creating User Defined Properties, see the 
`SystemRDL Compiler documentation <https://systemrdl-compiler.readthedocs.io/en/stable/model_structure.html#user-defined-properties>`_.
