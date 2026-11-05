# PeakRDL-BusDecoder — Draft 0.8.0 Specification

This specification defines the behavior, interface contracts, protocol invariants, and address-decoding mathematics of the **PeakRDL-BusDecoder** generator.

Every normative statement is assigned a unique identifier `BD-*`. Downstream audits and verification harnesses reference these identifiers directly.

Status: **0.8.0 candidate, pending integration verification; not shipped.**
This is the current routing contract, not an unbounded formal proof. Python
3.11 or newer is required. Historical audits retain pre-cutover evidence;
this draft supersedes their old coupled-AXI and global-single-flight models.

---

## 1. Top-Level Architectural Contract

```
                     +---------------------------------------+
                     |         PeakRDL-BusDecoder            |
                     |                                       |
  Slave CPUIF        |  +-------------+   +---------------+  |   Master CPUIF 0
  (APB/AXIL/AHB)    ===> | Slave CPUIF |-->| Write Decoder |--===> (Child 0)
                     |  |  Adapter    |   +---------------+  |
                     |  |             |                      |   Master CPUIF 1
                     |  |             |   +---------------+  |===> (Child 1)
                     |  |             |-->| Read Decoder  |--+
                     |  |             |   +---------------+  |   ...
                     |  |             |<--| Readback Mux  |--+   Master CPUIF K-1
                     |  +-------------+   +---------------+  |===> (Child K-1)
                     +---------------------------------------+
```

- **BD-ARCH-PURE-ROUTER**: The generated RTL shall be a pure routing and bus-translation layer containing no software register storage, no field-level logic, and no flip-flops unless required by protocol pipelining.
- **BD-ARCH-LOCAL-ADDR**: The decoder shall operate strictly on addresses relative to the root of the exported address map. The base address of the exported root addrmap within the system interconnect is defined to be 0.
- **BD-ARCH-SV-STD**: Generated RTL shall conform to IEEE 1800-2012 SystemVerilog and synthesize without errors on major EDA toolchains.

---

## 2. Configuration and Exporter Parameters

- **BD-CFG-CPUIF**: The exporter shall support the following standard CPU interface targets:
  - `apb3`: AMBA APB v3 using SystemVerilog interface (`apb3_intf.sv`).
  - `apb3-flat`: AMBA APB v3 flattened into discrete scalar/vector ports.
  - `apb4`: AMBA APB v4 using SystemVerilog interface (`apb4_intf.sv`).
  - `apb4-flat`: AMBA APB v4 flattened into discrete scalar/vector ports.
  - `axi4-lite`: AMBA AXI4-Lite using SystemVerilog interface (`axi4lite_intf.sv`).
  - `axi4-lite-flat`: AMBA AXI4-Lite flattened into discrete scalar/vector ports.
  - `ahb-lite`: single-manager AMBA AHB-Lite using `ahblite_intf.sv`.
  - `ahb-lite-flat`: the same AHB-Lite profile with discrete ports.
  - Plugin interfaces registered via entry points under `peakrdl_busdecoder.cpuif`.
- **BD-CFG-DEFAULT-CPUIF**: If unspecified, the CPU interface shall default to `apb4`.
- **BD-CFG-PYTHON**: The package requires Python 3.11 or newer.
- **BD-CFG-AXIL-DEPTH**: `axi4lite_max_outstanding` / `--axi4lite-max-outstanding`
  sets the fixed capacity of each independent AXI4-Lite order queue. Default 4;
  minimum 1. Partial AW and W beats have separate one-entry holding registers.
- **BD-CFG-DATA-WIDTH**:
  - Unless explicitly selected, the CPU interface data bus width $W_{\text{data}}$ shall be inferred as the maximum `accesswidth` of any register reachable within the internal scope of the exported addrmap.
  - `data_width` / `--data-width` may explicitly select a power-of-two width of at least 8 bits, no smaller than the inferred internal register accesswidth.
  - If no internal register accesswidth is available and no explicit width was selected (e.g. only external blocks), $W_{\text{data}}$ shall default to 32 bits and emit a warning that names the consequence for all decoder data ports and the `--data-width` remedy. An explicit selection shall suppress this warning.
  - All master interfaces shall have data width equal to $W_{\text{data}}$.
