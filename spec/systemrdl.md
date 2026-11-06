# SystemRDL 2.0 Address Space Semantics — Formal Specification

This specification formalizes the subset of the Accellera SystemRDL 2.0 Standard (IEEE 1685-derived register description standard) that governs component hierarchy, address allocation, array layout, and overlap validation. It provides the reference mathematical model for address decoders and downstream generators.

All clauses cited refer to the *Accellera SystemRDL 2.0 Standard* (January 2018). Text is paraphrased to preserve Accellera copyright while capturing exact semantics.

Status: reference semantics for the **0.8.0 candidate draft**, pending integrated
verification. This mathematical model is not a claim of an unbounded proof of
the generated RTL. Protocol-specific routing contracts are in `busdecoder.md`.

---

## 1. Component Hierarchy and Types

### 1.1 Components ($\mathcal{C}$)

A SystemRDL design is a rooted directed tree of component instances:

$$\mathcal{C} = \text{Addrmap} \cup \text{Regfile} \cup \text{Mem} \cup \text{Reg} \cup \text{Field} \cup \text{Signal}$$

- **Addressable components** ($\mathcal{A} \subset \mathcal{C}$):
  $$\mathcal{A} = \text{Addrmap} \cup \text{Regfile} \cup \text{Mem} \cup \text{Reg}$$
- **Block-like components** ($\mathcal{B} \subset \mathcal{A}$):
  $$\mathcal{B} = \text{Addrmap} \cup \text{Regfile}$$
- **Leaf addressable components**:
  $$\mathcal{L} = \text{Mem} \cup \text{Reg}$$
- **Non-addressable structural components**: $\text{Field}$ (contained strictly in $\text{Reg}$), $\text{Signal}$ (may be instantiated in $\text{Addrmap}$, $\text{Regfile}$, $\text{Reg}$).

### 1.2 Hierarchy Constraints

Let $\text{parent}(c)$ denote the enclosing component of $c$.
- **R-HIER-ROOT** (Clause 13.2): The elaboration root is an $\text{Addrmap}$ instance $c_{\text{root}}$ with $\text{parent}(c_{\text{root}}) = \bot$.
- **R-HIER-ADDRMAP** (Clause 13.3-b): For $a \in \text{Addrmap}$, children may be $\text{Addrmap}$, $\text{Regfile}$, $\text{Mem}$, $\text{Reg}$, $\text{Signal}$. At least one child must belong to $\mathcal{A}$.
- **R-HIER-BRIDGE** (Clause 13.3-c, 13.4.1): If $a.\text{bridge} = \text{true}$, then every child of $a$ must be an $\text{Addrmap}$, and $|\text{children}(a) \cap \text{Addrmap}| \ge 2$.
- **R-HIER-REGFILE** (Clause 12.2-c): For $rf \in \text{Regfile}$, children may be $\text{Regfile}$, $\text{Reg}$, $\text{Signal}$. At least one child must belong to $\text{Regfile} \cup \text{Reg}$.
- **R-HIER-REG** (Clause 10.1-c): For $r \in \text{Reg}$, children may be $\text{Field}$, $\text{Signal}$. At least one child must belong to $\text{Field}$.
- **R-HIER-MEM** (Clause 11.2): For $m \in \text{Mem}$, children may be virtual $\text{Reg}$ instances.
- **R-HIER-FIELD** (Clause 9.2): A $\text{Field}$ has no child components.

### 1.3 Instance Attributes

Every addressable instance $a \in \mathcal{A}$ possesses:
- $\text{name}(a) \in \Sigma^+$: Instance identifier.
- $\text{external}(a) \in \{\text{true}, \text{false}\}$:
  - Addrmaps are implicitly external: $a \in \text{Addrmap} \implies \text{external}(a) = \text{true}$ (Clause 13.3).
  - Mems are implicitly external: $m \in \text{Mem} \implies \text{external}(m) = \text{true}$ (Clause 11.2).
  - Regs and Regfiles default to internal unless enclosed in an external Regfile (Clause 12.2-f).
