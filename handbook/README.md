# Handbook Directory

This directory stores extracted documentation handbooks generated from NotebookLM mindmaps.

## Overview

Each extraction creates an isolated, timestamped run directory under `handbook/`:

```text
handbook/
├── README.md                                          # This guide
└── <notebook-slug>-<YYYYMMDD_HHMMSS>/                 # Versioned run directory
    ├── Overview.md                                    # Root mindmap overview
    ├── outline.yml                                    # Flattened compilation manifest
    ├── <Branch 1>/
    │   ├── Overview.md                                # Branch overview
    │   ├── <Leaf Node A>.md                           # Node documentation
    │   └── <Leaf Node B>.md
    └── <Branch 2>/
        ├── Overview.md
        └── <Leaf Node C>.md
```

Existing run directories are never overwritten or deleted. Each run persists independently so past extractions remain intact.

## Workflow

The handbook generator follows a two-stage process: extraction and compilation.

### 1. Extract Mindmap to Node Hierarchy

Running extraction discovers all mindmap branches, captures generated node responses, and populates the folder tree with an `outline.yml` manifest:

```bash
python -m notebooklm_mindmap_extractor
```

For a rapid structure test without querying chat answers:

```bash
python -m notebooklm_mindmap_extractor --dry-run
```

Extraction writes `Overview.md`, the branch subdirectories, node Markdown files, and `outline.yml`. It deliberately stops here without compiling the monolithic full document so you can review and adjust the outline.

### 2. Review and Customize `outline.yml`

Inside each run folder, `outline.yml` contains a clean, flattened list of all sections in default preorder traversal:

```yaml
- title: "Token Buffet AI Subscription Hub"
  file: "Overview.md"
  level: 1

- title: "Core Architecture"
  file: "Core Architecture/Overview.md"
  level: 2

- title: "Proxy Runtime: Standard HTTP server"
  file: "Core Architecture/Proxy Runtime- Standard HTTP server.md"
  level: 3
```

You can edit this file directly to customize your output:
- **Reorder sections**: Cut and paste blocks to rearrange chapters and topics.
- **Adjust heading depth**: Change `level` (e.g. from `3` to `2`) to promote or demote sections.
- **Rename headings**: Edit the `title` field to adjust the rendered Markdown heading without modifying source files.
- **Omit topics**: Comment out (`#`) or remove blocks you do not want in the compiled output.

### 3. Compile the Full Handbook

Once `outline.yml` matches your desired structure, compile the final unified Markdown handbook:

```bash
python -m notebooklm_mindmap_extractor --build handbook/<run-folder>
```

For example:

```bash
python -m notebooklm_mindmap_extractor --build handbook/token-buffet-ai-subscription-hub-20261027_175222
```

This reads `doc_full_order.yml` (or `outline.yml`), stitches the files together using the specified heading levels and order, and writes `<notebook-slug>-full-reference.md` directly into the run folder without requiring Chrome or network access.

To compile to a custom destination:

```bash
python -m notebooklm_mindmap_extractor --build handbook/<run-folder> --output custom_handbook.md
```
