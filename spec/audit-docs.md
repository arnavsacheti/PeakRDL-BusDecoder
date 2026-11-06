# Documentation vs. Formal Specification Audit

This audit evaluates the consistency and completeness of the documentation (`docs/**/*.rst`, `README.md`) against the formal specification (`spec/busdecoder.md`, `spec/systemrdl.md`, `spec/peakrdl.md`).

Every finding is assigned an ID (`DOC-FINDING-*`), categorized as **Compliant**, **Divergent** (doc contradicts formal spec), **Incomplete** (doc omits critical formal rule), or **Stale** (doc contains obsolete copy-paste).

## Follow-up status

The findings below retain the original audit evidence, not current source line numbers. The field-buffering restriction has been removed from `docs/limitations.rst` and the exporter; downstream blocks own field atomicity. The decoder's default-miss implementation now covers array stride gaps, preserving the documented unmapped-error contract rather than documenting the deadlock as supported behavior. Local submap addressing and direction-specific register routing are covered by the follow-up implementation and RTL conformance sweeps. The candidate status below supersedes the historical depth-policy finding; Avalon support remains unimplemented.

For the 0.8.0 candidate, `spec/busdecoder.md` is the current draft and
integration verification is pending. The old coupled-write/no-DECERR and
global-single-flight statements below are historical audit evidence, not the
current contract: AXI4-Lite accepts AW/W independently, uses separate ordered
read/write queues, and queues local DECERR; AHB-Lite has its own retained
address/data pipeline and two-cycle local errors. The candidate also preserves
shallow addressable leaves through the shared boundary helper. Avalon remains
an unimplemented adapter; its bundled interface is not a registered protocol.

---

## 1. Compliance Matrix

| Requirement | Doc Location | Documented Claim | Formal Spec | Status | Action Needed |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BD-ARCH-PURE-ROUTER** | `docs/index.rst:7-9` | *"strictly a bus-routing layer that decodes addresses and forwards requests to child blocks"* | BD-ARCH-PURE-ROUTER | **Compliant** | None. |
| **BD-ARCH-LOCAL-ADDR** | `docs/cpuif/introduction.rst:19-22` | *"The busdecoder exporter will always generate its address decoding logic using local address offsets."* | BD-ARCH-LOCAL-ADDR | **Compliant** | None. |
| **BD-CFG-CPUIF** | `docs/index.rst:21` | Lists `apb3`, `apb4`, `axi4-lite` + flat variants | BD-CFG-CPUIF | **Compliant** | None. |
| **BD-CFG-DATA-WIDTH** | `docs/cpuif/introduction.rst:10-13` | *"equal to the widest accesswidth encountered in the design. If the exported addrmap contains only external components... default to 32 bits"* | BD-CFG-DATA-WIDTH | **Incomplete** | Doc fails to note that only *internal* registers are scanned; child addrmaps (which are implicitly external) are ignored even if their inner registers have wider accesswidth. |
| **BD-CFG-MAX-DEPTH** | `docs/architecture.rst:19-24` | `0`: all levels; `1`: top-level children; `N`: depth $N$ | BD-CFG-MAX-DEPTH | **Incomplete** | Doc does not define whether leaves at depth $< N$ are preserved or dropped when $N > 1$. |
| **BD-DEC-UNMAPPED-ERROR** | `docs/architecture.rst:39-44`, `docs/cpuif/apb.rst:12-15` | Unmapped addresses complete with error response (PSLVERR / RRESP) | BD-DEC-UNMAPPED-ERROR | **Compliant** | None. |
| **BD-DEC-GAP-ERROR** | Not documented | — | BD-DEC-GAP-ERROR | **Divergent** | Docs imply all unmapped addresses error; neither docs nor RTL handle stride gaps in arrays. |
| **BD-AXIL-COUPLED-WRITE** | `docs/cpuif/axi4lite.rst:29-31` | *"AW and W channels must be asserted together for writes"* | BD-AXIL-COUPLED-WRITE | **Compliant** | None. |
| **BD-AXIL-NO-DECERR** | `docs/architecture.rst:44` | Mentions `RRESP/BRESP` | BD-AXIL-NO-DECERR | **Incomplete** | Doc omits that only `SLVERR` (`2'b10`) is returned, never `DECERR` (`2'b11`). |
| **Field Buffering** | `docs/limitations.rst:24-29` | Multi-word registers with fields spanning subwords must enable write/read buffering UDPs | N/A (regblock copy-paste) | **Stale / Erroneous** | BusDecoder does not synthesize fields or storage; read/write buffering UDPs are meaningless for a pure decoder. |
| **Avalon-MM** | `hdl-src/avalon_mm_intf.sv` | Interface file exists in repo | BD-CFG-CPUIF | **Omission** | Avalon-MM interface definition exists in source tree but is completely absent from docs and unreferenced by the exporter. |

