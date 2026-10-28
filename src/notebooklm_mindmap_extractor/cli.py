"""Command-line entry point for the installed package."""

import argparse
from pathlib import Path
import shutil
import socket
import sys
import time
from typing import Optional, Sequence
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError, sync_playwright

from .builder import (
    build_handbook_from_folder,
    generate_outline_yaml,
    slugify,
)
from .extractor import extract_mindmap_nodes, find_mindmap_frame, find_notebook_page, open_mindmap, traverse_and_populate
from .hierarchy import build_hierarchy


def archive_existing(path: Path) -> Optional[Path]:
    """Safely archive existing file or folder with a timestamp to preserve all output history."""
    if not path.exists():
        return None
    if path.is_file() and path.stat().st_size == 0:
        return None
    if path.is_dir() and not any(path.iterdir()):
        return None

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    parent = path.parent
    try:
        if path.is_dir():
            archive_path = parent / f"{path.name}_backup_{timestamp}"
            shutil.copytree(path, archive_path)
            print(f"[*] Versioned existing output directory -> {archive_path.name}")
            return archive_path
        else:
            archive_path = parent / f"{path.stem}_backup_{timestamp}{path.suffix}"
            shutil.copy2(path, archive_path)
            print(f"[*] Versioned existing output file -> {archive_path.name}")
            return archive_path
    except OSError as e:
        print(f"[-] Could not create archive for {path}: {e}", file=sys.stderr)
        return None


