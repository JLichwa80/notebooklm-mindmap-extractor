"""--clean on a saved real extraction (tests/fixtures/run): no browser, no new extraction needed."""
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from notebooklm_mindmap_extractor.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "run"


class TestCleanSavedRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.run_dir = Path(cls.tmp.name) / "run"
        shutil.copytree(FIXTURE, cls.run_dir)
        cls.code = main(["--clean", str(cls.run_dir / "tmp")])
        cls.files = {p.relative_to(cls.run_dir).as_posix(): p.read_text(encoding="utf-8") for p in cls.run_dir.rglob("*.md")}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_md_tree_mirrors_the_raw_tree(self):
        raws = {p.relative_to(self.run_dir / "tmp").with_suffix(".md").as_posix() for p in (self.run_dir / "tmp").rglob("*.txt")}
        self.assertEqual(self.code, 0)
        self.assertEqual(set(self.files), raws)

    def test_no_citation_leftovers_in_any_file(self):
        for name, text in self.files.items():
            lines = text.splitlines()
            with self.subTest(name):
                self.assertFalse([l for l in lines if re.fullmatch(r"\s*(\d+|[.,;:])\s*", l)])
                self.assertNotRegex(text, r"(?m)^\|.*[A-Za-z)\]]\d+(\.|\s*\|)")
                self.assertNotRegex(text, r"Would you like|📚|💡")
                self.assertNotRegex(text, r"(?m)^#{2,6} ")

    def test_tables_are_intact(self):
        for name in ("Overview.md", "Academic Research & Reference Management/Overview.md"):
            rows = [l for l in self.files[name].splitlines() if l.startswith("|")]
            with self.subTest(name):
                self.assertGreaterEqual(len(rows), 3)
                self.assertEqual({r.count("|") for r in rows}, {rows[0].count("|")})


if __name__ == "__main__":
    unittest.main()
