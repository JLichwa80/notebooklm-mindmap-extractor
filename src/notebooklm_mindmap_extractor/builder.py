"""Generate flattened outline YAML and compile handbooks from node hierarchies."""

from pathlib import Path
import re
from typing import Dict, List, Optional

from .models import MindmapNode


def sanitize_filename(name: str) -> str:
    """Make title safe for directory and file names across platforms."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "-", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"-+", "-", cleaned).strip("- ")
    return cleaned[:80] or "untitled"


def slugify(text: str) -> str:
    """Create a lowercase URL- and folder-friendly slug."""
    cleaned = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", cleaned)[:60] or "notebook"


def generate_outline_yaml(roots: List[MindmapNode]) -> str:
    """Generate doc_full_order.yml with nodeTitle and childNodes entries with order attributes."""
    lines = [
        "# Handbook Compilation Order (doc_full_order.yml)",
        "# Reorder sections by changing the 'order' integer or moving items.",
        ""
    ]

    def _walk(node: MindmapNode):
        if node.children:
            title = " ".join(node.title.splitlines())
            escaped_title = title.replace('"', '\\"')
            lines.append(f"- nodeTitle: \"{escaped_title}\"")
            lines.append("  childNodes:")
            for idx, child in enumerate(node.children, start=1):
                child_title = " ".join(child.title.splitlines()).replace('"', '\\"')
                lines.append(f"    - title: \"{child_title}\"")
                lines.append(f"      order: {idx}")
            lines.append("")
            for child in node.children:
                _walk(child)

    for root in roots:
        _walk(root)

    return "\n".join(lines).strip() + "\n"


def generate_flattened_outline_yaml(roots: List[MindmapNode]) -> str:
    """Backward-compatible alias for generate_outline_yaml."""
    return generate_outline_yaml(roots)


def parse_outline_yaml(text: str) -> List[Dict]:
    """Parse outline YAML supporting nodeTitle/childNodes with order attributes, flattened, and nested formats."""
    try:
        import yaml
        loaded = yaml.safe_load(text)
        if isinstance(loaded, list):
            return loaded
    except ImportError:
        pass

    items: List[Dict] = []
    current_item: Optional[Dict] = None
    current_key: Optional[str] = None

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))

        if raw_line.startswith("- "):
            rest = stripped[2:].strip()
            current_item = {}
            items.append(current_item)
            current_key = None
            if ":" in rest:
                k, v = rest.split(":", 1)
                k = k.strip()
                v = v.strip().strip('"\'')
                if v:
                    current_item[k] = int(v) if (k == "level" and v.isdigit()) else v
                else:
                    current_key = k
                    current_item[k] = []
            continue

        if current_item is not None:
            if stripped.startswith("- "):
                rest = stripped[2:].strip()
                if current_key:
                    target_list = current_item.setdefault(current_key, [])
                    if ":" in rest:
                        k, v = rest.split(":", 1)
                        k = k.strip()
                        v = v.strip().strip('"\'')
                        child_dict = {k: int(v) if (k == "order" and v.isdigit()) else v}
                        target_list.append(child_dict)
                    else:
                        target_list.append(rest.strip('"\''))
            elif ":" in stripped:
                k, v = stripped.split(":", 1)
                k = k.strip()
                v = v.strip().strip('"\'')
                if v:
                    val = int(v) if ((k in {"level", "order"}) and v.isdigit()) else v
                    if current_key and isinstance(current_item.get(current_key), list) and current_item[current_key] and isinstance(current_item[current_key][-1], dict):
                        current_item[current_key][-1][k] = val
                    elif current_key and indent > 2:
                        if not isinstance(current_item.get(current_key), dict):
                            current_item[current_key] = {}
                        current_item[current_key][k] = val
                    else:
                        current_item[k] = val
                        current_key = None
                else:
                    current_key = k
                    current_item[k] = []

    return items


def normalize_children_order(raw_order) -> List[str]:
    """Normalize childNodes supporting lists of dicts (with title and order), lists of strings, or dicts."""
    if not raw_order:
        return []
    if isinstance(raw_order, list):
        if raw_order and isinstance(raw_order[0], dict):
            sorted_items = sorted(
                raw_order,
                key=lambda x: int(x.get("order", 999)) if str(x.get("order", "")).isdigit() else 999
            )
            return [str(x.get("title") or x.get("nodeTitle") or x.get("tiltle", "")) for x in sorted_items if (x.get("title") or x.get("nodeTitle") or x.get("tiltle"))]
        return [str(item) for item in raw_order]
    elif isinstance(raw_order, dict):
        first_key = next(iter(raw_order.keys()))
        if str(first_key).isdigit():
            sorted_keys = sorted(raw_order.keys(), key=lambda k: int(k))
            return [str(raw_order[k]) for k in sorted_keys]
        first_val = next(iter(raw_order.values()))
        if str(first_val).isdigit():
            sorted_items = sorted(raw_order.items(), key=lambda kv: int(kv[1]))
            return [str(k) for k, _ in sorted_items]
        return [str(k) for k in raw_order.keys()]
    return []


BOX_CHARS = set("─│┌┐└┘├┤┬┴┼▼▲◄►╔╗╚╝╠╣╦╩╬═║╭╮╯╰╱╲╳")


def _is_diagram_element(line: str) -> bool:
    if any(c in BOX_CHARS for c in line):
        return True
    stripped = line.strip()
    if not stripped:
        return False
    if re.match(r"^\d+\.\s+[A-Z]", stripped):
        return False
    if stripped.startswith("#"):
        return False
    if ("Client" in stripped or "App" in stripped) and len(stripped) < 80:
        return True
    if re.search(r"\w+\s{3,}\w+", line):
        return True
    if stripped.startswith("[") and stripped.endswith("]"):
        return True
    if line.startswith("   ") and len(stripped) < 80:
        return True
    if any(sym in line for sym in ["-->", "---", "•", "·", "▼", "▲", "???"]):
        return True
    return False


def wrap_text_diagrams(text: str) -> str:
    """Wrap ASCII and Unicode box-drawing blocks in fenced code blocks for markdown preview."""
    text = re.sub(r"```text\n?", "", text)
    text = re.sub(r"```\n?", "", text)

    lines = text.splitlines()
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        is_diag_start = False
        if any(c in BOX_CHARS for c in line):
            is_diag_start = True
        elif _is_diagram_element(line) and i + 1 < len(lines) and any(c in BOX_CHARS for c in lines[i + 1]):
            is_diag_start = True
        elif (
            _is_diagram_element(line)
            and i + 2 < len(lines)
            and any(c in BOX_CHARS for c in lines[i + 2])
            and _is_diagram_element(lines[i + 1])
        ):
            is_diag_start = True

        if is_diag_start:
            diag_lines = []
            while i < len(lines):
                cur = lines[i]
                if cur.strip().startswith("#") or re.match(r"^\d+\.\s+[A-Z]", cur.strip()):
                    break
                if cur.strip() == "":
                    if i + 1 < len(lines) and (
                        any(c in BOX_CHARS for c in lines[i + 1]) or _is_diagram_element(lines[i + 1])
                    ):
                        diag_lines.append(cur)
                        i += 1
                        continue
                    else:
                        break
                if _is_diagram_element(cur):
                    diag_lines.append(cur)
                    i += 1
                else:
                    break

            while diag_lines and not diag_lines[-1].strip():
                diag_lines.pop()

            if any(any(c in BOX_CHARS for c in l) for l in diag_lines):
                result.append("```text")
                result.extend(diag_lines)
                result.append("```")
            else:
                result.extend(diag_lines)
            continue

        result.append(line)
        i += 1

    return "\n".join(result)


def stitch_stray_punctuation(text: str) -> str:
    """Stitch stray punctuation lines back to the preceding sentence."""
    pattern = r'([^\n])(?:[^\S\n]*\n)+(?:[^\S\n]*)([\.\,\:\;\?\!])(?:\s*([^\n]*))?'

    def _repl(m):
        prev = m.group(1)
        punct = m.group(2)
        rest = m.group(3)
        if rest:
            return f'{prev}{punct} {rest}'
        return f'{prev}{punct}'

    return re.sub(pattern, _repl, text)


def convert_tab_tables(text: str) -> str:
    """Convert tab-delimited table rows into formatted GFM Markdown tables."""
    if "\t" not in text:
        return text
    lines = text.splitlines()
    tab_line_indices = [i for i, l in enumerate(lines) if "\t" in l]
    if not tab_line_indices:
        return text

    # Cluster contiguous tab ranges (allowing gaps up to 4 lines between cells/rows)
    clusters = []
    current_cluster = [tab_line_indices[0]]
    for idx in tab_line_indices[1:]:
        if idx - current_cluster[-1] <= 4:
            current_cluster.append(idx)
        else:
            clusters.append(current_cluster)
            current_cluster = [idx]
    clusters.append(current_cluster)

    for c in reversed(clusters):
        s = c[0] - 1
        while s >= 0 and lines[s].strip() == "":
            s -= 1
        start = max(0, s)
        end = c[-1]
        while end + 1 < len(lines) and lines[end + 1].strip() != "" and not lines[end + 1].startswith("#"):
            end += 1

        raw = "\n".join(lines[start : end + 1])
        row_blocks = [r.strip() for r in re.split(r"\n[^\S\t]*\n", raw) if r.strip()]
        rows = []
        for rb in row_blocks:
            flat = re.sub(r"[\r\n]*\t[\r\n]*", "\t", rb)
            cells = [c.strip() for c in flat.split("\t")]
            if any(cells):
                rows.append(cells)
        if len(rows) >= 2:
            max_cols = max(len(r) for r in rows)
            if max_cols >= 2:
                padded = [r + [""] * (max_cols - len(r)) for r in rows]
                md = []
                md.append("| " + " | ".join(padded[0]) + " |")
                md.append("| " + " | ".join(["---"] * max_cols) + " |")
                for r in padded[1:]:
                    md.append("| " + " | ".join(r) + " |")
                lines[start : end + 1] = md

    return "\n".join(lines)


def clean_extracted_text(text: str) -> str:
    """Clean citations, UI action buttons, and follow-up prompts from extracted text."""
    if not text:
        return ""
    # 1. Clean citation numbers before punctuation: "word\n1\n\n.\n" -> "word.\n"
    text = re.sub(r'([^\n])\s*\n+(?:\s*\d+\s*\n+)+(\s*[\.\,\:\;\?\!])', r'\1\2', text)
    # 2. Clean citation numbers at line/paragraph ends
    text = re.sub(r'([^\n])\s*\n+(?:\s*\d+\s*\n+)+(?=\n|$)', r'\1\n', text)
    # 3. Stitch any stray punctuation lines back to preceding sentences
    text = stitch_stray_punctuation(text)
    # 4. Clean line-by-line UI buttons and trailing prompt safely without greedy multiline match
    lines = text.splitlines()
    ui_patterns = [
        re.compile(r'^\s*(?:save to note|save note)\s*$', re.IGNORECASE),
        re.compile(r'^\s*(?:copy|copy model response to clipboard|copy to clipboard|copied!?)\s*$', re.IGNORECASE),
        re.compile(r'^\s*thumbs (?:up|down)\s*$', re.IGNORECASE),
    ]

    cutoff_index = len(lines)
    for idx in range(len(lines) - 1, max(-1, len(lines) - 25), -1):
        line = lines[idx].strip()
        if re.search(
            r'^[^\w\s]*\s*(?:would you like to|would you like me to|do you want to|should we explore)\b',
            line,
            re.IGNORECASE,
        ):
            cutoff_index = idx
            break

    trimmed = lines[:cutoff_index]
    cleaned = [l for l in trimmed if not any(pat.match(l) for pat in ui_patterns) and not l.strip().isdigit()]
    text = '\n'.join(cleaned).strip()

    # 5. Convert broken tab-delimited tables into clean GFM Markdown tables
    text = convert_tab_tables(text)

    # 6. Wrap ASCII/Unicode diagrams in ```text blocks
    text = wrap_text_diagrams(text)

    return re.sub(r'\n{3,}', '\n\n', text).strip()



clean_citations = clean_extracted_text


def convert_body_headings(text: str) -> str:
    """Convert body headings (##, ###, ####) into numbered sections (1., 1.1) so they do not pollute the document outline."""
    lines = text.splitlines()
    result = []
    major_count = 0
    minor_count = 0

    for line in lines:
        stripped = line.strip()
        m_minor = re.match(r"^(?:#{4,6})\s+(.+)$", stripped)
        m_major = re.match(r"^(?:#{2,3})\s+(.+)$", stripped)

        if m_minor:
            minor_count += 1
            raw_title = m_minor.group(1).strip()
            clean_title = re.sub(r"^(?:[A-Za-z]|\d+)(?:[\.\:\)]|\s+)\s*", "", raw_title).strip()
            if not clean_title:
                clean_title = raw_title
            prefix = f"{major_count}.{minor_count}." if major_count > 0 else f"{minor_count}."
            result.append(f"**{prefix} {clean_title}**")
        elif m_major:
            major_count += 1
            minor_count = 0
            raw_title = m_major.group(1).strip()
            clean_title = re.sub(r"^(?:\d+)(?:[\.\:\)]|\s+)\s*", "", raw_title).strip()
            if not clean_title:
                clean_title = raw_title
            result.append(f"**{major_count}. {clean_title}**")
        elif re.match(r"^#\d+\s+in\s+Development\s+Priority", stripped):
            result.append(f"* **Rank {stripped[1:]}**")
        elif re.match(r"^#\s+(?:Register|Configure|Install|Run|Set)\b", stripped):
            result.append(f"```bash\n{stripped}")
        else:
            if result and result[-1].startswith("```bash\n#") and not stripped.startswith("```"):
                result[-1] = f"{result[-1]}\n{line}\n```"
            else:
                result.append(line)

    return "\n".join(result)


def _extract_body(raw_text: str) -> str:
    """Extract markdown content body omitting the leading top-level heading if present and cleaning citations/UI artifacts."""
    cleaned = clean_extracted_text(raw_text)
    lines = cleaned.strip().splitlines()
    if lines and lines[0].startswith("#"):
        cleaned = "\n".join(lines[1:]).strip()
    return convert_body_headings(cleaned)


def compile_node_order_entries(entries: List[Dict], base_dir: Path) -> str:
    """Compile document based on nodeTitle and childNodes hierarchy."""
    if not entries:
        return ""

    order_map: Dict[str, List[str]] = {}
    for item in entries:
        nt = item.get("nodeTitle")
        if nt:
            raw_children = (
                item.get("childNodes")
                or item.get("childNodesOrder")
                or item.get("childrenNodes")
                or item.get("childrenNode")
                or []
            )
            order_map[nt] = normalize_children_order(raw_children)

    root_title = entries[0].get("nodeTitle", "Overview")

    def _read_content_and_path(title: str, dir_path: Path, is_root: bool = False):
        if is_root:
            overview = dir_path / "Overview.md"
            content = _extract_body(overview.read_text(encoding="utf-8")) if overview.exists() else ""
            return content, dir_path

        safe = sanitize_filename(title)
        cand_dirs = [dir_path / safe, dir_path / title]
        for cd in cand_dirs:
            if cd.is_dir():
                ov = cd / "Overview.md"
                content = _extract_body(ov.read_text(encoding="utf-8")) if ov.exists() else ""
                return content, cd

        cand_files = [dir_path / f"{safe}.md", dir_path / f"{title}.md"]
        for cf in cand_files:
            if cf.is_file():
                return _extract_body(cf.read_text(encoding="utf-8")), dir_path

        return "", dir_path

    def _walk_compile(title: str, current_dir: Path, level: int, is_root: bool = False) -> List[str]:
        content, node_dir = _read_content_and_path(title, current_dir, is_root=is_root)
        heading = "#" * min(level, 6)
        body = f"\n\n{content}\n" if content else "\n"
        sections = [f"\n{heading} {title}{body}"]

        children = order_map.get(title, [])
        for child_title in children:
            sections.extend(_walk_compile(child_title, node_dir, level + 1, is_root=False))
        return sections

    sections = _walk_compile(root_title, base_dir, level=1, is_root=True)
    return "".join(sections)


def compile_flattened_entries(entries: List[Dict], base_dir: Path) -> str:
    """Compile flattened outline entries sequentially into a single Markdown string."""
    sections = []
    for item in entries:
        title = item.get("title", "Untitled")
        file_rel = item.get("file", "")
        level = item.get("level", 1)
        content = ""
        if file_rel:
            target_file = base_dir / file_rel
            if target_file.exists():
                content = _extract_body(target_file.read_text(encoding="utf-8"))
            else:
                print(f"[-] Warning: Outline file not found: {target_file}")

        heading = "#" * min(level, 6)
        body = f"\n\n{content}\n" if content else "\n"
        sections.append(f"\n{heading} {title}{body}")

        # If entry has nested children (backward compatibility with nested YAML)
        if item.get("children"):
            nested_compiled = compile_nested_entries(item["children"], base_dir, level + 1)
            if nested_compiled:
                sections.append(nested_compiled)

    return "".join(sections)


def compile_nested_entries(entries: List[Dict], base_dir: Path, level: int = 1) -> str:
    """Fallback compiler for nested outlines."""
    sections = []
    for item in entries:
        title = item.get("title", "Untitled")
        file_rel = item.get("file", "")
        item_level = item.get("level", level)
        content = ""
        if file_rel:
            target_file = base_dir / file_rel
            if target_file.exists():
                content = _extract_body(target_file.read_text(encoding="utf-8"))
        heading = "#" * min(item_level, 6)
        body = f"\n\n{content}\n" if content else "\n"
        sections.append(f"\n{heading} {title}{body}")
        if item.get("children"):
            sections.append(compile_nested_entries(item["children"], base_dir, item_level + 1))
    return "".join(sections)


def build_from_folder_scan(folder: Path) -> str:
    """Compile handbook by discovering and scanning files and directories when no outline exists."""
    sections = []
    overview = folder / "Overview.md"
    root_title = "Overview"
    if overview.exists():
        raw = overview.read_text(encoding="utf-8")
        lines = raw.strip().splitlines()
        if lines and lines[0].startswith("# "):
            root_title = lines[0][2:].strip()
        body = _extract_body(raw)
        sections.append(f"\n# {root_title}\n\n{body}\n" if body else f"\n# {root_title}\n")

    subdirs = sorted([d for d in folder.iterdir() if d.is_dir() and not d.name.startswith(".")], key=lambda d: d.name)
    for subdir in subdirs:
        sub_overview = subdir / "Overview.md"
        sub_title = subdir.name
        if sub_overview.exists():
            raw = sub_overview.read_text(encoding="utf-8")
            lines = raw.strip().splitlines()
            if lines and lines[0].startswith("# "):
                sub_title = lines[0][2:].strip()
            body = _extract_body(raw)
            sections.append(f"\n## {sub_title}\n\n{body}\n" if body else f"\n## {sub_title}\n")
        else:
            sections.append(f"\n## {sub_title}\n")

        files = sorted(
            [f for f in subdir.iterdir() if f.is_file() and f.suffix == ".md" and f.name != "Overview.md"],
            key=lambda f: f.name,
        )
        for f in files:
            raw = f.read_text(encoding="utf-8")
            lines = raw.strip().splitlines()
            file_title = f.stem
            if lines and lines[0].startswith("# "):
                file_title = lines[0][2:].strip()
            body = _extract_body(raw)
            sections.append(f"\n### {file_title}\n\n{body}\n" if body else f"\n### {file_title}\n")

    loose_files = sorted(
        [
            f for f in folder.iterdir()
            if f.is_file() and f.suffix == ".md"
            and f.name != "Overview.md"
            and not f.name.endswith("-full.md")
            and not f.name.endswith("-full-reference.md")
        ],
        key=lambda f: f.name,
    )
    for f in loose_files:
        raw = f.read_text(encoding="utf-8")
        lines = raw.strip().splitlines()
        file_title = f.stem
        if lines and lines[0].startswith("# "):
            file_title = lines[0][2:].strip()
        body = _extract_body(raw)
        sections.append(f"\n## {file_title}\n\n{body}\n" if body else f"\n## {file_title}\n")

    return "".join(sections)


def build_handbook_from_folder(
    folder: Path, output_file: Optional[Path] = None, outline_path: Optional[Path] = None
) -> Path:
    """Compile full handbook from a run folder using its outline.yml or custom outline."""
    folder = Path(folder)
    if not folder.exists():
        resolved = folder.resolve()
        if resolved.exists():
            folder = resolved
        else:
            raise FileNotFoundError(f"Handbook folder not found: {folder}")
    else:
        folder = folder.resolve()

    if outline_path is not None:
        custom_outline = Path(outline_path)
        if not custom_outline.is_absolute() and not custom_outline.exists():
            if (folder / custom_outline).exists():
                custom_outline = folder / custom_outline
        if not custom_outline.exists():
            raise FileNotFoundError(f"Outline file not found: {outline_path}")
        target_outline = custom_outline
    else:
        candidates = [
            folder / "doc_full_order.yml",
            folder / "doc_full_order.yaml",
            folder / "outline.yml",
            folder / "outline.yaml",
        ]
        target_outline = next((p for p in candidates if p.exists()), candidates[0])

    if target_outline.exists():
        print(f"[*] Compiling handbook using outline: {target_outline}")
        entries = parse_outline_yaml(target_outline.read_text(encoding="utf-8"))
        if entries and any("nodeTitle" in item for item in entries):
            document = compile_node_order_entries(entries, folder)
        else:
            document = compile_flattened_entries(entries, folder)
    else:
        print(f"[*] No outline found; compiling sequentially from folder: {folder}")
        document = build_from_folder_scan(folder)

    if output_file is None:
        # Determine [notebook-name]-full-reference.md
        folder_name = folder.name
        # Strip timestamp suffix like _20261027_174915 or -20261027_174915
        base_name = re.sub(r"[-_]\d{8}[-_]\d{6}$", "", folder_name)
        output_file = folder / f"{base_name}-full-reference.md"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(document.strip() + "\n", encoding="utf-8")
    print(f"[+] Full handbook compiled successfully: {output_file}")
    return output_file
