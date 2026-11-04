# AHB-Lite routing contract

Status: **current 0.8.0 candidate draft, pending integration verification; not shipped.**
This profile shares the current decoder and naming contracts in `spec/busdecoder.md`.
Normative source: [Arm AMBA AHB Protocol Specification IHI 0033C](https://documentation-service.arm.com/static/6141bf0d674a052ae36ca811), chapters 2–7. This document is an independently worded profile, not a reproduction or formalization of the entire Arm specification.

## Scope and signals

AHB-SCOPE: `ahb-lite` and `ahb-lite-flat` generate a single-manager AHB-Lite router: one subordinate ingress and one manager-side interface per decoded target. No multi-manager arbitration, SPLIT/RETRY, AHB5 exclusives, security extensions or width conversion. Burst address generation is the upstream manager's responsibility. Every NONSEQ/SEQ beat is routed independently; HBURST and HMASTLOCK are forwarded. Read and write share AHB's address/data pipeline, unlike AXI's independent channels.

AHB-SIGNALS: ingress HCLK, HRESETn (active-low asynchronous reset), HSEL, HREADY, HADDR, HTRANS[1:0], HWRITE, HSIZE[2:0], HBURST[2:0], HPROT[3:0], HMASTLOCK, HWDATA; egress HRDATA, HREADYOUT, HRESP (one bit). Each child receives HSEL, HREADY, address/control and write data and supplies HRDATA/HREADYOUT/HRESP. Clock/reset distribution must be documented explicitly for interface and flat forms. Data widths are common to all endpoints and are one of 32, 64, 128, 256, 512 or 1024 bits.

AHB-APERTURE: Arm §4.2 requires each subordinate region to start and end on a 1KiB boundary. Require decoded target element bases, sizes and array strides to honor this rule; diagnose unsupported layouts rather than silently widening a region or changing an RDL address. Small register maps must be placed inside an explicitly sized 1KiB-or-larger downstream block. Top address width must represent that space; child addresses are byte offsets relative to the selected target. Standalone sub-addrmap exports are local to that exported root.

## Transition system

Let `active = HSEL && HTRANS[1]`. NONSEQ=2 and SEQ=3 are active; IDLE=0 and BUSY=1 are not requests. On each rising HCLK edge:

AHB-ACCEPT: an address phase is accepted iff HRESETn && HREADY && active. Capture exactly its destination or local-error marker, not the live address of the following transfer. A completed data phase and new accepted address may share an edge (one beat/cycle for zero-wait children).

AHB-HOLD: when HREADY=0, retain data-phase destination and direction. Do not accept another address phase. Address-phase HSEL may reflect the next address; children must sample it only when HREADY=1. The response mux must never use this next address to select the preceding data response.

AHB-BUBBLE: on an HREADY=1 edge without active ingress, clear the data-phase-valid marker. With no pending data phase, return HREADYOUT=1, HRESP=0, HRDATA=0. IDLE/BUSY at unmapped addresses must not generate errors. A bubble must not discard an older stalled data phase.

AHB-DATA: write data belongs to the preceding accepted address. Forward live HWDATA during its data phase, not the value sampled with its address. The manager holds write data while that transfer is stalled. Forward HSIZE/HPROT/HBURST/HTRANS/HMASTLOCK in the address phase without modifying byte lanes or implementing burst address generation.

AHB-RESPONSE: for a mapped pending transfer, mux HRDATA/HREADYOUT/HRESP only from its retained child. Child wait states propagate without retargeting; child two-cycle ERROR responses pass through unchanged. Other children cannot complete the pending transaction.

AHB-MISS: an accepted address matching no permitted target, including array stride holes, produces exactly a local two-cycle ERROR: first data-response cycle HREADYOUT=0,HRESP=1; second HREADYOUT=1,HRESP=1. No downstream HSEL is asserted for the denied address. The error phase advances across the initial forced wait cycle even though HREADY=0. Following address cancellation is legal; recovery accepts the next active address only on HREADY=1. Read data on local errors is zero. No indefinite stalls are introduced locally.

AHB-RESET: asynchronously clear pending destination/valid and local error phase. During reset drive HREADYOUT=1,HRESP=0 and downstream HSEL=0; no stale completion survives reset release.

AHB-PERMISSIONS: where a target is a register, select reads only if it has a present software-readable field and writes only if it has a present writable field. Opaque block targets route both directions; permission and field-side-effect enforcement inside the block belongs to its downstream implementation. AHB HPROT is forwarded, not interpreted as authorization.

AHB-ASSUMPTIONS: manager and children obey AHB-Lite timing, legal HSIZE/data-bus width, aligned addresses, stable active address/control during stalls, write data stability, burst boundaries and legal two-cycle child ERROR. The router is not a protocol firewall and must not claim to validate malformed traffic unless explicit rejection logic is implemented and verified.

## Integration architecture

1. `ahb-lite` / `ahb-lite-flat` use the shared CPU-interface registry,
   target-boundary collector, target-name allocator, top-relative base helper,
   and direction-permission decode. No independent AHB boundary/naming policy
   replaces those shared decisions.
2. The Python adapter generates constant-index bridges for each target element,
   including every rolled ancestor dimension. Public ports support both rolled
   arrays and unrolled suffixes in outer-to-inner order. Package widths are
   emitted once per target identity.
3. Address selection is combinational; data-phase selection is retained state.
   The AHB pipeline does not impose a global CPUIF single-flight rule or
   serialize independent AXI4-Lite queues. Both directions use one exported
   layout; standalone custom read/write layouts are not implemented.
4. AHB always uses canonical ingress HCLK/HRESETn, independently of `--clk-src`
   and RDL reset metadata. Interface endpoints connect their same-domain
   clock/reset externally; flat ingress exposes them directly.

## Proof boundary

Executable cycle-level RTL tests establish conformance for exercised finite scenarios, not universal formal equivalence or full AHB certification. Safety obligations are retained-destination stability, no acceptance under stall, no side-effecting child select on a local miss, phase-correct write data and error termination. Liveness depends on downstream responders eventually asserting HREADYOUT. Future symbolic proofs must state that fairness assumption explicitly.

## Candidate coverage and evidence

`cpuif/ahblite`, `hdl-src/ahblite_intf.sv`, and `docs/cpuif/ahblite.rst`
implement and document this profile. `tests/ahblite` uses real generated RTL
and an independent public-pin cycle scoreboard, not private selector values.
Its cases cover alternating targets and directions, next-address/previous-data
overlap, wait states, live write data, IDLE/BUSY, local misses and array holes,
child ERROR, cancellation/recovery, reset, rolled/unrolled nested arrays,
submap-local addresses, permissions, and the address-space upper endpoint.

The imported isolated-development receipt recorded 20 RTL and 18 diagnostic
cases, plus existing non-AHB Python modules (241 passed, 1 skipped). That receipt
belongs to the older isolated AHB snapshot; it does **not** verify the integrated
0.8.0 candidate. No integrated tests, builds, lint, or formatters were run during
candidate preparation. The integration owner must exercise the complete suite
before publication. The current cases use 32/64-bit data; they do not establish
exhaustive conformance for every supported data width or valid aperture size.

Shared prerequisites include widened exclusive upper-bound comparisons,
outer-to-inner multidimensional stride/index ordering, balanced traversal,
direction-sensitive scalar/array permissions, and collision-free selector
typedefs. They are reconciled with the central 0.7.3 helpers rather than copied
over newer shared files. Existing depth/naming assertions remain behavioral
coverage, with expectations migrated only where public contracts changed.
