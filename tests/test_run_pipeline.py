from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from notebooklm_mindmap_extractor import extractor
from notebooklm_mindmap_extractor.builder import build_handbook_from_folder, generate_outline_yaml
from notebooklm_mindmap_extractor.cli import main
from notebooklm_mindmap_extractor.cleaner import clean_extracted_text
from notebooklm_mindmap_extractor.models import MindmapNode

RAW = (Path(__file__).parent / "fixtures" / "run" / "tmp" / "Overview.txt").read_text(encoding="utf-8", newline="")


def make_tree():
    root = MindmapNode("1", "Productivity", 1, 0, 0)
    parent = MindmapNode("2", "Academic Research", 2, 0, 0)
    leaf = MindmapNode("3", "Zotero", 3, 0, 0)
    parent.children = [leaf]
    root.children = [parent]
    return root


class TestExtractThenClean(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        self.root = make_tree()
        with patch.object(extractor, "click_and_capture_response", return_value=RAW):
            extractor.traverse_and_populate(MagicMock(), self.root, 5, None, None, self.run / "tmp")
        (self.run / "doc_full_order.yml").write_text(generate_outline_yaml([self.root]), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_extraction_saves_uncleaned_text_mirroring_the_md_layout(self):
        raws = sorted(p.relative_to(self.run / "tmp").as_posix() for p in (self.run / "tmp").rglob("*") if p.is_file())
        self.assertEqual(raws, ["Academic Research/Overview.txt", "Academic Research/Zotero.txt", "Overview.txt"])
        self.assertEqual((self.run / "tmp" / "Overview.txt").read_text(encoding="utf-8", newline=""), RAW)
        self.assertEqual(list(self.run.glob("**/*.md")), [])

    def test_max_nodes_limits_captured_nodes(self):
        with tempfile.TemporaryDirectory() as other, patch.object(extractor, "click_and_capture_response", return_value=RAW):
            extractor.traverse_and_populate(MagicMock(), make_tree(), 5, [2], None, Path(other) / "tmp")
            self.assertEqual(len([p for p in (Path(other) / "tmp").rglob("*.txt")]), 2)

    def test_clean_step_writes_cleaned_md_tree(self):
        extractor.clean_run(self.root, self.run)
        overview = (self.run / "Overview.md").read_text(encoding="utf-8")
        self.assertTrue(overview.startswith("# Productivity\n\n"))
        self.assertNotIn("Would you like", overview)
        self.assertEqual(overview.split("\n\n", 1)[1].strip(), clean_extracted_text(RAW))
        self.assertTrue((self.run / "Academic Research" / "Overview.md").exists())
        self.assertTrue((self.run / "Academic Research" / "Zotero.md").exists())

    def test_clean_option_works_from_saved_raw_files_only(self):
        self.assertEqual(main(["--clean", str(self.run / "tmp")]), 0)
        self.assertTrue((self.run / "Academic Research" / "Zotero.md").exists())

    def test_build_only_copies_cleaned_files_under_hierarchy_headings(self):
        main(["--clean", str(self.run)])
        zotero = self.run / "Academic Research" / "Zotero.md"
        zotero.write_text(zotero.read_text(encoding="utf-8") + "\nSave to note\n", encoding="utf-8")
        full = build_handbook_from_folder(self.run).read_text(encoding="utf-8")
        self.assertIn("\n## Academic Research\n", full)
        self.assertIn("\n### Zotero\n", full)
        self.assertIn("Save to note", full)  # the builder does not clean


if __name__ == "__main__":
    unittest.main()