- $\text{ispresent}(a) \in \{\text{true}, \text{false}\}$: When false, the component is excluded from the elaborated view (Clause 5.3.1).
- $\text{dims}(a) = [d_0, d_1, \dots, d_{k-1}]$ with $d_i \in \mathbb{N}_{\ge 1}$, $k \ge 0$.
  - If $k = 0$, $a$ is a scalar instance.
  - If $k \ge 1$, $a$ is an array instance with $N(a) = \prod_{i=0}^{k-1} d_i$ elements.
- $\text{stride}(a) \in \mathbb{N}_{\ge 1} \cup \{\bot\}$: Address stride between array elements (defined when $k \ge 1$).

---

## 2. Size Semantics

Let $\text{size}: \mathcal{A} \to \mathbb{N}_{\ge 1}$ denote the byte size of a single element of $a$, and $\text{total\_size}: \mathcal{A} \to \mathbb{N}_{\ge 1}$ denote the total byte footprint including array replication and strides.

### 2.1 Register Size
For $r \in \text{Reg}$ (Clause 10.3):
$$\text{size}(r) = \frac{r.\text{regwidth}}{8}, \quad r.\text{regwidth} \in \{8, 16, 24, 32, 40, \dots\} \cap 8\mathbb{Z}_{\ge 1}$$
$$\text{total\_size}(r) = \begin{cases}
\text{size}(r) & \text{if } k=0 \\
\text{stride}(r) \cdot N(r) & \text{if } k \ge 1
\end{cases}$$

### 2.2 Memory Size
For $m \in \text{Mem}$ (Clause 11.3):
$$\text{entry\_size}(m) = \frac{\text{roundup\_pow2}(\max(m.\text{memwidth}, 8))}{8}$$
$$\text{size}(m) = \text{entry\_size}(m) \cdot m.\text{mementries}$$
$$\text{total\_size}(m) = \begin{cases}
\text{size}(m) & \text{if } k=0 \\
\text{stride}(m) \cdot N(m) & \text{if } k \ge 1
\end{cases}$$

### 2.3 Block Size (Addrmap and Regfile)
For $b \in \mathcal{B} = \text{Addrmap} \cup \text{Regfile}$ with ordered addressable children $\langle c_0, c_1, \dots, c_{n-1} \rangle$ sorted ascending by $\text{raw\_offset}(c_i)$:

$$\text{size}(b) = \begin{cases}
0 & \text{if } n = 0 \\
\max_{0 \le i < n} \left( \text{raw\_offset}(c_i) + \text{total\_size}(c_i) \right) & \text{if } n > 0
\end{cases}$$

*(Note on implementation divergence: when $b.\text{bridge} = \text{false}$, children are strictly non-overlapping and sorted, so the maximum is identically $\text{raw\_offset}(c_{n-1}) + \text{total\_size}(c_{n-1})$. When $b.\text{bridge} = \text{true}$, all children start at offset 0, so the maximum over all children is required.)*

$$\text{total\_size}(b) = \begin{cases}
\text{size}(b) & \text{if } k=0 \\
\text{stride}(b) \cdot N(b) & \text{if } k \ge 1
\end{cases}$$

---

## 3. Addressing Modes and Alignment

### 3.1 Addressing Types
A block $b \in \mathcal{B}$ defines an addressing mode (Clause 13.4.1, 12.3.1):
$$b.\text{addressing} \in \{\text{compact}, \text{regalign}, \text{fullalign}\}, \quad \text{default} = \text{regalign}$$

### 3.2 Alignment Requirements
For a child $c \in \mathcal{A}$ under parent $b \in \mathcal{B}$:

1. **Property alignment** ($A_{\text{prop}}$):
   Inherited from nearest ancestor specifying `alignment`:
   $$A_{\text{prop}}(c) = \begin{cases} c.\text{alignment} & \text{if specified} \\ A_{\text{prop}}(b) & \text{otherwise (default 1)} \end{cases}$$
   Constraint (Clause 12.3.1-a, 13.4.1-b): $A_{\text{prop}} \in \{2^p \mid p \in \mathbb{N}\}$.