---

## 2. Detailed Findings

### DOC-FINDING-01: Stale Limitations Carried Over from PeakRDL-regblock
- **Location:** `docs/limitations.rst:24-29`
- **Text:**
  > Software-writable fields that span across multiple software-accessible sub-words must have write double-buffering enabled.
  > Fields that have an onread side-effect and span across multiple software-accessible sub-words must have read double-buffering enabled.
- **Problem:** PeakRDL-BusDecoder is a bus routing layer (`BD-ARCH-PURE-ROUTER`). It does not generate registers, flip-flops, or field logic. Demanding write/read double-buffering UDPs on a bus decoder is a verbatim copy-paste error from `PeakRDL-regblock`.
- **Required Change:** Delete lines 24–29 of `docs/limitations.rst` and the corresponding check in `src/peakrdl_busdecoder/validate_design.py:126-143`.

### DOC-FINDING-02: Silent Failure Mode in Array Stride Gaps
- **Location:** `docs/cpuif/apb.rst:12-15`, `docs/architecture.rst:39-44`
- **Problem:** The documentation states:
  > An unmapped address completes with an error in the first access cycle. The decoder asserts PREADY and PSLVERR together only when PSEL and PENABLE are high...
  However, for an array with `stride > size`, an address falling in the gap matches the outer array bound in the generated `if` statement, but matches no loop body `if` branch. The decoder defaults all selects to 0 and asserts `cpuif_err = 0`. On APB, this leaves `PREADY = 0` forever, **hanging the bus** rather than returning `PSLVERR`.
- **Required Change:** Document the stride gap behavior and add a fallback error assignment in `decode_logic_gen.py`.

### DOC-FINDING-03: Ambiguous Depth Semantics for Mixed Hierarchies
- **Location:** `docs/architecture.rst:19-24`
- **Problem:** The documentation specifies:
  > - 0: Decode all the way down to leaf registers
  > - 1: Decode only top-level children
  > - N: Decode down to depth N from the top-level
  In a design where one branch terminates in a register at depth 1 while another branch contains sub-addrmaps down to depth 3, the behavior of `--max-decode-depth 2` on the shallow branch is unspecified in the documentation.
- **Required Change:** Clarify that decode targets are collected at depth $N$, or at the first leaf encountered along a branch if depth $< N$.

### DOC-FINDING-04: Undocumented Omission of Avalon-MM CPUIF
- **Location:** `docs/index.rst:21`, `hdl-src/avalon_mm_intf.sv`
- **Problem:** The repository ships an `avalon_mm_intf.sv` SystemVerilog interface file in `hdl-src/`, but neither `docs/index.rst` nor `src/peakrdl_busdecoder/cpuif/` implement an Avalon-MM adapter class. Users reading `hdl-src/` reasonably expect Avalon-MM support.
- **Required Change:** Either document Avalon-MM as a roadmap item / unimplemented interface template, or remove `avalon_mm_intf.sv` from the active source tree.
