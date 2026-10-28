"""Playwright browser operations and recursive Markdown compilation."""

import re
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from playwright.sync_api import Frame, Page, TimeoutError as PlaywrightTimeoutError

from .builder import normalize_children_order, parse_outline_yaml
from .models import MindmapNode
from .cleaner import clean_extracted_text


NODE_SELECTOR = 'svg g[role="treeitem"], svg g.node, svg text, [data-node-id]'
RESPONSE_SELECTOR = (
    'mat-card.to-user-message-card-content .message-text-content, '
    '.chat-message-response, [role="region"][aria-label*="Response"], '
    '.model-response-text, .note-content, .editor-container, .response-container'
)
STREAMING_SELECTOR = (
    '.streaming-indicator, [aria-label*="Generating"], .typing, '
    'button[aria-label="Stop generating"]'
)
# Page-side function shared by _response_state and find_card_for_node. The raw capture is the
# element's visible text exactly as the page renders it; all cleaning happens in cleaner.py.
CLEAN_NODE_TEXT_JS = r"""const cleanNodeText = el => el.innerText.trim();"""


def find_notebook_page(browser_context, notebook_target: Optional[str] = None) -> Page:
    """Select a notebook tab matching ID, title, or URL. Defaults to open notebook."""
    notebook_pages = []
    for page in browser_context.pages:
        url = urlparse(page.url)
        if (url.hostname in {"notebooklm.google.com", "notebook.google.com"}
                and url.path.startswith("/notebook/")):
            notebook_pages.append(page)
    if not notebook_pages:
        raise RuntimeError("No matching NotebookLM tab. Open the target notebook and mindmap first.")
    if not notebook_target:
        if len(notebook_pages) == 1:
            return notebook_pages[0]
        raise RuntimeError("Multiple notebooks are open. Select one with --notebook (by ID, title, or URL).")
    target_clean = notebook_target.strip()
    if target_clean.startswith("http://") or target_clean.startswith("https://"):
        target_path = urlparse(target_clean).path.rstrip("/")
        for page in notebook_pages:
            if urlparse(page.url).path.rstrip("/") == target_path:
                return page
    for page in notebook_pages:
        path_parts = urlparse(page.url).path.strip("/").split("/")
        if len(path_parts) >= 2:
            nb_id = path_parts[1]
            if target_clean == nb_id or target_clean in page.url:
                return page
    for page in notebook_pages:
        try:
            tab_title = page.title() if callable(getattr(page, "title", None)) else getattr(page, "title", "")
        except Exception:
            tab_title = ""
        if target_clean.lower() in tab_title.lower():
            return page
    if len(notebook_pages) == 1:
        return notebook_pages[0]
    raise RuntimeError(f"No NotebookLM tab found matching '{notebook_target}'.")


def open_mindmap(page: Page, title: str) -> None:
    """Open the requested mindmap by title, switching artifacts if another is open."""
    clean_target = title.strip().lower()
    try:
        current = page.get_by_role("textbox", name="Artifact title", exact=True)
        if current.count() == 1 and current.input_value().strip().lower() == clean_target:
            return
    except Exception:
        pass

    # Look for button or artifact chip matching title
    clicked = page.evaluate("""targetTitle => {
        const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const target = norm(targetTitle);
        const candidates = Array.from(document.querySelectorAll(
            'button, [role="button"], mat-chip, .artifact-item, .studio-card, [data-artifact-title]'
        ));
        for (const el of candidates) {
            const label = norm(el.getAttribute('aria-label') || el.innerText || el.textContent || '');
            if (label.includes(target)) {
                const btn = el.closest('button') || el;
                btn.scrollIntoView();
                btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                return true;
            }
        }
        return false;
    }""", title)

    if not clicked:
        pattern = re.compile(r"^" + re.escape(title) + r"(?:\s|$)", re.IGNORECASE)
        btn = page.get_by_role("button", name=pattern)
        if btn.count() > 0:
            btn.first.click(timeout=10000)
        else:
            page.get_by_text(title, exact=False).first.click(timeout=10000)

    page.wait_for_timeout(1000)


