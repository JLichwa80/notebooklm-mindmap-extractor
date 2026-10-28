# NotebookLM Mindmap Extractor

Compile a NotebookLM mindmap and its generated responses into a hierarchical Markdown document using Playwright and Chrome DevTools Protocol (CDP).

## Install

Requires Python 3.10 or newer, Playwright 1.64.1 or newer, and Chrome.

```bash
pip install notebooklm-mindmap-extractor
```

Or from a checkout:

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
```

For an existing wheel, use `python -m pip install dist/<wheel-filename>.whl`.
The package installs the `notebooklm-mindmap-extractor` command. The module entry point is `python -m notebooklm_mindmap_extractor`.

## Prepare Chrome

Launch Chrome with a dedicated data directory and a local debugging port. Sign in to Google manually in that browser, open your notebook, and open the target mindmap. The extractor attaches to this session; it does not automate sign-in.

Windows PowerShell (adjust the executable path if needed):

```powershell
& 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe' --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="$env:LOCALAPPDATA\NotebookLMMindmapChrome"
```

macOS:

```bash
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --remote-debugging-port=9222 --user-data-dir="$HOME/.notebooklm-mindmap-chrome"
```

Linux:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.notebooklm-mindmap-chrome"
```

Chrome 136 and newer require a non-default data directory for remote debugging. See [Chrome's remote debugging guidance](https://developer.chrome.com/blog/remote-debugging-port). Keep the endpoint local and exclude profiles and private exports from source control.

## Extract

With the target mindmap already open:

```bash
notebooklm-mindmap-extractor --output output/mindmap.md
```

Select a particular notebook and open a map by its exact visible title:

```bash
notebooklm-mindmap-extractor --notebook "Token Buffet" --mindmap-title "Token MindMap" --max-nodes 1 --output output/token-smoke.md
```

Both `notebook.google.com` and `notebooklm.google.com` notebook links, IDs, and titles are accepted.

| Option | Default | Purpose |
| --- | --- | --- |
| `--cdp-url` | `http://localhost:9222` | Attach to a running Chrome session |
| `--notebook` | (Required for extraction) | Select notebook by ID, title, or URL |
| `--mindmap-title` | (Required for extraction) | Click the exact visible map title |
| `--output` | `None` (compiled via `--build`) | UTF-8 Markdown destination |
| `--folder-output` | `handbook` | Save docs in versioned node folder hierarchy |
| `--extract-only` | `False` | Only capture raw text into `<run>/tmp`; clean later with `--clean` |
| `--clean` | `None` | Offline: clean the saved raw `.txt` files of a run folder (or its `tmp` folder) into `.md` files |
| `--build` | `None` | Recompile document from run folder offline (supports relative path) |
| `--outline` | `doc_full_order.yml` in run dir | Custom order YAML for document compilation |
| `--wait-timeout` | `120` | Maximum response wait in seconds per node |
| `--max-nodes` | All discovered nodes | Limit generation for smoke testing |
| `--dry-run` | `False` | Fast structure test without waiting for chat generations |

## Two steps: capture, then clean

Extraction runs in two steps so you never have to re-extract to adjust the output.

1. **Capture** saves each node's text exactly as the page shows it, with no processing, to `<run>/tmp/`. The `.txt` files mirror the folder layout of the final `.md` files (`Overview.txt` for the root and for nodes with children, `<title>.txt` for leaves).
2. **Clean** (`cleaner.py`) reads those files and writes the `.md` files next to `tmp/`. It removes citations, page icons and the follow-up prompt, turns tables into Markdown tables, fences box diagrams, and separates paragraphs.

A normal run does both. To do them separately:

```powershell
# capture only
notebooklm-mindmap-extractor --notebook "My Notebook" --mindmap-title "My Map" --extract-only

# clean from the saved raw files, as often as needed, with no browser
notebooklm-mindmap-extractor --clean handbook/my-notebook/my-map-20261028_152843
```

The page text carries no markup, so bold, bullets and heading markers are not available; headings and list items arrive as plain paragraphs. `--build` only combines the cleaned `.md` files into one document and does no cleaning.

## Recompiling from Nodes and Customizing with doc_full_order.yml

Extraction automatically saves a `doc_full_order.yml` file inside your versioned run directory under `--folder-output`. It establishes the parent and child hierarchy with explicit `order:` attributes:

```yaml
- nodeTitle: "Token Buffet AI Subscription Hub"
  childNodes:
    - title: "Core Architecture"
      order: 1
    - title: "Smart Routing & Tiers"
      order: 2

- nodeTitle: "Core Architecture"
  childNodes:
    - title: "Proxy Runtime: Standard HTTP server"
      order: 1
    - title: "Local Router: Port 8090"
      order: 2
```

You can edit this file to change order numbers, reorder items, or omit sections.

To recompile the unified document offline using a relative path, without launching Chrome or NotebookLM:

```powershell
python -m notebooklm_mindmap_extractor --build handbook/token-buffet-ai-subscription-hub-20261027_175222
```

Or using a custom outline file:

```powershell
python -m notebooklm_mindmap_extractor --build handbook/token-buffet-ai-subscription-hub-20261027_175222 --outline custom_order.yml --output output/custom_mindmap.md
```

Extraction clicks nodes and triggers NotebookLM generation. A missing or stale response causes a nonzero exit instead of a success placeholder. The output is written after all requested nodes complete.

## Development and tests

```bash
python -m pip install -e ".[dev]"
python -m playwright install chromium
python -m pytest
python -m build
python -m twine check dist/*
```

Tests cover hierarchy reconstruction, the cleaner, and the capture-then-clean pipeline on a saved real extraction (`tests/fixtures/run/`). They do not contact Google or need a browser.

`python -m build` creates a source archive and wheel in `dist/`. Packaging follows the [Python Packaging User Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/). The package is MIT licensed (see `LICENSE`). Releases are published to PyPI by `.github/workflows/publish.yml` when a GitHub Release is published, using Trusted Publishing.

## Project layout

```text
pyproject.toml                       Package metadata, dependencies, console entry point
src/notebooklm_mindmap_extractor/
    __init__.py                     Public data model and hierarchy helper
    __main__.py                     python -m entry point
    cli.py                          Arguments and extraction orchestration
    extractor.py                    Raw capture to tmp/, then the clean step per node
    cleaner.py                      Cleaning of the raw page text
    builder.py                      doc_full_order.yml and combining the .md files
    hierarchy.py                    Parent-child reconstruction
    models.py                       MindmapNode dataclass
tests/                              Unit tests and a saved real extraction (fixtures/run)
```

The former root script is replaced by the installed console and module commands. `requirements.txt` remains an editable-install shortcut.

## Current limitations

The extractor supports mindmap trees rendered directly in the notebook or inside the embedded Studio App viewer. Wait for the viewer to finish loading before starting. Node clicks occur inside the map frame while generated answers are captured from the notebook chat panel. The command leaves the signed-in browser open and never reloads the notebook.

NotebookLM selectors may need updates when Google's UI changes. Only rendered nodes are discovered; collapsed branches are not automatically expanded. Complete accessibility levels use DOM preorder. Coordinate inference assumes a left-to-right map and uses the nearest parent vertically, so inspect the resulting hierarchy. Markdown headings are capped at six levels. A live test against a signed-in notebook is separate from the local fixture tests.
