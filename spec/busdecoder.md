# PeakRDL-BusDecoder — Formal Specification

This specification defines the behavior, interface contracts, protocol invariants, and address-decoding mathematics of the **PeakRDL-BusDecoder** generator.

Every normative statement is assigned a unique identifier `BD-*`. Downstream audits and verification harnesses reference these identifiers directly.

---

## 1. Top-Level Architectural Contract

```
                     +---------------------------------------+
                     |         PeakRDL-BusDecoder            |
                     |                                       |
  Slave CPUIF        |  +-------------+   +---------------+  |   Master CPUIF 0
  (APB3/4, AXI4-L) ===> | Slave CPUIF |-->| Write Decoder |--===> (Child 0)
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
  - Plugin interfaces registered via entry points under `peakrdl_busdecoder.cpuif`.
- **BD-CFG-DEFAULT-CPUIF**: If unspecified, the CPU interface shall default to `apb4`.
- **BD-CFG-DATA-WIDTH**:
  - The CPU interface data bus width $W_{\text{data}}$ shall be inferred as the maximum `accesswidth` of any register reachable within the internal scope of the exported addrmap.
  - If no internal register exists (e.g. only external blocks), $W_{\text{data}}$ shall default to 32 bits and emit a warning.
  - All master interfaces shall have data width equal to $W_{\text{data}}$.
- **BD-CFG-ADDR-WIDTH**:
  - The minimum address width $W_{\text{addr,min}}$ shall satisfy:
    $$W_{\text{addr,min}} = \max\left( \lceil\log_2(\text{size}(c_{\text{top}}))\rceil,\; \lceil\log_2(W_{\text{data}} / 8)\rceil + 1 \right)$$
  - The user may override $W_{\text{addr}} \ge W_{\text{addr,min}}$. If the user specifies $W_{\text{addr}} < W_{\text{addr,min}}$, export shall abort with a fatal error.
- **BD-CFG-MAX-DEPTH**:
  - `max_decode_depth = 0`: The decoder shall descend to leaf registers ($\text{RegNode}$) across all nested blocks.
  - `max_decode_depth = 1` (default): The decoder shall decode only immediate children of the top-level addrmap.
  - `max_decode_depth = N` ($N > 1$): The decoder shall decode children positioned at depth $N$ in the instance tree.
  - Leaves occurring at depth $< N$ shall also be preserved as decode targets. *(Formal requirement; see Audit for current divergence).*
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

Let $c_{\text{top}}$ be the exported addrmap. A component instance $t$ belongs to the decode target set $\mathcal{T}$ if and only if:

1. $t \in \mathcal{A} \land t \ne c_{\text{top}}$.
2. $t$ is an ancestor of no other target $t' \in \mathcal{T}$ (targets are mutually disjoint subtrees).
3. Selection rule:
   - If $\text{max\_decode\_depth} = 0$: $t \in \text{RegNode} \lor (t \in \text{MemNode} \land \text{virtual\_regs}(t) = \emptyset) \lor (t.\text{external} \land \text{is\_leaf}(t))$.
   - If $\text{max\_decode\_depth} = N \ge 1$: $\text{depth}(t) = N \lor (\text{depth}(t) < N \land t \in \text{RegNode})$.

Each target $t \in \mathcal{T}$ defines:
- A local address span within $c_{\text{top}}$:
  - If scalar: $S(t) = [\text{rel\_offset}(t),\; \text{rel\_offset}(t) + \text{size}(t))$.
  - If arrayed: for element $\vec{j}$, $S(t, \vec{j}) = [\text{elem\_rel\_offset}(t, \vec{j}),\; \text{elem\_rel\_offset}(t, \vec{j}) + \text{size}(t))$.
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

### 5.1 Internal CPUIF Interface Protocol
All protocol adapters convert slave transactions into the internal CPUIF signals:
- Request: `cpuif_req`, `cpuif_wr_en`, `cpuif_rd_en`, `cpuif_wr_addr`, `cpuif_rd_addr`, `cpuif_wr_data`, `cpuif_wr_byte_en`.
- Response: `cpuif_wr_ack`, `cpuif_wr_err`, `cpuif_rd_ack`, `cpuif_rd_err`, `cpuif_rd_data`.

**Invariants:**
- **BD-PROTO-SINGLE-FLIGHT**: At most one transaction (read or write) shall be in flight through the internal CPUIF at any clock cycle:
  $$\text{cpuif\_req} \implies (\text{cpuif\_wr\_en} \oplus \text{cpuif\_rd\_en})$$
- **BD-PROTO-REQ-STABLE**: Once asserted, `cpuif_req`, `cpuif_wr_en`, `cpuif_rd_en`, addresses, and write data shall remain stable until the qualifying acknowledgment (`cpuif_wr_ack` or `cpuif_rd_ack`) is asserted.
- **BD-PROTO-ACK-STROBE**: Acknowledgments `cpuif_wr_ack` and `cpuif_rd_ack` shall be single-cycle pulses.
- **BD-PROTO-ACK-DATA**: Read data `cpuif_rd_data` and error flag `cpuif_rd_err` are valid and sampled on the cycle of `cpuif_rd_ack`.

---

### 5.2 APB3 and APB4 Adapter Semantics

Let $P$ be the slave APB interface ($s\_apb$) and $M_t$ the master APB interface for target $t$.

#### Request Phase Mapping
- `cpuif_req = s_apb.PSEL`
- `cpuif_wr_en = s_apb.PSEL & s_apb.PWRITE`
- `cpuif_rd_en = s_apb.PSEL & ~s_apb.PWRITE`
- `cpuif_wr_addr = s_apb.PADDR`
- `cpuif_rd_addr = s_apb.PADDR`
- `cpuif_wr_data = s_apb.PWDATA`
- APB4: `cpuif_wr_byte_en = s_apb.PSTRB`

#### Master Forwarding Rules
- **BD-APB-SEL-GATE**: For each target $t$:
  $$M_t.\text{PSEL} = \text{sel}_{\text{wr}}(t) \lor \text{sel}_{\text{rd}}(t)$$
- **BD-APB-ENABLE-GATE**:
  $$M_t.\text{PENABLE} = (\text{sel}_{\text{wr}}(t) \lor \text{sel}_{\text{rd}}(t)) \land s\_apb.\text{PENABLE}$$
  *(Crucial bugfix from v0.7.0b3/v0.7.1: unselected master PENABLE must be forced low to prevent spurious downstream state transitions).*
- **BD-APB-BROADCAST**:
  $M_t.\text{PWRITE} = s\_apb.\text{PWRITE}$, $M_t.\text{PWDATA} = s\_apb.\text{PWDATA}$, $M_t.\text{PPROT} = s\_apb.\text{PPROT}$, $M_t.\text{PSTRB} = s\_apb.\text{PSTRB}$.

#### Response and Error Timing
- **BD-APB-MAPPED-RESP**: When $\text{sel}(t) = 1$:
  $$s\_apb.\text{PREADY} = M_t.\text{PREADY}$$
  $$s\_apb.\text{PSLVERR} = M_t.\text{PSLVERR}$$
  $$s\_apb.\text{PRDATA} = M_t.\text{PRDATA} \quad (\text{if read})$$
- **BD-APB-UNMAPPED-RESP**: When $\text{err}_{\text{wr}} = 1 \lor \text{err}_{\text{rd}} = 1$:
  - Setup cycle ($s\_apb.\text{PSEL} = 1 \land s\_apb.\text{PENABLE} = 0$):
    $$s\_apb.\text{PREADY} = 0, \quad s\_apb.\text{PSLVERR} = 0$$
  - Access cycle ($s\_apb.\text{PSEL} = 1 \land s\_apb.\text{PENABLE} = 1$):
    $$s\_apb.\text{PREADY} = 1, \quad s\_apb.\text{PSLVERR} = 1$$
  - This guarantees a standard 2-cycle unmapped APB error termination without hanging the bus.

---

### 5.3 AXI4-Lite Adapter Semantics

Let $AXI$ be the slave AXI4-Lite interface.

- **BD-AXIL-COUPLED-WRITE**: The write channel adapter shall require `AWVALID` and `WVALID` to be asserted together:
  $$\text{axi\_wr\_valid} = \text{AWVALID} \land \text{WVALID}$$
  $$\text{AWREADY} = \text{axi\_wr\_valid}, \quad \text{WREADY} = \text{axi\_wr\_valid}$$
- **BD-AXIL-DECOUPLED-ERR**: If `AWVALID ^ WVALID` occurs, the adapter shall immediately terminate the invalid request with `BVALID = 1` and `BRESP = 2'b10` (`SLVERR`).
- **BD-AXIL-READ-CHANNEL**:
  $$\text{ARREADY} = \text{ARVALID}$$
  $$\text{RVALID} = \text{cpuif\_rd\_ack} \lor \text{cpuif\_rd\_sel.cpuif\_err}$$
  $$\text{RRESP} = (\text{cpuif\_rd\_err} \lor \text{cpuif\_rd\_sel.cpuif\_err}) \;?\; 2'b10 : 2'b00$$
- **BD-AXIL-WRITE-CHANNEL**:
  $$\text{BVALID} = \text{cpuif\_wr\_ack} \lor \text{cpuif\_wr\_sel.cpuif\_err} \lor \text{axi\_wr\_invalid}$$
  $$\text{BRESP} = (\text{cpuif\_wr\_err} \lor \text{cpuif\_wr\_sel.cpuif\_err} \lor \text{axi\_wr\_invalid}) \;?\; 2'b10 : 2'b00$$
- **BD-AXIL-NO-DECERR**: All error responses on AXI4-Lite shall be signaled as `SLVERR` (`2'b10`). `DECERR` (`2'b11`) is never emitted.

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
  - Slave ports: prefixed with `s_apb_` or `s_axil_`.
  - Master ports: prefixed with `m_apb_<target>_` or `m_axil_<target>_`.
  - Port disambiguation: when targets share names across hierarchies or nested arrays, port names must uniquely identify the target. *(Formal requirement; see Audit for collision risks).*
- **BD-STRUCT-SEL**:
  - The select typedef `cpuif_sel_t` shall reflect the hierarchy down to each target.
  - An explicit `logic cpuif_err;` field shall be included at the root level of `cpuif_sel_t`.