def find_mindmap_frame(page: Page, timeout_sec: float = 30) -> Frame:
    """Locate a rendered tree in the page or one of its embedded frames."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        frames = [frame for frame in page.frames
                  if frame.locator(NODE_SELECTOR).first.is_visible()]
        if len(frames) > 1:
            raise RuntimeError("Multiple rendered mindmaps found. Leave only the target map open.")
        if frames:
            return frames[0]
        page.wait_for_timeout(200)
    raise RuntimeError("No rendered mindmap nodes found. Wait for the selected map to finish loading.")


def expand_mindmap_nodes(frame, max_passes: int = 5) -> int:
    """Expand collapsed branches in the mindmap viewer."""
    total_expanded = 0
    for _ in range(max_passes):
        expanded = frame.evaluate("""() => {
            const nodes = Array.from(document.querySelectorAll('g.node, g[role="treeitem"]'));
            let clicked = 0;
            for (const n of nodes) {
                const sym = n.querySelector('.expand-symbol');
                if (sym && sym.textContent.trim() === '>') {
                    const circle = n.querySelector('circle') || sym;
                    circle.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                    clicked++;
                }
            }
            return clicked;
        }""")
        if not expanded:
            break
        total_expanded += expanded
        frame.page.wait_for_timeout(400)
    if total_expanded > 0:
        print(f"[+] Auto-expanded {total_expanded} mindmap node branch(es).")
    return total_expanded


def extract_mindmap_nodes(page, auto_expand: bool = True) -> List[Dict]:
    """Read visible nodes; coordinates refer to the current viewport."""
    try:
        page.wait_for_selector(NODE_SELECTOR, timeout=30000)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError("No mindmap nodes found. Open a loaded Mind Map first.") from exc
    if auto_expand:
        expand_mindmap_nodes(page)
    nodes = page.evaluate("""selector => {
        const candidates = Array.from(document.querySelectorAll(selector));
        const results = [];
        const seen = new Set();
        for (const el of candidates) {
            if (el.matches('svg text') && el.closest('g.node, g[role="treeitem"], [data-node-id]')) continue;
            const label = el.querySelector('.node-name');
            const title = (label ? label.textContent : el.innerText || el.textContent || '').trim();
            const rect = el.getBoundingClientRect();
            if (!title || rect.width === 0 || rect.height === 0) continue;
            const key = title + '_' + Math.round(rect.x / 10) + '_' + Math.round(rect.y / 10);
            if (seen.has(key)) continue;
            seen.add(key);
            const d = el.__data__;
            const d3_id = (d && d.id !== undefined) ? String(d.id) : null;
            const parent_id = (d && d.parent && d.parent.id !== undefined) ? String(d.parent.id) : null;
            const level = (d && d.depth !== undefined)
                ? d.depth + 1
                : (el.hasAttribute('aria-level') ? Number(el.getAttribute('aria-level')) : null);
            results.push({
                id: d3_id || el.getAttribute('data-node-id') || 'node_' + results.length,
                d3_id,
                parent_id,
                title, x: rect.x, y: rect.y,
                level,
                aria_label: el.getAttribute('aria-label') || ''
            });
        }
        return results;
    }""", NODE_SELECTOR)
    if not nodes:
        raise RuntimeError("No mindmap nodes found. Ensure the target mindmap is open and loaded.")
    print(f"[+] Found {len(nodes)} mindmap node elements.")
    return nodes




def _response_state(page: Page) -> Dict:
    return page.evaluate("""selectors => {
        """ + CLEAN_NODE_TEXT_JS + """

        const responses = Array.from(document.querySelectorAll(selectors.response))
            .filter(el => el.getBoundingClientRect().width > 0);
        const last = responses[responses.length - 1];
        const streaming = Array.from(document.querySelectorAll(selectors.streaming))
            .some(el => el.getBoundingClientRect().width > 0);
        const card = last ? last.closest('mat-card.to-user-message-card-content') : null;
        const complete = !card || !!card.querySelector('button[aria-label="Copy model response to clipboard"]');
        let text = '';
        if (last) {
            text = cleanNodeText(last);
        }
        return {count: responses.length, text, streaming: streaming || !complete};
    }""", {"response": RESPONSE_SELECTOR, "streaming": STREAMING_SELECTOR})


def click_node(scope, node: MindmapNode) -> None:
    """Click a mindmap node directly in DOM to avoid viewport clipping and pointer interception."""
    clicked = scope.evaluate("""info => {
        const nodes = Array.from(document.querySelectorAll('g.node, g[role="treeitem"]'));
        for (const n of nodes) {
            const nameEl = n.querySelector('.node-name');
            const name = (nameEl ? nameEl.textContent : n.innerText || n.textContent || '').trim();
            const label = n.getAttribute('aria-label') || '';
            if ((info.aria_label && label === info.aria_label) || (name && name === info.title)) {
                const target = n.querySelector('rect') || n;
                target.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                return true;
            }
        }
        return false;
    }""", {"aria_label": node.aria_label, "title": node.title})
    if not clicked:
        if node.aria_label:
            item = scope.get_by_role("treeitem", name=node.aria_label, exact=True)
            target = item.locator("rect") if item.locator("rect").count() == 1 else item
            target.click(force=True, timeout=5000)
        else:
            scope.get_by_text(node.title, exact=True).first.click(force=True, timeout=5000)


def find_card_for_node(page: Page, title: str) -> Optional[str]:
    """Find the completed response card specifically generated for this node title."""
    clean_title = " ".join(title.split())
    card_text = page.evaluate("""title => {
        """ + CLEAN_NODE_TEXT_JS + """

        const norm = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
        const target = norm(title);
        const userMsgs = Array.from(document.querySelectorAll('chat-message.individual-message'));
        for (let i = userMsgs.length - 1; i >= 0; i--) {
            const msg = userMsgs[i];
            const fromCard = msg.querySelector('mat-card.from-user-message-card-content');
            if (fromCard && norm(fromCard.innerText).includes(target)) {
                const nextMsg = msg.nextElementSibling;
                if (nextMsg) {
                    const toCard = nextMsg.querySelector('mat-card.to-user-message-card-content') || nextMsg;
                    return cleanNodeText(toCard);
                }
            }
        }
        return null;
    }""", clean_title)
    return card_text or None


def click_and_capture_response(page: Page, node: MindmapNode, timeout_sec: int, mindmap=None) -> str:
    """Wait for a fresh response and stable text instead of returning stale chat."""
    print(f"[*] Processing [Level {node.level}]: {node.title}")
    before = _response_state(page)
    scope = mindmap if mindmap is not None else page
    click_node(scope, node)
    deadline = time.monotonic() + timeout_sec
    previous = None
    stable_since = time.monotonic()
    started_streaming = False
    while time.monotonic() < deadline:
        state = _response_state(page)
        if state["streaming"] or state["count"] > before["count"]:
            started_streaming = True
        if started_streaming:
            fresh = state["count"] > before["count"] or state["text"] != before["text"]
            text = state["text"]
            if text != previous or state["streaming"]:
                previous = text
                stable_since = time.monotonic()
            if fresh and text and not state["streaming"] and time.monotonic() - stable_since >= 1.0:
                return text
        else:
            if time.monotonic() - (deadline - timeout_sec) >= 3.0:
                existing = find_card_for_node(page, node.title)
                if existing:
                    return existing
        page.wait_for_timeout(200)
    raise RuntimeError(f"Timed out waiting for a new response for node: {node.title}")


def toggle_node(frame, node: MindmapNode, expand: bool = True) -> bool:
    """Toggle a node's expand/collapse circle in the mindmap viewer."""
    target_sym = ">" if expand else "<"
    return frame.evaluate("""({ info, target_sym }) => {
        const nodes = Array.from(document.querySelectorAll('g.node, g[role="treeitem"]'));
        for (const n of nodes) {
            const nameEl = n.querySelector('.node-name');
            const name = (nameEl ? nameEl.textContent : n.innerText || '').trim();
            const label = n.getAttribute('aria-label') || '';
            if ((info.aria_label && label === info.aria_label) || (name && name === info.title)) {
                const sym = n.querySelector('.expand-symbol');
                if (sym && sym.textContent.trim() === target_sym) {
                    const circle = n.querySelector('circle') || sym;
                    circle.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                    return true;
                }
            }
        }
        return false;
    }""", {"info": {"aria_label": node.aria_label, "title": node.title}, "target_sym": target_sym})