def check_cdp_available(cdp_url: str, timeout_sec: float = 1.5) -> bool:
    """Check if the Chrome DevTools Protocol endpoint is responding."""
    parsed = urlparse(cdp_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 9222
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def positive_integer(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def notebook_target(value: str) -> str:
    """Validate notebook target: URL, ID, or title."""
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        url = urlparse(value)
        if (url.scheme != "https" or url.hostname not in {"notebook.google.com", "notebooklm.google.com"}
                or not url.path.startswith("/notebook/") or not url.path.split("/notebook/", 1)[1]):
            raise argparse.ArgumentTypeError("expected an HTTPS NotebookLM notebook URL")
    return value


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract and compile a NotebookLM mindmap.")
    parser.add_argument("--cdp-url", default="http://localhost:9222", help="Chrome debugging endpoint (default: http://localhost:9222)")
    parser.add_argument(
        "--notebook", "--notebook-url", "--notebook-id", "-n",
        dest="notebook",
        type=notebook_target,
        default=None,
        help="Select notebook by ID, name, or URL (required for extraction)",
    )
    parser.add_argument(
        "--mindmap-title", "--mindmap", "-m",
        dest="mindmap_title",
        default=None,
        help="Open a mindmap by its exact visible title (required for extraction)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Optional path to unified Markdown file (by default, compile offline via --build)",
    )
    parser.add_argument(
        "--folder-output", "-f",
        type=Path,
        default=Path("handbook"),
        help="Parent directory for versioned handbook runs (default: handbook)",
    )
    parser.add_argument(
        "--wait-timeout", "-w",
        type=positive_integer,
        default=120,
        help="Seconds per node response (default: 120)",
    )
    parser.add_argument(
        "--build", "--compile", "--from-nodes",
        dest="build_folder",
        type=Path,
        help="Compile full handbook from a relative or absolute run folder using its doc_full_order.yml",
    )
    parser.add_argument(
        "--outline",
        type=Path,
        help="Path to custom doc_full_order.yml file for ordering",
    )
    parser.add_argument(
        "--dry-run", "--structure-only",
        action="store_true",
        help="Fast structure smoke test: create folder and file tree without querying chat responses",
    )
    parser.add_argument(
        "--max-nodes",
        type=positive_integer,
        help="Limit captured nodes for a live smoke test",
    )
    parser.add_argument(
        "positional",
        nargs="*",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    # Allow positional syntax: e.g. "build <path>" or "<notebook> <mindmap>"
    if args.positional:
        if args.positional[0].lower() == "build":
            if len(args.positional) > 1 and not args.build_folder:
                args.build_folder = Path(args.positional[1])
        else:
            if not args.notebook and len(args.positional) >= 1:
                args.notebook = notebook_target(args.positional[0])
            if not args.mindmap_title and len(args.positional) >= 2:
                args.mindmap_title = args.positional[1]

    if args.build_folder:
        folder = args.build_folder
        if not folder.is_absolute() and not folder.exists():
            base = args.folder_output or Path("handbook")
            candidate = base / folder
            if candidate.exists():
                folder = candidate
        args.build_folder = folder
    else:
        if not args.notebook:
            parser.error("The notebook name, URL, or ID is required (e.g. --notebook 'Notebook Name').")
        if not args.mindmap_title:
            parser.error("The mindmap title is required (e.g. --mindmap-title 'Mindmap Title').")

    args.notebook_url = args.notebook
    return args


def get_notebook_name(page, fallback: Optional[str] = None) -> str:
    """Extract visible notebook name from the page or fall back to argument."""
    try:
        title = page.evaluate("""() => {
            const el = document.querySelector('input[aria-label*="Notebook title" i], textarea.title, .notebook-title');
            if (el && el.value) return el.value.trim();
            if (el && el.textContent) return el.textContent.trim();
            const docTitle = (document.title || '').replace(/\\s*-\\s*NotebookLM.*$/i, '').trim();
            return docTitle || null;
        }""")
        if title:
            return title
    except Exception:
        pass
    if fallback:
        if fallback.startswith("http://") or fallback.startswith("https://"):
            parts = urlparse(fallback).path.strip("/").split("/")
            return parts[-1] if parts else "notebook"
        return fallback
    return "notebook"


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_arguments(argv)
    if args.build_folder:
        try:
            compiled = build_handbook_from_folder(args.build_folder, args.output, args.outline)
            print(f"[+] Recompiled handbook saved to: {compiled}")
            return 0
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"[-] {exc}", file=sys.stderr)
            return 1
    if not check_cdp_available(args.cdp_url):
        print(
            f"[-] Chrome debugging is not running at {args.cdp_url}.\n"
            f"[-] Please start Chrome/Chromium with remote debugging enabled:\n"
            f'    & "chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:LOCALAPPDATA\\Google\\Chrome\\User Data" --profile-directory="Default"',
            file=sys.stderr,
        )
        return 1
    try:
        print(f"[*] Connecting to Chrome session at {args.cdp_url}...")
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(args.cdp_url, timeout=15000)
            page = None
            for context in browser.contexts:
                try:
                    page = find_notebook_page(context, args.notebook)
                    break
                except RuntimeError:
                    continue
            if page is None:
                raise RuntimeError("No matching NotebookLM tab. Open the target notebook in signed-in Chrome.")
            print(f"[+] Attached to: {page.url}")
            if args.mindmap_title:
                open_mindmap(page, args.mindmap_title)
            mindmap = find_mindmap_frame(page)
            roots = build_hierarchy(extract_mindmap_nodes(mindmap))
            remaining = [args.max_nodes] if args.max_nodes else None

            notebook_name = get_notebook_name(page, args.notebook)
            nb_slug = slugify(notebook_name)

            mindmap_name = args.mindmap_title or (roots[0].title if roots else "mindmap")
            mm_slug = slugify(mindmap_name)

            timestamp = time.strftime("%Y%m%d_%H%M%S")

            base_folder = args.folder_output or Path("handbook")
            run_dir = base_folder / nb_slug / f"{mm_slug}-{timestamp}"
            run_dir.mkdir(parents=True, exist_ok=True)

            output_file = args.output
            if output_file:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text("", encoding="utf-8")

            print(f"[*] Creating handbook in: {run_dir}")
            document = "".join(
                traverse_and_populate(
                    page, root, args.wait_timeout, remaining, mindmap, output_file, run_dir, dry_run=args.dry_run
                )
                for root in roots
            )

            outline_path = run_dir / "doc_full_order.yml"
            outline_path.write_text(generate_outline_yaml(roots), encoding="utf-8")

            print(f"[+] Handbook folder created: {run_dir}")
            print(f"[+] Full order outline saved: {outline_path}")
            if output_file:
                if output_file.exists():
                    output_file.write_text(output_file.read_text(encoding="utf-8").strip() + "\n", encoding="utf-8")
                print(f"[+] Full compiled handbook: {output_file}")
            else:
                print(f"[*] Ready for review. Edit doc_full_order.yml, then compile when ready with:")
                print(f"    python -m notebooklm_mindmap_extractor --build \"{run_dir}\"")
        return 0
    except (PlaywrightError, RuntimeError, ValueError, OSError) as exc:
        print(f"[-] {exc}", file=sys.stderr)
        return 1
