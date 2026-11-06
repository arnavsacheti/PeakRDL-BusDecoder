# Implementation vs. Specification Audit

This audit evaluates the actual Python codebase (`src/peakrdl_busdecoder/**`) and generated SystemVerilog templates against the formal specification (`spec/busdecoder.md`, `spec/systemrdl.md`, `spec/peakrdl.md`) and the project documentation.

Every finding is assigned an ID (`IMPL-FINDING-*`), categorized by severity (**Critical** = functional bug / bus deadlock, **Major** = spec violation, **Minor** = non-fatal inconsistency, **Deadweight** = dead/obsolete code).

The detailed findings preserve pre-fix evidence and historical line numbers.
The recorded 0.7.3 follow-up implements findings 01–05; its verification receipt
below is historical, not a verification receipt for 0.8.0. The released 0.8.0
contract is `spec/busdecoder.md`; ordered AXI4-Lite and AHB-Lite supersede the old
coupled-write/no-DECERR assumptions. Current implementation and test-coverage
descriptions below do not assert release verification results.

Historical 0.7.3 verification receipt: `PYTHONPATH=src uv run pytest tests -q`
recorded **306 passed, 1 skipped**, including cocotb and standalone Verilator
regressions; `uv run ruff check src/peakrdl_busdecoder tests/formal` passed.
This was finite-design conformance testing, not an unbounded proof of every
SystemRDL design or AXI temporal behavior.

---

## 1. Compliance Summary Table

| Spec ID | Impl Location | Status | Implementation and Coverage |
| :--- | :--- | :--- | :--- |
| **BD-DEC-GAP-ERROR** | `module_tmpl.sv`, `decode_logic_gen.py` | **IMPLEMENTED** | Active requests default to error; both scalar and array-element hits clear error. Idle stays zero. Oracle sweeps cover every address in the sparse-array fixture. |
| **BD-CFG-MAX-DEPTH** | `design_state.py:is_decode_boundary`, `listener.py:should_skip_node` | **IMPLEMENTED IN 0.8.0** | One shared boundary helper covers depth caps, shallow leaves, and opaque all-external-child containers. The released contract preserves shallow-leaf support. |
| **BD-NAME-PORTS** | `design_state.py:get_target_name`, `cpuif/interface.py`, `package_tmpl.sv` | **IMPLEMENTED IN 0.8.0** | Shared target identifiers preserve unique local names and disambiguate collisions using relative paths plus deterministic suffixes, including uppercase and flattened-path collisions. Historical behavioral compile/runtime regressions recorded passes across the six then-covered protocol/style combinations; this is not a 0.8.0 verification receipt. |
| **BD-ARCH-LOCAL-ADDR** | `decode_logic_gen.py`, `cpuif/base_cpuif.py`, protocol fanout generators | **IMPLEMENTED** | Bounds, subtraction and truncation decisions use offsets relative to the exported top; a nonzero-base exported submap exercises non-power-of-two targets. |
| **BD-DEC-EXCLUSIVITY** | `decode_logic_gen.py:_access_predicate` | **IMPLEMENTED** | Register selects are direction-filtered for scalar and array targets. Both declaration orders of overlapping RO/WO registers are exercised; denied directions return a local error. |
| **BD-CFG-DATA-WIDTH** | `design_scanner.py` | **SCOPED CONTRACT** | Inference intentionally stops at external boundaries, matching BD-CFG-DATA-WIDTH's internal-scope rule. A deeper opaque block's width is not inferred; this is not a general width-conversion implementation. |
| **BD-AXIL-ERROR** | `cpuif/axi4lite/axi4_lite_tmpl.sv`, `axi4_lite_cpuif.py` | **IMPLEMENTED IN 0.8.0** | Local misses queue DECERR; child responses pass through unchanged. Historical BD-AXIL-NO-DECERR is retired. |
| **BD-APB-ENABLE-GATE** | `cpuif/apb/apb_cpuif.py` | **IMPLEMENTED IN 0.8.0** | Shared APB3/APB4 fanout retains the AND of master PENABLE with target select. |
| **Field buffering checks** | `validate_design.py`, `docs/limitations.rst` | **REMOVED** | Field atomicity belongs to the downstream block. The RTL sweep exports a writable/onread 64-bit field with 32-bit accesswidth without buffering UDPs. |

