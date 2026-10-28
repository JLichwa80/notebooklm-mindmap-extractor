from pathlib import Path
import re
import unittest

from notebooklm_mindmap_extractor.cleaner import clean_extracted_text

RAW = (Path(__file__).parent / "fixtures" / "run" / "tmp" / "Overview.txt").read_text(encoding="utf-8", newline="")


class TestCleanRealNotebookText(unittest.TestCase):
    """Cleaning of the page text exactly as captured (innerText, no processing)."""

    @classmethod
    def setUpClass(cls):
        cls.cleaned = clean_extracted_text(RAW)
        cls.lines = cls.cleaned.splitlines()

    def test_page_chrome_is_removed(self):
        self.assertNotRegex(self.cleaned, r"more_horiz|expand_more|Thoughts")
        self.assertTrue(self.cleaned.startswith("The local AI landscape"))

    def test_citations_are_removed_and_sentences_rejoined(self):
        self.assertFalse([l for l in self.lines if re.fullmatch(r"\s*(\d+|[.,;:])\s*", l)])
        self.assertTrue(self.lines[6].endswith("emit strict JSON schemas mapped directly to application database columns."))
        self.assertIn("modern single-task applications operate", self.cleaned)

    def test_follow_up_prompt_is_removed(self):
        self.assertNotIn("Would you like", self.cleaned)
        self.assertNotIn("💡", self.cleaned)

    def test_table_becomes_markdown_with_no_tabs(self):
        rows = [l for l in self.lines if l.startswith("|")]
        self.assertEqual(len(rows), 6)
        self.assertEqual({r.count("|") for r in rows}, {4})
        self.assertEqual(rows[1], "| --- | --- | --- |")
        self.assertIn("| Primary Interface | Native in-app buttons, hotkeys, cell formulas, or background file watchers. |", rows[2])
        self.assertNotIn("	", self.cleaned)

    def test_blocks_are_separated(self):
        i = self.lines.index("Summary Comparison: Specialized Apps vs. Generic Foundation Frontends")
        self.assertEqual((self.lines[i - 1], self.lines[i + 1]), ("", ""))

    def test_no_words_are_lost(self):
        words = lambda text: re.findall(r"[A-Za-z]{4,}", text)
        body = re.sub(r"expand_more|more_horiz|Thoughts", "", RAW.split("💡")[0])
        self.assertEqual(words(self.cleaned), words(body))


class TestCleanStructures(unittest.TestCase):
    def test_markdown_headings_become_numbered_sections(self):
        out = clean_extracted_text("Intro\n## First\ntext\n#### Sub\nmore\n## Second\nend")
        self.assertNotRegex(out, r"(?m)^#")
        for expected in ("**1. First**", "**1.1. Sub**", "**2. Second**"):
            self.assertIn(expected, out.splitlines())

    def test_shell_comment_and_command_become_bash_block(self):
        out = clean_extracted_text("Register an app:\n\n# Register an Obsidian vault\ntbuffet add-app obsidian --path /tmp/v\n\nDone.")
        self.assertIn("```bash\n# Register an Obsidian vault\ntbuffet add-app obsidian --path /tmp/v\n```", out)

    def test_box_diagram_is_one_text_block(self):
        diagram = "┌────┐\n│ A  │\n└────┘\n   ▼\n┌────┐\n│ B  │\n└────┘"
        out = clean_extracted_text("Before\n\n" + diagram + "\n\nAfter")
        self.assertEqual(out.count("```text"), 1)
        self.assertIn("```text\n" + diagram + "\n```", out)

    def test_ui_button_text_is_removed(self):
        self.assertEqual(clean_extracted_text("Answer text.\n\nSave to note\ncopy\n"), "Answer text.")


if __name__ == "__main__":
    unittest.main()
