Known Limitations
=================

The busdecoder exporter intentionally focuses on address decode and routing.
Some SystemRDL features are ignored, and a few are explicitly disallowed.


Address Alignment
-----------------
All address offsets and array strides must be aligned to the CPU interface data
bus width (in bytes). Misaligned offsets/strides are rejected.


Wide Registers
--------------
If a register is wider than its ``accesswidth`` (a multi-word register), its
``accesswidth`` must match the CPU interface data width. Multi-word registers
with a smaller accesswidth are not supported.


Fields Spanning Sub-Words
-------------------------
If a field spans multiple sub-words of a wide register:

* Software-writable fields must have write buffering enabled
* Fields with ``onread`` side-effects must have read buffering enabled

These rules are enforced to avoid ambiguous multi-word access behavior.


External Boundary References
----------------------------
Property references are not allowed to cross the internal/external boundary of
the exported addrmap. References must point to components that are internal to
the busdecoder being generated.

CPU Interface Reset Location
----------------------------
Only ``cpuif_reset`` signals instantiated at the top-level addrmap (or above)
are honored. Nested ``cpuif_reset`` signals are ignored.


Unsupported Properties
----------------------
The following SystemRDL properties are explicitly rejected:

* ``sharedextbus`` on addrmap/regfile components
