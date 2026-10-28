"""Clean text extracted from NotebookLM: citations, UI buttons, tables, diagrams, headings."""

import re


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


def _has_box(line: str) -> bool:
    return any(c in BOX_CHARS for c in line)


def _is_label(line: str) -> bool:
    """A short plain line such as 'Smart Router Gateway' that can sit between diagram rows."""
    stripped = line.strip()
    if not stripped or len(stripped) > 60 or stripped.endswith((".", ":", "?", "!")):
        return False
    return not stripped.startswith(("#", "* ", "- ", "|")) and not re.match(r"^\d+\.\s", stripped)


def wrap_text_diagrams(text: str) -> str:
    """Wrap ASCII and Unicode box-drawing blocks in fenced code blocks for markdown preview.

    A diagram runs from its first box-drawing line to its last, including short label lines (up to
    three lines apart) between rows. Existing fenced blocks are left untouched.
    """
    lines = text.splitlines()
    result = []
    in_fence = False
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            result.append(line)
            i += 1
            continue
        if in_fence or not _has_box(line):
            result.append(line)
            i += 1
            continue

        lead = []
        while (
            len(lead) < 2
            and result
            and result[-1].strip()
            and not result[-1].lstrip().startswith("```")
            and _is_diagram_element(result[-1])
        ):
            lead.insert(0, result.pop())

        end = i
        k = i + 1
        while k < len(lines) and k - end <= 3:
            cur = lines[k]
            if _has_box(cur):
                end = k
            elif cur.strip() and not (_is_diagram_element(cur) or _is_label(cur)):
                break
            k += 1

        stop = end + 1
        while (
            stop < len(lines)
            and lines[stop].strip()
            and not lines[stop].lstrip().startswith("```")
            and _is_diagram_element(lines[stop])
        ):
            stop += 1

        result.append("```text")
        result.extend(lead + lines[i:stop])
        result.append("```")
        i = stop

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
    """Convert a page table (innerText: cells split by a tab-only line, rows by a blank line) into a GFM table."""
    lines = text.split("\n")
    is_tab = lambda l: "\t" in l and not l.strip()
    out = []
    i = 0
    while i < len(lines):
        if not (lines[i].strip() and i + 1 < len(lines) and is_tab(lines[i + 1])):
            out.append(lines[i])
            i += 1
            continue
        rows = []
        start = i
        while True:
            cells = [lines[i].strip()]
            i += 1
            while i + 1 < len(lines) and is_tab(lines[i]):
                cells.append(lines[i + 1].strip())
                i += 2
            rows.append(cells)
            k = i
            while k < len(lines) and not lines[k].strip():
                k += 1
            if not (k + 1 < len(lines) and lines[k].strip() and is_tab(lines[k + 1])):
                break
            i = k
        width = max(len(r) for r in rows)
        if len(rows) < 2 or width < 2:
            out.extend(lines[start:i])
            continue
        padded = [r + [""] * (width - len(r)) for r in rows]
        out.append("| " + " | ".join(padded[0]) + " |")
        out.append("| " + " | ".join(["---"] * width) + " |")
        out.extend("| " + " | ".join(r) + " |" for r in padded[1:])
    return "\n".join(out)


def clean_extracted_text(text: str) -> str:
    """Clean citations, UI action buttons, and follow-up prompts from extracted text."""
    if not text:
        return ""
    # 0. Page chrome in innerText: icon names (Material icon ligatures) and the "Thoughts" header
    text = re.sub(r'(?m)^[ \t]*(?:more_horiz|expand_more)[ \t]*\r?\n', '', text)
    text = re.sub(r'\A\s*Thoughts[ \t]*\r?\n', '', text)
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

    # 7. Turn body headings into numbered sections and fence shell commands
    text = convert_body_headings(text)

    # 8. Each page block (paragraph, heading) is its own line: separate them so Markdown does not merge them
    text = separate_blocks(text)

    return re.sub(r'\n{3,}', '\n\n', text).strip()





def separate_blocks(text: str) -> str:
    """Put a blank line between consecutive text lines, except inside fences, bullet lists and tables."""
    result = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            if in_fence and result and result[-1].strip():
                result.append("")
            result.append(line)
            continue
        if not in_fence and line.strip() and result and result[-1].strip() and result[-1].lstrip()[:3] != "```":
            prev = result[-1]
            both_bullets = prev.startswith("* ") and line.startswith("* ")
            both_table = prev.startswith("|") and line.startswith("|")
            if not (both_bullets or both_table):
                result.append("")
        result.append(line)
    return "\n".join(result)


def convert_body_headings(text: str) -> str:
    """Convert body headings (##, ###, ####) into numbered sections (1., 1.1) so they do not pollute the document outline."""
    lines = text.splitlines()
    result = []
    major_count = 0
    minor_count = 0
    in_fence = False
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        i += 1

        if stripped.startswith("```"):
            in_fence = not in_fence
            result.append(line)
            continue
        if in_fence:
            result.append(line)
            continue

        m_minor = re.match(r"^(?:#{4,6})\s+(.+)$", stripped)
        m_major = re.match(r"^(?:#{1,3})\s+(.+)$", stripped)

        if re.match(r"^#\s+(?:Register|Configure|Install|Run|Set)\b", stripped):
            # A shell comment line and the command lines that follow it up to the next blank line.
            block = [stripped]
            while i < len(lines) and not lines[i].strip():
                i += 1
            while i < len(lines) and lines[i].strip():
                block.append(lines[i].rstrip())
                i += 1
            result.extend(["```bash", *block, "```"])
        elif m_minor:
            minor_count += 1
            raw_title = m_minor.group(1).strip()
            clean_title = re.sub(r"^(?:[A-Za-z]|\d+)(?:[\.\:\)]|\s+)\s*", "", raw_title).strip()
            if not clean_title:
                clean_title = raw_title
            prefix = f"{major_count}.{minor_count}." if major_count > 0 else f"{minor_count}."
            if result and result[-1].strip():
                result.append("")
            result.append(f"**{prefix} {clean_title}**")
        elif m_major:
            major_count += 1
            minor_count = 0
            raw_title = m_major.group(1).strip()
            clean_title = re.sub(r"^(?:\d+)(?:[\.\:\)]|\s+)\s*", "", raw_title).strip()
            if not clean_title:
                clean_title = raw_title
            if result and result[-1].strip():
                result.append("")
            result.append(f"**{major_count}. {clean_title}**")
        elif re.match(r"^#\d+\s+in\s+Development\s+Priority", stripped):
            result.append(f"* **Rank {stripped[1:]}**")
        else:
            result.append(line)

    return "\n".join(result)
