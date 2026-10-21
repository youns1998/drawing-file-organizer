import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import drawing_organizer as app


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input"
        self.source.mkdir()
        self.output = self.root / "output"

    def drawing(self, name, content=b"drawing"):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_normalizes_and_preserves_original(self):
        original = self.drawing("nested/house-ar-a101-r1.DWG", b"original")
        plan = app.analyze(self.source)
        self.assertEqual(plan[0].destination, "HOUSE/AR/A101/HOUSE-AR-A101-R01.dwg")
        self.assertEqual(app.apply_plan(plan, self.output), 1)
        self.assertEqual(original.read_bytes(), b"original")
        self.assertEqual((self.output / plan[0].destination).read_bytes(), b"original")

    def test_latest_revision_is_numeric_and_extension_specific(self):
        self.drawing("HOUSE-AR-A101-R2.pdf", b"old")
        self.drawing("HOUSE-AR-A101-R10.pdf", b"new")
        self.drawing("HOUSE-AR-A101-R1.dwg", b"model")
        plan = app.analyze(self.source, latest_only=True)
        selected = {row.source.name for row in plan if row.selected}
        self.assertEqual(selected, {"HOUSE-AR-A101-R10.pdf", "HOUSE-AR-A101-R1.dwg"})

    def test_case_insensitive_collision_prevents_all_copies(self):
        self.drawing("one/HOUSE-AR-A101-R01.pdf", b"one")
        self.drawing("two/house-ar-a101-r1.PDF", b"two")
        self.drawing("HOUSE-AR-A201-R01.pdf", b"three")
        plan = app.analyze(self.source)
        with self.assertRaises(ValueError):
            app.apply_plan(plan, self.output)
        self.assertFalse(self.output.exists())

    def test_duplicate_contents_are_reported(self):
        self.drawing("HOUSE-AR-A101-R01.pdf")
        self.drawing("HOUSE-AR-A201-R01.pdf")
        self.assertTrue(all("동일 내용 파일 존재" in row.issues for row in app.analyze(self.source)))

    def test_invalid_name_is_reported_and_not_copied(self):
        self.drawing("도면 최종.pdf")
        plan = app.analyze(self.source)
        self.assertFalse(plan[0].selected)
        self.assertIn("파일명 규칙 불일치", plan[0].issues)

    def test_korean_project_name(self):
        self.drawing("만화카페-AR-A101-R01.dxf")
        self.assertEqual(app.analyze(self.source)[0].project, "만화카페")

    def test_source_changed_after_analysis(self):
        original = self.drawing("HOUSE-AR-A101-R01.pdf")
        plan = app.analyze(self.source)
        original.write_bytes(b"changed")
        with self.assertRaises(ValueError):
            app.apply_plan(plan, self.output)

    def test_existing_destination_is_not_overwritten(self):
        self.drawing("HOUSE-AR-A101-R01.pdf")
        plan = app.analyze(self.source)
        target = self.output / plan[0].destination
        target.parent.mkdir(parents=True)
        target.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            app.apply_plan(plan, self.output)
        self.assertEqual(target.read_bytes(), b"keep")

    def test_copy_failure_rolls_back_new_files(self):
        self.drawing("HOUSE-AR-A101-R01.pdf", b"one")
        self.drawing("HOUSE-AR-A201-R01.pdf", b"two")
        plan = app.analyze(self.source)
        original_copy = app.shutil.copyfileobj
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated disk error")
            return original_copy(source, destination)

        with patch.object(app.shutil, "copyfileobj", side_effect=fail_second):
            with self.assertRaises(OSError):
                app.apply_plan(plan, self.output)
        self.assertFalse(list(self.output.rglob("*.pdf")))

    def test_input_and_output_cannot_overlap(self):
        for output in [self.source, self.source / "out", self.root]:
            with self.assertRaises(ValueError):
                app.validate_output(self.source, output)

    def test_dry_run_reports_without_copying(self):
        self.drawing("HOUSE-AR-A101-R01.pdf")
        self.assertEqual(app.main([str(self.source), str(self.output)]), 0)
        self.assertFalse(list(self.output.rglob("*.pdf")))
        self.assertTrue((self.output / "_reports/report.html").is_file())

    def test_report_escapes_html_and_spreadsheet_formulas(self):
        self.drawing("=SUM(1).pdf")
        self.drawing("&note.pdf")
        app.write_reports(app.analyze(self.source), self.output, applied=False)
        report = (self.output / "_reports/report.html").read_text(encoding="utf-8")
        self.assertIn("&amp;note.pdf", report)
        with (self.output / "_reports/manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream))
        self.assertTrue(any(row[0] == "'=SUM(1).pdf" for row in rows))

    def test_apply_command_copies_only_valid_files(self):
        self.drawing("HOUSE-AR-A101-R01.pdf")
        self.drawing("unclassified.pdf")
        self.assertEqual(app.main([str(self.source), str(self.output), "--apply"]), 0)
        self.assertEqual(len(list(self.output.rglob("*.pdf"))), 1)


if __name__ == "__main__":
    unittest.main()