- **BD-CFG-ADDR-WIDTH**:
  - The minimum address width $W_{\text{addr,min}}$ shall satisfy:
    $$W_{\text{addr,min}} = \max\left( \lceil\log_2(\text{size}(c_{\text{top}}))\rceil,\; \lceil\log_2(W_{\text{data}} / 8)\rceil + 1 \right)$$
  - The user may override $W_{\text{addr}} \ge W_{\text{addr,min}}$. If the user specifies $W_{\text{addr}} < W_{\text{addr,min}}$, export shall abort with a fatal error.
- **BD-CFG-INTERFACE-WIDTH-CHECKS**: Non-synthesis SV-interface width assertions
  shall terminate simulation with `$fatal(1, ...)`, naming the endpoint signals,
  actual widths, and requirements. APB/AXI ingress addresses may exceed the
  minimum decoder address width; AHB endpoint addresses must exactly match their
  configured widths. Checked data widths must exactly match $W_{\text{data}}$.
- **BD-CFG-MAX-DEPTH**:
  - `max_decode_depth = 0`: Descend without a depth cap, stopping at addressable
    leaves (including registers and external memories) or opaque early boundaries.
  - `max_decode_depth = 1` (default): The decoder shall decode only immediate children of the top-level addrmap.
  - `max_decode_depth = N` ($N > 1$): The decoder shall decode children positioned at depth $N$ in the instance tree.
  - Addressable leaves occurring at depth $< N$ are preserved. Containers whose
    addressable children are all external are opaque early boundaries, except
    that a register itself remains a register boundary.
- **BD-CFG-UNROLL**:
  - When `cpuif_unroll = false` (default), arrayed children shall be exported as SystemVerilog interface arrays (`[dim0][dim1]...` or `[N]`) and iterated procedurally with `for` loops.
  - When `cpuif_unroll = true`, arrayed children shall be expanded into distinct scalar master interfaces with index suffixes `_<idx0>_<idx1>`.
- **BD-CFG-PARAMETRIZE**:
  - When `--parametrize` is asserted, root-level RDL parameters that control array dimensions shall be extracted and emitted as SystemVerilog module parameters.
  - The module parameter default value shall be the elaborated maximum.
  - Package constant `<MODULE>_MAX_<PARAM>` shall be defined.
  - Runtime range assertion `assert (PARAM >= 0 && PARAM <= MAX)` shall be emitted.

---

## 3. Child Interface Target Set ($\mathcal{T}$)

Let $c_{\text{top}}$ be the exported addrmap. Traverse its addressable children
starting at depth 1, stopping at the first boundary in each subtree. A node is
a boundary when any of these conditions holds:

1. `max_decode_depth = N > 0` and the node has reached depth $N$.
2. The node has no addressable children, including register and external-memory leaves.
3. The node is a non-register container with at least one addressable child and
   every such child is external (an opaque early boundary).

With `max_decode_depth = 0`, only conditions 2 and 3 apply. Port collection and
every RTL listener use this same boundary predicate. The resulting targets
$\mathcal{T}$ form mutually disjoint subtrees, excluding the exported root.

Each target $t \in \mathcal{T}$ defines:
- A local address span within $c_{\text{top}}$:
  - If scalar: $S(t) = [\text{rel\_offset}(t),\; \text{rel\_offset}(t) + \text{size}(t))$.
  - If arrayed: for element $\vec{j}$, $S(t, \vec{j}) = [\text{elem\_rel\_offset}(t, \vec{j}),\; \text{elem\_rel\_offset}(t, \vec{j}) + \text{size}(t))$.
  - Element indices include every rolled ancestor dimension in outer-to-inner
    order. Concrete unrolled ancestor indices contribute to the target base.
- A master port on the generated decoder.
- Master address width $W_{\text{addr}}(t) = \max(\lceil\log_2(\text{size}(t))\rceil, 1)$.

---

## 4. Address Decoding Formal Model

Let $A \in [0, 2^{W_{\text{addr}}} - 1]$ be the incoming transaction byte address, and $D \in \{\text{READ}, \text{WRITE}\}$ the transaction flavor.

### 4.1 Target Match Predicate
For target $t \in \mathcal{T}$ and element index tuple $\vec{j}$:

$$\text{match}(t, \vec{j}, A) \iff A \ge \text{elem\_rel\_offset}(t, \vec{j}) \;\land\; A < \text{elem\_rel\_offset}(t, \vec{j}) + \text{size}(t)$$

$$\text{match}(t, A) \iff \exists \vec{j} \in \prod_{m=0}^{k-1} [0, d_m-1] : \text{match}(t, \vec{j}, A)$$