2. **Allocator alignment** ($A_{\text{alloc}}$):
   Specified by the `%=` allocation operator, or 1 if unspecified:
   $$A_{\text{alloc}}(c) \in \{2^p \mid p \in \mathbb{N}\} \cup \{1\}$$

3. **Mode alignment** ($A_{\text{mode}}$):
   - **`compact`**:
     $$A_{\text{mode}}(c) = \begin{cases}
     c.\text{accesswidth} / 8 & \text{if } c \in \text{Reg} \\
     1 & \text{otherwise}
     \end{cases}$$
   - **`regalign`**:
     $$A_{\text{mode}}(c) = \text{roundup\_pow2}(\text{size}(c))$$
   - **`fullalign`**:
     $$A_{\text{mode}}(c) = \text{roundup\_pow2}(\text{total\_size}(c))$$

4. **Effective alignment**:
   $$\text{align}(c) = \max(A_{\text{prop}}(c), A_{\text{alloc}}(c), A_{\text{mode}}(c))$$

---

## 4. Address Allocation Rules

Let $\text{children}_{\mathcal{A}}(b) = \langle c_0, c_1, \dots, c_{n-1} \rangle$ be the lexical declaration sequence of addressable children of $b$.

### 4.1 Explicit vs Inferred Offsets
Each child $c_i$ specifies an offset via one of:
- **Absolute / explicit offset** (`@ offset`): $\text{raw\_offset}(c_i) = \text{offset}$.
  Constraint: $\text{raw\_offset}(c_i) \equiv 0 \pmod{A_{\text{prop}}(c_i)}$.
- **Inferred offset** (no `@` operator):
  $$\text{next\_free}(i) = \begin{cases}
  0 & \text{if } i = 0 \lor b.\text{bridge} = \text{true} \\
  \text{raw\_offset}(c_{i-1}) + \text{total\_size}(c_{i-1}) & \text{if } i > 0 \land b.\text{bridge} = \text{false}
  \end{cases}$$
  $$\text{raw\_offset}(c_i) = \text{roundup\_to}(\text{next\_free}(i), \text{align}(c_i))$$
  where $\text{roundup\_to}(x, a) = \lceil x / a \rceil \cdot a$.

### 4.2 Array Stride Allocation
For an array instance $c \in \mathcal{A}$ with $\text{dims}(c) \ne \emptyset$:
- **Explicit stride** (`+= stride`): $\text{stride}(c) = \text{stride}$.
  Constraint (Clause 5.1.2.3.2): $\text{stride}(c) \ge \text{size}(c)$.
- **Implicit stride**: If `+=` is omitted:
  $$\text{stride}(c) = \text{size}(c)$$

### 4.3 Multidimensional Element Addressing
For $c$ with dimensions $[d_0, d_1, \dots, d_{k-1}]$, an element is indexed by tuple $\vec{j} = (j_0, j_1, \dots, j_{k-1})$ with $0 \le j_m < d_m$.

The **row-major flattened index** is:
$$\text{flat\_idx}(\vec{j}) = \sum_{m=0}^{k-1} \left( j_m \cdot \prod_{p=m+1}^{k-1} d_p \right)$$

The element offset relative to parent $b$ is:
$$\text{elem\_offset}(c, \vec{j}) = \text{raw\_offset}(c) + \text{flat\_idx}(\vec{j}) \cdot \text{stride}(c)$$

The element's byte span within parent $b$ is the half-open interval:
$$\text{span}(c, \vec{j}) = [\text{elem\_offset}(c, \vec{j}),\; \text{elem\_offset}(c, \vec{j}) + \text{size}(c))$$

The entire instance's byte span is:
$$\text{span\_total}(c) = [\text{raw\_offset}(c),\; \text{raw\_offset}(c) + \text{total\_size}(c))$$

### 4.4 Absolute Address
Let $\text{anc}(c) = \langle a_0, a_1, \dots, a_{h-1}, c \rangle$ be the ancestor chain from the root addrmap $a_0 = c_{\text{root}}$ down to $c$, with index tuple $\vec{j}^{(m)}$ for any arrayed ancestor $a_m$.

$$\text{abs\_address}(c, \vec{j}) = \sum_{m=0}^{h-1} \text{elem\_offset}(a_m, \vec{j}^{(m)}) + \text{elem\_offset}(c, \vec{j})$$

