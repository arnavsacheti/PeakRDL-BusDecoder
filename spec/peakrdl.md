# PeakRDL / systemrdl-compiler Elaboration Model — Formal Specification

This specification formalizes the object model, AST elaboration semantics, and exporter integration contract implemented by `systemrdl-compiler` (project dependency `~=1.30`) and the `peakrdl` CLI framework. It defines the interfaces through which an exporter consumes an elaborated register model.

Status: **released 0.8.0 reference**, requiring Python 3.11 or newer.
Protocol/state-machine requirements live in `busdecoder.md`; this reference
does not impose global single-flight routing or constitute a verification receipt.

---

## 1. Elaboration Pipeline

Let $\mathcal{S}$ denote the raw SystemRDL source text and $\mathcal{E}$ an elaboration environment (parameters, preprocessor defines). Compilation proceeds through four deterministic phases:

$$\mathcal{S} \xrightarrow{\text{Parse}} \text{CST} \xrightarrow{\text{Elaborate}} \text{Component AST} \xrightarrow{\text{Placement}} \text{Placed AST} \xrightarrow{\text{Validate}} \text{RootNode}$$

1. **Parse**: ANTLR-generated parser constructs a Concrete Syntax Tree.
2. **Elaborate** (`ComponentVisitor`, `elaborate.py`):
   - Instantiates parameterized definitions.
   - Binds property values and resolves user-defined properties (UDPs).
   - Coerces `external` attributes (Clause 12.2-f).
   - Prunes components with `ispresent = false`.
3. **Structural Placement** (`StructuralPlacementListener`):
   - Resolves bit positions of fields within registers (respecting `msb0`/`lsb0` ordering).
   - Resolves address offsets of children using the effective alignment $\max(A_{\text{prop}}, A_{\text{alloc}}, A_{\text{mode}})$.
   - Resolves implicit array strides to element `size`.
   - Sorts children ascending by address offset.
4. **Validation** (`validate.py`):
   - Enforces overlap disjointness (Section 5 of `spec/systemrdl.md`).
   - Verifies structural non-emptiness (addrmap, regfile, reg must contain children).
   - Emits fatal diagnostic if errors are observed.

The outcome is an immutable `RootNode` exposing the design tree.

---

## 2. Elaborated Node Object Model

### 2.1 Node Hierarchy
Every entity accessible to an exporter is an instance of `systemrdl.node.Node`:

$$\text{Node} \supset \text{AddressableNode} \supset \{\text{AddrmapNode}, \text{RegfileNode}, \text{MemNode}, \text{RegNode}\}$$
$$\text{Node} \supset \text{VectorNode} \supset \{\text{FieldNode}, \text{SignalNode}\}$$

### 2.2 Address and Size APIs

For any $n \in \text{AddressableNode}$:

| Property | Type | Mathematical Definition | Invariants |
| :--- | :--- | :--- | :--- |
| `raw_address_offset` | `int` | $\text{raw\_offset}(n)$ | Offset of first element relative to immediate parent; $\ge 0$. |
| `address_offset` | `int` | $\text{elem\_offset}(n, \vec{j})$ | Defined only when $n$ is unrolled or non-arrayed. Raises `ValueError` if $n$ is an unindexed array. |
| `raw_absolute_address`| `int` | $\sum_{a \in \text{anc}(n)} \text{raw\_offset}(a)$ | Byte offset from root addrmap excluding all ancestor array strides. |
| `absolute_address` | `int` | $\sum_{a \in \text{anc}(n)} \text{elem\_offset}(a, \vec{j}_a)$ | Byte offset from root addrmap including element index offsets. Defined only on fully-indexed nodes. |
| `size` | `int` | $\text{size}(n)$ | Byte size of a single element (see Section 2 of `spec/systemrdl.md`). |
| `total_size` | `int` | $\text{total\_size}(n)$ | $\text{stride}(n) \cdot \prod d_i$ if arrayed, else $\text{size}(n)$. |
| `array_dimensions` | `list[int] \| None` | $[d_0, \dots, d_{k-1}]$ | `None` if scalar. All $d_i \ge 1$. |
| `n_elements` | `int` | $\prod d_i$ | Total element count. 1 if scalar. |
| `array_stride` | `int \| None` | $\text{stride}(n)$ | Byte distance between successive elements; $\ge \text{size}(n)$. |
| `is_array` | `bool` | $k \ge 1$ | Shortcut for `array_dimensions is not None`. |
| `external` | `bool` | $\text{external}(n)$ | Inherited / coerced boolean flag. |