---

## 2. Historical Detailed Findings and Resolutions

### IMPL-FINDING-01: Array Stride Gap Causes Bus Deadlock (CRITICAL)
- **Files:** `src/peakrdl_busdecoder/decode_logic_gen.py:112-159`, `src/peakrdl_busdecoder/module_tmpl.sv:65-90`
- **Specification:** `BD-DEC-GAP-ERROR`
- **Evidence:**
  In `tests/cocotb_lib/rdl/array_only.rdl`:
  ```systemrdl
  dummy_regs dummy_regs[4] @0x00 += 0x80; // size = 4, stride = 0x80
  ```
  The generated SystemVerilog decode logic in `module_tmpl.sv` is:
  ```systemverilog
  always_comb begin
      cpuif_wr_sel = '{default: '0};
      if (cpuif_req && cpuif_wr_en) begin
          for (int i0 = 0; i0 < 4; i0++) begin
              if ((cpuif_wr_addr >= 9'(9'h0+(i0*9'h80))) && (cpuif_wr_addr < 9'(9'h4+(i0*9'h80)))) begin
                  cpuif_wr_sel.dummy_regs[i0] = 1'b1;
              end
          end
      end
  end
  ```
- **Consequence:**
  If an access is made to address `0x10` (inside the stride gap $[0x04, 0x80)$):
  1. The `if (cpuif_wr_addr >= ...)` condition inside the loop evaluates to `0` for all $i_0 \in [0, 3]$.
  2. All select signals remain `0`.
  3. `cpuif_wr_sel.cpuif_err` remains `0` (the unmapped fallback `else` branch is outside the loop or omitted).
  4. On APB, `PREADY` is generated as `cpuif_wr_ack | cpuif_rd_ack`. Because neither a child nor the unmapped error handler is selected, `PREADY` stays `0` indefinitely.
  5. **The bus hangs permanently.**
- **Required Fix:**
  Add a reduction check across array element hits: if the address falls within the overall array bounds $[0, 4 \times 0x80)$ but matches no element, explicitly assert `cpuif_<flavor>_sel.cpuif_err = 1'b1;`.

---

### IMPL-FINDING-02: Non-Relative Address Decode on Sub-Addrmap Exports (MAJOR)
- **Files:** `src/peakrdl_busdecoder/decode_logic_gen.py:45-48`
- **Specification:** `BD-ARCH-LOCAL-ADDR`
- **Evidence:**
  ```python
  l_bound = SVInt(
      node.raw_absolute_address,
      addr_width,
  )
  ```
  `node.raw_absolute_address` returns the byte offset from the *root of the compilation unit*, not the root of the exported addrmap.
- **Consequence:**
  If a user passes an inner sub-addrmap to `BusDecoderExporter.export(sub_node, ...)` via the Python API, where `sub_node` is at offset `0x1000` in the parent chip map:
  - The generated decoder will expect incoming addresses to start at `0x1000`.
  - But `BD-ARCH-LOCAL-ADDR` and `docs/cpuif/introduction.rst:19-22` state:
    > *"The busdecoder exporter will always generate its address decoding logic using local address offsets."*
  - The generated decoder will reject all valid local accesses in $[0, \text{size}(\text{sub\_node}))$.
- **Required Fix:**
  Replace `node.raw_absolute_address` with the relative offset from `self._ds.top_node`:
  ```python
  rel_addr = node.raw_absolute_address - self._ds.top_node.raw_absolute_address
  l_bound = SVInt(rel_addr, addr_width)
  ```

---

