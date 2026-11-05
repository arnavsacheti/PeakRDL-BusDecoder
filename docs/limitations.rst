Known Limitations
=================

The busdecoder exporter intentionally focuses on address decode and routing.
Some SystemRDL features are ignored, and a few are explicitly disallowed.


Address Alignment
-----------------
All address offsets and array strides must be aligned to the CPU interface data
bus width (in bytes). Misaligned offsets/strides are rejected. Diagnostics name
the component, actual byte offset or per-dimension stride, and required byte
alignment. Array dimension indices in diagnostics are zero-based.


Wide Registers
--------------
If a register is wider than its ``accesswidth`` (a multi-word register), its
``accesswidth`` must match the CPU interface data width. Multi-word registers
with a smaller accesswidth are not supported.

Field storage, read side-effects and multi-word access atomicity are owned by
the downstream register block. The decoder does not require field read/write
buffering properties; it forwards each bus transfer independently.


External Boundary References
----------------------------
Property references are not allowed to cross the internal/external boundary of
the exported addrmap. References must point to components that are internal to
the busdecoder being generated. Errors identify the assigned property, owning
component, and referenced component/property. Make the target internal to the
exported addrmap or remove the cross-boundary assignment.

CPU Interface Reset Metadata
----------------------------
Built-in adapters do not consume SystemRDL ``cpuif_reset`` declarations at any
hierarchy level. APB and AXI4-Lite use the active-high asynchronous ``rst``
port with ``--clk-src design`` or the active-low asynchronous ``PRESETn`` /
``ARESETn`` ingress signal with ``--clk-src cpuif``. AHB-Lite always uses its
active-low asynchronous ingress ``HRESETn``.
Unbuffered APB defaults to ``--clk-src off`` and has no reset port, so
``cpuif_reset`` declarations do not produce reset-port mismatch warnings.

A ``cpuif_reset`` declaration warns when its name, scope, explicitly declared
polarity, or explicitly declared synchronization conflicts with that fixed
port. A matching top-level declaration is silent; it still does not configure
the adapter. Wire the generated port with the required polarity instead.
Custom adapters may implement their own reset handling.


Protocol Scope
--------------
AXI4-Lite is a single-beat, no-ID protocol. Full AXI4 IDs, bursts, exclusive
accesses, and cross-ID response reordering are not implemented. Reads and
writes share one exported SystemRDL layout; standalone custom directional
layouts are not implemented.

AHB-Lite supports one manager and a shared address/data pipeline, not
multi-manager arbitration, SPLIT/RETRY, AHB5 extensions, or width conversion.
Every decoded target element must have a base and size aligned to 1 KiB,
a size of at least 1 KiB, and 1 KiB-aligned array strides. Unsupported layouts
are diagnosed, not silently widened. See :doc:`cpuif/ahblite`.


Unsupported Properties
----------------------
The following SystemRDL properties are explicitly rejected:

* ``sharedextbus`` on addrmap/regfile components
