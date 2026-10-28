# NotebookLM Mindmap Extractor

Turn a NotebookLM mindmap into a folder of Markdown files, one per node. For every node in your mindmap, the tool asks NotebookLM for its explanation, saves the answer, cleans it up, and organizes everything in the same hierarchy as the map. You can then combine the files into one document.

It works with your own signed-in Chrome. It never sees your Google password and never signs in for you.

## What you need

- Python 3.10 or newer
- Google Chrome
- A NotebookLM notebook that already has a mindmap

## Install

```bash
pip install notebooklm-mindmap-extractor
```

This installs the `notebooklm-mindmap-extractor` command.

## Step 1: Start Chrome with a debugging port

The tool controls a Chrome window that you start yourself. Close other windows of that Chrome profile first, then start Chrome like this.

Windows (PowerShell):

```powershell
& 'C:\Program Files\Google\Chrome\Application\chrome.exe' --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="$env:LOCALAPPDATA\NotebookLMMindmapChrome"
```

macOS:

```bash
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --remote-debugging-port=9222 --user-data-dir="$HOME/.notebooklm-mindmap-chrome"
```

Linux:

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.notebooklm-mindmap-chrome"
```

Chrome only allows the debugging port with a separate `--user-data-dir`, so the tool uses its own folder. The first launch creates it. Sign in to Google once in that window. Your sign-in and settings are kept in that folder, so every later run starts already signed in. Your normal Chrome profile is not touched. Keep the port local and do not share it.

## Step 2: Open your notebook and mindmap

In that Chrome window, open your notebook at notebooklm.google.com and wait for the page to load. The tool can open the mindmap for you by its title, so you do not have to open it yourself.

## Step 3: Run the extractor

```bash
notebooklm-mindmap-extractor --notebook "My Notebook" --mindmap-title "My Mindmap"
```

- `--notebook` is the notebook's name, ID, or URL.
- `--mindmap-title` is the exact title of the mindmap as shown in NotebookLM.

The tool clicks each node in turn and waits for NotebookLM to answer, so a large map takes a while. Leave the Chrome window alone while it runs. Each node can take up to two minutes by default.

To try it on a small part first, limit the number of nodes:

```bash
notebooklm-mindmap-extractor --notebook "My Notebook" --mindmap-title "My Mindmap" --max-nodes 3
```

## What you get

Each run creates its own dated folder, so runs never overwrite each other:

```text
handbook/
  my-notebook/
    my-mindmap-20261028_152843/
      Overview.md                  the root node
      Chapter One/
        Overview.md                a node that has children
        Leaf Node.md               a node without children
      doc_full_order.yml           the order used to combine the files
      tmp/                         the raw text exactly as NotebookLM showed it
```

The Markdown files have citations, page icons and the closing "Would you like to..." prompt removed. Tables become Markdown tables. The raw page text carries no formatting, so bold, bullets and heading markers are not available: headings and list items arrive as plain paragraphs.

Use `--folder-output` to save somewhere other than `handbook`.

## Combine everything into one document

To merge all the node files into a single Markdown document, with each node under a heading that matches its level in the map:

```bash
notebooklm-mindmap-extractor --build handbook/my-notebook/my-mindmap-20261028_152843 --output my-mindmap.md
```

This works offline, with no Chrome. To change the order or drop sections first, edit `doc_full_order.yml` in the run folder and change the `order:` numbers:

```yaml
- nodeTitle: "My Mindmap"
  childNodes:
    - title: "Chapter One"
      order: 1
    - title: "Chapter Two"
      order: 2
```

You can also point to a different file with `--outline custom_order.yml`.

## Capture now, clean later

Extraction is the slow part, so you can do it once and clean the results as many times as you like.

Capture only. This saves the raw text into the run's `tmp` folder and stops:

```bash
notebooklm-mindmap-extractor --notebook "My Notebook" --mindmap-title "My Mindmap" --extract-only
```

Clean from the saved raw files. This needs no Chrome and no internet:

```bash
notebooklm-mindmap-extractor --clean handbook/my-notebook/my-mindmap-20261028_152843
```

## All options

| Option | Default | What it does |
| --- | --- | --- |
| `--notebook`, `-n` | none | Notebook name, ID, or URL (required for extraction) |
| `--mindmap-title`, `-m` | none | Exact mindmap title (required for extraction) |
| `--cdp-url` | `http://localhost:9222` | Where to find your Chrome debugging port |
| `--folder-output`, `-f` | `handbook` | Folder for the dated run folders |
| `--wait-timeout`, `-w` | `120` | Seconds to wait for each node's answer |
| `--max-nodes` | all | Only capture this many nodes |
| `--extract-only` | off | Save raw text only, skip cleaning |
| `--clean FOLDER` | none | Clean the raw files of a saved run, offline |
| `--build FOLDER` | none | Combine a run's Markdown files into one document, offline |
| `--output`, `-o` | none | Path of the combined document |
| `--outline FILE` | the run's `doc_full_order.yml` | Custom order file for `--build` |
| `--dry-run` | off | Create the folder structure without waiting for answers |

## Troubleshooting

**"Chrome debugging is not running"**: Chrome was not started with `--remote-debugging-port=9222`, or it is on a different port. Close every window of that profile and start Chrome again with the command in Step 1, or pass `--cdp-url` with the right address.

**"No matching NotebookLM tab"**: open the notebook in the Chrome window you started for the tool, and check that you are signed in.

**"No rendered mindmap nodes found"**: wait for the mindmap to finish loading, then run again. Only nodes that are currently drawn are found, so expand branches you want included.

**"Timed out waiting for a new response"**: NotebookLM was slow or did not answer. Run again with a larger `--wait-timeout`, for example `--wait-timeout 240`.

**Your answers look different from before**: NotebookLM generates each answer fresh, so wording can change between runs. Use the dated folders to compare.

## Limits

- NotebookLM can change its page at any time, which may break the tool until it is updated.
- Only nodes drawn on screen are discovered. Collapsed branches are not expanded for you.
- Each node triggers a real NotebookLM request, so a large map uses a lot of your chat quota.
- Use it on your own notebooks and respect Google's terms of service.

## License

MIT. See `LICENSE`.

## For developers

```bash
git clone https://github.com/JLichwa80/notebooklm-mindmap-extractor
cd notebooklm-mindmap-extractor
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
```

Capture saves the page text unprocessed (`extractor.py`). All cleaning lives in `cleaner.py`, and `builder.py` only combines the cleaned files. The tests run on a saved real extraction in `tests/fixtures/run/`, so they need no browser and do not contact Google. Releases are published to PyPI by `.github/workflows/publish.yml` when a GitHub Release is published.