### 4.2 Select Signal Requirements
Let $\text{sel}_{D}(t, \vec{j}) \in \{0, 1\}$ denote the select signal asserted by the decoder for flavor $D$, and $\text{err}_{D} \in \{0, 1\}$ the unmapped error signal.

- **BD-DEC-SOUNDNESS (No Spurious Select):**
  $$\text{sel}_{D}(t, \vec{j}) = 1 \implies \text{match}(t, \vec{j}, A)$$
- **BD-DEC-EXCLUSIVITY (At Most One Select):**
  $$\sum_{t \in \mathcal{T}} \sum_{\vec{j}} \text{sel}_{D}(t, \vec{j}) \le 1$$
  *(If legal RO/WO overlap exists at address $A$, the read decoder selects the readable register and the write decoder selects the writable register independently).*
- **BD-DEC-COMPLETENESS (Mapped Hit):**
  For an active request of direction $D$, each select is asserted exactly when its element matches and permits that direction:
  $$\text{sel}_{D}(t,\vec{j}) = \text{match}(t,\vec{j},A) \land \text{permits}(t,D).$$
  For register targets, `permits(READ)` is `has_sw_readable` and `permits(WRITE)` is `has_sw_writable`, considering present fields. Blocks are routed as opaque regions in both directions; the downstream block enforces its own permissions.
- **BD-DEC-UNMAPPED-ERROR (Error on Miss):**
  For an active request, including an access with no direction-permitted register:
  $$\text{err}_{D} = \neg\bigvee_{t,\vec{j}}\text{sel}_{D}(t,\vec{j}).$$
  This default-miss invariant also applies inside nested arrays and to parameter-disabled elements. When idle, both selects and error remain zero.
- **BD-DEC-IDLE:**
  When no transaction of flavor $D$ is requested, all select and error signals for flavor $D$ shall be 0:
  $$\neg \text{req}_D \implies \forall t, \vec{j}: \text{sel}_{D}(t, \vec{j}) = 0 \;\land\; \text{err}_{D} = 0$$
- **BD-DEC-GAP-ERROR:**
  For any address $A$ that falls within an array's total span $[\text{raw\_offset}(t), \text{raw\_offset}(t) + \text{total\_size}(t))$ but does not satisfy $\text{match}(t, \vec{j}, A)$ for any element $\vec{j}$ (an array stride gap), the decoder shall assert $\text{err}_D = 1$ and all selects 0.

### 4.3 Master Address Forwarding
For selected target $t$ and element index $\vec{j}$:
- **BD-FWD-ADDR-LOCAL**: The master address driven to child $t$ shall be the byte offset relative to element $(t, \vec{j})$:
  $$A_{\text{master}}(t) = A - \text{elem\_rel\_offset}(t, \vec{j})$$
- **BD-FWD-ADDR-TRUNC**: If $\text{size}(t) = 2^p$ and $\text{elem\_rel\_offset}(t, \vec{j}) \equiv 0 \pmod{2^p}$ for all $\vec{j}$, the decoder may implement $A_{\text{master}}(t)$ as bit-truncation:
  $$A_{\text{master}}(t) = A[p-1:0]$$
  Otherwise, subtractive arithmetic must be emitted.

---

## 5. Protocol Handshake and Invariant Specifications

### 5.1 Internal CPUIF Decode and Response Contract
All protocol adapters use common direction-specific decode signals:
- Request: `cpuif_req`, `cpuif_wr_en`, `cpuif_rd_en`, `cpuif_wr_addr`,
  `cpuif_rd_addr`, `cpuif_wr_data`, `cpuif_wr_byte_en`.
- Response: `cpuif_wr_ack`, `cpuif_wr_err`, `cpuif_rd_ack`, `cpuif_rd_err`,
  `cpuif_rd_data`.

- **BD-PROTO-DIRECTION-INDEPENDENCE**: `cpuif_req && cpuif_wr_en` qualifies
  write decoding and `cpuif_req && cpuif_rd_en` qualifies read decoding. Both
  may be true in one cycle. There is no global single-flight or exclusive-
  direction requirement.
- **BD-PROTO-DESTINATION-LIFETIME**: APB uses live request payload with `none`
  and `out`, and retains the SETUP payload with `in` and `both`; every buffered
  mode tracks transaction ownership through upstream completion.
  AXI4-Lite latches destination/payload on queue insertion. AHB-Lite previews a
  live address phase and retains its destination/direction only on an
  `HREADY`-high acceptance edge. An outstanding response must not be retargeted
  by a later live address.