### 2.3 Group Node Size Formal Property
For $b \in \text{AddrmapNode} \cup \text{RegfileNode}$:
$$\text{size}(b) = \begin{cases}
0 & \text{if } b.\text{inst.children} = \emptyset \\
c_{\text{last}}.\text{raw\_address\_offset} + c_{\text{last}}.\text{total\_size} & \text{otherwise}
\end{cases}$$
where $c_{\text{last}} = b.\text{inst.children}[-1]$.

**Crucial Compiler Property:** Because children are sorted ascending by `addr_offset` during placement, this matches $\max_i (\text{offset}(c_i) + \text{total\_size}(c_i))$ whenever child spans are monotonic. In a bridge addrmap, offsets do not increase monotonically (all are zero), so $c_{\text{last}}$ may not represent the true maximum span.

---

## 3. Tree Traversal Semantics

### 3.1 Node Iteration Modes
`systemrdl-compiler` provides two modes for walking the hierarchy:

1. **Collapsed / Semantic View** (`unroll = False`):
   - Arrayed nodes appear as single `AddressableNode` instances with `array_dimensions` populated and `current_idx = None`.
   - Structural exporters (like BusDecoder) generate hardware loops or vectorized interfaces.
   - `address_offset` cannot be queried directly; address calculations must use `raw_address_offset` plus explicit stride math.

2. **Unrolled / Flattened View** (`unroll = True`):
   - Every element of an array of size $[d_0, \dots, d_{k-1}]$ expands into $\prod d_i$ distinct `Node` instances.
   - Each unrolled node shares the underlying `inst`, retaining `array_dimensions = [d_0, \dots, d_{k-1}]` and `is_array = True`, but populates `current_idx = [j_0, \dots, j_{k-1}]`. Retaining `array_dimensions` is essential because `node.address_offset` uses the dimension sizes to compute the row-major flattened index stride offset.
   - `address_offset` and `absolute_address` are directly queryable integers on unrolled nodes.
   - *(Note: In downstream exporters, helper methods such as `BaseCpuif.check_is_array(node)` may return `False` when `--unroll` is active to force scalar port generation, but the compiler-level `Node` itself remains an array instance with `current_idx` assigned).*
### 3.2 Walker Semantics
The `RDLWalker` and `RDLSteerableWalker` traverse components depth-first:
- `enter_Component(node)`: Called on arrival. May return `WalkerAction.Continue`, `WalkerAction.SkipDescendants`, or `WalkerAction.DoNotWalkSiblings`.
- `exit_Component(node)`: Called after visiting all permitted descendants.

**Invisibility Invariant (P-PRESENT):**
Any component with `ispresent = false` is pruned prior to walker execution:
$$\forall n \in \text{walk}(\text{root}): \quad n.\text{get\_property}(\text{"ispresent"}) = \text{true}$$

---

## 4. PeakRDL Exporter Contract

A compliant PeakRDL exporter plugin must satisfy:

1. **Entry Point**: The CLI plugin subclasses
   `peakrdl.plugins.exporter.ExporterSubcommandPlugin`; programmatic callers use
   `peakrdl_busdecoder.BusDecoderExporter`.
2. **CLI Registration** via setuptools entry points under `peakrdl.exporters`.
3. **Idempotence**: Running `export(node, out_dir)` twice on the same elaborated `node` must yield identical output files.
4. **Non-Destructive AST Access**: The exporter must not mutate node properties, instance variables, or compiler message handlers (exception: internal parameter discovery hooks must restore state).
5. **Diagnostic Discipline**: Errors must be reported via `node.env.msg.error()` or `node.env.msg.fatal()`, preserving source line numbers (`node.inst.inst_src_ref`).
6. **Relative Addressing Guarantee**: An exporter generating an address-mapped peripheral or interconnect must treat the exported top addrmap as sitting at base address 0, regardless of whether the exported node is an inner addrmap within a larger SoC model.
