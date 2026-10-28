"""Data model shared by extraction and Markdown rendering."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class MindmapNode:
    node_id: str
    title: str
    level: int
    x: float
    y: float
    content: str = ""
    children: List["MindmapNode"] = field(default_factory=list)
    aria_label: str = ""