- **BD-PROTO-RESPONSE-QUALIFICATION**: Acknowledgment signals represent response
  availability, not universal one-cycle pulses. External protocol handshakes
  determine completion and retained-state advancement. Read data and error are
  sampled on that protocol's completion. AHB's first ERROR cycle may assert
  error before acknowledgment/ready.
- **BD-PROTO-LAYOUT**: Read and write decode share one exported SystemRDL tree.
  Standalone custom read/write layouts are not implemented.

---

### 5.2 APB3 and APB4 Adapter Semantics

Let $P$ be the slave APB interface ($s\_apb$) and $M_t$ the master APB interface for target $t$.

#### Default Combinational Operation

The request, forwarding, and response rules immediately below describe
`apb_buffer='none'` (the default). This path is combinational and unchanged by
the buffered-mode reset contract. The transaction-aware modes described
afterward interpose request and/or response state; the live-interface equations
must not be applied unconditionally to them.

##### Request Phase Mapping
- `cpuif_req = s_apb.PSEL`
- `cpuif_wr_en = s_apb.PSEL & s_apb.PWRITE`
- `cpuif_rd_en = s_apb.PSEL & ~s_apb.PWRITE`
- `cpuif_wr_addr = s_apb.PADDR`
- `cpuif_rd_addr = s_apb.PADDR`
- `cpuif_wr_data = s_apb.PWDATA`
- APB4: `cpuif_wr_byte_en = s_apb.PSTRB`

##### Master Forwarding Rules
- **BD-APB-SEL-GATE**: For each target $t$:
  $$M_t.\text{PSEL} = \text{sel}_{\text{wr}}(t) \lor \text{sel}_{\text{rd}}(t)$$
- **BD-APB-ENABLE-GATE**:
  $$M_t.\text{PENABLE} = (\text{sel}_{\text{wr}}(t) \lor \text{sel}_{\text{rd}}(t)) \land s\_apb.\text{PENABLE}$$
  *(Crucial bugfix from v0.7.0b3/v0.7.1: unselected master PENABLE must be forced low to prevent spurious downstream state transitions).*
- **BD-APB-BROADCAST**:
  $M_t.\text{PWRITE} = s\_apb.\text{PWRITE}$, $M_t.\text{PWDATA} = s\_apb.\text{PWDATA}$, $M_t.\text{PPROT} = s\_apb.\text{PPROT}$, $M_t.\text{PSTRB} = s\_apb.\text{PSTRB}$.
- **BD-APB-PAYLOAD-GATE**: The broadcast equations above assume
  `gate_signals=false` (the default). With `gate_signals=true`, unselected
  children receive zero `PADDR`, `PWDATA`, `PSTRB`, and `PPROT`. `PWRITE` is
  unaffected, and `PENABLE` remains select-gated regardless of this option.

##### Response and Error Timing
- **BD-APB-MAPPED-RESP**: When $\text{sel}(t) = 1$:
  $$s\_apb.\text{PREADY} = M_t.\text{PREADY}$$
  $$s\_apb.\text{PSLVERR} = M_t.\text{PSLVERR}$$
  $$s\_apb.\text{PRDATA} = M_t.\text{PRDATA} \quad (\text{if read})$$
  Child `PREADY` may be high during SETUP; mapped responses are not
  universally ACCESS-gated in the default combinational mode.
- **BD-APB-UNMAPPED-RESP**: When $\text{err}_{\text{wr}} = 1 \lor \text{err}_{\text{rd}} = 1$:
  - Setup cycle ($s\_apb.\text{PSEL} = 1 \land s\_apb.\text{PENABLE} = 0$):
    $$s\_apb.\text{PREADY} = 0, \quad s\_apb.\text{PSLVERR} = 0$$
  - Access cycle ($s\_apb.\text{PSEL} = 1 \land s\_apb.\text{PENABLE} = 1$):
    $$s\_apb.\text{PREADY} = 1, \quad s\_apb.\text{PSLVERR} = 1$$
  - This guarantees a standard 2-cycle unmapped APB error termination without hanging the bus.


#### Transaction-Aware Buffered Operation

- **BD-APB-BUFFER-MODES**: `apb_buffer` / `--apb-buffer` accepts `none`
  (default), `in`, `out`, and `both`. Non-`none` settings apply only to APB and
  require `clk_src='design'`; the buffers use design `clk` and active-high
  asynchronous `rst`. Clock distribution and payload gating are unchanged.