def sanitize_filename(name: str) -> str:
    """Make title safe for directory and file names across platforms."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "-", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"-+", "-", cleaned).strip("- ")
    return cleaned[:80] or "untitled"


RAW_DIR_NAME = "tmp"


def node_paths(node: MindmapNode, folder: Path, suffix: str):
    """Where a node's file lives under folder (Overview for the root and parents), and its children's folder."""
    safe_title = sanitize_filename(" ".join(node.title.splitlines()))
    if node.level == 1:
        return folder / f"Overview{suffix}", folder
    if node.children:
        return folder / safe_title / f"Overview{suffix}", folder / safe_title
    return folder / f"{safe_title}{suffix}", folder


def traverse_and_populate(
    page: Page, node: MindmapNode, timeout_sec: int, remaining: Optional[List[int]] = None,
    mindmap=None, raw_dir: Optional[Path] = None, dry_run: bool = False,
) -> None:
    """Step 1: capture each node's raw text in preorder and save it uncleaned, mirroring the .md layout."""
    if remaining is not None:
        if remaining[0] <= 0:
            return
        remaining[0] -= 1

    if dry_run:
        print(f"[*] Processing [Level {node.level}] (structure): {node.title}")
        raw_text = find_card_for_node(page, node.title) or ""
    else:
        raw_text = click_and_capture_response(page, node, timeout_sec, mindmap)

    raw_file, child_dir = node_paths(node, raw_dir, ".txt")
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text(raw_text, encoding="utf-8", newline="")
    node.raw_file = str(raw_file)

    for child in node.children:
        traverse_and_populate(page, child, timeout_sec, remaining, mindmap, child_dir, dry_run)
    if node.children and mindmap and node.level > 1:
        toggle_node(mindmap, node, expand=False)


