"""Regenerate the documentation SVG figures from their editable sources.

Sources live in ``docs/diagrams/src``; generated figures are committed to
``docs/diagrams/svg`` so documentation builds need no diagram tooling.

* ``*.dot``   -> Graphviz ``dot``
* ``*.json5`` -> WaveDrom (``npx wavedrom-cli``, pinned below)
* ``address_map.rdl`` -> ``address_map.py`` (rendered from the elaborated design)

Each SVG records a hash of its inputs. ``--check`` verifies that every figure is
present and was generated from the current sources without needing any of the
rendering tools, so it can run in CI.

Usage::

    uv run python docs/diagrams/build.py          # regenerate stale figures
    uv run python docs/diagrams/build.py --force  # regenerate everything
    uv run python docs/diagrams/build.py --check  # verify freshness only
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
OUT = HERE / "svg"
WAVEDROM_CLI = "wavedrom-cli@3.2.0"
STAMP_RE = re.compile(r"<!-- diagram-source-sha256: ([0-9a-f]{64}) -->")


def _inputs(source: Path) -> list[Path]:
    """Files whose contents determine the rendered figure."""
    if source.suffix == ".rdl":
        return [source, HERE / "address_map.py"]
    return [source]


def _digest(source: Path) -> str:
    h = hashlib.sha256()
    for path in _inputs(source):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def _render_dot(source: Path, target: Path) -> None:
    subprocess.run(["dot", "-Tsvg", str(source), "-o", str(target)], check=True)


def _render_wavedrom(source: Path, target: Path) -> None:
    npx = shutil.which("npx")
    if npx is None:
        raise SystemExit("npx (Node.js) is required to render WaveDrom figures")
    subprocess.run([npx, "-y", WAVEDROM_CLI, "-i", str(source), "-s", str(target)], check=True)


def _render_address_map(source: Path, target: Path) -> None:
    sys.path.insert(0, str(HERE))
    from address_map import render

    target.write_text(render(source))


RENDERERS: dict[str, Callable[[Path, Path], None]] = {
    ".dot": _render_dot,
    ".json5": _render_wavedrom,
    ".rdl": _render_address_map,
}


def _sources() -> list[Path]:
    return sorted(p for p in SRC.iterdir() if p.suffix in RENDERERS)


def _stamp(target: Path, digest: str) -> None:
    svg = target.read_text()
    svg = STAMP_RE.sub("", svg)
    # Keep the XML declaration (if any) first; the stamp follows it.
    if svg.startswith("<?xml"):
        head, _, rest = svg.partition("?>")
        svg = f"{head}?>\n<!-- diagram-source-sha256: {digest} -->{rest}"
    else:
        svg = f"<!-- diagram-source-sha256: {digest} -->\n{svg}"
    target.write_text(svg)


def _recorded(target: Path) -> str | None:
    if not target.exists():
        return None
    match = STAMP_RE.search(target.read_text())
    return match.group(1) if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if any figure is missing or stale")
    mode.add_argument("--force", action="store_true", help="regenerate every figure")
    args = parser.parse_args()

    OUT.mkdir(exist_ok=True)
    sources = _sources()
    expected = {f"{s.stem}.svg" for s in sources}
    stale: list[str] = []

    for source in sources:
        target = OUT / f"{source.stem}.svg"
        digest = _digest(source)
        if _recorded(target) == digest and not args.force:
            continue
        if args.check:
            stale.append(target.name)
            continue
        print(f"render {source.relative_to(HERE)} -> {target.relative_to(HERE)}")
        RENDERERS[source.suffix](source, target)
        _stamp(target, digest)

    orphans = sorted(p.name for p in OUT.glob("*.svg") if p.name not in expected)
    if args.check:
        for name in stale:
            print(f"stale or missing: svg/{name}", file=sys.stderr)
        for name in orphans:
            print(f"orphaned (no source): svg/{name}", file=sys.stderr)
        if stale or orphans:
            print("Run: uv run python docs/diagrams/build.py", file=sys.stderr)
            return 1
        print(f"{len(sources)} diagrams up to date")
        return 0

    for name in orphans:
        (OUT / name).unlink()
        print(f"removed orphan svg/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
