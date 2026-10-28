from pathlib import Path
import socket
import subprocess
import sys

import pytest
from playwright.sync_api import sync_playwright

from notebooklm_mindmap_extractor import build_hierarchy
from notebooklm_mindmap_extractor.extractor import (
    click_and_capture_response, extract_mindmap_nodes, find_mindmap_frame, open_mindmap, traverse_and_populate,
)


pytestmark = pytest.mark.browser


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        fixture = Path(__file__).parent / "fixtures" / "mindmap.html"
        page.set_content(fixture.read_text(encoding="utf-8"))
        yield page
        browser.close()


def test_real_dom_to_markdown_waits_for_fresh_completed_responses(page):
    nodes = extract_mindmap_nodes(page)
    assert len(nodes) == 2  # SVG wrapper and nested text must not duplicate nodes.
    root, = build_hierarchy(nodes)
    markdown = traverse_and_populate(page, root, 5)
    assert '# Token MindMap\n' in markdown
    assert '## User\'s "tokens"\n' in markdown
    assert 'Grounded response for User\'s "tokens": complete.' in markdown
    assert "Old response" not in markdown


def test_live_smoke_limit_only_clicks_requested_nodes(page):
    root, = build_hierarchy(extract_mindmap_nodes(page))
    markdown = traverse_and_populate(page, root, 5, [1])
    assert "# Token MindMap" in markdown
    assert "## User" not in markdown
    assert page.locator(".chat-message-response").count() == 2


def test_missing_response_fails_instead_of_exporting_stale_text(page):
    root, = build_hierarchy(extract_mindmap_nodes(page))
    page.evaluate("window.suppressResponse = true")
    with pytest.raises(RuntimeError, match="Timed out waiting for a new response"):
        click_and_capture_response(page, root, 1)


def test_artifact_button_is_clicked_instead_of_duplicate_tooltip(page):
    page.set_content('''
        <span id="map-label">Token MindMap</span>
        <div role="tooltip" style="display:none">Token MindMap</div>
        <button aria-labelledby="map-label" onclick="this.dataset.clicked='yes'">Open</button>
    ''')
    open_mindmap(page, "Token MindMap")
    assert page.get_by_role("button").get_attribute("data-clicked") == "yes"


def test_already_open_artifact_is_not_clicked_again(page):
    page.set_content('<input aria-label="Artifact title" value="Token MindMap">')
    open_mindmap(page, "Token MindMap")
    assert page.get_by_role("textbox").input_value() == "Token MindMap"


def test_embedded_tree_captures_completed_parent_page_responses(page):
    fixture = Path(__file__).parent / "fixtures" / "embedded_mindmap.html"
    page.set_content(fixture.read_text(encoding="utf-8"))
    mindmap = find_mindmap_frame(page)
    assert mindmap != page.main_frame
    nodes = extract_mindmap_nodes(mindmap)
    assert [node["title"] for node in nodes] == ["Root", "Child"]
    root, = build_hierarchy(nodes)
    markdown = traverse_and_populate(page, root, 6, [2], mindmap)
    assert "# Root\n\nCompleted response for Root" in markdown
    assert "## Child\n\nCompleted response for Child" in markdown
    assert "Partial" not in markdown
    assert "Thoughts" not in markdown
    assert "Old response" not in markdown


def test_unloaded_map_reports_clear_error(page):
    page.set_content('<iframe title="Empty viewer"></iframe>')
    with pytest.raises(RuntimeError, match="finish loading"):
        find_mindmap_frame(page, timeout_sec=0.2)


def test_installed_cli_cdp_round_trip(tmp_path):
    """Exercise the installed entry point over real CDP, without contacting Google."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=[f"--remote-debugging-port={port}"])
        page = browser.new_page()
        fixture = Path(__file__).parent / "fixtures" / "mindmap.html"
        url = "https://notebook.google.com/notebook/local-fixture"
        page.route("**/*", lambda route: route.fulfill(
            status=200, content_type="text/html", body=fixture.read_text(encoding="utf-8")
        ))
        page.goto(url)
        output = tmp_path / "nested" / "smoke.md"
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-m", "notebooklm_mindmap_extractor",
                 "--cdp-url", f"http://127.0.0.1:{port}", "--notebook-url", url,
                 "--mindmap-title", "Token MindMap",
                 "--max-nodes", "1", "--output", str(output)],
                cwd=tmp_path, capture_output=True, text=True, timeout=45,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            assert output.read_text(encoding="utf-8") == (
                "# Token MindMap\n\nGrounded response for Token MindMap: complete.\n"
            )
            assert page.title() == "Local mindmap test fixture"  # Attached Chrome stays open.
        finally:
            browser.close()
