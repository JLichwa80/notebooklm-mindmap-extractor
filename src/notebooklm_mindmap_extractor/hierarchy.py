"""Reconstruct a tree from accessibility levels or mindmap coordinates."""

import re
from typing import Dict, List

from .models import MindmapNode


def build_hierarchy(raw_nodes: List[Dict]) -> List[MindmapNode]:
    """Reconstruct tree from native parent pointers, explicit levels, or visual coordinates."""
    if not raw_nodes:
        return []
    nodes = [dict(node) for node in raw_nodes]

    has_parent_ids = any(n.get("parent_id") is not None for n in nodes)
    if has_parent_ids:
        node_map: Dict[str, MindmapNode] = {}
        for raw in nodes:
            node = MindmapNode(raw["id"], raw["title"], raw["level"] or 1, raw["x"], raw["y"])
            node.aria_label = raw.get("aria_label", "")
            node_map[raw["id"]] = node

        roots: List[MindmapNode] = []
        for raw in nodes:
            node = node_map[raw["id"]]
            pid = raw.get("parent_id")
            if pid and pid in node_map:
                node_map[pid].children.append(node)
            else:
                roots.append(node)
        return roots

    has_levels = any(n.get("level") is not None for n in nodes)
    if has_levels:
        if any(type(n.get("level")) is not int or n["level"] < 1 for n in nodes):
            raise ValueError("Mindmap levels must be positive integers on every node.")
        base_level = min(n["level"] for n in nodes)
        for node in nodes:
            node["level"] -= base_level - 1
        all_levels = {n["level"] for n in nodes}
        for lvl in range(1, max(all_levels) + 1):
            if lvl not in all_levels:
                raise ValueError("Mindmap levels skip a parent level.")
        nodes.sort(key=lambda n: (n["level"], n["y"]))
    else:
        # Cluster nearby X coordinates without fixed bucket boundary artifacts.
        columns = []
        for node in sorted(nodes, key=lambda n: n["x"]):
            if not columns or node["x"] - columns[-1] >= 40:
                columns.append(node["x"])
            node["level"] = len(columns)
        nodes.sort(key=lambda n: (n["level"], n["y"]))

    roots: List[MindmapNode] = []
    by_level: Dict[int, List[MindmapNode]] = {}
    for raw in nodes:
        node = MindmapNode(raw["id"], raw["title"], raw["level"], raw["x"], raw["y"])
        node.aria_label = raw.get("aria_label", "")
        match = re.search(r"(\d+)\s+children", node.aria_label)
        node.declared_children = int(match.group(1)) if match else None

        candidates = [
            p for p in by_level.get(node.level - 1, [])
            if getattr(p, "declared_children", None) is None or len(p.children) < p.declared_children
        ]
        parent = min(candidates, key=lambda p: abs(p.y - node.y)) if candidates else None
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
        by_level.setdefault(node.level, []).append(node)
    return roots