### IMPL-FINDING-03: Port Name Collisions at Deep Hierarchies (IMPLEMENTED IN 0.8.0)
- **Files:** `src/peakrdl_busdecoder/design_state.py`, `src/peakrdl_busdecoder/cpuif/interface.py`, `src/peakrdl_busdecoder/cpuif/base_cpuif.py`, `src/peakrdl_busdecoder/cpuif/fanin_intermediate_gen.py`, the APB3/APB4/AXI4-Lite CPU adapters, and `src/peakrdl_busdecoder/package_tmpl.sv`
- **Specification:** `BD-NAME-PORTS`, `BD-NAME-PACKAGE`
- **Original defect:** At decode depth 2, `blk_a.ctrl` and `blk_b.ctrl` both emitted `m_apb_ctrl`. The same local-name-only construction also collided in flat ports, package address-width constants, array-count localparams, and interface-array response intermediates.
- **Implemented resolution:**
  - `DesignState` allocates a shared target identifier before rendering either package or module. Identity is the path relative to the exported top, independent of array indices and Python node wrappers.
  - Unique local names are preserved. Uniqueness is checked after uppercase conversion so package constants and array-count localparams remain distinct as well.
  - Conflicting local names use the flattened full relative path: `blk_a_ctrl` and `blk_b_ctrl`. Unique legacy names are reserved before allocating qualified names.
  - Flattened-path or uppercase collisions receive deterministic `__2`, `__3`, ... suffixes in sorted relative-path order.
  - All APB3/APB4/AXI4-Lite flat/interface declarations and references, fanout width references, fanin intermediates, package constants, and array-count localparams use that identifier. Package constants are emitted once per rolled target identity.
  - Hierarchical select-structure member paths remain unchanged.
  - Port collection and RTL listeners share `DesignState.is_decode_boundary`; depth-zero external memory leaves therefore receive both declarations and resolved names rather than a dictionary fallback.
- **Regression coverage:** `tests/formal/test_target_naming.py` compiles and runs generated RTL for duplicate `ctrl` targets under two blocks at depth 2, scalar and rolled-array targets, all three protocols, and both flat and interface ports. It also exercises uppercase and flattened-path collisions, preservation of an existing unique name, and depth-zero external memory alongside internal register leaves. The tests use independently driven target responses and hardcoded public port/constant names, not generated-source string assertions.
- **Historical preparation note:** These regressions were added but not executed during fix 4. This records that development step, not the verification status of released 0.8.0. The regression coverage above describes test behavior, not a release execution receipt.

---

### IMPL-FINDING-04: Sub-Word Buffering Validations are Deadweight (DEADWEIGHT)
- **Files:** `src/peakrdl_busdecoder/validate_design.py:126-143`
- **Specification:** `BD-ARCH-PURE-ROUTER`
- **Evidence:**
  `DesignValidator` checks whether software-writable fields spanning multiple subwords have `rdl_write_buffering` UDPs, and whether on-read fields have `rdl_read_buffering`.
- **Consequence:**
  This check blocks valid SystemRDL designs from generating a bus decoder simply because they contain wide fields, even though a bus decoder never handles subword slicing (it merely forwards transfers to the downstream register block that owns the fields).
- **Required Fix:**
  Delete lines 126–143 of `validate_design.py`.

---

### IMPL-FINDING-05: Missing Independent Read/Write Decode for Overlapping Registers (MINOR)
- **Files:** `src/peakrdl_busdecoder/decode_logic_gen.py:94-131`
- **Specification:** `BD-DEC-EXCLUSIVITY`, SystemRDL Clause 10.1-h
- **Evidence:**
  SystemRDL 2.0 explicitly permits two registers to occupy the same address offset if one is read-only and the other is write-only.
  However, `DecodeLogicGenerator` treats read and write decoding identically (`enter_AddressableComponent` does not check `is_sw_readable` or `is_sw_writable`). It emits an `if ... else if ...` ladder based on tree order alone.
- **Consequence:**
  In a design with legal RO/WO overlapping registers, a read request will hit whichever register is visited first, even if that register is write-only!
- **Required Fix:**
  In `DecodeLogicGenerator.cpuif_addr_predicate()`, gate read decoding with `node.has_sw_readable` and write decoding with `node.has_sw_writable`.