def clean_run(node: MindmapNode, folder_path: Path) -> str:
    """Step 2: clean each saved raw file and write the node .md files. Returns the compiled sections."""
    if not node.raw_file:
        return ""
    node.content = clean_extracted_text(Path(node.raw_file).read_text(encoding="utf-8", newline=""))

    title = " ".join(node.title.splitlines())
    heading = "#" * min(node.level, 6)
    body = f"\n\n{node.content}\n" if node.content else "\n"
    section = f"\n{heading} {title}{body}"

    node_file, child_dir = node_paths(node, folder_path, ".md")
    node_file.parent.mkdir(parents=True, exist_ok=True)
    node_file.write_text(f"# {title}\n\n{node.content}\n" if node.content else f"# {title}\n", encoding="utf-8")

    return section + "".join(clean_run(child, child_dir) for child in node.children)


def load_run_tree(run_dir: Path) -> List[MindmapNode]:
    """Rebuild the node tree of a saved run from doc_full_order.yml and the raw files in <run_dir>/tmp."""
    entries = parse_outline_yaml((run_dir / "doc_full_order.yml").read_text(encoding="utf-8"))
    children_of = {item["nodeTitle"]: normalize_children_order(item.get("childNodes")) for item in entries}
    raw_dir = run_dir / RAW_DIR_NAME

    def build(title: str, level: int, folder: Path) -> MindmapNode:
        node = MindmapNode("", title, level, 0, 0)
        node.children = [MindmapNode("", child, level + 1, 0, 0) for child in children_of.get(title, [])]
        raw_file, child_dir = node_paths(node, folder, ".txt")
        node.raw_file = str(raw_file) if raw_file.exists() else ""  # absent when the run was limited by --max-nodes
        node.children = [build(child.title, level + 1, child_dir) for child in node.children]
        return node

    child_titles = {child for kids in children_of.values() for child in kids}
    roots = [build(title, 1, raw_dir) for title in children_of if title not in child_titles]
    if not list(raw_dir.rglob("*.txt")):
        raise RuntimeError(f"No raw files found in {raw_dir}")
    return roots
