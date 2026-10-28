from pathlib import Path
from types import SimpleNamespace

import pytest

from notebooklm_mindmap_extractor.cli import main, parse_arguments
from notebooklm_mindmap_extractor.extractor import find_notebook_page


NOTEBOOK = "https://notebook.google.com/notebook/test-id"


@pytest.mark.parametrize("option", ["--wait-timeout", "--max-nodes"])
@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_reject_invalid_limits(option, value):
    with pytest.raises(SystemExit) as error:
        parse_arguments(["--notebook", "Test Notebook", "--mindmap", "Test Map", option, value])
    assert error.value.code == 2


@pytest.mark.parametrize("url", ["https://example.com/notebook/a", "http://notebook.google.com/notebook/a",
                                 "https://notebook.google.com/notebook/"])
def test_reject_invalid_notebook_url(url):
    with pytest.raises(SystemExit):
        parse_arguments(["--notebook-url", url, "--mindmap", "Test Map"])


def test_extraction_requires_notebook():
    with pytest.raises(SystemExit):
        parse_arguments(["--mindmap", "Test Map"])


def test_extraction_requires_mindmap():
    with pytest.raises(SystemExit):
        parse_arguments(["--notebook", "Test Notebook"])


def test_build_mode_accepts_relative_path_without_notebook_or_mindmap():
    args = parse_arguments(["--build", "relative/path/to/run"])
    assert args.build_folder == Path("relative/path/to/run")


def test_target_notebook_accepts_both_google_hostnames():
    target = SimpleNamespace(url=NOTEBOOK.replace("notebook.google", "notebooklm.google"))
    other = SimpleNamespace(url="https://notebook.google.com/notebook/other")
    assert find_notebook_page(SimpleNamespace(pages=[other, target]), NOTEBOOK) is target


def test_unrelated_tab_is_never_selected():
    with pytest.raises(RuntimeError, match="No matching"):
        find_notebook_page(SimpleNamespace(pages=[SimpleNamespace(url="https://example.com")]))


def test_multiple_notebooks_require_target():
    context = SimpleNamespace(pages=[SimpleNamespace(url=NOTEBOOK),
                                    SimpleNamespace(url=NOTEBOOK + "-other")])
    with pytest.raises(RuntimeError, match="Multiple notebooks"):
        find_notebook_page(context)


def test_find_notebook_by_id():
    target = SimpleNamespace(url="https://notebook.google.com/notebook/abc-123-xyz")
    other = SimpleNamespace(url="https://notebook.google.com/notebook/other-456")
    assert find_notebook_page(SimpleNamespace(pages=[other, target]), "abc-123-xyz") is target


def test_find_notebook_by_title():
    target = SimpleNamespace(url="https://notebook.google.com/notebook/some-id", title="Token Buffet - AI Hub")
    other = SimpleNamespace(url="https://notebook.google.com/notebook/other-id", title="Research Notes")
    assert find_notebook_page(SimpleNamespace(pages=[other, target]), "Token Buffet") is target


def test_single_notebook_auto_selected():
    target = SimpleNamespace(url="https://notebook.google.com/notebook/only-one")
    assert find_notebook_page(SimpleNamespace(pages=[target])) is target


def test_connection_failure_returns_nonzero(capsys, tmp_path):
    output = tmp_path / "no-output.md"
    assert main(["--cdp-url", "http://127.0.0.1:1", "--notebook", "Test Notebook", "--mindmap", "Test Map", "--output", str(output)]) == 1
    assert not output.exists()
    assert "[-] Chrome debugging is not running" in capsys.readouterr().err


def test_get_notebook_name_resolves_title_or_fallback():
    from notebooklm_mindmap_extractor.cli import get_notebook_name

    page_mock = SimpleNamespace(evaluate=lambda code: "My Research Notebook")
    assert get_notebook_name(page_mock, "Fallback") == "My Research Notebook"

    fail_page = SimpleNamespace(evaluate=lambda code: None)
    assert get_notebook_name(fail_page, "Local Fallback") == "Local Fallback"
    assert get_notebook_name(fail_page, "https://notebooklm.google.com/notebook/test-slug-123") == "test-slug-123"


def test_folder_hierarchy_notebook_then_mindmap():
    from notebooklm_mindmap_extractor.builder import slugify
    nb_name = "Token Buffet"
    mm_title = "Token MindMap"
    timestamp = "20261028_120000"

    nb_slug = slugify(nb_name)
    mm_slug = slugify(mm_title)
    base = Path("handbook")
    run_dir = base / nb_slug / f"{mm_slug}-{timestamp}"

    assert run_dir.as_posix() == "handbook/token-buffet/token-mindmap-20261028_120000"
