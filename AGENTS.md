# Repository Guidelines

## Requirements and rules
All node content generation must happen through NotebookLM

### Extraction & Cleaning Safety Rules
- Never use greedy multiline regexes (`re.DOTALL`, `.*`, `[\s\S]*`) for stripping UI elements, follow-up questions, or citations. Text cleaning must be strictly line-bounded or anchored to the tail of the document so body content is never truncated.
- Before and after modifying extracted markdown files, verify file lengths and line counts. If a transformation empties or drastically reduces body content, abort and report immediately.
- Do not modify or overwrite generated handbook files without an explicit verification step.

## Project Structure & Module Organization

This repository is a small Python CLI for compiling NotebookLM mindmaps into Markdown.

- `notebooklm_mindmap_extractor.py` contains argument parsing, Playwright CDP connection, DOM extraction, hierarchy reconstruction, response capture, and Markdown output.
- `requirements.txt` declares the Playwright dependency.
- `README.md` documents setup, browser preparation, and CLI usage.

There are no separate source, test, or asset directories. Keep changes focused on the existing script unless a larger structure is justified.

## Build, Test, and Development Commands

Use Python 3.9 or newer. No build step is configured.

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python notebooklm_mindmap_extractor.py --output my_notes.md
```

The first two commands install dependencies and browser binaries. Extraction requires Chrome running with remote debugging enabled and the target NotebookLM mindmap open. See `README.md` for platform-specific launch instructions.

Use `--cdp-url http://localhost:9222` to select the debugging endpoint and `--wait-timeout 60` to set the per-node generation wait limit.

## Coding Style & Naming Conventions

Follow the existing four-space Python indentation, `snake_case` functions and variables, and `PascalCase` dataclasses such as `MindmapNode`. Preserve type annotations and short function docstrings. Keep embedded browser JavaScript readable and selectors close to the extraction logic they support. No formatter or linter is configured.

## Testing Guidelines

Do not run tests (unit tests, pytest, or browser tests) unless specifically instructed to do so by the user. Leave testing to the user. For hierarchy changes, add focused cases under `tests/test_*.py` covering explicit levels, coordinate-derived levels, and parent-child relationships. For browser changes, verify against a prepared NotebookLM tab and inspect generated headings and captured responses. Live extraction clicks nodes and triggers generation, so run it only when explicitly authorized.

## Commit & Pull Request Guidelines

No Git metadata is available in this checkout, so commit conventions cannot be inferred. Use concise imperative subjects, such as `Fix hierarchy inference for sibling nodes`. Pull requests should explain the behavior change, validation performed, and any selector assumptions. Include sanitized output examples when Markdown structure changes.

## Security & Agent Instructions

Keep CDP endpoints local. Do not commit browser profiles, authentication data, or private notebook exports. Follow directions strictly and do not use em dashes as punctuation.
Do not run tests unless specifically instructed to do so by the user. Do not loop or run in circles. Do not perform autonomous troubleshooting unless explicitly asked to do so. When asked a question, answer it directly without initiating unrequested investigative actions. If there are any concerns, blockers, or ambiguities, stop immediately and ask for user direction. The strict limit for any internal action or extended reasoning is 60 seconds.