- **BD-APB-BUFFER-OWNERSHIP**: Every buffered mode tracks one transaction from
  upstream SETUP through upstream completion. No multiple outstanding
  transactions are allowed. A selected child completes exactly once; continued
  upstream ACCESS while a response is retained must not replay the child.
- **BD-APB-BUFFER-IN**: `in` captures `PWRITE`, `PADDR`, `PWDATA`, and APB4
  `PSTRB`/`PPROT` at the rising edge ending upstream SETUP
  (`PSEL && !PENABLE`). It holds this payload, drives one downstream SETUP
  followed by ACCESS, and preserves the combinational response path during
  downstream ACCESS. Child and upstream completion occur on the same edge.
- **BD-APB-BUFFER-OUT**: `out` uses live upstream payload, which the APB master
  must hold through completion, and forwards upstream SETUP/ACCESS to the child.
  On child completion it captures read data, error, and ready status, immediately
  removes downstream `PSEL`/`PENABLE`, and holds the registered response until
  upstream `PSEL && PENABLE && PREADY` acceptance.
- **BD-APB-BUFFER-BOTH**: `both` combines the retained request and registered
  response stages, including downstream retirement at child completion.
- **BD-APB-BUFFER-TIMING**: For a child with no wait states:

  | Mode | Upstream ACCESS cycles through completion | Minimum upstream completion spacing |
  |---|---:|---:|
  | `none` | 1 | 2 |
  | `in` | 2 | 3 |
  | `out` | 2 | 3 |
  | `both` | 3 | 4 |

  Spacing includes the mandatory SETUP between back-to-back transfers, including
  transfers with continuously asserted upstream `PSEL`. Each child wait cycle
  adds one cycle to both measures. Local unmapped errors pass through the same
  buffering stages around the ACCESS-phase error response; the default
  two-cycle error timing above is not a buffered-mode latency claim.
- **BD-APB-BUFFER-RESET**: Reset clears retained request and response state,
  suppresses downstream requests and upstream ready, and aborts a pending
  transfer. Downstream side effects already completed cannot be undone.
  Upstream must restart with a fresh SETUP after reset; stale ACCESS held across
  reset must not be replayed. These requirements apply only to buffered modes.

---

### 5.3 AXI4-Lite Adapter Semantics

This profile is **AXI4-Lite**, not full AXI4: it has single-beat transfers and
no transaction IDs, bursts, exclusives, or cross-ID reordering.

- **BD-AXIL-INDEPENDENT-WRITE**: Upstream AW and W are accepted independently
  on their own VALID/READY handshakes, in either order. Each has one holding
  register. A lone AW or W is legal and must not create an error response.
  Beats are paired in channel acceptance order; a write enters its direction's
  order queue when both retained beats of the next pair are enqueued.
- **BD-AXIL-READ-ACCEPT**: A read enters the read queue on `ARVALID && ARREADY`.
  Reads and paired writes can enter their queues in the same cycle.
- **BD-AXIL-RETAIN**: Each queue entry retains its decoded destination or local
  error marker and the request payload. Changing live addresses after
  acceptance cannot redirect the entry.
- **BD-AXIL-DISPATCH**: Requests dispatch FIFO within each direction. Child AW
  and W handshakes are independent; VALID and payload on AW, W, and AR remain
  stable until that channel handshakes. Several fully dispatched transactions
  may await responses concurrently.
- **BD-AXIL-ORDER**: Read responses appear in AR acceptance order. Write
  responses appear in completed-pair queue order. A later response is not
  presented until every older same-direction response has handshaken upstream.
  Reads and writes have no ordering relationship.
- **BD-AXIL-BACKPRESSURE**: Full queues deassert the corresponding upstream
  request READY. An occupied AW/W holding register also deasserts its channel's
  READY. Only the response-head child receives RREADY or BREADY, following the
  upstream READY. Response VALID and payload remain stable while upstream READY
  is low; children are required to obey that same AXI stability rule.
- **BD-AXIL-ERROR**: Unmapped, direction-denied, array-hole, disabled-element,
  and unrepresentable high-address requests return local DECERR (`2'b11`) in
  their normal FIFO position, with zero local-error read data and no child
  request. Child RRESP and BRESP pass through unchanged, including SLVERR.
- **BD-AXIL-RESET**: Reset clears partial AW/W captures and both queues and
  removes response VALID. Connected children must reset consistently so
  abandoned pre-reset responses cannot be consumed as new transactions.
