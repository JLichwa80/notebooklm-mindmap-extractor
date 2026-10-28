from pathlib import Path
import tempfile
import unittest

from notebooklm_mindmap_extractor.models import MindmapNode
from notebooklm_mindmap_extractor.builder import (
    build_handbook_from_folder,
    generate_outline_yaml,
    parse_outline_yaml,
)


class TestBuilder(unittest.TestCase):
    def test_generate_and_parse_doc_full_order_yaml(self):
        root = MindmapNode("1", "Root Node", 1, 0, 0)
        child1 = MindmapNode("2", "Child A", 2, 100, 0)
        child2 = MindmapNode("3", "Child B", 2, 100, 100)
        root.children = [child1, child2]

        yaml_text = generate_outline_yaml([root])
        self.assertIn('nodeTitle: "Root Node"', yaml_text)
        self.assertIn("childNodes:", yaml_text)
        self.assertIn('title: "Child A"', yaml_text)
        self.assertIn("order: 1", yaml_text)
        self.assertIn('title: "Child B"', yaml_text)
        self.assertIn("order: 2", yaml_text)

        parsed = parse_outline_yaml(yaml_text)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["nodeTitle"], "Root Node")
        self.assertEqual(len(parsed[0]["childNodes"]), 2)
        self.assertEqual(parsed[0]["childNodes"][0]["title"], "Child A")
        self.assertEqual(parsed[0]["childNodes"][0]["order"], 1)

    def test_build_handbook_with_doc_full_order_yml(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "my-book-20261027_120000"
            folder.mkdir()
            (folder / "Overview.md").write_text("# Root Book\n\nWelcome to the handbook.", encoding="utf-8")
            (folder / "Child A.md").write_text("# Child A\n\nDetails of Child A.", encoding="utf-8")
            (folder / "Child B.md").write_text("# Child B\n\nDetails of Child B.", encoding="utf-8")
            (folder / "Child C.md").write_text("# Child C\n\nDetails of Child C (omitted).", encoding="utf-8")

            # Custom order: Child B before Child A, Child C is excluded
            order_content = (
                "- nodeTitle: \"Root Book\"\n"
                "  childNodes:\n"
                "    - title: \"Child A\"\n"
                "      order: 2\n"
                "    - title: \"Child B\"\n"
                "      order: 1\n"
            )
            (folder / "doc_full_order.yml").write_text(order_content, encoding="utf-8")

            out_file = build_handbook_from_folder(folder)
            self.assertTrue(out_file.exists())
            self.assertEqual(out_file.name, "my-book-full-reference.md")
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("# Root Book", content)
            self.assertIn("Welcome to the handbook.", content)
            # Verify Child B appears before Child A due to childNodesOrder
            pos_b = content.index("## Child B")
            pos_a = content.index("## Child A")
            self.assertLess(pos_b, pos_a)
            # Verify omitted node Child C is completely excluded
            self.assertNotIn("Child C", content)

    def test_build_handbook_with_numeric_order(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "my-book-numeric-20261027_120000"
            folder.mkdir()
            (folder / "Overview.md").write_text("# Root Book\n\nWelcome to the handbook.", encoding="utf-8")
            (folder / "Child A.md").write_text("# Child A\n\nDetails A.", encoding="utf-8")
            (folder / "Child B.md").write_text("# Child B\n\nDetails B.", encoding="utf-8")

            # Numeric dictionary: 1: Child B, 2: Child A
            order_content = (
                "- nodeTitle: \"Root Book\"\n"
                "  childNodesOrder:\n"
                "    1: \"Child B\"\n"
                "    2: \"Child A\"\n"
            )
            (folder / "doc_full_order.yml").write_text(order_content, encoding="utf-8")

            out_file = build_handbook_from_folder(folder)
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            pos_b = content.index("## Child B")
            pos_a = content.index("## Child A")
            self.assertLess(pos_b, pos_a)

    def test_build_handbook_from_folder_legacy_outline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "my-legacy-book-20261027_120000"
            folder.mkdir()
            (folder / "Overview.md").write_text("# Root Book\n\nWelcome to the handbook.", encoding="utf-8")
            (folder / "Chapter1.md").write_text("# Chapter 1\n\nChapter 1 details.", encoding="utf-8")

            outline_content = (
                "- title: \"Root Book\"\n"
                "  file: \"Overview.md\"\n"
                "  level: 1\n"
                "- title: \"Chapter 1\"\n"
                "  file: \"Chapter1.md\"\n"
                "  level: 2\n"
            )
            (folder / "outline.yml").write_text(outline_content, encoding="utf-8")

            out_file = build_handbook_from_folder(folder)
            self.assertTrue(out_file.exists())
            self.assertEqual(out_file.name, "my-legacy-book-full-reference.md")
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("# Root Book", content)
            self.assertIn("Welcome to the handbook.", content)
            self.assertIn("## Chapter 1", content)
            self.assertIn("Chapter 1 details.", content)

    def test_clean_citations(self):
        from notebooklm_mindmap_extractor.builder import clean_citations
        dirty = (
            "This is a sentence\n1\n\n.\n"
            "Multiple citations\n4\n7\n. Next paragraph\n16\n\n:\n"
            "- list item\n"
        )
        cleaned = clean_citations(dirty)
        self.assertNotIn("\n1\n", cleaned)
        self.assertNotIn("\n4\n", cleaned)
        self.assertNotIn("\n7\n", cleaned)
        self.assertIn("This is a sentence.", cleaned)
        self.assertIn("Multiple citations. Next paragraph:", cleaned)

    def test_clean_follow_up_questions_and_ui_buttons(self):
        from notebooklm_mindmap_extractor.builder import clean_extracted_text
        sample = (
            "This is important architecture documentation.\n\n"
            "┌────────┐\n"
            "│ Router │\n"
            "└────────┘\n\n"
            "More body details.\n\n"
            "Save to note\n"
            "Copy model response to clipboard\n"
            "💡 Would you like to explore setting up an integration?\n"
            "- Suggested Chip 1\n"
            "- Suggested Chip 2\n"
        )
        cleaned = clean_extracted_text(sample)
        self.assertIn("This is important architecture documentation.", cleaned)
        self.assertIn("```text", cleaned)
        self.assertIn("│ Router │", cleaned)
        self.assertIn("More body details.", cleaned)
        self.assertNotIn("Save to note", cleaned)
        self.assertNotIn("Copy model response to clipboard", cleaned)
        self.assertNotIn("Would you like to", cleaned)
        self.assertNotIn("Suggested Chip", cleaned)

    def test_clean_various_emojis_in_prompts(self):
        from notebooklm_mindmap_extractor.builder import clean_extracted_text
        for emoji in ["💡", "✉️", "⌨️", "🦁", ""]:
            sample = f"Body paragraph.\n\n{emoji} Would you like to explore further?\n"
            cleaned = clean_extracted_text(sample)
            self.assertEqual(cleaned, "Body paragraph.")

    def test_wrap_complex_multitier_architecture_diagram(self):
        from notebooklm_mindmap_extractor.builder import clean_extracted_text, wrap_text_diagrams

        sample_diagram = (
            "Leading explanation paragraph.\n\n"
            "Client Apps (Obsidian / Brave Leo / Claudia / Open WebUI)\n"
            "                     │\n"
            "                     ▼ (Port 8090)\n"
            "          [ Smart Router Gateway ]\n"
            "                     │\n"
            "     ┌───────────────┼───────────────┬───────────────┐\n"
            "     ▼ (Port 8000)   ▼ (Port 8001)   ▼ (Port 8002)   ▼ (Port 8003)\n"
            "Grok Proxy      Claude Proxy    Codex Proxy     Agy Proxy\n"
            "     │               │               │               │\n"
            "     ▼               ▼               ▼               ▼\n"
            " Grok CLI        Claude CLI      Codex CLI       Agy CLI\n\n"
            "Trailing conclusion paragraph.\n"
        )
        cleaned = clean_extracted_text(sample_diagram)
        self.assertIn("Leading explanation paragraph.", cleaned)
        self.assertIn("Trailing conclusion paragraph.", cleaned)
        self.assertIn("```text\nClient Apps (Obsidian / Brave Leo / Claudia / Open WebUI)", cleaned)
        self.assertIn("Grok CLI        Claude CLI      Codex CLI       Agy CLI\n```", cleaned)
        # Verify it was wrapped as a single unified code block, not fragmented
        self.assertEqual(cleaned.count("```text"), 1)
        self.assertEqual(cleaned.count("```"), 2)

    def test_build_handbook_fallback_scan(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "auto-scan-20261027_120000"
            folder.mkdir()
            (folder / "Overview.md").write_text("# Auto Book\n\nAuto book overview.", encoding="utf-8")
            sub = folder / "SubSection"
            sub.mkdir()
            (sub / "Overview.md").write_text("# SubSection\n\nSubSection details.", encoding="utf-8")
            (sub / "Detail.md").write_text("# Detail Item\n\nDetailed content.\n\nSave to note\n", encoding="utf-8")

            # No outline.yml or doc_full_order.yml present
            out_file = build_handbook_from_folder(folder)
            self.assertTrue(out_file.exists())
            self.assertEqual(out_file.name, "auto-scan-full-reference.md")
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("# Auto Book", content)
            self.assertIn("## SubSection", content)
            self.assertIn("### Detail Item", content)
            self.assertNotIn("Save to note", content)

    def test_stitch_stray_punctuation(self):
        from notebooklm_mindmap_extractor.builder import stitch_stray_punctuation

        s1 = "extension to port 8090\n. This provides instant"
        self.assertEqual(stitch_stray_punctuation(s1), "extension to port 8090. This provides instant")

        s2 = "router on port 8090\n\n, users can run"
        self.assertEqual(stitch_stray_punctuation(s2), "router on port 8090, users can run")

        s3 = "endpoint at http://127.0.0.1:8090/v1\n."
        self.assertEqual(stitch_stray_punctuation(s3), "endpoint at http://127.0.0.1:8090/v1.")

        s4 = "strictly on 127.0.0.1:8080\n:"
        self.assertEqual(stitch_stray_punctuation(s4), "strictly on 127.0.0.1:8080:")

    def test_convert_tab_tables(self):
        from notebooklm_mindmap_extractor.builder import convert_tab_tables

        raw = (
            "Intro paragraph.\n\n"
            "Endpoint\n\t\nMethod\n\t\nOperational Purpose\n\n"
            "/api/fleet\n\t\nGET\n\t\nFetches fleet state.\n\n"
            "/api/router\n\t\nGET / POST\n\t\nReads or updates router settings.\n\n"
            "Trailing conclusion.\n"
        )
        converted = convert_tab_tables(raw)
        self.assertIn("| Endpoint | Method | Operational Purpose |", converted)
        self.assertIn("| --- | --- | --- |", converted)
        self.assertIn("| /api/fleet | GET | Fetches fleet state. |", converted)
        self.assertIn("| /api/router | GET / POST | Reads or updates router settings. |", converted)
        self.assertNotIn("\t", converted)


if __name__ == "__main__":
    unittest.main()