$$\text{abs\_span}(c, \vec{j}) = [\text{abs\_address}(c, \vec{j}),\; \text{abs\_address}(c, \vec{j}) + \text{size}(c))$$

---

## 5. Overlap Rules and Legality

For any parent block $b \in \mathcal{B}$, let $c_i, c_j \in \text{children}_{\mathcal{A}}(b)$ with $i \ne j$.

### 5.1 Disjointness Axiom (R-NO-OVERLAP)
Unless explicitly exempted by Section 5.2:
$$\text{span\_total}(c_i) \cap \text{span\_total}(c_j) = \emptyset$$

### 5.2 Overlap Exemptions
Overlap is permitted **if and only if** at least one of the following holds:
1. **Bridge Addrmap** (Clause 13.3-c): $b \in \text{Addrmap} \land b.\text{bridge} = \text{true}$.
2. **Read-Only / Write-Only Register Pair** (Clause 10.1-h):
   $c_i, c_j \in \text{Reg} \land \text{dims}(c_i) = \text{dims}(c_j) = \emptyset$, and:
   $$(\neg \text{is\_sw\_writable}(c_i) \land \neg \text{is\_sw\_readable}(c_j)) \lor (\neg \text{is\_sw\_readable}(c_i) \land \neg \text{is\_sw\_writable}(c_j))$$
   where the field access type satisfies $f.\text{sw} \in \{\text{na}, \text{r}, \text{w}, \text{rw}, \text{w1}, \text{rw1}\}$ (Clause 9.5.1), and:
   $$\text{is\_sw\_readable}(r) \iff \exists f \in \text{children}(r) \cap \text{Field}: f.\text{sw} \in \{\text{r}, \text{rw}, \text{rw1}\}$$
   $$\text{is\_sw\_writable}(r) \iff \exists f \in \text{children}(r) \cap \text{Field}: f.\text{sw} \in \{\text{w}, \text{rw}, \text{w1}, \text{rw1}\}$$
   *(Note: Read/write side-effects such as `rclr`, `rset`, `woclr`, `woset` are defined separately under the `onread` and `onwrite` properties and do not alter software accessibility).*
Any overlap not matching (1) or (2) is a fatal SystemRDL semantic violation.

---

## 6. Access and Field Placement Invariants

- **R-FIELD-BOUNDS** (Clause 10.1-d): For every $f \in \text{Field}$ inside $r \in \text{Reg}$:
  $$0 \le f.\text{lsb} \le f.\text{msb} < r.\text{regwidth}$$
- **R-FIELD-OVERLAP** (Clause 10.1-d): Two fields $f_1, f_2 \in r$ may overlap in bit position **if and only if** one is read-only and the other is write-only.
- **R-MEM-CAPACITY** (Clause 11.2-i): For virtual registers $r \in m \in \text{Mem}$:
  $$\max_{r} (\text{raw\_offset}(r) + \text{total\_size}(r)) \le \text{size}(m)$$

---

## 7. Reference Semantics Summary

A fully elaborated SystemRDL register model $(\mathcal{C}, \text{root})$ defines a deterministic mapping from relative byte address $A \in [0, \text{size}(\text{root}))$ and transaction direction $D \in \{\text{READ}, \text{WRITE}\}$ to a set of matching leaf components:

$$\text{lookup}(A, D) = \{ c \in \mathcal{L} \mid A \in \text{abs\_span}(c, \vec{j}) \land \text{permits}(c, D) \}$$

where:
$$\text{permits}(c, \text{READ}) \iff c \in \text{Mem} \lor \text{is\_sw\_readable}(c)$$
$$\text{permits}(c, \text{WRITE}) \iff c \in \text{Mem} \lor \text{is\_sw\_writable}(c)$$

Under R-NO-OVERLAP and the legal register-pair exception:
$$\forall A \in [0, \text{size}(\text{root})), \forall D \in \{\text{READ}, \text{WRITE}\}: \quad |\text{lookup}(A, D)| \le 1$$
This determinism is the foundational invariant required by every bus decoder.