- **BD-AXIL-WIDTH**: Standard data widths are 32 and 64 bits. Other selected
  widths are generator extensions requiring endpoint agreement, not a claim
  of AXI4-Lite compliance.

The detailed ordering/queue design is in
`docs/cpuif/axi4lite_response_ordering.rst`.

### 5.4 AHB-Lite Adapter Semantics

- **BD-AHB-SCOPE**: One manager and one shared address/data pipeline; no
  multi-manager arbitration, SPLIT/RETRY, AHB5 extensions, width conversion,
  or burst-address generation. Every active NONSEQ/SEQ beat is routed
  independently. See the detailed profile in `spec/ahb-lite.md`.
- **BD-AHB-ACCEPT**: Accept address/control only on rising HCLK when HRESETn,
  HREADY, HSEL, and HTRANS[1] are high. Retain the decoded destination or local
  error marker and direction for the following data phase.
- **BD-AHB-HOLD**: While HREADY is low, do not accept a new address or change
  the retained destination/direction. Live next-address HSEL is combinational
  and must not select the previous data response. With HREADY high, completion
  and a new address may share an edge. IDLE/BUSY clears valid state only on a
  ready edge and never discards a stalled transaction.
- **BD-AHB-DATA**: Forward live HWDATA for the preceding accepted write. The
  manager holds it during stalls; do not capture it with the address.
  Address/control signals, including HBURST and HMASTLOCK, are forwarded in
  the address phase. Each child address is the incoming byte address minus
  that child's top-relative element base.
- **BD-AHB-RESPONSE**: Only the retained child supplies HRDATA/HREADYOUT/HRESP.
  Child waits and legal two-cycle ERROR responses pass through unchanged.
  Idle/reset returns ready/OKAY/zero data.
- **BD-AHB-ERROR**: An accepted address with no permitted target produces
  exactly two local ERROR cycles: HREADYOUT/HRESP = 0/1, then 1/1, with zero
  read data and no child HSEL for the denied address. The error phase advances
  across its forced first wait even when HREADY is low. Recovery accepts a
  new address only on HREADY high.
- **BD-AHB-RESET**: Canonical ingress HRESETn asynchronously clears retained
  data-phase and error state; downstream HSEL is zero during reset. All
  endpoints share the same externally connected HCLK/HRESETn domain.
- **BD-AHB-APERTURE**: Target bases and sizes must be multiples of 1 KiB,
  sizes at least 1 KiB, and every ancestor/target array stride a multiple of
  1 KiB. The ingress width must represent every element endpoint. Unsupported
  maps are diagnosed rather than widened.
- **BD-AHB-WIDTH**: All endpoints share a data width in
  `{32,64,128,256,512,1024}`. Legal HSIZE, address alignment, traffic stability,
  burst boundaries, and legal child ERROR timing are protocol assumptions,
  not implemented firewall checks.

---

## 6. Naming and Structural Contracts

- **BD-NAME-KW-FILTER**: Any identifier matching a SystemVerilog keyword shall be appended with an underscore `_`.
- **BD-NAME-PACKAGE**:
  - The generated package shall be named `<package_name>.sv`.
  - Constants emitted:
    - `<MODULE>_DATA_WIDTH`
    - `<MODULE>_MIN_ADDR_WIDTH`
    - `<MODULE>_SIZE`
    - `<MODULE>_<TARGET>_ADDR_WIDTH` for every target.
    - `<MODULE>_MAX_<PARAM>` for extracted RDL parameters.
- **BD-NAME-PORTS**:
  - Slave prefixes are `s_apb_`, `s_axil_`, or `s_ahb_` for flat ports.
  - Master prefixes are `m_apb_<target>_`, `m_axil_<target>_`, or
    `m_ahb_<target>_`; interface ports omit the final signal separator.
  - One shared target-name allocator preserves unique local names after
    case folding, disambiguates conflicts with flattened relative paths and
    deterministic suffixes, and reserves generated package names.
  - Rolled port dimensions include all target/ancestor dimensions. Unrolled
    suffixes include all concrete target/ancestor indices. Package constants
    are emitted once per target identity.
- **BD-STRUCT-SEL**:
  - The select typedef `cpuif_sel_t` shall reflect the hierarchy down to each target.
  - An explicit `logic cpuif_err;` field shall be included at the root level of `cpuif_sel_t`.
  - Nested typedef names are collision-free under case folding and path
    flattening while preserving hierarchical selector member paths.
