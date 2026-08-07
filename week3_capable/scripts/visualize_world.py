"""Standalone map renderer for world.db (plan §10). Python-only, read-only --
no dependency on the agent loop or a live DB connection beyond opening the
file directly. Renders nodes = rooms (fill color by area_type, dashed
border for unvisited placeholders) and directed labeled edges = exits
(§10: exits aren't guaranteed symmetric in a MUD, so this never collapses
reciprocal pairs into one undirected edge).

Requires the `graphviz` pip package *and* the system `dot` binary
(decision #2): `sudo apt-get install graphviz && pip install graphviz`.

Run: python3 week3_capable/scripts/visualize_world.py [--db path] [--out path]
"""
import argparse
import sqlite3
from pathlib import Path

import graphviz

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "world.db"
DEFAULT_OUT_PATH = Path(__file__).resolve().parents[2] / "docs" / "maps" / "world"

# Small fixed palette by area_type -- unrecognized/NULL area_type falls
# back to a neutral gray rather than erroring, since area_type is often
# unset for placeholder rooms.
AREA_TYPE_COLORS = {
    "town": "#fde68a",
    "sewer": "#a3e4d7",
    "castle": "#c7b6f0",
    "dungeon": "#f4a3a3",
    "mountain": "#cbd5e1",
}
DEFAULT_COLOR = "#e5e7eb"


def build_graph(conn):
    dot = graphviz.Digraph("world", format="jpg")
    dot.attr(rankdir="LR")

    mob_counts = dict(conn.execute(
        "SELECT location_id, COUNT(*) FROM location_mobs GROUP BY location_id"
    ).fetchall())
    item_counts = dict(conn.execute(
        "SELECT location_id, COUNT(*) FROM location_items GROUP BY location_id"
    ).fetchall())

    for row in conn.execute("SELECT location_id, name, area_type, visited FROM locations"):
        location_id, name, area_type, visited = row
        label = name if name else "? (unvisited)"
        annotations = []
        if mob_counts.get(location_id):
            annotations.append(f"{mob_counts[location_id]} mob(s)")
        if item_counts.get(location_id):
            annotations.append(f"{item_counts[location_id]} item(s)")
        if annotations:
            label += "\\n" + ", ".join(annotations)

        dot.node(
            str(location_id),
            label=label,
            style="filled,dashed" if not visited else "filled",
            fillcolor=AREA_TYPE_COLORS.get(area_type, DEFAULT_COLOR),
        )

    for location_id, direction, leads_to_location_id in conn.execute(
        "SELECT location_id, direction, leads_to_location_id FROM exits"
    ):
        dot.edge(str(location_id), str(leads_to_location_id), label=direction)

    return dot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to world.db")
    parser.add_argument("--out", default=str(DEFAULT_OUT_PATH),
                         help="Output path, without extension (default: docs/maps/world)")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        parser.error(f"no such file: {db_path} (run the agent at least once to create it)")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dot = build_graph(conn)
    finally:
        conn.close()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = dot.render(str(out_path), cleanup=True)
    print(f"Wrote {rendered}")


if __name__ == "__main__":
    main()
