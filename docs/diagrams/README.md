# Documentation diagrams

Editable sources are in `src/`; the SVGs in `svg/` are generated and committed,
so building the docs needs no diagram tooling.

| Source | Renderer | Used for |
|---|---|---|
| `*.dot` | Graphviz `dot` | block/architecture figures |
| `*.json5` | WaveDrom (`npx wavedrom-cli`, version pinned in `build.py`) | timing diagrams |
| `address_map.rdl` | `address_map.py` | address-map figure computed from the elaborated design |

## Editing

1. Edit or add a file in `src/`. The output name is the source stem (`foo.dot` → `svg/foo.svg`).
2. Regenerate: `uv run python docs/diagrams/build.py` (needs `dot` and Node.js `npx`).
3. Reference new figures from the `.rst` pages with `.. figure::`, `:class: diagram` (applies the figure CSS to the image),
   a caption, and `:alt:` text that states what the figure shows.
4. Commit the source and the regenerated SVG together.

`python3 docs/diagrams/build.py --check` needs no rendering tools. It fails if a
figure is missing, was rendered from an older source, or has no source. CI runs
it in the lint workflow.

Deleting a source and running `build.py` removes its SVG.

## Conventions

- Blue solid: request path. Green dashed: response path. Red: locally generated
  error. Orange: per-transaction retained state. Grey: export-time processing.
- Light fills with a darker border of the same hue; white figure background.
- Interface figures live with the released interface or ordering contract they
  illustrate; captions must preserve the protocol's scope and timing caveats.
- Timing diagrams are illustrative; state exact contracts in the page text.
